"""
Pure-Python utility functions shared across modules.

Everything in this file is free of side-effects and does not call any
Streamlit API beyond ``@st.cache_data`` (for the logo helper).  This
makes the functions easy to unit-test.

Key helpers:

- ``html_escape`` — safe HTML escaping for ``unsafe_allow_html`` output
- ``markdown_table_to_html`` — pipe-table → styled ``<table>`` conversion
- ``auto_title`` — truncate a user prompt to a short thread name
- ``categorize_threads`` — bucket a thread list into Today / Last week / Older
- ``extract_msg_id`` / ``extract_thread_id`` — resilient ID extraction
- ``find_output_boundary`` — skip draft output when agent rethinks mid-response
- ``extract_chart_spec`` — unwrap a Vega-Lite spec from the API envelope
"""

from __future__ import annotations

import base64
import html as _html
import json
import re
from datetime import datetime, timedelta
from typing import Any

import streamlit as st

from config import LOGO_PATH


def html_escape(text: str) -> str:
    """Escape text for safe embedding in HTML (ampersands, brackets, quotes)."""
    return _html.escape(text, quote=True)


# ---------------------------------------------------------------------------
# Markdown pipe-table → HTML converter (for reasoning box / unsafe_allow_html)
# ---------------------------------------------------------------------------

_SEP_CELL_RE = re.compile(r"^:?-+:?$")


def _is_pipe_row(line: str) -> bool:
    """Return True if *line* looks like a markdown pipe-table row."""
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and s.count("|") >= 3


def _is_separator_row(line: str) -> bool:
    """Return True if *line* is a pipe-table separator (e.g. ``| --- | --- |``)."""
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")):
        return False
    cells = [c.strip() for c in s.strip("|").split("|")]
    return all(_SEP_CELL_RE.match(c) for c in cells if c)


def _parse_row_cells(line: str) -> list[str]:
    """Split a pipe-table row into a list of stripped cell strings."""
    return [c.strip() for c in line.strip().strip("|").split("|")]


def markdown_table_to_html(text: str) -> str:
    """Convert markdown pipe tables in *text* to styled HTML tables.

    Non-table text is HTML-escaped and wrapped in ``<p>`` tags.
    Tables become ``<div class="vald-table-wrap"><table>…</table></div>``.
    Incomplete tables (e.g. mid-stream) fall back to escaped text.
    """
    if not text or not text.strip():
        return ""

    lines = text.split("\n")
    parts: list[str] = []
    buf: list[str] = []
    i = 0

    def _flush():
        joined = "\n".join(buf)
        if joined.strip():
            parts.append(
                f'<p style="margin:0.3rem 0;white-space:pre-wrap;">'
                f"{html_escape(joined)}</p>"
            )
        buf.clear()

    while i < len(lines):
        # Detect table: header row followed immediately by separator row
        if (
            i + 1 < len(lines)
            and _is_pipe_row(lines[i])
            and _is_separator_row(lines[i + 1])
        ):
            _flush()
            headers = _parse_row_cells(lines[i])
            i += 2  # skip header + separator

            rows: list[list[str]] = []
            while i < len(lines) and _is_pipe_row(lines[i]):
                rows.append(_parse_row_cells(lines[i]))
                i += 1

            h = '<div class="vald-table-wrap"><table><thead><tr>'
            for cell in headers:
                h += f"<th>{html_escape(cell)}</th>"
            h += "</tr></thead><tbody>"
            for row in rows:
                h += "<tr>"
                for cell in row:
                    h += f"<td>{html_escape(cell)}</td>"
                for _ in range(len(headers) - len(row)):
                    h += "<td></td>"
                h += "</tr>"
            h += "</tbody></table></div>"
            parts.append(h)
        else:
            buf.append(lines[i])
            i += 1

    _flush()
    return "\n".join(parts)


@st.cache_data
def get_logo_b64() -> str | None:
    """Return the VALD logo as a base64-encoded string, or ``None`` if missing."""
    if LOGO_PATH.exists():
        return base64.b64encode(LOGO_PATH.read_bytes()).decode()
    return None


def auto_title(text: str, max_chars: int = 50) -> str:
    """Generate a concise thread title from user message text."""
    text = text.strip().replace("\n", " ")
    for sep in (".", "?", "!"):
        idx = text.find(sep)
        if 0 < idx <= max_chars:
            return text[: idx + 1]
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > max_chars // 2:
        truncated = truncated[:last_space]
    return truncated + "..."


def categorize_threads(
    threads: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a sorted thread list into (today, last_week, older) buckets."""
    now = datetime.now()
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago_midnight = today_midnight - timedelta(days=7)
    today_ms = int(today_midnight.timestamp() * 1000)
    week_ago_ms = int(week_ago_midnight.timestamp() * 1000)

    today, last_week, older = [], [], []
    for t in threads:
        ts = t.get("updated_on") or t.get("created_on") or 0
        if ts >= today_ms:
            today.append(t)
        elif ts >= week_ago_ms:
            last_week.append(t)
        else:
            older.append(t)
    return today, last_week, older


def extract_msg_id(msg: dict[str, Any] | Any) -> Any:
    """Extract message ID from a Threads API message dict."""
    if not isinstance(msg, dict):
        return None
    for key in ("message_id", "id", "msg_id", "uuid", "message_uuid"):
        val = msg.get(key)
        if val:
            return val
    meta = msg.get("metadata")
    if isinstance(meta, dict):
        for key in ("message_id", "id"):
            val = meta.get(key)
            if val:
                return val
    return None


def extract_thread_id(resp: dict[str, Any] | Any) -> str | None:
    """Extract thread ID from a Threads API create/describe response dict."""
    if not isinstance(resp, dict):
        return None
    for key in ("thread_id", "id", "thread_uuid"):
        val = resp.get(key)
        if val:
            return val
    return None


def find_output_boundary(content_items: list[dict[str, Any]]) -> int:
    """Find the last THINKING item that precedes text/chart output.

    When the Cortex Agent rethinks mid-response, it replays its output.
    The API stores both the draft and revised content.  This function
    finds the boundary so callers can skip the superseded draft.

    Returns the index of the boundary THINKING item, or ``-1`` if there
    is no rethinking boundary.  Content items with ``index > boundary``
    are the agent's final output.
    """
    for i in reversed(range(len(content_items))):
        item = content_items[i]
        if isinstance(item, dict) and item.get("type") == "thinking":
            if any(
                isinstance(content_items[j], dict)
                and content_items[j].get("type") in ("text", "chart")
                for j in range(i + 1, len(content_items))
            ):
                return i
    return -1


def extract_chart_spec(chart_data: dict[str, Any]) -> dict[str, Any] | None:
    """Extract a parsed Vega-Lite spec dict from a chart data envelope."""
    spec_str = chart_data.get("chart_spec") or (
        chart_data.get("chart") or {}
    ).get("chart_spec")
    if not spec_str:
        return None
    try:
        return json.loads(spec_str) if isinstance(spec_str, str) else spec_str
    except json.JSONDecodeError:
        return None
