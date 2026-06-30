-- 118_social_substrate.sql
-- ============================================================================
-- Social intelligence data layer (Twitter / Reddit / Telegram / Instagram).
--
-- A future-proof ATOMIC layer: "extract once, capture maximally, derive forever."
-- Built to the proven RIG substrate pattern (articles / clippings / youtube), plus
-- the social-only primitives (authors, communities, engagement-over-time, edges)
-- that CANNOT be retrofitted later.
--
-- Design + decisions: docs/design/social-data-layer-and-backlog.md
--                     docs/design/social-pipeline-design.md
--
-- Idempotent: safe to re-run (IF NOT EXISTS throughout). pgvector required.
-- Extraction routes to CLOUD (Cerebras primary / Groq overflow); embeddings local.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ── A. AUTHORS — the account as a first-class entity (the WHO) ───────────────
CREATE TABLE IF NOT EXISTS social_authors (
    id                  BIGSERIAL PRIMARY KEY,
    platform            VARCHAR(16) NOT NULL,           -- twitter|reddit|telegram|instagram
    platform_user_id    TEXT,                           -- platform's native id (may be null early)
    username            TEXT NOT NULL,
    display_name        TEXT,
    bio                 TEXT,
    verified            BOOLEAN,
    account_created_at  TIMESTAMPTZ,
    followers           BIGINT,
    following           BIGINT,
    post_count          BIGINT,
    -- derived slots (filled later; nullable so features become a query, not a migration)
    influence_score     REAL,
    bot_likelihood      REAL,
    cadence_mean_sec    REAL,                           -- posting-rhythm mean (bot signal)
    cadence_cv          REAL,                           -- coefficient of variation (too-regular = bot)
    source_reliability  REAL,                           -- credibility slot
    home_geo            TEXT,
    home_state          TEXT,
    language            VARCHAR(8),
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw                 JSONB,
    UNIQUE (platform, platform_user_id)
);
CREATE INDEX IF NOT EXISTS idx_social_authors_username ON social_authors (platform, lower(username));
CREATE INDEX IF NOT EXISTS idx_social_authors_influence ON social_authors (influence_score DESC NULLS LAST);

-- author metrics over time (append-only) — follower velocity, rising-account detection
CREATE TABLE IF NOT EXISTS social_author_snapshots (
    id          BIGSERIAL PRIMARY KEY,
    author_id   BIGINT NOT NULL REFERENCES social_authors(id) ON DELETE CASCADE,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    followers   BIGINT,
    following   BIGINT,
    post_count  BIGINT
);
CREATE INDEX IF NOT EXISTS idx_social_author_snap ON social_author_snapshots (author_id, captured_at DESC);

-- ── B. COMMUNITIES — subreddit / channel (the WHERE) ────────────────────────
CREATE TABLE IF NOT EXISTS social_communities (
    id            BIGSERIAL PRIMARY KEY,
    platform      VARCHAR(16) NOT NULL,                 -- reddit|telegram (twitter/ig leave null)
    community_uid TEXT NOT NULL,                        -- subreddit name / channel id
    name          TEXT NOT NULL,
    ctype         VARCHAR(16),                          -- subreddit|channel|group
    subscribers   BIGINT,
    description   TEXT,
    language      VARCHAR(8),
    verified      BOOLEAN,
    is_fringe     BOOLEAN,                              -- derived slot
    credibility   REAL,                                 -- derived slot
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw           JSONB,
    UNIQUE (platform, community_uid)
);
CREATE INDEX IF NOT EXISTS idx_social_communities_name ON social_communities (platform, lower(name));

CREATE TABLE IF NOT EXISTS social_community_snapshots (
    id           BIGSERIAL PRIMARY KEY,
    community_id BIGINT NOT NULL REFERENCES social_communities(id) ON DELETE CASCADE,
    captured_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    subscribers  BIGINT
);
CREATE INDEX IF NOT EXISTS idx_social_comm_snap ON social_community_snapshots (community_id, captured_at DESC);

