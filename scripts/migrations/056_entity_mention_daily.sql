-- 056_entity_mention_daily.sql — T6: per-day entity mention aggregation.
--
-- Populated hourly by backend/tasks/entity_mention_task.py from
-- article_claims.subject_text, article_quotes.speaker_name, and
-- article_stances.actor. Powers /brief trending, watchlist matchers,
-- and per-entity dashboards.

BEGIN;

CREATE TABLE IF NOT EXISTS entity_mention_daily (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_text      text NOT NULL,           -- LOWER()'d for case-insensitive joins
    date             date NOT NULL,           -- collected_at::date bucket
    n_claims         int  NOT NULL DEFAULT 0,
    n_quotes         int  NOT NULL DEFAULT 0,
    n_stances        int  NOT NULL DEFAULT 0,
    n_sources        int  NOT NULL DEFAULT 0,
    -- Stored generated column for fast trending queries
    n_mentions_total int  GENERATED ALWAYS AS (n_claims + n_quotes + n_stances) STORED,
    computed_at      timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT entity_mention_daily_unique UNIQUE (entity_text, date)
);

CREATE INDEX IF NOT EXISTS idx_entity_mention_daily_date_total
  ON entity_mention_daily (date DESC, n_mentions_total DESC);

CREATE INDEX IF NOT EXISTS idx_entity_mention_daily_entity
  ON entity_mention_daily (entity_text);

COMMIT;
