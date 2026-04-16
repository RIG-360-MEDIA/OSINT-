-- ============================================================
-- RIG SURVEILLANCE — P01 Initial Schema
-- Migration: 001_initial_schema.sql
-- All column names are FINAL. Do not rename after deployment.
-- ============================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================================
-- TABLE: users
-- Managed by Supabase Auth in production.
-- Created manually for local development.
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT        NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TABLE: user_profiles
-- ============================================================
CREATE TABLE IF NOT EXISTS user_profiles (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID        NOT NULL UNIQUE
                                     REFERENCES users(id) ON DELETE CASCADE,
    raw_description      TEXT        NOT NULL,
    role_type            TEXT        NOT NULL
                                     CHECK (role_type IN (
                                         'government','business','journalist',
                                         'security','other'
                                     )),
    organisation         TEXT,
    geo_primary          TEXT        NOT NULL DEFAULT '',
    geo_secondary        TEXT[]      DEFAULT '{}',
    signal_priorities    JSONB       NOT NULL DEFAULT '{}',
    language_preferences TEXT[]      DEFAULT '{"en"}',
    brief_time           TIME        DEFAULT '06:00:00',
    brief_timezone       TEXT        DEFAULT 'Asia/Kolkata',
    role_context         TEXT        NOT NULL DEFAULT '',
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TABLE: user_entities
-- ============================================================
CREATE TABLE IF NOT EXISTS user_entities (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID        NOT NULL
                               REFERENCES users(id) ON DELETE CASCADE,
    canonical_name TEXT        NOT NULL,
    entity_type    TEXT        NOT NULL
                               CHECK (entity_type IN (
                                   'person','organisation','place',
                                   'scheme','project','topic'
                               )),
    aliases        TEXT[]      DEFAULT '{}',
    why_watching   TEXT,
    priority       INTEGER     DEFAULT 5
                               CHECK (priority BETWEEN 1 AND 10),
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, canonical_name)
);

-- ============================================================
-- TABLE: sources
-- ============================================================
CREATE TABLE IF NOT EXISTS sources (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 TEXT        NOT NULL,
    domain               TEXT        NOT NULL UNIQUE,
    rss_url              TEXT,
    source_type          TEXT        NOT NULL
                                     CHECK (source_type IN (
                                         'rss','scrape','api',
                                         'youtube','govt','social'
                                     )),
    source_tier          INTEGER     NOT NULL DEFAULT 2
                                     CHECK (source_tier BETWEEN 1 AND 3),
    language             TEXT        DEFAULT 'en',
    geo_states           TEXT[]      DEFAULT '{}',
    topics               TEXT[]      DEFAULT '{}',
    health_score         FLOAT       DEFAULT 1.0
                                     CHECK (health_score BETWEEN 0.0 AND 1.0),
    consecutive_failures INTEGER     DEFAULT 0,
    is_active            BOOLEAN     DEFAULT TRUE,
    last_collected_at    TIMESTAMPTZ,
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TABLE: story_threads
-- Must be created BEFORE articles (articles references it)
-- ============================================================
CREATE TABLE IF NOT EXISTS story_threads (
    id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    title              TEXT        NOT NULL,
    primary_entities   TEXT[]      NOT NULL DEFAULT '{}',
    article_count      INTEGER     DEFAULT 0,
    source_count       INTEGER     DEFAULT 0,
    momentum           TEXT        DEFAULT 'stable'
                                   CHECK (momentum IN (
                                       'escalating','stable','fading'
                                   )),
    centroid_embedding VECTOR(768),
    first_seen_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated_at    TIMESTAMPTZ DEFAULT NOW(),
    is_active          BOOLEAN     DEFAULT TRUE
);

-- ============================================================
-- TABLE: articles
-- ============================================================
CREATE TABLE IF NOT EXISTS articles (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id            UUID        NOT NULL
                                     REFERENCES sources(id),
    url                  TEXT        NOT NULL,
    url_hash             TEXT        NOT NULL UNIQUE,
    title                TEXT        NOT NULL,
    lead_text_original   TEXT,
    lead_text_translated TEXT,
    full_text_scraped    TEXT,
    language_detected    VARCHAR(10),
    published_at         TIMESTAMPTZ,
    collected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    nlp_processed        BOOLEAN     DEFAULT FALSE,
    is_duplicate         BOOLEAN     DEFAULT FALSE,
    duplicate_of         UUID        REFERENCES articles(id),
    content_type         TEXT        NOT NULL DEFAULT 'article',
    source_tier          INTEGER,
    thumbnail_url        TEXT,
    author_name          TEXT,
    topic_category       TEXT,
    geo_primary          TEXT,
    geo_secondary        TEXT[]      DEFAULT '{}',
    entities_extracted   JSONB       DEFAULT '[]',
    labse_embedding      VECTOR(768),
    thread_id            UUID        REFERENCES story_threads(id)
);

-- ============================================================
-- TABLE: user_article_relevance
-- ============================================================
CREATE TABLE IF NOT EXISTS user_article_relevance (
    id                      UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID    NOT NULL
                                    REFERENCES users(id) ON DELETE CASCADE,
    article_id              UUID    NOT NULL
                                    REFERENCES articles(id) ON DELETE CASCADE,
    score_stage1            FLOAT   NOT NULL DEFAULT 0.0,
    score_final             FLOAT   NOT NULL DEFAULT 0.0,
    relevance_tier          INTEGER NOT NULL DEFAULT 0
                                    CHECK (relevance_tier BETWEEN 0 AND 3),
    relevance_explanation   TEXT,
    sentiment_for_user      TEXT
                                    CHECK (sentiment_for_user IN (
                                        'FOR_USER','AGAINST_USER','NEUTRAL',NULL
                                    )),
    geo_multiplier_applied  FLOAT,
    matched_entity_names    TEXT[]  DEFAULT '{}',
    scored_at               TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, article_id)
);

