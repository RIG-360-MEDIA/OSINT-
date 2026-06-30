-- 117_api_gateway.sql
--
-- Client API gateway: per-org API keys, provisioned data scope, usage
-- metering, and webhook subscriptions. Powers the read-only /v1 API that
-- external clients use to pull their own slice of intelligence.
--
-- Every table lives in analytics.* (the only schema the read-path
-- analytics_user role may write). All statements are idempotent — safe to
-- re-run. Raw API keys are NEVER stored; only an HMAC hash, so a database
-- dump cannot recover a usable key.

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()
CREATE SCHEMA IF NOT EXISTS analytics;

-- ── API keys ────────────────────────────────────────────────────────────
-- One row per issued key. key_hash = HMAC-SHA256(OSINT_APIKEY_HASH_SECRET,
-- raw_key) in hex; key_prefix is a non-secret display fragment for support.
CREATE TABLE IF NOT EXISTS analytics.api_keys (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              uuid NOT NULL REFERENCES analytics.orgs(id) ON DELETE CASCADE,
    key_hash            text NOT NULL UNIQUE,
    key_prefix          text NOT NULL DEFAULT '',
    label               text NOT NULL DEFAULT '',
    is_sandbox          boolean NOT NULL DEFAULT false,
    rate_limit_per_min  integer NOT NULL DEFAULT 120,
    monthly_quota       integer,                       -- NULL = unlimited
    created_at          timestamptz NOT NULL DEFAULT now(),
    created_by          uuid,
    last_used_at        timestamptz,
    expires_at          timestamptz,                   -- NULL = no expiry
    revoked_at          timestamptz                    -- non-NULL = disabled
);
CREATE INDEX IF NOT EXISTS api_keys_org_idx ON analytics.api_keys(org_id);

-- ── Provisioned scope ───────────────────────────────────────────────────
-- The agreed slice an org's keys may read. An absent row or empty arrays
-- mean NO data (fail-safe). all_entities=true deliberately grants the whole
-- corpus (rare). Topics/regions/languages further constrain coverage.
CREATE TABLE IF NOT EXISTS analytics.org_api_scope (
    org_id          uuid PRIMARY KEY REFERENCES analytics.orgs(id) ON DELETE CASCADE,
    all_entities    boolean NOT NULL DEFAULT false,
    entity_ids      uuid[]  NOT NULL DEFAULT '{}',
    topics          text[]  NOT NULL DEFAULT '{}',
    regions         text[]  NOT NULL DEFAULT '{}',
    languages       text[]  NOT NULL DEFAULT '{}',
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- ── Usage metering ──────────────────────────────────────────────────────
-- One row per /v1 request, written fire-and-forget (never on the critical
-- path). Drives billing and the "what do clients value" analytics. Never
-- stores secrets — only safe query params.
CREATE TABLE IF NOT EXISTS analytics.api_usage_events (
    id           bigserial PRIMARY KEY,
    org_id       uuid,
    key_id       uuid,
    ts           timestamptz NOT NULL DEFAULT now(),
    method       text,
    endpoint     text,
    status_code  integer,
    result_count integer,
    latency_ms   integer,
    ip           inet,
    user_agent   text,
    params       jsonb
);
CREATE INDEX IF NOT EXISTS api_usage_org_ts_idx ON analytics.api_usage_events(org_id, ts DESC);
CREATE INDEX IF NOT EXISTS api_usage_key_ts_idx ON analytics.api_usage_events(key_id, ts DESC);

-- ── Monthly quota counter ───────────────────────────────────────────────
-- Cheap rollup so a per-request quota check is an O(1) upsert+read instead
-- of a COUNT over api_usage_events. period = 'YYYY-MM' (UTC).
CREATE TABLE IF NOT EXISTS analytics.api_usage_counters (
    key_id        uuid NOT NULL,
    period        text NOT NULL,
    request_count bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (key_id, period)
);

-- ── Webhooks ────────────────────────────────────────────────────────────
-- Push subscriptions. secret signs each delivery (HMAC) so the receiver can
-- verify authenticity. filter is the same scoped filter language as /v1.
CREATE TABLE IF NOT EXISTS analytics.api_webhooks (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            uuid NOT NULL REFERENCES analytics.orgs(id) ON DELETE CASCADE,
    url               text NOT NULL,
    secret            text NOT NULL,
    filter            jsonb NOT NULL DEFAULT '{}',
    is_active         boolean NOT NULL DEFAULT true,
    created_at        timestamptz NOT NULL DEFAULT now(),
    last_delivered_at timestamptz,
    failure_count     integer NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS api_webhooks_org_idx ON analytics.api_webhooks(org_id);

-- ── Runtime grants ──────────────────────────────────────────────────────
-- The API process connects as analytics_user; it needs RW on the gateway
-- tables (all in analytics.*). Guarded so envs without the role don't error.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analytics_user') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON
            analytics.api_keys,
            analytics.org_api_scope,
            analytics.api_usage_events,
            analytics.api_usage_counters,
            analytics.api_webhooks
        TO analytics_user;
        GRANT USAGE, SELECT ON SEQUENCE analytics.api_usage_events_id_seq TO analytics_user;
    END IF;
END $$;
