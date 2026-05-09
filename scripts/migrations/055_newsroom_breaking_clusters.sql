-- 055_newsroom_breaking_clusters.sql
-- THE NEWSROOM — Phase 1 schema #5 of 7
--
-- Cross-channel breaking-event clusters. Populated every 2 minutes by
-- tasks.newsroom.detect_breaking, which clusters segments from the
-- last 20 minutes by entity overlap + LaBSE cosine similarity, then
-- runs a Cerebras quality gate to set is_real_event + severity.
--
-- A cluster with channel_count ≥ 3 is the candidate threshold; below
-- that it doesn't appear in the WALL "BREAKING" overlay even if
-- is_real_event=TRUE.
--
-- Note: distinct from existing `breaking_clusters` table introduced in
-- migration 042 (Hetzner-only). That serves the /coverage breaking
-- band; this serves the /clips newsroom WALL. Different signal sources,
-- different consumers, kept separate.

CREATE TABLE IF NOT EXISTS newsroom_breaking_clusters (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    headline        TEXT        NOT NULL,
    headline_en     TEXT,
    first_seen_at   TIMESTAMPTZ NOT NULL,
    last_seen_at    TIMESTAMPTZ NOT NULL,
    channel_count   INTEGER     NOT NULL,
    segment_count   INTEGER     NOT NULL,
    is_real_event   BOOLEAN     NOT NULL,                -- Cerebras quality gate
    severity        SMALLINT    NOT NULL CHECK (severity BETWEEN 1 AND 5),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_newsroom_breaking_recent
    ON newsroom_breaking_clusters (last_seen_at DESC)
    WHERE is_real_event = TRUE;

CREATE INDEX IF NOT EXISTS idx_newsroom_breaking_severity
    ON newsroom_breaking_clusters (severity DESC, last_seen_at DESC)
    WHERE is_real_event = TRUE;

COMMENT ON TABLE newsroom_breaking_clusters IS
    'Cross-channel breaking-event clusters for THE NEWSROOM WALL banner. Distinct from coverage `breaking_clusters` (042).';
