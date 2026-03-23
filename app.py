"""
VALD Performance Intelligence — Snowflake Intelligence clone with
radar & quadrant chart support.  Deployed on SiS container runtime.

This is the thin entry point.  All logic lives in dedicated modules:

  config.py      — constants, URLs, brand tokens
  auth.py        — SPCS OAuth tokens, RCR session, viewer identity
  threads_api.py — Cortex Threads CRUD
  helpers.py     — pure-Python utilities
  styles.py      — CSS string builder
  charts.py      — Vega-Lite chart rendering (bundled JS, CSP-safe)
  reasoning.py   — collapsible thinking/tool-call box
  streaming.py   — background SSE streaming infrastructure
  messages.py    — thread message loading & parsing
  ui.py          — sidebar, chat area, streaming display fragment
"""

from __future__ import annotations

import streamlit as st

from config import APP_FAVICON, APP_TITLE, PAGE_SIZE_FULL, SNOWFLAKE_HOST
from auth import get_viewer_login, get_viewer_display_name, init_rcr_connection
from helpers import extract_msg_id
from messages import load_thread_messages
from styles import get_app_css
from threads_api import api_describe_thread
from ui import render_sidebar, render_chat


def main() -> None:
    """Entry point — initialise page, session state, and render the UI.

    Session state contract (keys used across modules):
        active_thread_id   (str | None)  – Cortex thread ID for the current conversation
        parent_message_id  (int)         – last assistant message ID (for threading replies)
        messages           (list[dict])  – display-format chat history for the active thread
        _viewer_login      (str | None)  – Snowflake login name of the current viewer
        _user_display_name (str | None)  – human-friendly name resolved via DESCRIBE USER
        _cached_threads    (list[dict])  – thread list cached per render cycle (sidebar → dialog)
        _streaming_states  (dict)        – per-thread background stream state dicts
        _scroll_to_bottom  (bool)        – one-shot flag to auto-scroll after sending a message
    """
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon=APP_FAVICON,
        layout="centered",
        initial_sidebar_state="expanded",
    )

    if not SNOWFLAKE_HOST:
        st.error("This app must be accessed through Snowflake. Please open it from Snowsight.")
        st.stop()

    # Initialise the Restricted Caller's Rights connection IMMEDIATELY.
    # The Sf-Context-Current-User-Token header expires after 2 minutes,
    # so this must happen before any conditional logic or UI rendering.
    init_rcr_connection()

    # Inject full CSS
    st.markdown(get_app_css(), unsafe_allow_html=True)

    # Session state defaults
    if "active_thread_id" not in st.session_state:
        st.session_state.active_thread_id = None
    if "parent_message_id" not in st.session_state:
        st.session_state.parent_message_id = 0
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # --- Viewer identity ---
    # The Sf-Context-Current-User header is injected by SPCS on every request.
    # If it's missing on the very first render after a container restart, rerun
    # once so the sidebar never falls back to the generic origin_application
    # (which would show an empty thread list).
    if not st.session_state.get("_viewer_login"):
        login = get_viewer_login()
        if login:
            st.session_state["_viewer_login"] = login
            st.session_state["_user_display_name"] = get_viewer_display_name(login)
        elif not st.session_state.get("_viewer_login_retry"):
            st.session_state["_viewer_login_retry"] = True
            st.rerun()

    # --- Restore thread from query params on refresh ---
    qp = st.query_params
    if st.session_state.active_thread_id is None and qp.get("thread"):
        restored_id = qp.get("thread")
        try:
            msgs = load_thread_messages(restored_id)
            if msgs is None:
                # Could not reach the API — clear stale query param
                del st.query_params["thread"]
            elif msgs:
                st.session_state.active_thread_id = restored_id
                st.session_state.messages = msgs
                desc = api_describe_thread(restored_id, page_size=PAGE_SIZE_FULL)
                last_asst_id = 0
                for m in desc.get("messages", []):
                    if m.get("role") == "assistant":
                        mid = extract_msg_id(m)
                        if mid:
                            last_asst_id = mid
                            break
                st.session_state.parent_message_id = last_asst_id
        except Exception:
            # Thread no longer exists — clear the stale query param
            del st.query_params["thread"]

    # Sync active thread to query params
    if st.session_state.active_thread_id:
        st.query_params["thread"] = st.session_state.active_thread_id
    elif "thread" in st.query_params:
        del st.query_params["thread"]

    # --- Layout ---
    with st.sidebar:
        render_sidebar()

    render_chat()


if __name__ == "__main__":
    main()
