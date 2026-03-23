#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy.sh — Deploy or update the Streamlit app in Snowflake (SiS container)
#
# Usage:
#   ./deploy.sh init     First-time setup: deploy + GRANT USAGE to viewer role
#   ./deploy.sh update   In-place update:  deploy changed files to live version
#   ./deploy.sh status   Show current app versions and live version info
#
# Prerequisites:
#   - Snowflake CLI v3.14+ installed (https://docs.snowflake.com/en/developer-guide/snowflake-cli/index)
#   - A named connection configured via `snow connection add`
#   - snowflake.yml project definition in the same directory as this script
# ─────────────────────────────────────────────────────────────────────────────
set -Eeuo pipefail

# ─── Configuration — << CHANGE THESE to match your environment ────────────
# Edit these values for your environment.
# Most settings (compute pool, runtime, stage, artifacts) live in snowflake.yml.

# Snowflake CLI connection name (from ~/.snowflake/connections.toml)
CONNECTION="demo"                  # << CHANGE THIS: your snow CLI connection name

# Warehouse for SQL operations (status, grants)
WAREHOUSE="COMPUTE_WH"            # << CHANGE THIS: your warehouse

# Fully-qualified Streamlit object name (must match snowflake.yml identifier)
FQN="VALD.GOLD.VALD_PERFORMANCE_INTELLIGENCE_V2"  # << CHANGE THIS: your DB.SCHEMA.APP_NAME

# Role to grant USAGE on the Streamlit app
VIEWER_ROLE="VALD_SIS_VIEWER"     # << CHANGE THIS: your viewer role

# ─── Derived values (do not edit) ───────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─── Helpers ────────────────────────────────────────────────────────────────

CURRENT_STEP=""

on_error() {
    echo "" >&2
    echo "  [deploy] ERROR: Script failed during: ${CURRENT_STEP:-unknown step}" >&2
    echo "  [deploy] Check the error message above for details." >&2
    echo "" >&2
}
trap on_error ERR

step() {
    # Track the current step for error reporting
    CURRENT_STEP="$1"
    log "$1"
}

sql() {
    # Execute a SQL statement via snow CLI.
    # Errors (stderr) flow to the terminal even when callers suppress stdout.
    snow sql -q "$1" -c "${CONNECTION}" --warehouse "${WAREHOUSE}"
}

log() {
    echo "  [deploy] $1"
}

preflight() {
    # Verify prerequisites before running any command.
    if ! command -v snow &>/dev/null; then
        echo "" >&2
        echo "  [deploy] ERROR: 'snow' CLI not found in PATH." >&2
        echo "  [deploy] Install Snowflake CLI v3.14+: https://docs.snowflake.com/en/developer-guide/snowflake-cli" >&2
        echo "" >&2
        exit 1
    fi

    # Check CLI version >= 3.14 (required for modern container runtime syntax)
    local version
    version=$(snow --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "0.0.0")
    local major minor
    major=$(echo "${version}" | cut -d. -f1)
    minor=$(echo "${version}" | cut -d. -f2)
    if [ "${major}" -lt 3 ] || { [ "${major}" -eq 3 ] && [ "${minor}" -lt 14 ]; }; then
        echo "" >&2
        echo "  [deploy] ERROR: Snowflake CLI v3.14+ is required (found v${version})." >&2
        echo "  [deploy] Upgrade with: brew upgrade snowflake-cli" >&2
        echo "" >&2
        exit 1
    fi

    step "Verifying connection '${CONNECTION}'..."
    if ! snow sql -q "SELECT 1" -c "${CONNECTION}" --warehouse "${WAREHOUSE}" > /dev/null 2>&1; then
        echo "" >&2
        echo "  [deploy] ERROR: Cannot connect using connection '${CONNECTION}'." >&2
        echo "  [deploy] Check that the connection exists in ~/.snowflake/connections.toml" >&2
        echo "  [deploy] and that warehouse '${WAREHOUSE}' is accessible." >&2
        echo "" >&2
        exit 1
    fi
    log "  Connection OK (CLI v${version})."
}

# ─── Commands ───────────────────────────────────────────────────────────────

cmd_init() {
    echo ""
    echo "=== Initialising ${FQN} ==="
    echo ""
    echo "  WARNING: This will CREATE OR REPLACE the Streamlit app."
    echo "  Any existing app with this name will be dropped and recreated."
    echo "  Cortex threads are preserved (RCR threads are owned by the viewer, not the app)."
    echo ""
    echo "  For routine code updates, use: ./deploy.sh update"
    echo ""
    read -rp "  Continue? [y/N] " confirm
    if [[ ! "${confirm}" =~ ^[Yy]$ ]]; then
        echo "  Aborted."
        exit 0
    fi
    echo ""

    preflight

    step "Deploying via snow streamlit deploy --replace ..."
    snow streamlit deploy --replace -c "${CONNECTION}" --project "${SCRIPT_DIR}"

    step "Granting USAGE to ${VIEWER_ROLE}..."
    sql "GRANT USAGE ON STREAMLIT ${FQN} TO ROLE ${VIEWER_ROLE};"

    echo ""
    step "Verifying deployment..."
    sql "SHOW VERSIONS IN STREAMLIT ${FQN};"

    echo ""
    log "Done. App created at ${FQN}."
    echo ""
}