-- ============================================================
-- TABLE: velocity_baselines
-- ============================================================
CREATE TABLE IF NOT EXISTS velocity_baselines (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_name       TEXT        NOT NULL,
    baseline_type     TEXT        NOT NULL
                                  CHECK (baseline_type IN (
                                      'entity','topic','geo'
                                  )),
    daily_mean        FLOAT       NOT NULL DEFAULT 0.0,
    daily_stddev      FLOAT       NOT NULL DEFAULT 0.0,
    spike_threshold   FLOAT       NOT NULL DEFAULT 0.0,
    silence_threshold FLOAT       NOT NULL DEFAULT 0.0,
    computed_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(entity_name, baseline_type)
);

-- ============================================================
-- TABLE: alerts
-- ============================================================
CREATE TABLE IF NOT EXISTS alerts (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID        NOT NULL
                               REFERENCES users(id) ON DELETE CASCADE,
    alert_type     TEXT        NOT NULL
                               CHECK (alert_type IN (
                                   'velocity_spike','silence',
                                   'thread_escalating','confidence_high'
                               )),
    entity_name    TEXT,
    headline       TEXT        NOT NULL,
    detail         TEXT,
    confidence     TEXT        NOT NULL DEFAULT 'MEDIUM'
                               CHECK (confidence IN ('HIGH','MEDIUM','LOW')),
    relevance_score FLOAT,
    is_read        BOOLEAN     DEFAULT FALSE,
    triggered_at   TIMESTAMPTZ DEFAULT NOW(),
    expires_at     TIMESTAMPTZ
);

