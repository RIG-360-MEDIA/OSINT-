-- ============================================================================
-- Migration 080 — rigwire_app role + auth/rigwire schemas
-- ============================================================================
-- Coordination request from the Rig Wire chat — adds a new role + two
-- isolated schemas for downstream-product user identity & per-user data.
--
-- Follows the pattern from migration 076 (analytics_user), with three
-- improvements over their original request:
--   1. Schemas created with AUTHORIZATION rigwire_app (they own them outright)
--   2. Skipped pg_read_all_settings grant (not needed for app-level RLS)
--   3. Explicit REVOKE on public + EXECUTE on functions (parity w/ analytics_user)
--
-- BEFORE APPLYING:
--   Replace 'REPLACE_ME_WITH_STRONG_PASSWORD' below with a generated value.
--   Suggested: `openssl rand -base64 24`.
--   Then hand the password back to the Rig Wire chat for their .env file.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. Create the role with login + password
-- ----------------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rigwire_app') THEN
    CREATE ROLE rigwire_app LOGIN PASSWORD 'REPLACE_ME_WITH_STRONG_PASSWORD'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
END
$$;

-- ----------------------------------------------------------------------------
-- 2. Create the two isolated schemas owned by rigwire_app
--    AUTHORIZATION: rigwire_app owns them end-to-end (can CREATE/DROP/etc.)
-- ----------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS auth    AUTHORIZATION rigwire_app;
CREATE SCHEMA IF NOT EXISTS rigwire AUTHORIZATION rigwire_app;

COMMENT ON SCHEMA auth IS
  'Rig Wire identity tables: users, sessions, password reset tokens. Owned by rigwire_app.';
COMMENT ON SCHEMA rigwire IS
  'Rig Wire per-user content: preferences, reading history, audit log. Owned by rigwire_app.';

-- ----------------------------------------------------------------------------
-- 3. Grant rigwire_app read access to existing substrate (public.*) tables
--    (parity with analytics_user role from migration 076)
-- ----------------------------------------------------------------------------
GRANT USAGE   ON SCHEMA public TO rigwire_app;
GRANT SELECT  ON ALL TABLES    IN SCHEMA public TO rigwire_app;
GRANT SELECT  ON ALL SEQUENCES IN SCHEMA public TO rigwire_app;

-- Auto-grant SELECT on FUTURE public tables (so new substrate migrations
-- propagate access automatically without manual intervention)
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES    TO rigwire_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON SEQUENCES TO rigwire_app;

-- Belt + suspenders — explicit REVOKE of writes on public (default already
-- excludes, but prevents accidents if a future migration GRANTs ALL on public)
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON ALL TABLES IN SCHEMA public FROM rigwire_app;

-- Allow EXECUTE on helper functions (compute_location_scope, compute_effective_event_date, etc.)
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO rigwire_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO rigwire_app;

-- ----------------------------------------------------------------------------
-- 4. Grant read access to analytics schema (existing materialised views)
--    NOTE: ALTER DEFAULT PRIVILEGES run by `rig` only fires for tables that
--    `rig` itself creates inside analytics. Since analytics is owned by
--    analytics_user and they create most tables there, future analytics
--    tables WILL NOT auto-grant SELECT to rigwire_app via this line. The
--    Rig Wire chat needs to ask analytics_user to add their own
--    ALTER DEFAULT PRIVILEGES if they want forward-compat access.
-- ----------------------------------------------------------------------------
GRANT USAGE   ON SCHEMA analytics TO rigwire_app;
GRANT SELECT  ON ALL TABLES IN SCHEMA analytics TO rigwire_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA analytics
  GRANT SELECT ON TABLES TO rigwire_app;  -- effective only for rig-created tables

-- ----------------------------------------------------------------------------
-- 5. rigwire_app owns auth/rigwire schemas — no extra grants needed
--    (ownership confers all privileges within their own schemas)
-- ----------------------------------------------------------------------------

COMMIT;

-- ============================================================================
-- VERIFICATION (run as rig, then as rigwire_app)
-- ============================================================================
--
-- As rig:
--   SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole
--     FROM pg_roles WHERE rolname = 'rigwire_app';
--   SELECT nspname, nspowner::regrole FROM pg_namespace
--    WHERE nspname IN ('auth','rigwire');
--
-- As rigwire_app, confirm:
--   - CAN: SELECT * FROM articles LIMIT 1;
--   - CAN: CREATE TABLE auth.users (id uuid PRIMARY KEY, email text);
--   - CAN: CREATE TABLE rigwire.user_prefs (user_id uuid, key text);
--   - CANNOT: INSERT INTO articles VALUES (...);    -- expect permission denied
--   - CANNOT: CREATE TABLE public.foo (id int);    -- expect permission denied
--
-- Test from outside:
--   psql "postgresql://rigwire_app:PASSWORD@178.105.63.154:5433/rig" \
--     -c "SELECT current_user, current_schemas(true);"
--
-- ============================================================================
-- ROLLBACK procedure (DESTRUCTIVE — drops their work!)
-- ============================================================================
--   BEGIN;
--     -- Drop their schemas + everything in them (irreversibly deletes data!)
--     DROP SCHEMA auth    CASCADE;
--     DROP SCHEMA rigwire CASCADE;
--     -- Revoke remaining grants on public/analytics
--     REVOKE ALL ON SCHEMA public, analytics FROM rigwire_app;
--     REVOKE ALL ON ALL TABLES IN SCHEMA public, analytics FROM rigwire_app;
--     DROP ROLE rigwire_app;
--   COMMIT;
-- ============================================================================
