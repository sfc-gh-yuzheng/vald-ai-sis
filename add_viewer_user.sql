-- ============================================================
-- VALD Performance Intelligence — Add Viewer User
-- ============================================================
--
-- Configures an EXISTING Snowflake user as a viewer of the VALD
-- Streamlit app.  Run this script once per user.
--
-- PREREQUISITES:
--   1. The user must already exist in Snowflake.
--   2. setup_rcr_grants.sql must have been run (one-time infrastructure).
--
-- WHO RUNS THIS: A user with ACCOUNTADMIN or SECURITYADMIN.
--
-- WHAT THIS DOES:
--   1. Sets DEFAULT_ROLE, DEFAULT_WAREHOUSE, DEFAULT_SECONDARY_ROLES
--      so the app works correctly on first login.
--   2. Grants the viewer role to the user.
--   3. (Optional) Sets ALLOWED_INTERFACES to restrict the user to
--      app-only access.
--
-- ALLOWED_INTERFACES NOTE (OPTIONAL):
--   Setting ALLOWED_INTERFACES is optional.  It restricts which
--   Snowflake interfaces the user can access.  If you do NOT set it,
--   the user can access the Streamlit app AND Snowsight/worksheets —
--   this is perfectly fine for most deployments.
--
--   If you want to lock the user to ONLY the Streamlit app (no
--   Snowsight access), set both values below:
--     STREAMLIT              — allows the Streamlit app UI
--     SNOWFLAKE_INTELLIGENCE — allows the Cortex Agent REST API
--                              (/api/v2/.../agents/:run) via RCR token
--   Both are needed if you set this.  Using STREAMLIT alone will break
--   the agent with "denying access to the ALL interface".
--
--   To skip this restriction, comment out Section 3 below.
--
-- APP-VIEWER URL (no Snowsight chrome):
--   https://app.snowflake.com/streamlit/<ORG>/<ACCOUNT>/#/apps/<URL_ID>
--   Find url_id via: SHOW STREAMLITS LIKE '<app>' IN SCHEMA <schema>;
-- ============================================================


-- ============================================================
-- PARAMETERS — Set these before running
-- ============================================================

SET rcr_viewer_user   = 'JANE_DOE';           -- << CHANGE THIS: existing Snowflake username
SET rcr_viewer_role   = 'VALD_SIS_VIEWER';    -- Must match setup_rcr_grants.sql
SET rcr_warehouse     = 'COMPUTE_WH';         -- Must match setup_rcr_grants.sql


-- ============================================================
-- 1. Configure user defaults
-- ============================================================

ALTER USER IDENTIFIER($rcr_viewer_user)
  SET DEFAULT_ROLE            = $rcr_viewer_role
      DEFAULT_WAREHOUSE       = $rcr_warehouse
      DEFAULT_SECONDARY_ROLES = ('ALL');


-- ============================================================
-- 2. Grant the viewer role
-- ============================================================

GRANT ROLE IDENTIFIER($rcr_viewer_role) TO USER IDENTIFIER($rcr_viewer_user);


-- ============================================================
-- 3. (Optional) Restrict to app-only access
-- ============================================================
-- Comment out the ALTER below if the user also needs Snowsight.

ALTER USER IDENTIFIER($rcr_viewer_user)
  SET ALLOWED_INTERFACES = ('STREAMLIT', 'SNOWFLAKE_INTELLIGENCE');


-- ============================================================
-- VERIFICATION
-- ============================================================

-- Confirm role was granted:
SHOW GRANTS TO USER IDENTIFIER($rcr_viewer_user);

-- Confirm user properties:
DESCRIBE USER IDENTIFIER($rcr_viewer_user);
