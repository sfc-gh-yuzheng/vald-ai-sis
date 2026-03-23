"""
UI components — sidebar, chat area, streaming display fragment, thread management.

This is the main presentation layer.  It imports from every other module but
contains no business logic of its own beyond layout and rendering.

Key entry points (called from ``app.py``):

- ``render_sidebar()`` — thread list, new-chat button, search dialog, user card
- ``render_chat()``    — greeting, message history, streaming fragment, chat input
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from config import (
    CHAT_PLACEHOLDER,
    MAX_VISIBLE_THREADS,
    PAGE_SIZE_AUTONAME,
    PAGE_SIZE_FULL,
    THINKING_ICON_SVG,
    VALD_ORANGE,
    VALD_WHITE,
)
from charts import render_vega_chart
from helpers import (
    auto_title,
    categorize_threads,
    extract_msg_id,
    extract_thread_id,
    get_logo_b64,
    html_escape,
    markdown_table_to_html,
)
from messages import load_thread_messages
from reasoning import render_reasoning
from streaming import (
    get_streaming_states,
    has_active_streaming,
    start_background_stream,
)
from threads_api import (
    api_create_thread,
    api_describe_thread,
    api_list_threads,
    api_update_thread_name,
)


# Shared inline style for section headers (Today / Last week / Older)
_SECTION_HDR_STYLE = (
    "color:#b0b3b8;font-family:Roboto,sans-serif;"
    "font-weight:500;letter-spacing:0.06em;text-transform:uppercase;"
)

# How often to refresh the thread list from the API (seconds)
_THREAD_LIST_TTL = 10

# If a streaming response has not updated in this many seconds, treat it as stale
_STREAM_STALE_TIMEOUT = 120


# ---------------------------------------------------------------------------
# Thread row renderer (shared by sidebar and search-chats dialog)
# ---------------------------------------------------------------------------

def _render_thread_row(t: dict[str, Any], active_id: str | None, key_prefix: str = "thread") -> None:
    """Render a single thread row as a button.

    *key_prefix* avoids duplicate widget keys when the same thread appears
    in both the sidebar and the search-chats dialog.
    """
    tid = t.get("thread_id")
    name = t.get("thread_name") or ""

    # Auto-name untitled threads from their first user message.
    # Cache resolved names to avoid re-fetching on every render.
    if not name and tid:
        name_cache = st.session_state.setdefault("_thread_name_cache", {})
        if tid in name_cache:
            name = name_cache[tid]
        else:
            try:
                desc = api_describe_thread(tid, page_size=PAGE_SIZE_AUTONAME)
                for m in reversed(desc.get("messages", [])):
                    if m.get("role") == "user":
                        payload_str = m.get("message_payload", "")
                        payload = json.loads(payload_str) if isinstance(payload_str, str) and payload_str else payload_str
                        if isinstance(payload, dict):
                            for c in payload.get("content", []):
                                if isinstance(c, dict) and c.get("type") == "text" and c.get("text", "").strip():
                                    name = auto_title(c["text"].strip())
                                    break
                        if name:
                            api_update_thread_name(tid, name)
                            break
            except Exception:
                pass
            if not name:
                name = "New Chat"
            name_cache[tid] = name

    is_active = tid == active_id
    if st.button(name, key=f"{key_prefix}_{tid}", use_container_width=True, disabled=is_active):
        st.session_state.active_thread_id = tid
        msgs = load_thread_messages(tid)
        st.session_state.messages = msgs if msgs is not None else []
        # Clean up completed/error streaming state for this thread
        states = get_streaming_states()
        if tid in states and states[tid]["status"] != "streaming":
            del states[tid]
        try:
            desc = api_describe_thread(tid, page_size=PAGE_SIZE_FULL)
            last_asst_id = 0
            for m in desc.get("messages", []):
                if m.get("role") == "assistant":
                    mid = extract_msg_id(m)
                    if mid:
                        last_asst_id = mid
                        break
            st.session_state.parent_message_id = last_asst_id
        except Exception:
            st.session_state.parent_message_id = None
        st.rerun()


# ---------------------------------------------------------------------------
# Search chats dialog
# ---------------------------------------------------------------------------

@st.dialog("Search chats", width="medium")
def _show_search_chats_dialog() -> None:
    """Modal dialog listing all threads with search and Today/Last week/Older sections."""
    search_q = st.text_input(
        "Search", placeholder="Search chats...", key="dlg_search", label_visibility="collapsed",
    )

    # Reuse threads cached by sidebar render; fall back to API if not available
    all_threads = st.session_state.get("_cached_threads")
    fetch_failed = False
    if all_threads is None:
        try:
            all_threads = api_list_threads()
        except Exception:
            all_threads = []
            fetch_failed = True
        all_threads.sort(
            key=lambda t: t.get("updated_on") or t.get("created_on") or 0,
            reverse=True,
        )

    if search_q:
        q = search_q.lower()
        all_threads = [t for t in all_threads if q in (t.get("thread_name") or "").lower()]

    today, last_week, older = categorize_threads(all_threads)
    active_id = st.session_state.active_thread_id

    _dlg_hdr = f'{_SECTION_HDR_STYLE}font-size:0.76rem;margin:0.8rem 0 0.4rem 0.2rem;'

    with st.container(height=500, border=False):
        if today:
            st.markdown(f'<div style="{_dlg_hdr}">Today</div>', unsafe_allow_html=True)
            for t in today:
                _render_thread_row(t, active_id, key_prefix="dlg_thread")

        if last_week:
            st.markdown(f'<div style="{_dlg_hdr}">Last week</div>', unsafe_allow_html=True)
            for t in last_week:
                _render_thread_row(t, active_id, key_prefix="dlg_thread")

        if older:
            st.markdown(f'<div style="{_dlg_hdr}">Older</div>', unsafe_allow_html=True)
            for t in older:
                _render_thread_row(t, active_id, key_prefix="dlg_thread")

        if not today and not last_week and not older:
            if fetch_failed:
                st.caption("Could not load chats. Please try again.")
            else:
                st.caption("No chats found.")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar() -> None:
    """Render the full sidebar with thread list."""
    logo_b64 = get_logo_b64()
    if logo_b64:
        st.markdown(
            f'<div style="padding:0 0 0.6rem 0;text-align:center;">'
            f'<img src="data:image/webp;base64,{logo_b64}" style="height:48px;">'
            f'</div>',
            unsafe_allow_html=True,
        )

    if st.button("New Chat", icon=":material/edit_square:", use_container_width=True, type="primary", disabled=st.session_state.active_thread_id is None):
        st.session_state.active_thread_id = None
        st.session_state.parent_message_id = 0
        st.session_state.messages = []
        if "thread" in st.query_params:
            del st.query_params["thread"]
        st.rerun()

    if st.button("Search Chats", icon=":material/search:", use_container_width=True, type="primary"):
        _show_search_chats_dialog()

    try:
        # Use cached thread list if still fresh to avoid hammering the API
        cache = st.session_state.get("_thread_list_cache")
        if cache and (time.time() - cache["ts"]) < _THREAD_LIST_TTL:
            threads_list = cache["data"]
        else:
            threads_list = api_list_threads()
            threads_list.sort(
                key=lambda t: t.get("updated_on") or t.get("created_on") or 0,
                reverse=True,
            )
            st.session_state._thread_list_cache = {"data": threads_list, "ts": time.time()}
    except Exception:
        st.warning("Could not load your conversations. Please try refreshing.")
        threads_list = []

    # Cache for reuse by the search-chats dialog
    st.session_state._cached_threads = threads_list

    active_id = st.session_state.active_thread_id

    today_threads, lastweek_threads, older_threads = categorize_threads(threads_list)

    _hdr_style = f'{_SECTION_HDR_STYLE}font-size:0.72rem;margin:0.2rem 0 0.4rem 0.2rem;'

    remaining = MAX_VISIBLE_THREADS

    if today_threads:
        st.markdown(f'<div style="{_hdr_style}">Today</div>', unsafe_allow_html=True)
        today_visible = today_threads[:remaining]
        for t in today_visible:
            _render_thread_row(t, active_id)
        remaining -= len(today_visible)

    if lastweek_threads and remaining > 0:
        st.markdown(f'<div style="{_hdr_style}">Last week</div>', unsafe_allow_html=True)
        lw_visible = lastweek_threads[:remaining]
        for t in lw_visible:
            _render_thread_row(t, active_id)
        remaining -= len(lw_visible)

    if older_threads and remaining > 0:
        st.markdown(f'<div style="{_hdr_style}">Older</div>', unsafe_allow_html=True)
        older_visible = older_threads[:remaining]
        for t in older_visible:
            _render_thread_row(t, active_id)
        remaining -= len(older_visible)

    total_threads = len(today_threads) + len(lastweek_threads) + len(older_threads)
    if total_threads > MAX_VISIBLE_THREADS:
        if st.button("Show more", key="show_more_btn", type="tertiary", use_container_width=True):
            _show_search_chats_dialog()

    # --- Profile fixed to bottom of sidebar ---
    user_name = st.session_state.get("_user_display_name")
    if user_name:
        initials = "".join(w[0].upper() for w in user_name.split() if w)[:2]
        safe_name = html_escape(user_name)
        safe_initials = html_escape(initials)
        st.markdown(
            f'<div class="sidebar-profile">'
            f'<div style="width:30px;height:30px;border-radius:50%;background:{VALD_ORANGE};color:{VALD_WHITE};'
            f'display:flex;align-items:center;justify-content:center;font-size:0.7rem;font-weight:600;'
            f'font-family:Roboto,sans-serif;flex-shrink:0;">{safe_initials}</div>'
            f'<span style="color:{VALD_WHITE};font-size:0.88rem;font-family:Roboto,sans-serif;'
            f'font-weight:400;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{safe_name}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Chat area
# ---------------------------------------------------------------------------

def render_chat() -> None:
    """Chat area — history + input + streaming display fragment."""
    is_streaming = has_active_streaming()

    prompt = st.chat_input(CHAT_PLACEHOLDER)

    # --- Hero greeting (shown only on empty/new chat) ---
    if not st.session_state.messages and not prompt and not is_streaming:
        # Server-time greeting as immediate fallback; JS corrects to viewer
        # local time within milliseconds (see components.html snippet below).
        hour = datetime.now().hour
        if hour < 12:
            greeting = "Good morning"
        elif hour < 18:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"
        display_name = st.session_state.get("_user_display_name") or ""
        if display_name.isupper():
            display_name = display_name.title()
        first_name = display_name.split()[0] if display_name else ""
        safe_first = html_escape(first_name) if first_name else ""
        name_suffix = f", {safe_first}." if safe_first else ""
        st.markdown(
            f'<div class="vald-hero">'
            f'<h1><span id="vald-greeting">{greeting}</span>{name_suffix}</h1>'
            f"<p>What insights are you looking for?</p>"
            f"</div>",
            unsafe_allow_html=True,
        )
        # Correct greeting using the viewer's local machine time.
        # new Date().getHours() runs in the browser and returns the hour
        # from the viewer's system clock — not the SPCS container.
        components.html(
            """<script>
            (function() {
                var h = new Date().getHours();
                var g = h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
                var el = window.parent.document.getElementById("vald-greeting");
                if (el) el.textContent = g;
            })();
            </script>""",
            height=0,
        )

    # --- Scroll guard ---------------------------------------------------
    # Streamlit's built-in useScrollToBottom React hook polls every 17 ms
    # and re-requests scroll-to-bottom 34 ms after any user scroll-away.
    # This fights user attempts to scroll up in long threads.  We cannot
    # patch Streamlit's React code, so we intercept programmatic scrollTop
    # assignments on section.main and block downward ones while the user
    # has intentionally scrolled up.  The guard auto-clears when the user
    # reaches the bottom or when our own _scroll_to_bottom fires.
    components.html(
        """<script>
        (function() {
            var main = window.parent.document.querySelector('[data-testid="stAppScrollToBottomContainer"]')
                    || window.parent.document.querySelector('section.stMain')
                    || window.parent.document.querySelector('section.main');
            if (!main) return;
            if (!main.__vald_scroll_guard) {
                main.__vald_scroll_guard = true;
                var desc = Object.getOwnPropertyDescriptor(
                    Element.prototype, 'scrollTop');
                if (!desc || !desc.set) return;
                Object.defineProperty(main, 'scrollTop', {
                    get: function() { return desc.get.call(this); },
                    set: function(val) {
                        if (this.__vald_allow_scroll) {
                            this.__vald_allow_scroll = false;
                            this.__vald_user_scrolled_up = false;
                            return desc.set.call(this, val);
                        }
                        if (this.__vald_user_scrolled_up
                            && val > desc.get.call(this) + 5) {
                            return;
                        }
                        desc.set.call(this, val);
                    },
                    configurable: true, enumerable: true
                });
                main.addEventListener('wheel', function(e) {
                    if (e.deltaY < 0) main.__vald_user_scrolled_up = true;
                    var cur = desc.get.call(main);
                    if (e.deltaY > 0
                        && main.scrollHeight - cur - main.offsetHeight < 50) {
                        main.__vald_user_scrolled_up = false;
                    }
                }, { passive: true });
                var lastTouchY = 0;
                main.addEventListener('touchstart', function(e) {
                    if (e.touches.length) lastTouchY = e.touches[0].clientY;
                }, { passive: true });
                main.addEventListener('touchmove', function(e) {
                    if (!e.touches.length) return;
                    var y = e.touches[0].clientY;
                    if (y > lastTouchY + 3) main.__vald_user_scrolled_up = true;
                    lastTouchY = y;
                    var cur = desc.get.call(main);
                    if (main.scrollHeight - cur - main.offsetHeight < 50) {
                        main.__vald_user_scrolled_up = false;
                    }
                }, { passive: true });
            }
            var proto_d = Object.getOwnPropertyDescriptor(
                Element.prototype, 'scrollTop');
            if (proto_d) {
                var c = proto_d.get.call(main);
                if (main.scrollHeight - c - main.offsetHeight < 5) {
                    main.__vald_user_scrolled_up = false;
                }
            }
        })();
        </script>""",
        height=0,
    )

    # --- Chat history ---
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                render_reasoning(msg)
            st.markdown(msg["content"])
            for chart in msg.get("charts", []):
                render_vega_chart(chart)

    # --- Auto-scroll to bottom after submitting a message ---
    if st.session_state.pop("_scroll_to_bottom", False):
        components.html(
            "<script>"
            "var m = window.parent.document.querySelector('[data-testid=\"stAppScrollToBottomContainer\"]')"
            "  || window.parent.document.querySelector('section.stMain')"
            "  || window.parent.document.querySelector('section.main');"
            "if (m) { m.__vald_allow_scroll = true; m.scrollTop = 999999; }"
            "</script>",
            height=0,
        )

    # ------------------------------------------------------------------
    # Streaming display fragment
    # ------------------------------------------------------------------
    @st.fragment(run_every=0.1 if is_streaming else None)
    def _streaming_display():
        tid = st.session_state.get("active_thread_id")
        if not tid:
            return
        states = get_streaming_states()
        state = states.get(tid)
        if state is None:
            return

        status = state["status"]

        # Detect stale streams (background thread may have hung)
        if status == "streaming" and (time.time() - state["last_update"]) > _STREAM_STALE_TIMEOUT:
            state["error"] = "The response timed out. Please try again."
            state["status"] = "error"
            status = "error"

        if status == "streaming":
            with st.chat_message("assistant"):
                # --- Live thinking box ---
                thinking_text = state["thinking"]
                if state["thinking_shown"] and thinking_text:
                    thinking_html = markdown_table_to_html(thinking_text)
                    st.markdown(
                        f'<details class="reasoning-box" open>'
                        f'<summary class="reasoning-header">'
                        f'{THINKING_ICON_SVG}'
                        f'<span class="label">Thinking...</span>'
                        f'</summary>'
                        f'<div class="reasoning-content">'
                        f'{thinking_html}'
                        f'</div>'
                        f'</details>',
                        unsafe_allow_html=True,
                    )
                else:
                    # Initial "Thinking..." skeleton before any text arrives
                    st.markdown(
                        f'<details class="reasoning-box" open>'
                        f'<summary class="reasoning-header">'
                        f'{THINKING_ICON_SVG}'
                        f'<span class="label">Thinking...</span>'
                        f'</summary>'
                        f'</details>',
                        unsafe_allow_html=True,
                    )

                # --- Live response text ---
                if state["text"]:
                    st.markdown(state["text"])

        elif status == "completed":
            # Build thinking list matching historical message format
            thinking_list = [state["thinking"]] if state["thinking"] else []

            # Append finalized assistant message to history
            st.session_state.messages.append({
                "role": "assistant",
                "content": state["text"],
                "charts": list(state["charts"]),
                "thinking": thinking_list,
                "tool_calls": list(state["tool_calls"]),
                "sql_queries": list(state["sql_queries"]),
            })

            # Update parent_message_id for the next message in this thread
            if state["assistant_message_id"] is not None:
                st.session_state.parent_message_id = state["assistant_message_id"]

            # Auto-name thread from first question
            if len(st.session_state.messages) == 2:
                try:
                    user_prompt = st.session_state.messages[0]["content"]
                    api_update_thread_name(tid, auto_title(user_prompt))
                except Exception:
                    pass

            # Clean up and trigger full rerun so history loop renders cleanly
            del states[tid]
            st.rerun()

        elif status == "error":
            if state.get("error_type") == "ThreadNotFoundError":
                # Thread was deleted or expired — create a fresh thread and retry
                try:
                    thread_resp = api_create_thread()
                    new_id = extract_thread_id(thread_resp)
                    st.session_state.active_thread_id = new_id
                    st.session_state.parent_message_id = 0
                    user_msgs = [m for m in st.session_state.messages if m["role"] == "user"]
                    del states[tid]
                    if user_msgs:
                        start_background_stream(user_msgs[-1]["content"], new_id, 0)
                    st.rerun()
                except Exception:
                    del states[tid]
                    with st.chat_message("assistant"):
                        st.error("Your conversation has expired. Please start a new chat.")
            else:
                del states[tid]
                with st.chat_message("assistant"):
                    st.error("Something went wrong. Please try again.")

    _streaming_display()

    # --- Handle new prompt submission (ignored while a stream is active) ---
    if prompt and not is_streaming:
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Auto-create thread on first message
        if st.session_state.active_thread_id is None:
            try:
                thread_resp = api_create_thread()
                new_thread_id = extract_thread_id(thread_resp)
                st.session_state.active_thread_id = new_thread_id
                st.session_state.parent_message_id = 0
                # Invalidate thread list cache so the sidebar picks up the new thread
                st.session_state.pop("_thread_list_cache", None)
            except Exception:
                st.error("Could not start a new conversation. Please try again.")
                st.stop()

        start_background_stream(
            prompt=prompt,
            thread_id=st.session_state.active_thread_id,
            parent_message_id=st.session_state.parent_message_id,
        )
        st.session_state._scroll_to_bottom = True
        st.rerun()
