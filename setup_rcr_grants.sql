-- ============================================================
-- VALD Performance Intelligence — RCR Setup Script
-- ============================================================
--
-- This script configures Restricted Caller's Rights (RCR) for
-- the VALD Streamlit app.  It must be run ONCE by an administrator
-- before deploying the RCR-enabled app code.
--
-- WHO RUNS THIS: A user with ACCOUNTADMIN or a role that has the
--   MANAGE CALLER GRANTS privilege.  This is a one-time admin setup.
--
-- WHO DOES *NOT* NEED ACCOUNTADMIN: End-user viewers of the Streamlit
--   app.  They use the viewer role (VALD_SIS_VIEWER by default) and
--   never need admin privileges.
--
-- WHAT THIS DOES:
--   Section A — Normal grants to the viewer role so the Cortex Agent's
--               tools (Analyst, RadarChart, QuadrantChart) can execute
--               as the viewer.
--   Section B — Caller Grants to the app owner role so the SiS
--               container runtime is trusted to act on behalf of
--               the viewer for specific objects.
--   Section C — App access: USAGE ON STREAMLIT + role assignment to users.
--   Section D — (Optional) SiS-only user lockdown and app-viewer URL.
--
-- BREAKING CHANGE: After enabling RCR, threads created under the
--   previous owner-token model will no longer be visible to viewers.
--   New threads will be properly isolated per user.
--
-- Reference: https://github.com/sfc-gh-bhess/ex_rcr_cortex_spcs
-- ============================================================


-- ============================================================
-- PARAMETERS — Modify these for your environment
-- ============================================================

SET rcr_owner_role   = 'ACCOUNTADMIN';       -- << CHANGE THIS: role that owns the SiS Streamlit app
SET rcr_viewer_role  = 'VALD_SIS_VIEWER';    -- << CHANGE THIS: role assigned to end-user viewers
SET rcr_app_db       = 'VALD';               -- << CHANGE THIS: database containing the app's objects
SET rcr_app_schema   = 'GOLD';               -- << CHANGE THIS: schema containing the app's objects
SET rcr_warehouse    = 'COMPUTE_WH';         -- << CHANGE THIS: warehouse used by the agent's tools
SET rcr_streamlit    = 'VALD_PERFORMANCE_INTELLIGENCE_V2';  -- << CHANGE THIS: Streamlit app name
SET rcr_full_schema  = $rcr_app_db || '.' || $rcr_app_schema;
SET rcr_full_streamlit = $rcr_full_schema || '.' || $rcr_streamlit;


-- ============================================================
-- SECTION A: Normal Grants to Viewer Role
-- ============================================================
-- These grants allow the Cortex Agent's tools to function when
-- API calls execute as the viewer (instead of the owner).
--
-- The viewer role likely already has USAGE on the database, schema,
-- warehouse, agent, and streamlit.  The grants below cover what is
-- typically MISSING: table SELECT, semantic view SELECT, and
-- procedure USAGE.
-- ============================================================

-- A1. Database & schema (idempotent — safe if already granted)
GRANT USAGE ON DATABASE IDENTIFIER($rcr_app_db)
  TO ROLE IDENTIFIER($rcr_viewer_role);
GRANT USAGE ON SCHEMA IDENTIFIER($rcr_full_schema)
  TO ROLE IDENTIFIER($rcr_viewer_role);

-- A2. Warehouse
GRANT USAGE ON WAREHOUSE IDENTIFIER($rcr_warehouse)
  TO ROLE IDENTIFIER($rcr_viewer_role);

-- A3. Tables — required by Cortex Analyst (generates SQL that SELECTs
--     from the base tables referenced by the semantic view)
GRANT SELECT ON ALL TABLES IN SCHEMA IDENTIFIER($rcr_full_schema)
  TO ROLE IDENTIFIER($rcr_viewer_role);
GRANT SELECT ON FUTURE TABLES IN SCHEMA IDENTIFIER($rcr_full_schema)
  TO ROLE IDENTIFIER($rcr_viewer_role);

-- A4. Semantic view — required by Cortex Analyst
GRANT SELECT ON ALL SEMANTIC VIEWS IN SCHEMA IDENTIFIER($rcr_full_schema)
  TO ROLE IDENTIFIER($rcr_viewer_role);
GRANT SELECT ON FUTURE SEMANTIC VIEWS IN SCHEMA IDENTIFIER($rcr_full_schema)
  TO ROLE IDENTIFIER($rcr_viewer_role);

