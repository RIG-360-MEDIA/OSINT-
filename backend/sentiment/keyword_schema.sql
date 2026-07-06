-- On-demand keyword sentiment (Scenario 2): the keyword is NOT a precomputed
-- entity, so there is no row in article_entity_sentiment. We find its mentions
-- by full-text search over a recent window, live-score each article against the
-- keyword with the two-field scorer, aggregate, and CACHE the result here so the
-- second identical (keyword, window) call is instant.
--
-- Idempotent; safe to re-run. Apply into the analytics schema.

CREATE SCHEMA IF NOT EXISTS analytics;

-- ---------------------------------------------------------------------------
-- Cached aggregate: one row per (normalized keyword, window length).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analytics.keyword_sentiment_cache (
    keyword_norm   TEXT        NOT NULL,          -- lower(trim(keyword))
    window_days    INT         NOT NULL,
    n_matched      INT         NOT NULL,          -- FTS matches in window (before cap)
    n_scored       INT         NOT NULL,          -- articles actually scored (<= cap)
    capped         BOOLEAN     NOT NULL DEFAULT false,  -- true => n_matched > cap, tail not scored
    stance_pos     INT         NOT NULL DEFAULT 0,
    stance_neg     INT         NOT NULL DEFAULT 0,
    stance_neu     INT         NOT NULL DEFAULT 0,
    impact_pos     INT         NOT NULL DEFAULT 0,
    impact_neg     INT         NOT NULL DEFAULT 0,
    impact_neu     INT         NOT NULL DEFAULT 0,
    impact_nr      INT         NOT NULL DEFAULT 0,  -- not_relevant
    stance_score   REAL,                            -- (pos-neg)/n_scored, range -1..1
    impact_score   REAL,
    model          TEXT        NOT NULL,
    source         TEXT        NOT NULL DEFAULT 'ondemand',  -- ondemand | precomputed | mixed
    computed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (keyword_norm, window_days)
);
CREATE INDEX IF NOT EXISTS ksc_computed_idx ON analytics.keyword_sentiment_cache (computed_at);

-- ---------------------------------------------------------------------------
-- Per-article hits backing a cached keyword result (drill-down + audit).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analytics.keyword_sentiment_hits (
    keyword_norm      TEXT        NOT NULL,
    window_days       INT         NOT NULL,
    article_id        UUID        NOT NULL,
    stance            TEXT        NOT NULL CHECK (stance IN ('positive','negative','neutral')),
    impact            TEXT        NOT NULL CHECK (impact IN ('positive','negative','neutral','not_relevant')),
    impact_confidence REAL,
    published_at      TIMESTAMPTZ,
    model             TEXT,
    scored_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (keyword_norm, window_days, article_id)
);
CREATE INDEX IF NOT EXISTS ksh_kw_idx ON analytics.keyword_sentiment_hits (keyword_norm, window_days);

-- ---------------------------------------------------------------------------
-- Discovery substrate: a trigram GIN index on the concatenated title+lead makes
-- arbitrary-keyword ILIKE search fast (the `fts` column is name-weighted and
-- misses common-noun keywords, which is exactly the Scenario-2 case). The
-- expression MUST stay byte-identical to _TITLELEAD in keyword_sentiment.py.
-- Requires the pg_trgm extension. On a populated DB build it out-of-band with
-- CONCURRENTLY so it does not lock writes (cannot run in a txn):
--
--   CREATE INDEX CONCURRENTLY IF NOT EXISTS articles_titlelead_trgm_idx
--     ON public.articles USING gin (
--       (coalesce(title,'') || ' ' || coalesce(lead_text_original,'') || ' '
--        || coalesce(lead_text_translated,'')) gin_trgm_ops);
--
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;
