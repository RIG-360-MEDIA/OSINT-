-- ============================================================
-- Migration 041 — user_custom_cards + user_card_summaries
-- ============================================================
-- Custom-card system for /coverage/articles. A user creates a
-- "card" to track an entity / topic / scheme; a daily Celery
-- task generates a structured 4-section LLM summary per unique
-- card definition. Multiple users tracking the same definition
-- share one summary row (dedupe by definition_hash).
--
-- Idempotent — safe to re-run.
-- ============================================================

-- ── Per-user card definitions ───────────────────────────────
CREATE TABLE IF NOT EXISTS user_cards (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID        NOT NULL,
    label               TEXT        NOT NULL,
    -- SHA256 of normalized config_json. Multiple users tracking the
    -- same definition share one row in user_card_summaries.
    definition_hash     TEXT        NOT NULL,
    -- Filters that define what this card tracks.
    entity_refs         JSONB       NOT NULL DEFAULT '[]',
    topic_filters       JSONB       NOT NULL DEFAULT '[]',
    geo_filter          JSONB       NOT NULL DEFAULT '[]',
    -- Free-text the user typed when creating the card. Used by the
    -- summary prompt as "user's stated intent" so the chain-of-thought
    -- paragraph reasons against it.
    user_intent         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_refreshed_at   TIMESTAMPTZ,
    -- Hard cap on tracked entities per card.
    CONSTRAINT user_cards_entity_cap_chk
      CHECK (jsonb_array_length(entity_refs) <= 10)
);

CREATE INDEX IF NOT EXISTS user_cards_user_id_idx
  ON user_cards (user_id);
CREATE INDEX IF NOT EXISTS user_cards_definition_hash_idx
  ON user_cards (definition_hash);

COMMENT ON TABLE user_cards IS
  'Per-user custom tracker cards on /coverage/articles. Multiple users with the same definition_hash share one summary row.';


-- ── Shared LLM-generated summaries (one row per unique definition) ──
CREATE TABLE IF NOT EXISTS user_card_summaries (
    definition_hash     TEXT        PRIMARY KEY,
    -- Structured 4-section summary as JSONB:
    --   { state: "...", whats_new: ["...", "..."],
    --     why_matters: "...", watch_for: ["...", "..."] }
    sections            JSONB       NOT NULL,
    -- Article IDs that fed this summary, ordered by relevance.
    citations           JSONB       NOT NULL DEFAULT '[]',
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    generated_by_model  TEXT        NOT NULL DEFAULT 'llama-3.1-8b-instant',
    sample_size         INTEGER     NOT NULL DEFAULT 0
);

COMMENT ON TABLE user_card_summaries IS
  'LLM-cached 4-section card summary, keyed by definition_hash so multiple users share one row.';
