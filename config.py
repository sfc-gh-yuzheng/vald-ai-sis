"""
Shared constants, environment configuration, and brand tokens.

Every tunable value lives here so the rest of the codebase imports from a
single source of truth.  Sections:

- **SiS runtime** — SNOWFLAKE_HOST, SPCS_TOKEN_PATH, agent coordinates
- **Brand** — colour palette (hex strings)
- **Timeouts** — HTTP and SSE limits
- **UI** — page titles, thread-list limits, page sizes for the Threads API
- **Derived URLs** — account URL, Threads API base, Agent :run endpoint
- **Assets** — logo path, reasoning-box SVG icon
"""

from __future__ import annotations

import os
from pathlib import Path


# ---------------------------------------------------------------------------
# SiS container runtime — << CHANGE THESE to match your environment
# ---------------------------------------------------------------------------
SNOWFLAKE_HOST: str | None = os.getenv("SNOWFLAKE_HOST")
SPCS_TOKEN_PATH: str = "/snowflake/session/token"
AGENT_DATABASE: str = "VALD"                       # << CHANGE THIS: your database
AGENT_SCHEMA: str = "GOLD"                         # << CHANGE THIS: your schema
AGENT_NAME: str = "VALD_PERFORMANCE_AGENT"         # << CHANGE THIS: your agent name
ORIGIN_APP_BASE: str = "vald_performance"           # << CHANGE THIS: unique prefix for your app

# ---------------------------------------------------------------------------
# Brand palette — << CHANGE THESE to match your brand
# ---------------------------------------------------------------------------
VALD_ORANGE: str = "#F16E00"      # << CHANGE THIS: primary accent colour
VALD_DARK: str = "#25282A"        # << CHANGE THIS: main background
VALD_DARKER: str = "#1a1c1e"      # << CHANGE THIS: sidebar / darker panels
VALD_NEAR_BLACK: str = "#070707"   # << CHANGE THIS: code block background
VALD_WHITE: str = "#FFFFFF"
VALD_GRAY: str = "#9a9da0"

# ---------------------------------------------------------------------------
# Timeouts (seconds)
# ---------------------------------------------------------------------------
API_TIMEOUT: int = 30
AGENT_STREAM_TIMEOUT: tuple[int, int] = (10, 300)  # (connect, read) for SSE

# ---------------------------------------------------------------------------
# UI limits
# ---------------------------------------------------------------------------
MAX_VISIBLE_THREADS: int = 12

# Thread API page sizes — different call-sites need different amounts of data
PAGE_SIZE_AUTONAME: int = 5       # just enough to grab latest message for naming
PAGE_SIZE_FALLBACK: int = 10      # lightweight lookups (e.g. streaming fallback)
PAGE_SIZE_RECOVERY: int = 20      # recovery / existence check after errors
PAGE_SIZE_FULL: int = 100         # full thread load for message history

# Page / chat — << CHANGE THESE for your app branding
APP_TITLE: str = "VALD Performance Intelligence"    # << CHANGE THIS: page title
APP_FAVICON: str = "https://valdperformance.com/favicon.ico"  # << CHANGE THIS: favicon URL
CHAT_PLACEHOLDER: str = "Ask VALD Hub AI..."        # << CHANGE THIS: chat input placeholder

# ---------------------------------------------------------------------------
# Derived URLs (computed once at import time from SNOWFLAKE_HOST)
# ---------------------------------------------------------------------------
ACCOUNT_URL: str = f"https://{SNOWFLAKE_HOST}" if SNOWFLAKE_HOST else ""
THREADS_BASE: str = f"{ACCOUNT_URL}/api/v2/cortex/threads"
AGENT_RUN_URL: str = (
    f"{ACCOUNT_URL}/api/v2/databases/{AGENT_DATABASE}"
    f"/schemas/{AGENT_SCHEMA}/agents/{AGENT_NAME}:run"
)

# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------
LOGO_PATH: Path = Path(__file__).parent / "vald_logo.webp"  # << CHANGE THIS: replace with your logo file; also update snowflake.yml and deploy.sh if you rename it

# Shared SVG icon for the reasoning/thinking box
THINKING_ICON_SVG: str = (
    f'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="{VALD_ORANGE}" '
    f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;">'
    f'<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 '
    f'8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 '
    f'8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>'
)