-- ============================================================
-- TABLE: collections
-- ============================================================
CREATE TABLE IF NOT EXISTS collections (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID        NOT NULL
                              REFERENCES users(id) ON DELETE CASCADE,
    name          TEXT        NOT NULL,
    description   TEXT,
    article_count INTEGER     DEFAULT 0,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TABLE: collection_articles
-- ============================================================
CREATE TABLE IF NOT EXISTS collection_articles (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    collection_id UUID        NOT NULL
                              REFERENCES collections(id) ON DELETE CASCADE,
    article_id    UUID        NOT NULL
                              REFERENCES articles(id) ON DELETE CASCADE,
    added_at      TIMESTAMPTZ DEFAULT NOW(),
    note          TEXT,
    UNIQUE(collection_id, article_id)
);

-- ============================================================
-- TABLE: briefs
-- ============================================================
CREATE TABLE IF NOT EXISTS briefs (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID        NOT NULL
                              REFERENCES users(id) ON DELETE CASCADE,
    content       TEXT        NOT NULL,
    brief_date    DATE        NOT NULL,
    generated_at  TIMESTAMPTZ DEFAULT NOW(),
    articles_used INTEGER     DEFAULT 0,
    model_used    TEXT        DEFAULT 'llama-3.3-70b-versatile',
    UNIQUE(user_id, brief_date)
);

-- ============================================================
-- TABLE: analyst_sessions
-- ============================================================
CREATE TABLE IF NOT EXISTS analyst_sessions (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID        NOT NULL
                           REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TABLE: analyst_turns
-- ============================================================
CREATE TABLE IF NOT EXISTS analyst_turns (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id     UUID        NOT NULL
                               REFERENCES analyst_sessions(id) ON DELETE CASCADE,
    question       TEXT        NOT NULL,
    answer         TEXT        NOT NULL,
    evidence_count INTEGER     DEFAULT 0,
    confidence     TEXT
                               CHECK (confidence IN (
                                   'HIGH','MEDIUM','LOW',NULL
                               )),
    retrieval_ms   INTEGER,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TABLE: journalist_profiles
-- ============================================================
CREATE TABLE IF NOT EXISTS journalist_profiles (
    id               UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    author_name      TEXT    NOT NULL,
    entity_name      TEXT    NOT NULL,
    for_count        INTEGER DEFAULT 0,
    against_count    INTEGER DEFAULT 0,
    neutral_count    INTEGER DEFAULT 0,
    bias_indicator   TEXT
                             CHECK (bias_indicator IN (
                                 'consistent_for','consistent_against',
                                 'mixed',NULL
                             )),
    updated_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(author_name, entity_name)
);

-- ============================================================
-- TABLE: entity_dictionary
-- Global reference dictionary — separate from user_entities
-- ============================================================
CREATE TABLE IF NOT EXISTS entity_dictionary (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name TEXT        NOT NULL UNIQUE,
    entity_type    TEXT        NOT NULL,
    aliases        TEXT[]      DEFAULT '{}',
    state          TEXT,
    party          TEXT,
    metadata       JSONB       DEFAULT '{}',
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================

-- NLP pipeline: most critical index
CREATE INDEX IF NOT EXISTS idx_articles_nlp_pending
    ON articles(collected_at DESC)
    WHERE nlp_processed = FALSE;

-- Coverage Room feed
CREATE INDEX IF NOT EXISTS idx_articles_collected
    ON articles(collected_at DESC);

-- Deduplication (url_hash already has UNIQUE — covers this)
CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_url_hash
    ON articles(url_hash);

-- Topic filter
CREATE INDEX IF NOT EXISTS idx_articles_topic
    ON articles(topic_category, collected_at DESC)
    WHERE topic_category IS NOT NULL;

-- Geographic filter
CREATE INDEX IF NOT EXISTS idx_articles_geo
    ON articles(geo_primary)
    WHERE geo_primary IS NOT NULL;

-- Thread lookup
CREATE INDEX IF NOT EXISTS idx_articles_thread
    ON articles(thread_id)
    WHERE thread_id IS NOT NULL;

-- Relevance feed — most used query
CREATE INDEX IF NOT EXISTS idx_uar_user_score
    ON user_article_relevance(user_id, score_final DESC);

-- Tier-filtered feed
CREATE INDEX IF NOT EXISTS idx_uar_user_tier
    ON user_article_relevance(user_id, relevance_tier, score_final DESC);

-- Active threads
CREATE INDEX IF NOT EXISTS idx_threads_active
    ON story_threads(last_updated_at DESC)
    WHERE is_active = TRUE;

-- Unread alerts
CREATE INDEX IF NOT EXISTS idx_alerts_user
    ON alerts(user_id, triggered_at DESC)
    WHERE is_read = FALSE;

-- Brief history
CREATE INDEX IF NOT EXISTS idx_briefs_user_date
    ON briefs(user_id, brief_date DESC);

-- Entity dictionary lookup
CREATE INDEX IF NOT EXISTS idx_entity_dict_name
    ON entity_dictionary(canonical_name);

-- Source lookup by type
CREATE INDEX IF NOT EXISTS idx_sources_active
    ON sources(source_type, is_active)
    WHERE is_active = TRUE;

-- ============================================================
-- NOTE: HNSW index on articles.labse_embedding
-- Created in P06 after NLP pipeline is running:
--
-- CREATE INDEX idx_articles_embedding
--   ON articles USING hnsw
--   (labse_embedding vector_cosine_ops)
--   WITH (m=16, ef_construction=64);
-- ============================================================
