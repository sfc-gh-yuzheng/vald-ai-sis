"""
Reasoning box renderer — collapsible thinking/tool-call/SQL display.

Produces a ``<details>/<summary>`` HTML block that shows the agent's
internal reasoning (thinking text, tool calls, SQL queries) in a
collapsible panel styled by ``styles.py``.

All dynamic content is HTML-escaped before insertion to prevent XSS.
"""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from config import THINKING_ICON_SVG
from helpers import html_escape, markdown_table_to_html


def _reasoning_html(
    thinking: str | list[str] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    sql_queries: list[str] | None = None,
) -> str:
    """Build the reasoning box as raw HTML with a details/summary toggle."""
    parts = []
    if thinking:
        for t in (thinking if isinstance(thinking, list) else [thinking]):
            parts.append(markdown_table_to_html(t))
    if tool_calls:
        for tc in tool_calls:
            name = html_escape(tc.get("name", ""))
            inp = json.dumps(tc.get("input", {}), indent=2)
            escaped_inp = html_escape(inp)
            parts.append(f"<pre>{name}({escaped_inp})</pre>")
    if sql_queries:
        for sql in sql_queries:
            escaped_sql = html_escape(sql)
            parts.append(f"<pre><code>{escaped_sql}</code></pre>")

    if not parts:
        return ""

    icon_html = THINKING_ICON_SVG
    label = "Thinking completed"

    content_html = "".join(parts)

    return (
        f'<details class="reasoning-box">'
        f'<summary class="reasoning-header">'
        f'{icon_html}'
        f'<span class="label">{label}</span>'
        f'</summary>'
        f'<div class="reasoning-content">'
        f'{content_html}'
        f'</div>'
        f'</details>'
    )


def render_reasoning(msg: dict[str, Any]) -> None:
    """Render reasoning box for completed messages."""
    has_reasoning = msg.get("thinking") or msg.get("tool_calls") or msg.get("sql_queries")
    if not has_reasoning:
        return
    html = _reasoning_html(
        thinking=msg.get("thinking"),
        tool_calls=msg.get("tool_calls"),
        sql_queries=msg.get("sql_queries"),
    )
    if html:
        st.markdown(html, unsafe_allow_html=True)
