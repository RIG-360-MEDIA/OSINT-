-- ============================================================
-- Migration 045 — user_watchlist + notification_rules + notification_events
-- ============================================================
-- Watchlist: user pins entities, topbar badge counts new mentions
-- since last visit.
--
-- Notification rules: user describes "alert me when X mentioned in
-- Y by tier-1 sources" → Groq parses into structured predicate →
-- a 15-min cron evaluates the predicate against new articles and
-- fires notification_events.
--
-- Idempotent — safe to re-run.
-- ============================================================

CREATE TABLE IF NOT EXISTS user_watchlist (
    user_id             UUID        NOT NULL,
    entity_id           UUID        NOT NULL
                                    REFERENCES entity_dictionary(id) ON DELETE CASCADE,
    pinned_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Last "mark as seen" cursor. New mentions since this timestamp
    -- contribute to the topbar badge.
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, entity_id)
);

CREATE INDEX IF NOT EXISTS user_watchlist_entity_idx
  ON user_watchlist (entity_id);
CREATE INDEX IF NOT EXISTS user_watchlist_user_idx
  ON user_watchlist (user_id);

COMMENT ON TABLE user_watchlist IS
  'Per-user pinned entities. Topbar badge = mentions since last_seen_at.';


-- ── Notification rules (per user) ───────────────────────────
CREATE TABLE IF NOT EXISTS notification_rules (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID        NOT NULL,
    -- Human-readable label (the user's free-text description, untouched).
    label               TEXT        NOT NULL,
    -- Structured predicate parsed by Groq from the label:
    --   { entity_ids: [...], topic: "...", source_tier_min: 1,
    --     keywords: [...], geo: [...] }
    predicate           JSONB       NOT NULL,
    -- Channels the alert fires on: { in_app: true, email: false }
    channels            JSONB       NOT NULL DEFAULT '{"in_app": true}',
    is_active           BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Last time the evaluator scanned this rule. Lets us scope the
    -- next scan to articles ingested since.
    last_evaluated_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS notification_rules_user_active_idx
  ON notification_rules (user_id, is_active);

COMMENT ON TABLE notification_rules IS
  'Per-user rules. 15-min cron evaluates each predicate against fresh articles and writes notification_events on matches.';


-- ── Notification events (one row per fired alert) ───────────
CREATE TABLE IF NOT EXISTS notification_events (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id             UUID        NOT NULL
                                    REFERENCES notification_rules(id) ON DELETE CASCADE,
    user_id             UUID        NOT NULL,
    article_id          UUID        NOT NULL
                                    REFERENCES articles(id) ON DELETE CASCADE,
    fired_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_read             BOOLEAN     NOT NULL DEFAULT FALSE,
    UNIQUE (rule_id, article_id)
);

CREATE INDEX IF NOT EXISTS notification_events_user_unread_idx
  ON notification_events (user_id, fired_at DESC)
  WHERE is_read = FALSE;

COMMENT ON TABLE notification_events IS
  'Fired-alert log. UNIQUE(rule_id, article_id) prevents duplicate fires for re-evaluated articles.';
