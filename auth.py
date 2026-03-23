"""
Authentication, token management, and viewer identity helpers.

Token architecture
------------------
Two token types coexist in this app:

- **Owner token** (``/snowflake/session/token``): refreshed by SPCS every
  few minutes, valid up to 1 hour.  Used **only** for owner-privileged
  operations like ``DESCRIBE USER`` (via ``get_owner_headers()``).

- **Restricted Caller's Rights (RCR) token**: obtained via
  ``st.connection("snowflake-callers-rights")``, which creates a session-scoped
  Snowpark connection using the viewer's identity.  A session token is then
  extracted for REST API calls (Threads, agent:run) so that each viewer's
  requests execute as *that* viewer.

  The RCR connection must be initialised at the top of the app script, within
  the 2-minute lifespan of the ``Sf-Context-Current-User-Token`` header.
  Once established, the connection stays alive via ``client_session_keep_alive``.

  **RCR is required in production.**  If the connection cannot be established
  the app halts (``st.stop()``).  If a token cannot be extracted later,
  ``get_auth_headers()`` / ``build_auth_headers_snapshot()`` raise
  ``RuntimeError`` — there is no fallback to the owner token.

  Reference: https://github.com/sfc-gh-bhess/ex_rcr_cortex_spcs

Per-user thread isolation is enforced by the Threads API itself (threads are
scoped to the caller identity).  ``origin_application`` is retained as a
secondary defense-in-depth filter.
"""

from __future__ import annotations

import hashlib
import logging

import requests
import streamlit as st

from config import (
    ACCOUNT_URL,
    ORIGIN_APP_BASE,
    SPCS_TOKEN_PATH,
)

log = logging.getLogger(__name__)


def get_viewer_login() -> str | None:
    """Return the Snowflake login name of the current viewer.

    In SiS container runtime, Snowflake injects the viewer's identity
    into the ``Sf-Context-Current-User`` HTTP header on every request.
    This is per-session (each viewer gets their own value).
    """
    try:
        return st.context.headers.get("Sf-Context-Current-User") or None
    except Exception:
        return None


def get_viewer_display_name(login_name: str | None) -> str | None:
    """Look up a human-friendly display name for *login_name*.

    Uses ``DESCRIBE USER`` via the owner's token (ACCOUNTADMIN can
    describe any user).  Falls back to title-casing the login name.
    """
    if not login_name:
        return None
    try:
        resp = requests.post(
            f"{ACCOUNT_URL}/api/v2/statements",
            headers=get_owner_headers(),
            json={
                "statement": f'DESCRIBE USER "{login_name}"',
                "timeout": 30,
            },
            timeout=15,
        )
        resp.raise_for_status()
        rows = resp.json().get("data", [])
        # DESCRIBE USER returns rows of [property, value, default, description].
        props = {r[0]: (r[1] or "").strip() for r in rows if r}
        name = props.get("DISPLAY_NAME", "")
        if not name:
            first = props.get("FIRST_NAME", "")
            last = props.get("LAST_NAME", "")
            name = f"{first} {last}".strip()
        if not name:
            name = login_name.replace("_", " ").title()
        return name
    except Exception:
        pass
    return login_name.replace("_", " ").title()


def _read_owner_token() -> str:
    """Read the owner's OAuth session token from the SPCS container.

    Snowflake refreshes this file every few minutes; each token is valid
    for up to one hour.
    """
    try:
        with open(SPCS_TOKEN_PATH, "r") as f:
            return f.read().strip()
    except OSError as exc:
        raise RuntimeError(
            f"Cannot read SPCS session token at {SPCS_TOKEN_PATH} — "
            "is this app running inside SiS container runtime?"
        ) from exc


def get_owner_headers(content_type: bool = True) -> dict[str, str]:
    """Auth headers using the **owner's** OAuth session token.

    Used only for operations that require the owner's elevated privileges
    (e.g. ``DESCRIBE USER``).  Viewer-facing API calls should use
    ``get_auth_headers()`` instead, which returns the RCR caller's token.
    """
    h: dict[str, str] = {
        "Authorization": f"Bearer {_read_owner_token()}",
        "X-Snowflake-Authorization-Token-Type": "OAUTH",
    }
    if content_type:
        h["Content-Type"] = "application/json"
    return h


