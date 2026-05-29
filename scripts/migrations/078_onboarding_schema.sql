-- 078_onboarding_schema.sql
-- Onboarding + personalization plumbing for the OSINT brief product.
-- All tables in the analytics schema (analytics_user has RW per migration 076).
-- Supabase handles authentication (password, email-verify, MFA); we mirror the
-- user identity locally + own everything else (orgs, prefs, invites).
--
-- IDs are UUIDs to match Supabase's auth.users.id naming convention.

BEGIN;

-- ─── orgs ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analytics.orgs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    role_template   TEXT NOT NULL CHECK (role_template IN ('govt','pr','journalist','academic','corporate')),
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS orgs_role_template_idx ON analytics.orgs (role_template);

-- ─── users ──────────────────────────────────────────────────────────────────
-- id matches Supabase auth.users.id (same UUID flows in via the JWT sub claim).
CREATE TABLE IF NOT EXISTS analytics.users (
    id              UUID PRIMARY KEY,
    org_id          UUID REFERENCES analytics.orgs(id) ON DELETE RESTRICT,
    email           TEXT NOT NULL UNIQUE,
    full_name       TEXT,
    designation     TEXT,                  -- "Senior Analyst, Telangana CMO"
    is_super_admin  BOOLEAN NOT NULL DEFAULT FALSE,
    invited_by      UUID REFERENCES analytics.users(id) ON DELETE SET NULL,
    onboarded_at    TIMESTAMPTZ,           -- NULL until they finish the wizard
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS users_org_id_idx ON analytics.users (org_id);
CREATE INDEX IF NOT EXISTS users_super_admin_idx ON analytics.users (is_super_admin) WHERE is_super_admin;

-- ─── user_brief_prefs ───────────────────────────────────────────────────────
-- One row per user. JSONB columns hold the rich pref groups (arrays, nested).
-- See docs/ONBOARDING_SPEC.md for the field-by-field meaning.
CREATE TABLE IF NOT EXISTS analytics.user_brief_prefs (
    user_id               UUID PRIMARY KEY REFERENCES analytics.users(id) ON DELETE CASCADE,
    primary_subject_id    UUID,                  -- entity_dictionary.id, optional
    primary_subject_meta  JSONB,                 -- {name, party, region, relationship}

    -- Step 3: watchlist groups
    watchlist             JSONB NOT NULL DEFAULT '{}'::jsonb,
        -- {"allies":[uuid…], "opposition":[…], "bureaucrats":[…], "civil_society":[…], "auto_adjacents":true}

    -- Step 4: geo scope
    regions               JSONB NOT NULL DEFAULT '{}'::jsonb,
        -- {"primary":"multi-state", "states":["TG","AP"], "districts":["Hyderabad"…], "adjacent":[…], "countries":["IN","US"]}

    -- Step 5: topics
    topics                JSONB NOT NULL DEFAULT '{}'::jsonb,
        -- {"core":["politics","economy"…], "subtopics":{"politics":[…]…}, "deprioritize":[…], "freeform_tags":["mvp"…]}

    -- Step 6: languages
    languages             JSONB NOT NULL DEFAULT '{}'::jsonb,
        -- {"read":["en","te","hi"], "primary":"en", "show_others":"translate"}

    -- Step 7: sources & outlets
    sources               JSONB NOT NULL DEFAULT '{}'::jsonb,
        -- {"trusted":[…], "include":[…], "exclude":[…], "vernacular_pct":40,
        --  "opinion_mix":"mixed", "min_length":300}

    -- Step 8: stance & tone
    stance                JSONB NOT NULL DEFAULT '{}'::jsonb,
        -- {"types":["supportive","neutral","critical"], "tone_toward_subject":"balanced",
        --  "highlight_provocative":false, "llm_synthesis":true}

    -- Step 9: events to track
    events                JSONB NOT NULL DEFAULT '{}'::jsonb,
        -- {"types":["cabinet","press_briefing"…], "confidence":"high", "lookahead_days":7}

    -- Step 10: delivery & notifications (NO editions — single live page)
    delivery              JSONB NOT NULL DEFAULT '{}'::jsonb,
        -- {"email_digest":true, "digest_format":"executive", "digest_time":"06:00",
        --  "send_report_to":[…emails], "timezone":"Asia/Kolkata",
        --  "alerts":{"enabled":true, "threshold":"surge_5", "channels":["email","in_app"]}}

    -- Step 11: brief personality
    personality           JSONB NOT NULL DEFAULT '{}'::jsonb,
        -- {"depth":"5-min", "density":"standard", "voice":"formal-analyst",
        --  "show_citations":true, "show_metadata":true}

    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── invites ────────────────────────────────────────────────────────────────
-- Admin-issued, single-use, time-bound. The token_hash stores SHA-256 of the
-- JWT issued in the email link so the raw JWT never lives in the DB.
CREATE TABLE IF NOT EXISTS analytics.invites (
    token_hash      TEXT PRIMARY KEY,
    email           TEXT NOT NULL,
    org_id          UUID REFERENCES analytics.orgs(id) ON DELETE RESTRICT,
    role_template   TEXT NOT NULL CHECK (role_template IN ('govt','pr','journalist','academic','corporate')),
    invited_by      UUID REFERENCES analytics.users(id) ON DELETE SET NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    consumed_at     TIMESTAMPTZ,
    consumed_by     UUID REFERENCES analytics.users(id) ON DELETE SET NULL,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS invites_email_idx ON analytics.invites (email);
CREATE INDEX IF NOT EXISTS invites_org_id_idx ON analytics.invites (org_id);
CREATE INDEX IF NOT EXISTS invites_active_idx ON analytics.invites (expires_at) WHERE consumed_at IS NULL;

-- ─── updated_at touch trigger (shared) ──────────────────────────────────────
CREATE OR REPLACE FUNCTION analytics.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS orgs_set_updated_at ON analytics.orgs;
CREATE TRIGGER orgs_set_updated_at BEFORE UPDATE ON analytics.orgs
    FOR EACH ROW EXECUTE FUNCTION analytics.set_updated_at();

DROP TRIGGER IF EXISTS users_set_updated_at ON analytics.users;
CREATE TRIGGER users_set_updated_at BEFORE UPDATE ON analytics.users
    FOR EACH ROW EXECUTE FUNCTION analytics.set_updated_at();

DROP TRIGGER IF EXISTS user_brief_prefs_set_updated_at ON analytics.user_brief_prefs;
CREATE TRIGGER user_brief_prefs_set_updated_at BEFORE UPDATE ON analytics.user_brief_prefs
    FOR EACH ROW EXECUTE FUNCTION analytics.set_updated_at();

-- ─── Permissions: analytics_user (osint-backend's role) ────────────────────
-- Migration 076's grants only covered tables that existed at the time. New
-- tables need explicit GRANTs + ALTER DEFAULT PRIVILEGES for future tables.
GRANT SELECT, INSERT, UPDATE, DELETE ON analytics.orgs              TO analytics_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON analytics.users             TO analytics_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON analytics.user_brief_prefs  TO analytics_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON analytics.invites           TO analytics_user;
GRANT EXECUTE ON FUNCTION analytics.set_updated_at()                TO analytics_user;

ALTER DEFAULT PRIVILEGES FOR ROLE rig IN SCHEMA analytics
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES   TO analytics_user;
ALTER DEFAULT PRIVILEGES FOR ROLE rig IN SCHEMA analytics
    GRANT USAGE, SELECT                  ON SEQUENCES TO analytics_user;
ALTER DEFAULT PRIVILEGES FOR ROLE rig IN SCHEMA analytics
    GRANT EXECUTE                        ON FUNCTIONS TO analytics_user;

-- ─── Seed: bootstrap super-admin org + user ─────────────────────────────────
-- Bootstrap entry for the platform's super-admin (pranavsinghpuri09@gmail.com per
-- existing RBAC memory). Real user_id will be backfilled via app code on first
-- login — for now a placeholder NULL-able row so the FK self-ref doesn't block.
INSERT INTO analytics.orgs (name, role_template, notes)
SELECT 'RIG 360 Media (internal)', 'corporate', 'Bootstrap org for platform staff'
WHERE NOT EXISTS (SELECT 1 FROM analytics.orgs WHERE name = 'RIG 360 Media (internal)');

COMMIT;

-- Smoke checks (run manually):
-- \dt analytics.*
-- SELECT * FROM analytics.orgs;
-- SELECT COUNT(*) FROM analytics.invites WHERE consumed_at IS NULL AND expires_at > NOW();
