-- Sentiment engine v2: two-field, per-entity, perspective-aware.
-- Idempotent; safe to re-run. Apply into the analytics schema.
--
-- Design notes:
--   * One row per (article, entity). "stance" = tone the article takes toward
--     the entity; "impact" = whether the events are good/bad for that entity's
--     interests. These are DIFFERENT questions (see README.md) and are stored
--     as two independent columns, never blurred into one "sentiment".
--   * Ground truth for benchmarking lives in analytics.sentiment_gold, split by
--     verified=true (human-checked GOLD) vs false (model pre-labeled SILVER).
--   * Every audit sample (LLM-judge cross-check) is appended to sentiment_audit.

CREATE SCHEMA IF NOT EXISTS analytics;

-- ---------------------------------------------------------------------------
-- Production output: one row per (article, entity)
-- ---------------------------------------------------------------------------
-- article_id / entity_id are UUIDs (match public.articles.id and
-- public.article_entity_mentions.entity_id). entity = canonical_name.
CREATE TABLE IF NOT EXISTS analytics.article_entity_sentiment (
    article_id       UUID         NOT NULL,
    entity_id        UUID,                          -- from article_entity_mentions
    entity           TEXT         NOT NULL,          -- canonical_name
    stance           TEXT         NOT NULL CHECK (stance IN ('positive','negative','neutral')),
    impact           TEXT         NOT NULL CHECK (impact IN ('positive','negative','neutral','not_relevant')),
    impact_confidence REAL,
    note             TEXT,
    model            TEXT         NOT NULL,          -- e.g. qwen2.5-7b-instruct
    schema_version   SMALLINT     NOT NULL DEFAULT 2,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (article_id, entity)
);
CREATE INDEX IF NOT EXISTS aes_entity_idx ON analytics.article_entity_sentiment (entity);
CREATE INDEX IF NOT EXISTS aes_entity_id_idx ON analytics.article_entity_sentiment (entity_id);
CREATE INDEX IF NOT EXISTS aes_created_idx ON analytics.article_entity_sentiment (created_at);

-- ---------------------------------------------------------------------------
-- Frozen benchmark set. verified=true rows are the regression GOLD.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analytics.sentiment_gold (
    id            BIGSERIAL PRIMARY KEY,
    article_id    UUID,
    entity        TEXT        NOT NULL,
    text_snapshot TEXT        NOT NULL,            -- frozen title+lead used at labeling time
    gold_stance   TEXT        NOT NULL CHECK (gold_stance IN ('positive','negative','neutral')),
    gold_impact   TEXT        CHECK (gold_impact IN ('positive','negative','neutral','not_relevant')),
    verified      BOOLEAN     NOT NULL DEFAULT false,  -- true = human-checked GOLD, false = SILVER
    source        TEXT        NOT NULL DEFAULT 'silver', -- 'human' | 'silver'
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (article_id, entity)
);

-- ---------------------------------------------------------------------------
-- LLM-judge audit trail: a stronger model re-scores a sample of production rows.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analytics.sentiment_audit (
    id             BIGSERIAL PRIMARY KEY,
    article_id     UUID        NOT NULL,
    entity         TEXT        NOT NULL,
    prod_stance    TEXT        NOT NULL,
    prod_impact    TEXT        NOT NULL,
    judge_stance   TEXT        NOT NULL,
    judge_impact   TEXT        NOT NULL,
    judge_model    TEXT        NOT NULL,
    stance_agree   BOOLEAN     NOT NULL,
    impact_agree   BOOLEAN     NOT NULL,
    audited_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS audit_time_idx ON analytics.sentiment_audit (audited_at);

-- ---------------------------------------------------------------------------
-- Backfill work queue — GUARANTEES an article is scored exactly once.
-- Workers claim via UPDATE ... FOR UPDATE SKIP LOCKED, so no two workers (local
-- GPU or cloud) ever grab the same article. Re-running is idempotent: 'done'
-- rows are never re-claimed. A reaper resets stale 'processing' rows.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analytics.sentiment_backfill_queue (
    article_id  UUID        PRIMARY KEY,
    pub_at      TIMESTAMPTZ,                 -- denormalized so claims can order newest-first
    status      TEXT        NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','processing','done','error')),
    worker      TEXT,
    attempts    SMALLINT    NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- partial index keeps the recency-ordered "grab next pending" claim fast even at 700k rows
CREATE INDEX IF NOT EXISTS sbq_claim_idx ON analytics.sentiment_backfill_queue (pub_at DESC)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS sbq_status_idx ON analytics.sentiment_backfill_queue (status);

-- ---------------------------------------------------------------------------
-- Per-run distribution/health monitor (one row per backfill batch or day).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analytics.sentiment_run_stats (
    id            BIGSERIAL PRIMARY KEY,
    node          TEXT,
    n_scored      INT,
    pct_positive  REAL,
    pct_negative  REAL,
    pct_neutral   REAL,
    pct_notrel    REAL,
    parse_ok_pct  REAL,
    art_per_sec   REAL,
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
