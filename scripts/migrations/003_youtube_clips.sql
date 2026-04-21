-- P14: YouTube Clip Intelligence
-- youtube_channels: monitored channel registry
-- youtube_clips: extracted clip records with transcript + embeddings

CREATE TABLE IF NOT EXISTS youtube_channels (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id       TEXT NOT NULL UNIQUE,
    channel_name     TEXT NOT NULL,
    channel_url      TEXT NOT NULL,
    description      TEXT,
    subscriber_count INTEGER,
    is_active        BOOLEAN DEFAULT TRUE,
    last_checked_at  TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS youtube_clips (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Video metadata
    video_id              TEXT NOT NULL,
    video_title           TEXT NOT NULL,
    channel_id            TEXT NOT NULL,
    channel_name          TEXT NOT NULL,
    video_published_at    TIMESTAMPTZ,
    video_url             TEXT NOT NULL,

    -- Clip window
    clip_start_seconds    INTEGER NOT NULL,
    clip_end_seconds      INTEGER NOT NULL,
    embed_url             TEXT NOT NULL,

    -- Transcript
    transcript_segment    TEXT NOT NULL,
    transcript_language   TEXT DEFAULT 'en',
    transcript_translated TEXT,

    -- Matched entity
    matched_entity        TEXT NOT NULL,
    matched_entity_type   TEXT,

    -- Intelligence
    labse_embedding       vector(768),
    relevance_score       FLOAT,

    -- Metadata
    collected_at          TIMESTAMPTZ DEFAULT NOW(),
    processed             BOOLEAN DEFAULT FALSE,

    UNIQUE (video_id, clip_start_seconds, matched_entity)
);

CREATE INDEX IF NOT EXISTS idx_clips_entity
    ON youtube_clips (matched_entity);

CREATE INDEX IF NOT EXISTS idx_clips_collected
    ON youtube_clips (collected_at DESC);

CREATE INDEX IF NOT EXISTS idx_clips_channel
    ON youtube_clips (channel_id);

CREATE INDEX IF NOT EXISTS idx_clips_processed
    ON youtube_clips (processed, collected_at DESC)
    WHERE processed = TRUE;

CREATE INDEX IF NOT EXISTS idx_clips_embedding
    ON youtube_clips USING hnsw (labse_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE labse_embedding IS NOT NULL;
