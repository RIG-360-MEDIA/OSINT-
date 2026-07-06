-- 121_keyword_tracking.sql
-- Keyword tracking + alerts for the Keyword-Intelligence product (Phase 5).
-- notification_rules/notification_events do NOT exist (verified 2026-07-06); build fresh.
-- Tables live in the `analytics` schema so the read-only night-desk API (analytics_user,
-- RW on analytics.*) can write them. Additive/safe — no impact on existing data.

CREATE TABLE IF NOT EXISTS analytics.keyword_watch (
    id              BIGSERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL,
    keyword         TEXT NOT NULL,
    classification  JSONB,                 -- Tasking-brain output at track time
    perspective     TEXT,
    days            INT  DEFAULT 7,
    cadence_minutes INT  DEFAULT 60,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT now(),
    last_checked_at TIMESTAMPTZ,
    UNIQUE (user_id, keyword)
);

CREATE TABLE IF NOT EXISTS analytics.keyword_alerts (
    id         BIGSERIAL PRIMARY KEY,
    watch_id   BIGINT REFERENCES analytics.keyword_watch(id) ON DELETE CASCADE,
    alert_type TEXT NOT NULL,              -- spike | sentiment_flip | new_harmful_actor | new_narrative
    payload    JSONB,                      -- {metric, before, after, evidence...}
    fired_at   TIMESTAMPTZ DEFAULT now(),
    seen_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_keyword_watch_user
    ON analytics.keyword_watch (user_id) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_keyword_watch_due
    ON analytics.keyword_watch (last_checked_at) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_keyword_alerts_watch
    ON analytics.keyword_alerts (watch_id, fired_at DESC);

-- The night-desk API connects as analytics_user; grant it access.
GRANT SELECT, INSERT, UPDATE, DELETE ON analytics.keyword_watch, analytics.keyword_alerts
    TO analytics_user;
GRANT USAGE, SELECT ON SEQUENCE analytics.keyword_watch_id_seq,
    analytics.keyword_alerts_id_seq TO analytics_user;
