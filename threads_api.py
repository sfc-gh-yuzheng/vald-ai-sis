"""
Snowflake Cortex Threads API CRUD helpers.

Thin wrappers around the ``/api/v2/cortex/threads`` REST endpoints.
All functions authenticate via the viewer's RCR token (``get_auth_headers``)
so that thread operations are scoped to the logged-in user.

Functions raise ``requests.HTTPError`` on non-2xx responses; callers in
``ui.py``, ``app.py``, ``streaming.py``, and ``messages.py`` wrap every
call in ``try/except``.
"""

from __future__ import annotations

from typing import Any

import requests

from config import API_TIMEOUT, THREADS_BASE
from auth import get_auth_headers, get_viewer_origin_app


def api_create_thread() -> dict[str, Any]:
    """Create a new Cortex thread for the current viewer."""
    resp = requests.post(
        THREADS_BASE,
        headers=get_auth_headers(),
        json={"origin_application": get_viewer_origin_app()},
        timeout=API_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def api_list_threads() -> list[dict[str, Any]]:
    """List all threads for the current viewer's origin_application."""
    origin = get_viewer_origin_app()
    resp = requests.get(
        f"{THREADS_BASE}?origin_application={origin}",
        headers=get_auth_headers(content_type=False),
        timeout=API_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        return data.get("threads", [])
    return data if isinstance(data, list) else []


def api_describe_thread(thread_id: str, page_size: int = 50) -> dict[str, Any]:
    """Retrieve thread metadata and messages."""
    resp = requests.get(
        f"{THREADS_BASE}/{thread_id}?page_size={page_size}",
        headers=get_auth_headers(content_type=False),
        timeout=API_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def api_update_thread_name(thread_id: str, name: str) -> None:
    """Rename an existing thread."""
    resp = requests.post(
        f"{THREADS_BASE}/{thread_id}",
        headers=get_auth_headers(),
        json={"thread_name": name},
        timeout=API_TIMEOUT,
    )
    resp.raise_for_status()
