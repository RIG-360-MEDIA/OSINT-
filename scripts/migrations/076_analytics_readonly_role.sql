-- ============================================================================
-- Migration 076 — read-only analytics role + sandbox schema for sister product
-- ============================================================================
-- Creates a new PostgreSQL role (`analytics_user`) that can:
--   - SELECT from every table in `public` schema (articles, claims, sources,
--     entity_dictionary, etc.) — present AND future via default privileges
--   - CREATE / USE its own schema `analytics` (sandbox)
--   - CREATE TABLE / VIEW / MATERIALIZED VIEW / FUNCTION / INDEX inside
--     `analytics`
--   - Run SELECT against its own schema obviously
--
-- It CANNOT:
--   - INSERT / UPDATE / DELETE / TRUNCATE on `public`
--   - ALTER / DROP / GRANT on `public`
--   - Run migrations
--   - Touch `pg_*` system catalogs in dangerous ways
--   - Create roles
--
-- This means a sister product can build whatever data product it wants on top
-- of our intelligence data without any risk of corrupting the source-of-truth
-- tables.
--
-- BEFORE APPLYING: replace REPLACE_ME_WITH_STRONG_PASSWORD below with a
-- generated password. Suggested: `openssl rand -base64 24` or any
-- 24-character random string. Then copy the password into the kickoff
-- prompt at docs/NEXT_CHAT_NEW_PRODUCT_PROMPT.md (placeholder
-- $ANALYTICS_DB_PASSWORD).
-- ============================================================================

BEGIN;

-- 1. Create the role with login + a password
-- (Make sure to replace the placeholder before running.)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analytics_user') THEN
    CREATE ROLE analytics_user LOGIN PASSWORD 'REPLACE_ME_WITH_STRONG_PASSWORD'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
END
$$;

-- 2. Create the sandbox schema owned by analytics_user
CREATE SCHEMA IF NOT EXISTS analytics AUTHORIZATION analytics_user;

-- 3. Grant SELECT on every existing table in public to analytics_user
GRANT USAGE ON SCHEMA public TO analytics_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analytics_user;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO analytics_user;  -- if any

-- 4. Auto-grant SELECT on FUTURE tables/sequences created in public
--    (so when we add a migration that creates a new table, analytics_user
--     immediately gets SELECT on it without manual GRANT)
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO analytics_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON SEQUENCES TO analytics_user;

-- 5. Explicit REVOKE of write privileges (belt + braces — default in PG
--    already excludes them, but being explicit prevents accidents if a future
--    migration GRANTs ALL on public)
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON ALL TABLES IN SCHEMA public FROM analytics_user;

-- 6. Allow EXECUTE on read-only functions in public (so they can call our
--    helper functions like `compute_location_scope`, `compute_effective_event_date`)
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO analytics_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO analytics_user;

-- 7. Inside their own schema they have all privileges (by ownership)
--    Already granted via OWNERSHIP of the analytics schema in step 2.
--    No additional GRANT needed.

-- 8. Disallow access to other potentially-sensitive schemas if any exist
--    (Adjust this list if you have non-public schemas — e.g. a `private`
--    schema for auth tokens.)
-- REVOKE ALL ON SCHEMA private FROM analytics_user;  -- uncomment if needed

COMMIT;

-- ============================================================================
-- VERIFICATION QUERIES (run after migration)
-- ============================================================================
--
-- As the rig user, confirm the role exists with right capabilities:
--   SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole
--     FROM pg_roles WHERE rolname = 'analytics_user';
--
-- As analytics_user, confirm:
--   - You CAN: SELECT * FROM articles LIMIT 1;
--   - You CAN: CREATE TABLE analytics.my_thing (id int);
--   - You CANNOT: INSERT INTO articles VALUES (...);    -- expect 'permission denied'
--   - You CANNOT: DROP TABLE articles;                  -- expect 'must be owner of table'
--   - You CANNOT: CREATE TABLE public.my_thing (id int);-- expect 'permission denied for schema public'
--
-- Test from outside:
--   psql "postgresql://analytics_user:PASSWORD@178.105.63.154:5433/rig" \
--     -c "SELECT COUNT(*) FROM articles;"
--
-- ============================================================================
-- ROLLBACK procedure (if you ever need to revoke this access)
-- ============================================================================
--   BEGIN;
--     REVOKE ALL ON SCHEMA public FROM analytics_user;
--     REVOKE ALL ON ALL TABLES IN SCHEMA public FROM analytics_user;
--     ALTER DEFAULT PRIVILEGES IN SCHEMA public
--       REVOKE SELECT ON TABLES FROM analytics_user;
--     -- Drop their schema + everything they created (DESTRUCTIVE for their work!)
--     DROP SCHEMA analytics CASCADE;
--     DROP ROLE analytics_user;
--   COMMIT;
-- ============================================================================
