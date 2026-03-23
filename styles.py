"""
VALD dark-theme CSS for the Streamlit app.

All CSS lives here to keep app.py slim. The ``get_app_css()`` function
returns the full ``<style>`` block with VALD brand colours interpolated.
"""

from __future__ import annotations

from config import (
    VALD_DARK,
    VALD_DARKER,
    VALD_GRAY,
    VALD_NEAR_BLACK,
    VALD_ORANGE,
    VALD_WHITE,
)


def get_app_css() -> str:
    """Return the complete ``<style>…</style>`` markup for the VALD app."""
    return f"""
<style>
    /* Roboto loaded via @import is blocked by SiS CSP; all font-family rules
       already declare sans-serif as fallback, so the UI degrades gracefully. */

    /* Font scale — 3 tiers for consistency */
    :root {{
        --fs-sm: 0.78rem;
        --fs-md: 0.88rem;
        --fs-lg: 1.1rem;
    }}

    /* Global font — exclude Material icon elements */
    html, body, .stMarkdown, .stChatMessage, .stTextInput {{
        font-family: 'Roboto', sans-serif !important;
    }}
    [class*="st-"]:not([data-testid="stIconMaterial"]):not([data-testid="stExpandSidebarButton"] *):not([data-testid="stSidebarCollapseButton"] *) {{
        font-family: 'Roboto', sans-serif !important;
    }}

    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    /* Style header but keep sidebar toggle button visible */
    header[data-testid="stHeader"] {{
        background: {VALD_DARK} !important;
        border-bottom: none !important;
    }}
    /* Hide only the right-side toolbar items (deploy button, menu etc)
       but NOT the left-side which contains the sidebar expand button */
    [data-testid="stToolbar"] [data-testid="stToolbarActions"] {{
        display: none !important;
    }}
    [data-testid="stToolbar"] [data-testid="stHeaderActionElements"] {{
        display: none !important;
    }}
    /* Also hide the deploy button specifically */
    [data-testid="stAppDeployButton"] {{
        display: none !important;
    }}

    /* Scroll anchoring — keep viewport stable when chart iframes resize */
    section.stMain,
    section[data-testid="stAppScrollToBottomContainer"],
    section.main {{
        overflow-anchor: auto;
    }}

    /* Main container — use both old and new class names with !important */
    .block-container,
    .stMainBlockContainer {{
        padding-top: 2.5rem;
        padding-bottom: 2rem;
        max-width: 51.25rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }}
    [data-testid="stBottomBlockContainer"] {{
        padding-top: 0 !important;
        max-width: 51.25rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }}

    /* Hero section — greeting shown on empty chat */
    .vald-hero {{
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        text-align: left;
        padding: 30vh 0 1rem 0;
    }}
    .vald-hero h1 {{
        font-family: 'Roboto', sans-serif;
        font-size: 2.1rem;
        font-weight: 800;
        background: linear-gradient(to right, {VALD_WHITE}, #b0b0b0);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin: 0;
        letter-spacing: 0.01em;
        line-height: 1.2;
    }}
    .vald-hero p {{
        font-family: 'Roboto', sans-serif;
        font-size: 2.1rem;
        font-weight: 800;
        background: linear-gradient(to right, {VALD_ORANGE}, #FFB347);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-top: 0;
        letter-spacing: 0.01em;
        line-height: 1.2;
    }}

    /* Chat messages - hide avatars completely */
    .stChatMessage {{
        background: transparent !important;
        border: none !important;
        gap: 0 !important;
        padding-left: 0 !important;
        padding-right: 0 !important;
    }}
    /* Nuclear approach: hide every avatar-related element */
    .stChatMessage [data-testid="stChatMessageAvatarUser"],
    .stChatMessage [data-testid="stChatMessageAvatarAssistant"],
    .stChatMessage [data-testid="stChatMessageAvatarCustom"],
    .stChatMessage [data-testid="chatAvatarIcon-user"],
    .stChatMessage [data-testid="chatAvatarIcon-assistant"],
    .stChatMessage [data-testid="stChatMessageAvatarContainer"],
    .stChatMessage .stChatMessageAvatarContainer {{
        display: none !important;
        width: 0 !important;
        height: 0 !important;
        min-width: 0 !important;
        min-height: 0 !important;
        max-width: 0 !important;
        max-height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        overflow: hidden !important;
        position: absolute !important;
        opacity: 0 !important;
    }}

    /* User messages right-aligned speech bubble */
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {{
        display: flex !important;
        flex-direction: row-reverse !important;
        justify-content: flex-start !important;
        height: auto !important;
        min-height: 0 !important;
        overflow: visible !important;
        background: transparent !important;
    }}
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {{
        text-align: left !important;
        background: #2f3234 !important;
        border-radius: 18px 18px 4px 18px !important;
        padding: 0.55rem 1rem !important;
        max-width: 75% !important;
        margin-left: auto !important;
        margin-right: 0 !important;
        width: fit-content !important;
        flex-grow: 0 !important;
        flex-shrink: 1 !important;
        flex-basis: auto !important;
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        height: auto !important;
        min-height: unset !important;
        max-height: none !important;
        overflow: visible !important;
        line-height: 1.5 !important;
    }}
    /* Force ALL nested wrappers inside user bubble to shrink-wrap */
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] div,
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] div[class*="emotion-cache"],
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] div[class*="st-emotion"] {{
        height: auto !important;
        min-height: unset !important;
        max-height: none !important;
        overflow: visible !important;
        padding: 0 !important;
        margin: 0 !important;
    }}
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] p {{
        text-align: left !important;
        margin: 0 !important;
        padding: 0 !important;
        overflow: visible !important;
        word-break: break-word !important;
        height: auto !important;
        line-height: 1.5 !important;
    }}

    /* Assistant messages left-aligned, no bubble */
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) [data-testid="stChatMessageContent"] {{
        max-width: 95% !important;
    }}
    /* Chat message text — slightly larger for readability */
    [data-testid="stChatMessageContent"] {{
        font-size: var(--fs-lg) !important;
    }}

    /* Remove iframe border from embedded charts */
    iframe {{
        border: none !important;
    }}

    /* Reasoning box (custom HTML details/summary) */
    details.reasoning-box {{
        background: {VALD_DARKER};
        border: 1px solid {VALD_ORANGE}40;
        border-radius: 8px;
        margin: 0.2rem 0 0.6rem 0;
        font-family: 'Roboto', sans-serif;
        font-size: var(--fs-md);
        overflow: hidden;
    }}
    details.reasoning-box > summary {{
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.5rem 0.75rem;
        color: {VALD_GRAY};
        cursor: pointer;
        user-select: none;
        list-style: none;
    }}
    details.reasoning-box > summary::-webkit-details-marker {{
        display: none;
    }}
    details.reasoning-box > summary::after {{
        content: '\\25B6';
        font-size: 0.55rem;
        margin-left: auto;
        transition: transform 0.2s;
        color: {VALD_GRAY};
    }}
    details.reasoning-box[open] > summary::after {{
        transform: rotate(90deg);
    }}
    details.reasoning-box > summary:hover {{
        color: {VALD_WHITE};
    }}
    details.reasoning-box > summary .icon {{
        font-size: var(--fs-lg);
    }}
    details.reasoning-box > summary .label {{
        font-weight: 500;
        color: {VALD_GRAY};
    }}
    details.reasoning-box .reasoning-content {{
        padding: 0 0.75rem 0.6rem 0.75rem;
        color: {VALD_GRAY};
        font-size: var(--fs-md);
        border-top: 1px solid {VALD_ORANGE}20;
        max-height: 300px;
        overflow-y: auto;
    }}
    details.reasoning-box .reasoning-content pre {{
        background: {VALD_NEAR_BLACK} !important;
        border: 1px solid #3a3d40;
        border-radius: 6px;
        padding: 0.5rem;
        font-size: var(--fs-sm);
        overflow-x: auto;
        white-space: pre-wrap;
        word-break: break-word;
        color: #D4D4D4;
    }}
    details.reasoning-box .reasoning-content pre code {{
        font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', Consolas, monospace;
        background: transparent;
    }}

    /* Chat input - VALD styled */
    .stChatInput {{
        padding-bottom: 2.5rem !important;
        position: relative !important;
    }}
    .stChatInput::after {{
        content: 'Agents can make mistakes, double-check responses.';
        display: block;
        text-align: center;
        color: {VALD_GRAY};
        font-size: var(--fs-sm);
        font-family: 'Roboto', sans-serif;
        margin-top: 0.35rem;
    }}
    .stChatInput > div {{
        border-radius: 12px;
        border: 1px solid #3a3d40 !important;
        background: {VALD_DARKER} !important;
        color: {VALD_WHITE} !important;
        font-family: 'Roboto', sans-serif !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
    }}
    .stChatInput > div:focus-within {{
        border-color: {VALD_ORANGE} !important;
        box-shadow: 0 0 0 1px {VALD_ORANGE}40 !important;
    }}
    .stChatInput textarea {{
        color: {VALD_WHITE} !important;
        font-family: 'Roboto', sans-serif !important;
    }}
    .stChatInput textarea::placeholder {{
        color: {VALD_GRAY} !important;
    }}

    /* Sidebar */
    section[data-testid="stSidebar"] {{
        background: {VALD_DARKER};
        border-right: none;
        /* contain: layout makes fixed children position relative to sidebar, not viewport */
        contain: layout;
    }}
    /* Lock sidebar width only when expanded — allows normal collapse to 0 width */
    section[data-testid="stSidebar"][aria-expanded="true"] {{
        width: 280px !important;
        min-width: 280px !important;
        max-width: 280px !important;
    }}
    section[data-testid="stSidebar"][aria-expanded="true"] > div:first-child {{
        width: 280px !important;
        min-width: 280px !important;
        max-width: 280px !important;
    }}
    section[data-testid="stSidebar"] > div:first-child {{
        background: {VALD_DARKER};
        position: relative;
        padding-bottom: 5rem;
    }}

    /* Profile pinned to bottom of sidebar via fixed positioning */
    .sidebar-profile {{
        position: fixed;
        bottom: 0;
        left: 1rem;
        width: calc(100% - 2rem);
        background: {VALD_DARKER};
        border-top: 1px solid #3a3d40;
        padding: 1rem 0 1.2rem 0;
        display: flex;
        align-items: center;
        gap: 0.6rem;
        z-index: 100;
        box-sizing: border-box;
    }}
    section[data-testid="stSidebar"] .block-container {{
        padding-top: 1rem;
    }}
    /* Always show the sidebar collapse (close) button */
    [data-testid="stSidebarCollapseButton"] {{
        visibility: visible !important;
    }}
    /* Add padding inside sidebar user content for breathing room */
    [data-testid="stSidebarUserContent"] {{
        padding-top: 0 !important;
        padding-bottom: 5rem !important;
    }}
    section[data-testid="stSidebar"] h3 {{
        color: {VALD_ORANGE} !important;
        font-family: 'Roboto', sans-serif !important;
        font-weight: 600;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        font-size: var(--fs-md);
    }}

    /* Sidebar buttons */
    section[data-testid="stSidebar"] button {{
        font-family: 'Roboto', sans-serif !important;
        border-radius: 8px !important;
        font-size: var(--fs-md) !important;
    }}
    section[data-testid="stSidebar"] button[kind="primary"] {{
        background: transparent !important;
        color: #ccc !important;
        border: 1px solid #3a3d40 !important;
        font-weight: 400 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        gap: 0.5rem !important;
    }}
    section[data-testid="stSidebar"] button[kind="primary"]:hover {{
        background: #2f3234 !important;
        color: {VALD_WHITE} !important;
        border-color: #555 !important;
    }}
    section[data-testid="stSidebar"] button[kind="primary"][disabled] {{
        background: #2f3234 !important;
        color: {VALD_WHITE} !important;
        border-color: #555 !important;
        opacity: 1 !important;
    }}

    /* "Show more" link — styled like section headers */
    section[data-testid="stSidebar"] button[kind="tertiary"] {{
        background: transparent !important;
        color: #9a9da0 !important;
        border: none !important;
        font-size: var(--fs-sm) !important;
        font-weight: 400 !important;
        text-align: left !important;
        padding: 0.3rem 0.2rem !important;
        min-height: 0 !important;
    }}
    section[data-testid="stSidebar"] button[kind="tertiary"]:hover {{
        color: {VALD_WHITE} !important;
        background: transparent !important;
    }}

    /* Thread name buttons — left-aligned, compact */
    section[data-testid="stSidebar"] button[kind="secondary"],
    div[data-testid="stDialog"] button[kind="secondary"] {{
        background: transparent !important;
        color: #ccc !important;
        border: none !important;
        text-align: left !important;
        padding: 0.35rem 0.5rem !important;
        border-radius: 6px !important;
        font-size: var(--fs-sm) !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        display: flex !important;
        justify-content: flex-start !important;
        align-items: center !important;
        min-height: 0 !important;
        line-height: 1.3 !important;
    }}
    /* Override Streamlit's inner StyledButtonLabel flex centering */
    section[data-testid="stSidebar"] button[kind="secondary"] > div,
    div[data-testid="stDialog"] button[kind="secondary"] > div {{
        justify-content: flex-start !important;
        overflow: hidden !important;
        min-width: 0 !important;
    }}
    section[data-testid="stSidebar"] button[kind="secondary"] p,
    div[data-testid="stDialog"] button[kind="secondary"] p {{
        text-align: left !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        min-width: 0 !important;
    }}
    section[data-testid="stSidebar"] button[kind="secondary"]:hover,
    div[data-testid="stDialog"] button[kind="secondary"]:hover {{
        background: #2f3234 !important;
        color: {VALD_WHITE} !important;
        border: none !important;
    }}
    /* Active thread highlight */
    section[data-testid="stSidebar"] button[kind="secondary"][disabled],
    div[data-testid="stDialog"] button[kind="secondary"][disabled] {{
        background: #2f3234 !important;
        color: {VALD_WHITE} !important;
        opacity: 1 !important;
        font-weight: 500 !important;
    }}

    /* Reduce vertical spacing between thread rows in sidebar */
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div {{
        margin-bottom: -0.6rem !important;
    }}
    /* But keep spacing around bigger elements and section headers */
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div:has(button[kind="primary"]),
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div:has(hr),
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div:has([data-testid="stMarkdown"]) {{
        margin-bottom: 0 !important;
    }}
    /* Tighten gap between New Chat and Search Chats buttons */
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div:has(button[kind="primary"]) + div:has(button[kind="primary"]) {{
        margin-top: -0.4rem !important;
    }}

    /* Add breathing room above section headers that follow thread rows */
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div:has(button[kind="secondary"]) + div:has([data-testid="stMarkdown"]) {{
        margin-top: 0.5rem !important;
    }}

    /* Dividers */
    hr {{
        border: none;
        border-top: 1px solid #3a3d40;
        margin: 1rem 0;
    }}

    /* Scrollbar */
    ::-webkit-scrollbar {{
        width: 6px;
    }}
    ::-webkit-scrollbar-track {{
        background: {VALD_DARK};
    }}
    ::-webkit-scrollbar-thumb {{
        background: #3a3d40;
        border-radius: 3px;
    }}
    ::-webkit-scrollbar-thumb:hover {{
        background: {VALD_ORANGE};
    }}

    /* ── Tables (response text + reasoning box) ── */
    [data-testid="stChatMessageContent"] table,
    .reasoning-content table {{
        width: 100%;
        border-collapse: collapse;
        margin: 0.5rem 0;
        font-size: var(--fs-md);
        font-family: 'Roboto', sans-serif;
    }}
    [data-testid="stChatMessageContent"] th,
    .reasoning-content th {{
        background: {VALD_NEAR_BLACK};
        font-weight: 600;
        text-align: left;
        border-bottom: 2px solid {VALD_ORANGE}60;
        color: {VALD_WHITE};
    }}
    [data-testid="stChatMessageContent"] td,
    .reasoning-content td {{
        border-bottom: 1px solid #3a3d40;
        background: #282c2e;
    }}
    [data-testid="stChatMessageContent"] th,
    [data-testid="stChatMessageContent"] td,
    .reasoning-content th,
    .reasoning-content td {{
        padding: 0.5rem 0.75rem;
        color: {VALD_GRAY};
    }}
    [data-testid="stChatMessageContent"] tr:hover td,
    .reasoning-content tr:hover td {{
        background: #2f3234;
    }}
    /* Horizontal scroll wrapper for wide tables in reasoning box */
    .vald-table-wrap {{
        overflow-x: auto;
        margin: 0.4rem 0;
        border-radius: 6px;
        border: 1px solid #3a3d40;
    }}
    .vald-table-wrap table {{
        margin: 0;
    }}

    /* Code blocks */
    .stCodeBlock {{
        background: {VALD_NEAR_BLACK} !important;
        border: 1px solid #3a3d40;
        border-radius: 8px;
    }}

    /* Error messages */
    .stAlert {{
        border-radius: 8px;
        font-family: 'Roboto', sans-serif !important;
    }}
    /* ── Search-chats dialog ── */
    div[data-testid="stDialog"] {{
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        width: 100% !important;
        height: 100% !important;
    }}
    /* Override baseweb DialogContainer inline styles (alignItems:"start", paddingTop:~32px) */
    div[data-testid="stDialog"] div:has(> div[role="dialog"]) {{
        align-items: center !important;
        padding-top: 0 !important;
    }}
    div[data-testid="stDialog"] div[role="dialog"] {{
        border: none !important;
        border-radius: 12px !important;
        background: #2f3234 !important;
        max-height: 85vh !important;
        overflow: hidden !important;
    }}
    div[data-testid="stDialog"] button[kind="secondary"] {{
        font-family: 'Roboto', sans-serif !important;
        font-size: var(--fs-md) !important;
    }}
    div[data-testid="stDialog"] [data-testid="stVerticalBlock"] > div {{
        margin-bottom: -0.4rem !important;
    }}
    div[data-testid="stDialog"] [data-testid="stVerticalBlock"] > div:has([data-testid="stMarkdown"]) {{
        margin-bottom: 0 !important;
    }}
    div[data-testid="stDialog"] [data-testid="stVerticalBlock"] > div:has(button[kind="secondary"]) + div:has([data-testid="stMarkdown"]) {{
        margin-top: 0.5rem !important;
    }}
    /* Reset all dialog block wrappers to auto height (overrides Streamlit inline height) */
    div[data-testid="stDialog"] [data-testid="stVerticalBlockBorderWrapper"] {{
        height: auto !important;
    }}
    /* Cap only the INNER scroll container (nested wrapper from st.container) */
    div[data-testid="stDialog"] [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlockBorderWrapper"] {{
        max-height: calc(85vh - 7rem) !important;
    }}
</style>
"""