-- A5. Stored procedures — required by agent tools (RadarChart, QuadrantChart)
GRANT USAGE ON ALL PROCEDURES IN SCHEMA IDENTIFIER($rcr_full_schema)
  TO ROLE IDENTIFIER($rcr_viewer_role);
GRANT USAGE ON FUTURE PROCEDURES IN SCHEMA IDENTIFIER($rcr_full_schema)
  TO ROLE IDENTIFIER($rcr_viewer_role);

-- A6. Cortex Agent — likely already granted, included for completeness
GRANT USAGE ON ALL AGENTS IN SCHEMA IDENTIFIER($rcr_full_schema)
  TO ROLE IDENTIFIER($rcr_viewer_role);


-- ============================================================
-- SECTION B: Caller Grants to Owner Role
-- ============================================================
-- These CALLER GRANTS tell Snowflake that the owner role is trusted
-- to execute operations on behalf of callers for specific objects.
-- Both the caller's normal grants AND these caller grants must exist.
--
-- Requires: MANAGE CALLER GRANTS privilege (ACCOUNTADMIN has this).
-- ============================================================

-- B1. Cortex functions (in the SNOWFLAKE database)
--     Required for the Cortex Agent orchestration and Analyst tool.
GRANT CALLER USAGE ON DATABASE SNOWFLAKE
  TO ROLE IDENTIFIER($rcr_owner_role);
GRANT INHERITED CALLER USAGE ON ALL SCHEMAS IN DATABASE SNOWFLAKE
  TO ROLE IDENTIFIER($rcr_owner_role);
GRANT INHERITED CALLER USAGE ON ALL FUNCTIONS IN DATABASE SNOWFLAKE
  TO ROLE IDENTIFIER($rcr_owner_role);

-- B2. App database & schema
GRANT CALLER USAGE ON DATABASE IDENTIFIER($rcr_app_db)
  TO ROLE IDENTIFIER($rcr_owner_role);
GRANT CALLER USAGE ON SCHEMA IDENTIFIER($rcr_full_schema)
  TO ROLE IDENTIFIER($rcr_owner_role);

-- B3. Warehouse
GRANT CALLER USAGE ON WAREHOUSE IDENTIFIER($rcr_warehouse)
  TO ROLE IDENTIFIER($rcr_owner_role);

-- B4. Tables (for Cortex Analyst SQL queries)
GRANT INHERITED CALLER SELECT ON ALL TABLES IN SCHEMA IDENTIFIER($rcr_full_schema)
  TO ROLE IDENTIFIER($rcr_owner_role);

-- B5. Semantic views (for Cortex Analyst)
GRANT INHERITED CALLER SELECT ON ALL SEMANTIC VIEWS IN SCHEMA IDENTIFIER($rcr_full_schema)
  TO ROLE IDENTIFIER($rcr_owner_role);

-- B6. Stored procedures (for agent tools: RadarChart, QuadrantChart)
GRANT INHERITED CALLER USAGE ON ALL PROCEDURES IN SCHEMA IDENTIFIER($rcr_full_schema)
  TO ROLE IDENTIFIER($rcr_owner_role);

-- B7. Cortex Agent
GRANT INHERITED CALLER USAGE ON ALL AGENTS IN SCHEMA IDENTIFIER($rcr_full_schema)
  TO ROLE IDENTIFIER($rcr_owner_role);


-- ============================================================
-- SECTION C: App Access & User Provisioning
-- ============================================================
-- These grants give the viewer role access to the Streamlit app
-- itself, and assign the viewer role to specific users.
--
-- NOTE: For first-time setup, the Streamlit object may not exist
-- yet.  deploy.sh init creates the app AND grants USAGE
-- automatically — you can skip Section C and come back later,
-- or re-run this entire script after the first deploy.
-- ============================================================

-- C1. Streamlit app access (idempotent — safe if already granted)
GRANT USAGE ON STREAMLIT IDENTIFIER($rcr_full_streamlit)
  TO ROLE IDENTIFIER($rcr_viewer_role);

-- C2. Configure viewer users
--     Run add_viewer_user.sql for each user who needs access.
--     That script grants the viewer role, sets DEFAULT_ROLE/WAREHOUSE,
--     and optionally restricts ALLOWED_INTERFACES for app-only access.


-- ============================================================
-- VERIFICATION
-- ============================================================

-- Check caller grants were applied:
SHOW CALLER GRANTS TO ROLE IDENTIFIER($rcr_owner_role);

-- Check viewer role grants:
SHOW GRANTS TO ROLE IDENTIFIER($rcr_viewer_role);
