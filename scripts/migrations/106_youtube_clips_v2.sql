-- 106_youtube_clips_v2.sql
-- Greenfield YouTube pipeline (youtube_v2). ONE entity-keyed clips table and a
-- discovery→transcript queue that decouples cheap/safe Hetzner discovery from
-- the residential-only transcript fetch. Idempotent.
--
-- See docs/sessions/youtube-rebuild-kickoff.md and
-- backend/collectors/youtube_v2/.

-- ── Discovery queue ──────────────────────────────────────────────────────────
-- Hetzner RSS discovery writes rows here (status='pending'). A residential
-- worker drains them: fetch transcript → store transcript_json → 'transcribed'
-- (or 'no_transcript'/'failed'). A Hetzner task then extracts clips → 'extracted'.
CREATE TABLE IF NOT EXISTS pending_youtube_videos (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    video_id            TEXT NOT NULL UNIQUE,
    video_title         TEXT NOT NULL,
    channel_id          TEXT NOT NULL,
    channel_name        TEXT NOT NULL,
    video_published_at  TIMESTAMPTZ,
    status              TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','transcribed','extracted','no_transcript','failed')),
    transcript_json     JSONB,            -- segments + language + source (set by worker)
    transcript_language TEXT,
    transcript_source   TEXT,
    attempts            INT NOT NULL DEFAULT 0,
    last_error          TEXT,
    discovered_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    transcribed_at      TIMESTAMPTZ,
    extracted_at        TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pending_yt_status
    ON pending_youtube_videos (status, discovered_at);
CREATE INDEX IF NOT EXISTS idx_pending_yt_channel
    ON pending_youtube_videos (channel_id);

-- ── Clips (entity-keyed, ONE table, no keyword path) ─────────────────────────
CREATE TABLE IF NOT EXISTS youtube_clips_v2 (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    video_id            TEXT NOT NULL,
    video_title         TEXT NOT NULL,
    channel_id          TEXT NOT NULL,
    channel_name        TEXT NOT NULL,
    video_published_at  TIMESTAMPTZ,
    video_url           TEXT NOT NULL,

    -- Real timestamp XOR full-video link: clip_start/end are always real (we
    -- never store metadata-only clips), and embed_url always carries &t=<start>.
    clip_start_seconds  INT NOT NULL CHECK (clip_start_seconds >= 0),
    clip_end_seconds    INT NOT NULL CHECK (clip_end_seconds > clip_start_seconds),
    embed_url           TEXT NOT NULL,

    matched_entity      TEXT NOT NULL,    -- canonical name, validated at insert
    summary             TEXT NOT NULL,    -- English, non-filler, validated at insert
    transcript_segment  TEXT NOT NULL CHECK (length(btrim(transcript_segment)) > 0),
    transcript_language TEXT NOT NULL,
    transcript_source   TEXT NOT NULL
        CHECK (transcript_source IN ('manual_captions','auto_captions')),
    confidence          REAL NOT NULL,
    importance          TEXT NOT NULL DEFAULT 'medium'
        CHECK (importance IN ('high','medium','low')),

    labse_embedding     VECTOR(768),
    relevance_score     REAL,
    processed           BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (video_id, clip_start_seconds, matched_entity)
);

CREATE INDEX IF NOT EXISTS idx_yt_clips_v2_entity
    ON youtube_clips_v2 (matched_entity);
CREATE INDEX IF NOT EXISTS idx_yt_clips_v2_published
    ON youtube_clips_v2 (video_published_at DESC);
CREATE INDEX IF NOT EXISTS idx_yt_clips_v2_video
    ON youtube_clips_v2 (video_id);
CREATE INDEX IF NOT EXISTS idx_yt_clips_v2_embedding
    ON youtube_clips_v2 USING hnsw (labse_embedding vector_cosine_ops)
    WHERE labse_embedding IS NOT NULL;