cmd_update() {
    echo ""
    echo "=== Updating ${FQN} in-place ==="
    echo ""

    preflight

    # We use direct PUT + version cycling instead of 'snow streamlit deploy --replace'
    # because it is lighter-weight (no DDL recreate).  --replace (used by cmd_init)
    # is safe — it preserves the SPCS url_id and RCR threads survive because they
    # are owned by the viewer's identity, not the app's container.  Both approaches
    # cause a brief container restart when the version cycles.
    #
    # The Streamlit object stores files in a managed internal stage
    # (snow://streamlit/…/versions/live/), NOT the external stage declared in
    # snowflake.yml.  We PUT files directly to the live version URI, then
    # cycle the version (COMMIT + ADD LIVE VERSION) to force the SPCS
    # container to restart and pick up the new files.

    # Resolve the live version URI from the Streamlit object metadata.
    step "Resolving live version location..."
    local live_uri
    live_uri=$(snow sql -q "DESCRIBE STREAMLIT ${FQN};" \
        -c "${CONNECTION}" --warehouse "${WAREHOUSE}" --format json 2>/dev/null \
        | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['live_version_location_uri'])")

    if [ -z "${live_uri}" ] || [ "${live_uri}" = "None" ]; then
        echo "" >&2
        echo "  [deploy] ERROR: Could not resolve live_version_location_uri." >&2
        echo "  [deploy] Has the app been initialised?  Run: ./deploy.sh init" >&2
        echo "" >&2
        exit 1
    fi
    log "  Live URI: ${live_uri}"

    step "Uploading source files..."
    local src_files=(
        app.py auth.py charts.py config.py helpers.py messages.py
        reasoning.py requirements.txt streaming.py styles.py
        threads_api.py ui.py
        vald_logo.webp              # << CHANGE THIS: your logo filename (must match config.py LOGO_PATH)
    )
    for f in "${src_files[@]}"; do
        sql "PUT file://${SCRIPT_DIR}/${f} '${live_uri}' OVERWRITE=TRUE AUTO_COMPRESS=FALSE" > /dev/null
    done

    step "Uploading .streamlit/config.toml..."
    sql "PUT file://${SCRIPT_DIR}/.streamlit/config.toml '${live_uri}.streamlit/' OVERWRITE=TRUE AUTO_COMPRESS=FALSE" > /dev/null

    step "Uploading js/ assets..."
    for f in "${SCRIPT_DIR}"/js/*.js; do
        sql "PUT file://${f} '${live_uri}js/' OVERWRITE=TRUE AUTO_COMPRESS=FALSE" > /dev/null
    done

    # Cycle the version to force the SPCS container to restart.
    # COMMIT freezes the current live version (with new files) as a named
    # version; ADD LIVE VERSION FROM LAST creates a fresh live version from
    # that snapshot, triggering a container restart.
    step "Committing current live version..."
    sql "ALTER STREAMLIT ${FQN} COMMIT;" > /dev/null

    step "Creating new live version from latest commit..."
    sql "ALTER STREAMLIT ${FQN} ADD LIVE VERSION FROM LAST;" > /dev/null

    # Re-resolve the live URI (may have changed after version cycle).
    live_uri=$(snow sql -q "DESCRIBE STREAMLIT ${FQN};" \
        -c "${CONNECTION}" --warehouse "${WAREHOUSE}" --format json 2>/dev/null \
        | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['live_version_location_uri'])")

    echo ""
    step "Verifying deployment..."
    sql "LIST '${live_uri}' PATTERN='.*\.py';"

    echo ""
    log "Done. Version cycled — container will restart with new files."
    echo ""
}

cmd_status() {
    echo ""
    echo "=== Status: ${FQN} ==="
    echo ""
    preflight
    sql "SHOW VERSIONS IN STREAMLIT ${FQN};"
    echo ""
}

# ─── Main ───────────────────────────────────────────────────────────────────

case "${1:-}" in
    init)
        cmd_init
        ;;
    update)
        cmd_update
        ;;
    status)
        cmd_status
        ;;
    -h|--help|"")
        echo "Usage: $0 {init|update|status}"
        echo ""
        echo "  init    First-time setup (deploy + GRANT USAGE to viewer role)"
        echo "  update  In-place update (deploy changed files to live version)"
        echo "  status  Show current versions"
        echo ""
        echo "  Requires: Snowflake CLI v3.14+, snowflake.yml in project root"
        exit 0
        ;;
    *)
        echo "Unknown command: $1" >&2
        echo "Usage: $0 {init|update|status}" >&2
        exit 1
        ;;
esac
