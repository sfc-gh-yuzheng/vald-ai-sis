"""
Background SSE streaming infrastructure for Cortex Agent responses.

Architecture
------------
The agent:run endpoint returns a Server-Sent Events (SSE) stream.  Streamlit
reruns the script on every interaction, so we cannot consume the stream on the
main thread.  Instead:

1. ``start_background_stream()`` captures the RCR auth headers on the main
   thread, creates a shared ``state`` dict, and spawns a daemon thread.
2. ``_background_stream_worker()`` runs in the daemon thread.  It opens the
   SSE connection and writes deltas (text, thinking, charts, tool_calls,
   sql_queries) into ``state``.  **It must NEVER call any** ``st.*`` **API.**
3. A ``@st.fragment`` in ``ui.py`` polls ``state`` every ~0.3 s and renders
   incremental updates.

Thread-safety is guaranteed by the GIL: the daemon is the sole writer and
the fragment is the sole reader — both operate on plain Python dicts.

SSE event types handled
-----------------------
- ``metadata`` — captures user/assistant message IDs
- ``response.thinking`` / ``message.delta[thinking]`` — reasoning text
- ``response.text`` / ``message.delta[text]`` — answer text deltas
- ``response.chart`` / ``message.delta[chart]`` — Vega-Lite chart specs
- ``tool_use`` — tool call names + inputs
- ``response`` (final) — complete message with content array; used as
  fallback when delta events were incomplete
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import requests
import streamlit as st

from config import (
    AGENT_RUN_URL,
    AGENT_STREAM_TIMEOUT,
    API_TIMEOUT,
    PAGE_SIZE_FALLBACK,
    PAGE_SIZE_RECOVERY,
    THREADS_BASE,
)
from auth import build_auth_headers_snapshot
from helpers import extract_msg_id, extract_chart_spec, find_output_boundary
from threads_api import api_describe_thread


# ---------------------------------------------------------------------------
# Streaming state infrastructure
# ---------------------------------------------------------------------------

def get_streaming_states() -> dict[str, dict[str, Any]]:
    """Return the dict of per-thread streaming states, creating it if needed."""
    if "_streaming_states" not in st.session_state:
        st.session_state._streaming_states = {}
    return st.session_state._streaming_states


def has_active_streaming() -> bool:
    """True if the current active thread has an in-progress background stream."""
    tid = st.session_state.get("active_thread_id")
    if not tid:
        return False
    states = get_streaming_states()
    s = states.get(tid)
    return s is not None and s["status"] == "streaming"


def _make_streaming_state() -> dict[str, Any]:
    """Create a fresh streaming state dict for a new background stream."""
    return {
        "status": "streaming",
        "thinking": "",
        "text": "",
        "charts": [],
        "tool_calls": [],
        "sql_queries": [],
        "thinking_shown": False,
        "user_message_id": None,
        "assistant_message_id": None,
        "error": None,
        "error_type": None,       # "ThreadNotFoundError" or None
        "last_update": time.time(),
    }


# ---------------------------------------------------------------------------
# Background stream worker (runs in a daemon thread — NO Streamlit API calls)
# ---------------------------------------------------------------------------

def _background_stream_worker(
    state: dict[str, Any],
    payload: dict[str, Any],
    headers: dict[str, str],
) -> None:
    """Consume SSE stream in a background thread, writing results to *state* dict.

    This function must NEVER call any st.* API.  It only writes to the plain
    Python dict *state*, which the polling fragment reads from the main thread.
    Thread-safety: single-writer (this thread) / single-reader (fragment) under GIL.
    """
    current_thinking = ""
    current_text = ""
    thinking_shown = False

    try:
        with requests.post(
            AGENT_RUN_URL,
            headers=headers,
            json=payload,
            timeout=AGENT_STREAM_TIMEOUT,
            stream=True,
        ) as response:
            if response.status_code != 200:
                if response.status_code == 404 or "does not exist" in response.text[:500]:
                    state["error"] = "This conversation no longer exists."
                    state["error_type"] = "ThreadNotFoundError"
                elif response.status_code == 401:
                    state["error"] = "Session expired. Please refresh the page."
                elif response.status_code == 429:
                    state["error"] = "Too many requests. Please wait a moment and try again."
                else:
                    state["error"] = "Something went wrong. Please try again."
                state["status"] = "error"
                return

            response.encoding = "utf-8"
            current_event = None

            # SSE protocol: lines are "event: <type>\n" followed by
            # "data: <json>\n".  A blank line terminates the event.
            for raw_line in response.iter_lines():
                if isinstance(raw_line, bytes):
                    line = raw_line.decode("utf-8", errors="replace")
                else:
                    line = raw_line
                if not line:
                    current_event = None
                    continue

                if line.startswith("event:"):
                    current_event = line.split("event:", 1)[1].strip()
                    continue

                if not line.startswith("data:"):
                    continue

                raw_data = line[5:].strip()
                if not raw_data:
                    continue

                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    continue

                state["last_update"] = time.time()

                # --- metadata events: capture message IDs ---
                if current_event == "metadata":
                    role = data.get("role")
                    mid = extract_msg_id(data)
                    if role == "user" and mid is not None:
                        state["user_message_id"] = mid
                    elif role == "assistant" and mid is not None:
                        state["assistant_message_id"] = mid
                    continue

                # --- response.chart events ---
                if current_event == "response.chart":
                    spec = extract_chart_spec(data)
                    if spec and spec not in state["charts"]:
                        state["charts"].append(spec)
                    continue

                event_type = data.get("type", "")

                # --- Thinking events (delta + aggregated) ---
                if (current_event and current_event.startswith("response.thinking")) or event_type == "thinking" or "thinking" in data:
                    thinking_data = data.get("thinking", data)
                    if isinstance(thinking_data, dict):
                        text = thinking_data.get("text", "")
                    else:
                        text = str(thinking_data)
                    if text:
                        if current_event == "response.thinking" and current_thinking:
                            thinking_shown = True
                        else:
                            current_thinking += text
                            thinking_shown = True
                            state["thinking"] = current_thinking
                            state["thinking_shown"] = True

                # --- Text events (delta + aggregated) ---
                elif (current_event and current_event.startswith("response.text")) or (event_type == "text" and "thinking" not in data):
                    delta_text = data.get("text", "")
                    if delta_text:
                        if current_event == "response.text" and current_text:
                            pass
                        else:
                            current_text += delta_text
                            state["text"] = current_text

                # --- Tool use ---
                elif event_type == "tool_use" or "tool_use" in data:
                    tool_use = data.get("tool_use", data)
                    if isinstance(tool_use, dict) and "name" in tool_use:
                        tool_info = {
                            "name": tool_use.get("name", ""),
                            "input": tool_use.get("input", {}),
                        }
                        state["tool_calls"].append(tool_info)
                        if not thinking_shown:
                            thinking_shown = True
                            state["thinking_shown"] = True

                # --- message.delta ---
                elif current_event == "message.delta":
                    delta = data.get("delta", {})
                    for c in delta.get("content", []):
                        if c.get("type") == "thinking":
                            thinking_data = c.get("thinking", c)
                            if isinstance(thinking_data, dict):
                                t = thinking_data.get("text", "")
                            elif isinstance(thinking_data, str):
                                t = thinking_data
                            else:
                                t = str(thinking_data)
                            if t:
                                current_thinking += t
                                thinking_shown = True
                                state["thinking"] = current_thinking
                                state["thinking_shown"] = True
                        elif c.get("type") == "text" and isinstance(c.get("text"), str):
                            current_text += c["text"]
                            state["text"] = current_text
                        elif c.get("type") == "chart":
                            spec = extract_chart_spec(c.get("chart", c))
                            if spec and spec not in state["charts"]:
                                state["charts"].append(spec)

                # --- Final response ---
                # The stored content may contain draft output that the agent
                # superseded after rethinking.  Use the boundary to skip drafts.
                # Delta-accumulated text is authoritative; final response text
                # is only used as a fallback when no deltas arrived.
                if current_event == "response" and "role" in data and "content" in data:
                    if data.get("role") == "assistant":
                        final_mid = extract_msg_id(data)
                        if final_mid and state["assistant_message_id"] is None:
                            state["assistant_message_id"] = final_mid
                    final_content = data["content"]
                    boundary = find_output_boundary(final_content)
                    final_text_parts = []
                    for idx, item in enumerate(final_content):
                        item_type = item.get("type", "")
                        # Text/chart: only from final output (after boundary)
                        if item_type == "text" and idx > boundary:
                            t = item.get("text", "").strip()
                            if t:
                                final_text_parts.append(t)
                        elif item_type == "chart" and idx > boundary:
                            spec = extract_chart_spec(item.get("chart", item))
                            if spec and spec not in state["charts"]:
                                state["charts"].append(spec)
                        elif item_type == "thinking":
                            td = item.get("thinking", {})
                            t = td.get("text", "").strip()
                            if t:
                                state["thinking"] = t
                        elif item_type == "tool_use":
                            tu = item.get("tool_use", {})
                            ti = {"name": tu.get("name", ""), "input": tu.get("input", {})}
                            if ti not in state["tool_calls"]:
                                state["tool_calls"].append(ti)
                        # Tool results: always process (no boundary filter)
                        elif item_type == "tool_result":
                            tool_result = item.get("tool_result", {})
                            for content in tool_result.get("content", []):
                                if content.get("type") == "json":
                                    json_data = content.get("json", {})
                                    if "sql" in json_data:
                                        state["sql_queries"].append(json_data["sql"])
                                    res = json_data.get("result", "")
                                    if isinstance(res, str) and "$schema" in res:
                                        try:
                                            parsed = json.loads(res)
                                            if parsed not in state["charts"]:
                                                state["charts"].append(parsed)
                                        except json.JSONDecodeError:
                                            pass
                    # Use final response text only as fallback
                    if final_text_parts and not state["text"]:
                        state["text"] = "\n\n".join(final_text_parts)

        # --- Finalize accumulated text ---
        if not state["text"] and current_text:
            state["text"] = current_text
        # Only use delta-accumulated thinking as fallback — the final response
        # event may have set a cleaner version from the stored content.
        if not state["thinking"] and current_thinking and current_thinking.strip():
            state["thinking"] = current_thinking.strip()

        # Fallback: query thread for assistant_message_id if SSE didn't provide it
        if state["assistant_message_id"] is None and payload.get("thread_id"):
            try:
                tid = payload["thread_id"]
                fallback_resp = requests.get(
                    f"{THREADS_BASE}/{tid}?page_size={PAGE_SIZE_FALLBACK}",
                    headers={k: v for k, v in headers.items()
                             if k != "Content-Type"},
                    timeout=API_TIMEOUT,
                )
                fallback_resp.raise_for_status()
                desc = fallback_resp.json()
                for m in desc.get("messages", []):
                    if m.get("role") == "assistant":
                        mid = extract_msg_id(m)
                        if mid:
                            state["assistant_message_id"] = mid
                            break
            except Exception:
                pass

        state["status"] = "completed"

    except Exception:
        state["error"] = "Something went wrong. Please try again."
        state["status"] = "error"


# ---------------------------------------------------------------------------
# Thread launcher — called from the main Streamlit thread
# ---------------------------------------------------------------------------

def start_background_stream(
    prompt: str,
    thread_id: str,
    parent_message_id: int | str | None,
) -> None:
    """Build payload, create streaming state, and spawn a daemon thread.

    Must be called from the main Streamlit thread so that the viewer's
    RCR token can be captured.  The background thread receives a snapshot
    of the headers dict — no further st.* calls needed.
    """
    # --- Resolve parent_message_id when genuinely unknown (None) ---
    if parent_message_id is None and thread_id:
        try:
            desc = api_describe_thread(thread_id, page_size=PAGE_SIZE_RECOVERY)
            msgs = desc.get("messages", [])
            for m in msgs:
                mid = extract_msg_id(m)
                if mid:
                    parent_message_id = mid
                    break
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                # Thread gone — store error state, don't spawn thread
                states = get_streaming_states()
                state = _make_streaming_state()
                state["error"] = "This conversation no longer exists."
                state["error_type"] = "ThreadNotFoundError"
                state["status"] = "error"
                states[thread_id] = state
                return
        except Exception:
            pass

    # --- Build API payload ---
    payload = {
        "thread_id": thread_id,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            }
        ],
        "stream": True,
    }
    if thread_id:
        # parent_message_id=0 tells the API "append to the thread" when
        # the actual ID is unknown (e.g. after thread recovery).
        payload["parent_message_id"] = parent_message_id if parent_message_id is not None else 0

    # --- Capture auth headers while still on the main thread ---
    try:
        headers = build_auth_headers_snapshot()
    except Exception:
        state = _make_streaming_state()
        state["error"] = "Session unavailable — please refresh the page."
        state["status"] = "error"
        states = get_streaming_states()
        states[thread_id] = state
        return

    # --- Create streaming state and register it ---
    state = _make_streaming_state()
    states = get_streaming_states()
    states[thread_id] = state

    # --- Spawn daemon thread ---
    t = threading.Thread(
        target=_background_stream_worker,
        args=(state, payload, headers),
        daemon=True,
    )
    t.start()
