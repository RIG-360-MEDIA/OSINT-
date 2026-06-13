-- 114_cross_pillar_relevance.sql
-- Per-user relevance for clips (youtube_clips_v2) and cuttings (clippings), mirroring
-- user_article_relevance so the Entity page / feed can rank all pillars together (#9).
-- Idempotent.

CREATE TABLE IF NOT EXISTS user_clip_relevance (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               uuid   NOT NULL,
    clip_id               bigint NOT NULL,
    score_stage1          real,
    score_final           real,
    relevance_tier        smallint,
    relevance_explanation text,
    sentiment_for_user    text,
    geo_multiplier_applied real,
    matched_entity_names  text[],
    scored_at             timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, clip_id)
);
CREATE INDEX IF NOT EXISTS idx_ucr_user_tier  ON user_clip_relevance (user_id, relevance_tier);
CREATE INDEX IF NOT EXISTS idx_ucr_user_score ON user_clip_relevance (user_id, score_final DESC);

CREATE TABLE IF NOT EXISTS user_cutting_relevance (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               uuid NOT NULL,
    clipping_id           uuid NOT NULL,
    score_stage1          real,
    score_final           real,
    relevance_tier        smallint,
    relevance_explanation text,
    sentiment_for_user    text,
    geo_multiplier_applied real,
    matched_entity_names  text[],
    scored_at             timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, clipping_id)
);
CREATE INDEX IF NOT EXISTS idx_ucutr_user_tier  ON user_cutting_relevance (user_id, relevance_tier);
CREATE INDEX IF NOT EXISTS idx_ucutr_user_score ON user_cutting_relevance (user_id, score_final DESC);
