# VALD Performance Intelligence

SiS container runtime chat app powered by a Cortex Agent with Restricted Caller's Rights (RCR) per-viewer auth, Cortex Threads for persistence, and bundled Vega-Lite chart rendering.

## Setup

All values marked `<< CHANGE THIS` must be set before deployment. Work through files in this order:

1. **`agent_setup.sql`** — Agent + stored procedures (RadarChart, QuadrantChart). Skip if you already have an agent; cherry-pick Sections 1-2 for the chart procs only. Requires a semantic view to exist first.
2. **`setup_rcr_grants.sql`** — RCR infrastructure grants (Sections A+B). Section C requires the app to exist — `deploy.sh init` handles it.
3. **`config.py`** + **`.streamlit/config.toml`** — Agent coordinates, brand palette, UI strings. Keep colours in sync between the two files.
4. **`snowflake.yml`** — Snow CLI project definition (database, schema, compute pool, stage, viewer role).
5. **`deploy.sh`** — Connection name, warehouse, FQN, viewer role.

## Deploy

```bash
./deploy.sh init      # First time: creates app + grants USAGE to viewer role
./deploy.sh update    # Routine: uploads changed files, cycles live version (thread-safe)
./deploy.sh status    # Show current versions
```

`update` is the preferred routine deploy — it uploads changed files and cycles the live version, causing a brief container restart. `init` (which uses `--replace`) recreates the Streamlit object at the DDL level, also causing a container restart. Both preserve the app's SPCS identity and all existing Cortex threads.

## Adding viewers

Run `add_viewer_user.sql` per user. Sets DEFAULT_ROLE/WAREHOUSE, grants the viewer role. Section 3 (ALLOWED_INTERFACES) is optional — only needed to lock users out of Snowsight. If you set it, both `STREAMLIT` and `SNOWFLAKE_INTELLIGENCE` are required or the agent API fails.

## Auth & RCR

The app uses **Restricted Caller's Rights (RCR)** so that every viewer's API calls (Threads, Agent) execute under their own identity — not the app owner's. This is what gives you per-user thread isolation out of the box.

```
Viewer browser
  → SPCS container (SiS runtime)
    → st.connection("snowflake-callers-rights")   ← viewer's identity
    → REST calls with Snowflake Token="…"
      → Cortex Threads / Agent API
        → executes as the viewer's role
```

The RCR connection must be established at the top of the script within the 2-minute lifespan of the `Sf-Context-Current-User-Token` header injected by SPCS. Once established, `client_session_keep_alive` keeps it alive for the session. A session token is then extracted from the connection for REST API calls.

Two tokens coexist, never interchangeable:

| Token | Header format | Source | Used for |
|---|---|---|---|
| **Owner** | `Authorization: Bearer {token}` | `/snowflake/session/token` (SPCS file) | `DESCRIBE USER` only (display name lookup) |
| **RCR** | `Authorization: Snowflake Token="{token}"` | `st.connection("snowflake-callers-rights")` | All viewer-facing API calls (Threads, Agent) |

There is no owner-token fallback — if the RCR connection fails, the app halts (`st.stop()`).

**Grant chain** (`setup_rcr_grants.sql`):
- **Section A** — Normal grants to the viewer role (database, schema, warehouse, tables, semantic views, procedures, agent).
- **Section B** — `CALLER` grants to the owner role, which tells Snowflake the SiS runtime is trusted to delegate on behalf of viewers. Both normal grants (A) and caller grants (B) must exist for RCR to work.
- **Section C** — `USAGE ON STREAMLIT` to the viewer role.

**Thread ownership**: Because every API call uses the viewer's RCR token, Cortex Threads are owned by the viewer — not the app or the app owner. This means:
- Threads survive redeployments (both `update` and `init --replace`) because ownership is tied to the viewer's Snowflake identity, not the app's SPCS container.
- Viewer A cannot see Viewer B's threads — the Threads API scopes results to the caller whose token is in the request.
- If the same viewer uses multiple Cortex-powered apps, an `origin_application` hash (`sha256(login)`) is passed when listing threads to prevent cross-app thread leakage.

## Files

```
app.py              Entry point
config.py           Constants, URLs, brand tokens
auth.py             Owner token + RCR session
threads_api.py      Threads API CRUD
messages.py         Message loading & parsing
streaming.py        Background SSE (daemon thread + polling fragment)
helpers.py          Pure-Python utilities
reasoning.py        Collapsible thinking/tool-call box
charts.py           Vega-Lite rendering (bundled JS, CSP-safe)
styles.py           CSS theme
ui.py               Sidebar, chat area, streaming display
deploy.sh           Deploy script
snowflake.yml       Snow CLI project definition
agent_setup.sql     Agent + tool DDLs (reference)
setup_rcr_grants.sql  RCR grants (one-time)
add_viewer_user.sql   Per-viewer provisioning
js/                 Bundled Vega JS
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Unable to establish your session" | Re-run `setup_rcr_grants.sql`; check ALLOWED_INTERFACES includes both values |
| Empty thread list | Verify `Sf-Context-Current-User` header (requires container runtime) |
| Charts not rendering | Re-deploy — Vega JS files missing from `js/` |
| "Session expired" | Refresh browser to re-establish RCR connection |