# ---------------------------------------------------------------------------
# Restricted Caller's Rights (RCR) session
# ---------------------------------------------------------------------------

def init_rcr_connection() -> None:
    """Initialise the caller's-rights connection.

    **Must** be called at the top of the app script — within the 2-minute
    lifespan of ``Sf-Context-Current-User-Token``.

    Uses the official SiS mechanism: ``st.connection("snowflake-callers-rights")``,
    which auto-detects account/host and sets ``client_session_keep_alive=True``.
    The connection is session-scoped (one per viewer) and cached by Streamlit.
    """
    try:
        conn = st.connection("snowflake-callers-rights")
        # Warm the connection so a valid session exists immediately.
        conn.query("SELECT 1")
        log.info("RCR connection initialised for viewer")
    except Exception:
        log.warning("RCR connection failed", exc_info=True)
        st.error("Unable to establish your session. Please refresh the page.")
        st.stop()


def _get_rcr_token() -> str | None:
    """Extract a session token from the caller's-rights connection.

    Uses Brian Hess's token-extraction technique::

        conn.raw_connection._rest._token_request('ISSUE')['data']['sessionToken']

    Returns ``None`` if the RCR connection is not available (e.g. local dev).

    Note: ``_token_request`` is an internal API of the Snowflake Python
    Connector.  It works today but may change in future connector versions.
    """
    try:
        conn = st.connection("snowflake-callers-rights")
        raw = conn.raw_connection
        resp = raw._rest._token_request("ISSUE")
        return resp["data"]["sessionToken"]
    except Exception:
        log.debug("Could not extract RCR token — RCR unavailable", exc_info=True)
        return None


def _rcr_headers(content_type: bool = True) -> dict[str, str]:
    """Build auth headers from the current RCR session token.

    Raises ``RuntimeError`` if the token cannot be obtained.
    """
    token = _get_rcr_token()
    if not token:
        raise RuntimeError("Viewer session unavailable")
    h: dict[str, str] = {"Authorization": f'Snowflake Token="{token}"'}
    if content_type:
        h["Content-Type"] = "application/json"
    return h


def get_auth_headers(content_type: bool = True) -> dict[str, str]:
    """Auth headers for viewer-facing REST API calls (Threads, agent:run).

    Returns the caller's RCR session token, which ensures the Threads API
    scopes every request to the logged-in viewer's identity.

    Raises ``RuntimeError`` if the RCR token cannot be obtained — callers
    must handle this (all current call-sites have ``try/except``).
    """
    return _rcr_headers(content_type)


def build_auth_headers_snapshot(content_type: bool = True) -> dict[str, str]:
    """Capture auth headers for use in a background thread.

    Extracts the RCR token *now* (on the main Streamlit thread) so the
    background worker can authenticate without calling ``st.*`` APIs.

    Raises ``RuntimeError`` if the RCR token cannot be obtained.
    """
    return _rcr_headers(content_type)


def get_viewer_origin_app() -> str:
    """Return a per-user ``origin_application`` value (max 16 bytes).

    Uses a deterministic hash of the viewer's login name::

        "vp" + sha256(login)[:14]  →  exactly 16 bytes

    Falls back to ``ORIGIN_APP_BASE`` when no viewer identity is available.

    Thread persistence note
    -----------------------
    With RCR, the Cortex Threads API scopes thread visibility to the
    *viewer's identity* (the caller's session token).  Each user sees only
    their own threads.  ``origin_application`` is retained as a secondary
    filter on the LIST endpoint.

    **Breaking change**: threads created before RCR was enabled used the
    owner's token and are scoped to the service identity.  They will not
    appear in a viewer's thread list after RCR is activated.
    """
    login = st.session_state.get("_viewer_login")
    if not login:
        return ORIGIN_APP_BASE
    h = hashlib.sha256(login.upper().encode("utf-8")).hexdigest()[:14]
    return f"vp{h}"
