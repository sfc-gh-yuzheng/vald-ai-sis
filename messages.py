"""
Load and parse thread messages from the Cortex Threads API into display format.

Converts the raw Threads API response (newest-first, nested content arrays)
into a chronological list of display-ready dicts with ``role``, ``content``,
and optional ``thinking``, ``tool_calls``, ``sql_queries``, ``charts`` keys.

The ``find_output_boundary`` logic handles Cortex Agent rethinking — when the
agent revises its answer mid-stream, the API stores both draft and final
output.  Only the final output (after the boundary) is shown to the user.
"""

from __future__ import annotations

import json
from typing import Any

from config import PAGE_SIZE_FULL
from helpers import extract_chart_spec, find_output_boundary
from threads_api import api_describe_thread


def load_thread_messages(thread_id: str) -> list[dict[str, Any]] | None:
    """Load messages from the Threads API and convert to display format."""
    try:
        data = api_describe_thread(thread_id, page_size=PAGE_SIZE_FULL)
    except Exception:
        return None

    raw_messages = data.get("messages", [])
    # API returns newest first; reverse to chronological order
    raw_messages = list(reversed(raw_messages))

    display = []
    for m in raw_messages:
        role = m.get("role", "")
        if role not in ("user", "assistant"):
            continue

        payload_str = m.get("message_payload", "")
        if not payload_str:
            continue

        try:
            payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
        except (json.JSONDecodeError, TypeError):
            # Treat as plain text
            if isinstance(payload_str, str) and payload_str.strip():
                display.append({"role": role, "content": payload_str})
            continue

        # Extract the content array — may be at payload["content"] or payload itself
        content_items = []
        if isinstance(payload, dict):
            content_items = payload.get("content", [])
        elif isinstance(payload, list):
            content_items = payload

        if not isinstance(content_items, list):
            content_items = []

        # Parse content items by type.
        # When the agent rethinks mid-response the API stores both the
        # draft and revised output.  Use the boundary to skip drafts.
        text_parts = []
        thinking_parts = []
        tool_calls = []
        sql_queries = []
        charts = []

        boundary = find_output_boundary(content_items)

        for idx, item in enumerate(content_items):
            if not isinstance(item, dict):
                continue
            item_type = item.get("type", "")

            # Text and chart items: only from the final output (after boundary)
            if item_type == "text":
                if idx > boundary:
                    t = item.get("text", "").strip()
                    if t:
                        text_parts.append(t)

            elif item_type == "chart":
                if idx > boundary:
                    spec = extract_chart_spec(item.get("chart", item))
                    if spec and spec not in charts:
                        charts.append(spec)

            elif item_type == "thinking":
                thinking_data = item.get("thinking", {})
                if isinstance(thinking_data, dict):
                    t = thinking_data.get("text", "").strip()
                elif isinstance(thinking_data, str):
                    t = thinking_data.strip()
                else:
                    t = ""
                if t:
                    thinking_parts.append(t)

            elif item_type == "tool_use":
                tool_use = item.get("tool_use", {})
                if isinstance(tool_use, dict) and tool_use.get("name"):
                    tool_calls.append({
                        "name": tool_use.get("name", ""),
                        "input": tool_use.get("input", {}),
                    })

            # Tool results: always process (charts from RadarChart/
            # QuadrantChart appear in the setup phase and are never duplicated)
            elif item_type == "tool_result":
                tool_result = item.get("tool_result", {})
                for c in (tool_result.get("content", []) if isinstance(tool_result, dict) else []):
                    if isinstance(c, dict) and c.get("type") == "json":
                        json_data = c.get("json", {})
                        if isinstance(json_data, dict) and "sql" in json_data:
                            sql_queries.append(json_data["sql"])
                        res = json_data.get("result", "") if isinstance(json_data, dict) else ""
                        if isinstance(res, str) and "$schema" in res:
                            try:
                                parsed = json.loads(res)
                                if parsed not in charts:
                                    charts.append(parsed)
                            except json.JSONDecodeError:
                                pass
                        elif isinstance(res, dict) and "$schema" in res:
                            if res not in charts:
                                charts.append(res)

        # Build display message
        text = "\n\n".join(text_parts)
        if not text and role == "user":
            continue

        msg = {"role": role, "content": text}
        if thinking_parts:
            msg["thinking"] = thinking_parts
        if tool_calls:
            msg["tool_calls"] = tool_calls
        if sql_queries:
            msg["sql_queries"] = sql_queries
        if charts:
            msg["charts"] = charts

        display.append(msg)

    return display