-- ── C. POSTS — the atomic post (the WHAT) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS social_posts (
    id                  BIGSERIAL PRIMARY KEY,
    platform            VARCHAR(16) NOT NULL,
    platform_post_id    TEXT NOT NULL,
    author_id           BIGINT REFERENCES social_authors(id) ON DELETE SET NULL,
    community_id        BIGINT REFERENCES social_communities(id) ON DELETE SET NULL,

    -- content: RAW (verbatim) + cleaned (markdown/emoji stripped, for display)
    post_text           TEXT,
    text_clean          TEXT,
    post_url            TEXT,

    -- posting time: canonical UTC (source of truth) + IST for convenience.
    -- posted_at is timestamptz so any timezone is a trivial query-time cast
    -- (posted_at AT TIME ZONE 'Asia/Kolkata'); posted_at_ist is materialised by
    -- ingest for cheap IST display/sort. (Not GENERATED: tz cast is not IMMUTABLE.)
    posted_at           TIMESTAMPTZ,
    posted_at_ist       TIMESTAMP,

    -- engagement (point-in-time); platform-specific cols left null when absent
    likes               BIGINT,
    comments_count      BIGINT,
    shares              BIGINT,     -- retweets / forwards
    upvotes             BIGINT,     -- reddit
    views               BIGINT,     -- telegram / video (promoted out of raw)
    upvote_ratio        REAL,       -- reddit controversy gauge (promoted out of raw)

    -- thread / network structure (capture-now)
    in_reply_to_post_id BIGINT,
    quoted_post_id      BIGINT,
    conversation_root_id BIGINT,
    thread_depth        INT DEFAULT 0,
    forwarded_from      TEXT,                           -- telegram/retweet origin
    is_retweet          BOOLEAN DEFAULT FALSE,          -- skip-extraction flag
    is_reply            BOOLEAN DEFAULT FALSE,

    -- geo / lang / media
    lang                VARCHAR(8),
    language_confidence REAL,
    geo_inferred        TEXT,
    geo_state           TEXT,
    has_media           BOOLEAN DEFAULT FALSE,
    media_type          VARCHAR(16),                    -- photo|video|carousel|audio|none
    media_urls          JSONB,                          -- captured now; analysis is a later layer

    -- provenance / lifecycle of the row
    watchlist_id        BIGINT,
    is_deleted          BOOLEAN DEFAULT FALSE,
    deleted_at          TIMESTAMPTZ,
    edit_history        JSONB,
    raw                 JSONB,                          -- full platform payload (forward-compat)

    -- substrate (EXTRACT-ONCE superset; from GROQ_SYS_SOCIAL)
    summary             TEXT,                           -- long posts only
    sentiment           VARCHAR(12),                    -- positive|negative|neutral|mixed
    sentiment_score     REAL,                           -- -1..1
    emotion             VARCHAR(16),
    topic_category      TEXT,
    primary_subject     TEXT,
    toxicity            REAL,
    weaponization_signals JSONB,                        -- raw signals for NWS later
    entities_extracted  JSONB,
    labse_embedding     vector(768),                    -- local GPU; reliable
    extraction_tier     VARCHAR(8) DEFAULT 'full',      -- full|light|deeper
    extraction_confidence REAL,
    substrate_status    VARCHAR(16) NOT NULL DEFAULT 'pending', -- pending|processing|ok|extract_failed|junk
    extraction_version  INT DEFAULT 0,

    -- derived slots (nullable; CIB / narrative features become a query later)
    narrative_id        TEXT,
    coordination_cluster_id TEXT,

    collected_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    enriched_at         TIMESTAMPTZ,
    UNIQUE (platform, platform_post_id)
);
CREATE INDEX IF NOT EXISTS idx_social_posts_status   ON social_posts (substrate_status, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_social_posts_posted   ON social_posts (posted_at DESC);
CREATE INDEX IF NOT EXISTS idx_social_posts_author   ON social_posts (author_id);
CREATE INDEX IF NOT EXISTS idx_social_posts_community ON social_posts (community_id);
CREATE INDEX IF NOT EXISTS idx_social_posts_platform ON social_posts (platform, posted_at DESC);
CREATE INDEX IF NOT EXISTS idx_social_posts_sentiment ON social_posts (sentiment);
CREATE INDEX IF NOT EXISTS idx_social_posts_reply    ON social_posts (in_reply_to_post_id);
CREATE INDEX IF NOT EXISTS idx_social_posts_root     ON social_posts (conversation_root_id);

-- ── D. ENGAGEMENT TIME-SERIES (append-only) — CANNOT RETROFIT ───────────────
-- snapshots at T+1h/6h/24h on active posts -> velocity, virality, breakout
CREATE TABLE IF NOT EXISTS social_post_metrics (
    id          BIGSERIAL PRIMARY KEY,
    post_id     BIGINT NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    likes       BIGINT,
    comments    BIGINT,
    shares      BIGINT,
    upvotes     BIGINT,
    views       BIGINT
);
CREATE INDEX IF NOT EXISTS idx_social_post_metrics ON social_post_metrics (post_id, captured_at DESC);

-- ── E. NETWORK GRAPH (capture-now) — CANNOT RETROFIT ────────────────────────
CREATE TABLE IF NOT EXISTS social_edges (
    id            BIGSERIAL PRIMARY KEY,
    src_author_id BIGINT REFERENCES social_authors(id) ON DELETE CASCADE,
    dst_author_id BIGINT REFERENCES social_authors(id) ON DELETE CASCADE,
    edge_type     VARCHAR(12) NOT NULL,                 -- reply|mention|quote|retweet|forward
    post_id       BIGINT REFERENCES social_posts(id) ON DELETE CASCADE,
    weight        REAL DEFAULT 1.0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_social_edges_src ON social_edges (src_author_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_social_edges_dst ON social_edges (dst_author_id, edge_type);

-- ── F. SUBSTRATE CHILD TABLES (per-post 1:N, cascade) ───────────────────────
CREATE TABLE IF NOT EXISTS social_post_claims (
    id              BIGSERIAL PRIMARY KEY,
    post_id         BIGINT NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
    claim_text      TEXT NOT NULL,
    claim_text_en   TEXT,                               -- English translation (Hindi/regional fix)
    subject_text    TEXT,
    subject_entity_id UUID,
    predicate       TEXT,
    object_text     TEXT,
    confidence      REAL,
    claim_embedding vector(768),                        -- corroboration / mutation / counter-narrative
    claim_fingerprint TEXT                              -- near-dup / astroturf clustering
);
CREATE INDEX IF NOT EXISTS idx_social_claims_post ON social_post_claims (post_id);
CREATE INDEX IF NOT EXISTS idx_social_claims_fp   ON social_post_claims (claim_fingerprint);

CREATE TABLE IF NOT EXISTS social_post_quotes (
    id           BIGSERIAL PRIMARY KEY,
    post_id      BIGINT NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
    speaker_name TEXT,
    speaker_entity_id UUID,
    quote_text   TEXT NOT NULL,
    quote_text_en TEXT,
    is_direct    BOOLEAN
);
CREATE INDEX IF NOT EXISTS idx_social_quotes_post ON social_post_quotes (post_id);

-- directed sentiment; ALL stances kept, weighted by intensity (no cap)
CREATE TABLE IF NOT EXISTS social_post_stances (
    id              BIGSERIAL PRIMARY KEY,
    post_id         BIGINT NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
    actor           TEXT,                               -- real account handle, not "author"
    actor_entity_id UUID,
    target          TEXT,
    target_entity_id UUID,
    stance          VARCHAR(16),                        -- supports|opposes|criticises|praises|neutral
    intensity       REAL                                -- 0..1 (weak drive-by vs focused attack)
);
CREATE INDEX IF NOT EXISTS idx_social_stances_post   ON social_post_stances (post_id);
CREATE INDEX IF NOT EXISTS idx_social_stances_target ON social_post_stances (target_entity_id);

CREATE TABLE IF NOT EXISTS social_post_locations (
    id            BIGSERIAL PRIMARY KEY,
    post_id       BIGINT NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
    location_text TEXT,
    country       TEXT,
    region        TEXT,
    city          TEXT,
    lat           DOUBLE PRECISION,
    lng           DOUBLE PRECISION,
    is_primary    BOOLEAN DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_social_locations_post ON social_post_locations (post_id);

CREATE TABLE IF NOT EXISTS social_post_hashtags (
    id      BIGSERIAL PRIMARY KEY,
    post_id BIGINT NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
    tag     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_social_hashtags_tag  ON social_post_hashtags (lower(tag));
CREATE INDEX IF NOT EXISTS idx_social_hashtags_post ON social_post_hashtags (post_id);

CREATE TABLE IF NOT EXISTS social_post_mentions (
    id                 BIGSERIAL PRIMARY KEY,
    post_id            BIGINT NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
    mentioned_username TEXT NOT NULL,
    mentioned_author_id BIGINT REFERENCES social_authors(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_social_mentions_post ON social_post_mentions (post_id);
CREATE INDEX IF NOT EXISTS idx_social_mentions_user ON social_post_mentions (lower(mentioned_username));

-- events / dates mentioned IN text (resolved relative to posted_at; fuzzy = low confidence)
CREATE TABLE IF NOT EXISTS social_post_events (
    id             BIGSERIAL PRIMARY KEY,
    post_id        BIGINT NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
    event_text     TEXT,
    mention_raw    TEXT,                                -- "tomorrow 4pm" as written
    resolved_at    TIMESTAMPTZ,                         -- best-effort resolution
    date_confidence REAL,                               -- LLM date math is approximate; guard on this
    is_future      BOOLEAN
);
CREATE INDEX IF NOT EXISTS idx_social_events_post ON social_post_events (post_id);
CREATE INDEX IF NOT EXISTS idx_social_events_when ON social_post_events (resolved_at);

-- ── G. WATCHLIST — what we scrape (standing corpus + demand) ─────────────────
-- scheduling columns (priority/next_check_at/avg_activity) make adaptive polling
-- a drop-in later with NO schema change.
CREATE TABLE IF NOT EXISTS social_watchlist (
    id            BIGSERIAL PRIMARY KEY,
    platform      VARCHAR(16) NOT NULL,
    target_type   VARCHAR(16) NOT NULL,                 -- handle|subreddit|channel|hashtag|keyword|location
    target_value  TEXT NOT NULL,
    label         TEXT,
    source        VARCHAR(12) DEFAULT 'corpus',         -- corpus|trending|demand
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    fetch_limit   INT DEFAULT 25,
    priority      INT DEFAULT 5,                         -- 1=hot ... 9=cold (adaptive scheduling)
    next_check_at TIMESTAMPTZ DEFAULT now(),
    avg_activity  REAL,                                  -- learned posting rate (auto-tune cadence)
    last_seen_id  TEXT,                                  -- incremental cursor (reddit after / tg min_id / tweet id)
    last_run_at   TIMESTAMPTZ,
    added_by_user BIGINT,                                -- null = standing corpus
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (platform, target_type, target_value)
);
CREATE INDEX IF NOT EXISTS idx_social_watchlist_due ON social_watchlist (is_active, priority, next_check_at);

-- ── H. PERSONALIZATION LAYER (append-only signals) ──────────────────────────
CREATE TABLE IF NOT EXISTS social_user_watchlists (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT NOT NULL,
    target_type  VARCHAR(16) NOT NULL,
    target_value TEXT NOT NULL,
    params       JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, target_type, target_value)
);
CREATE INDEX IF NOT EXISTS idx_social_user_wl ON social_user_watchlists (user_id);

CREATE TABLE IF NOT EXISTS social_user_events (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL,
    event_type VARCHAR(16) NOT NULL,                    -- view|click|dwell|share|save
    post_id    BIGINT,
    entity_id  UUID,
    dwell_ms   INT,
    ts         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_social_user_events ON social_user_events (user_id, ts DESC);

CREATE TABLE IF NOT EXISTS social_user_prefs (
    user_id            BIGINT PRIMARY KEY,
    notification_rules JSONB,
    brief_length       VARCHAR(8),                       -- learned: short|long
    channels           JSONB,                            -- email|telegram|whatsapp|push
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── I. ENTITY RESOLUTION MATVIEW ────────────────────────────────────────────
-- Mirrors article_entity_mentions / clipping_entity_mentions: unrolls
-- social_posts.entities_extracted -> entity_lookup.name_norm -> entity_dictionary.
-- (Transliteration-aware via entity_lookup variants.) Refresh via cron.
-- NOTE: column names follow the existing entity_lookup/entity_dictionary pattern;
-- verify against live schema before first refresh.
CREATE MATERIALIZED VIEW IF NOT EXISTS social_post_entity_mentions AS
SELECT
    sp.id                                   AS post_id,
    sp.platform                             AS platform,
    ed.id                                   AS entity_id,
    ed.canonical_name                       AS canonical_name,
    ed.entity_type                          AS entity_type,
    ed.country                              AS country,
    elem.value ->> 'name'                   AS surface_form,
    sp.posted_at                            AS posted_at
FROM social_posts sp
CROSS JOIN LATERAL jsonb_array_elements(
    CASE WHEN jsonb_typeof(sp.entities_extracted) = 'array'
         THEN sp.entities_extracted ELSE '[]'::jsonb END
) AS elem
JOIN entity_lookup el
    ON el.name_norm = lower(trim(elem.value ->> 'name'))
JOIN entity_dictionary ed
    ON ed.id = el.entity_id
WHERE sp.substrate_status = 'ok'
WITH NO DATA;
CREATE INDEX IF NOT EXISTS idx_social_pem_entity ON social_post_entity_mentions (entity_id, posted_at DESC);
CREATE INDEX IF NOT EXISTS idx_social_pem_post   ON social_post_entity_mentions (post_id);

-- ── J. GRANTS (conditional on analytics_user existing) ──────────────────────
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analytics_user') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO analytics_user;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO analytics_user;
        GRANT SELECT ON social_post_entity_mentions TO analytics_user;
    END IF;
END $$;

-- ============================================================================
-- DONE. Collectors (twitter/reddit/telegram/instagram _scraper.py) land posts
-- here as substrate_status='pending'; a drain task runs GROQ_SYS_SOCIAL (cloud:
-- Cerebras primary / Groq overflow) -> writes substrate cols + child tables.
-- Media URLs captured; media ANALYSIS (vision/audio) is a later layer on URLs
-- already stored — no schema change required when added.
-- ============================================================================
