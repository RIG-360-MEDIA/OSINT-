-- ============================================================
-- Migration 042 — breaking_clusters
-- ============================================================
-- Live event detector. A Celery task (tasks.detect_breaking_events)
-- runs HDBSCAN over BGE-M3/LaBSE embeddings of articles published
-- in the last 2 hours. Cluster size >= 4 → write to this table
-- with a Groq-generated headline. Auto-decay flag at 6h.
--
-- Idempotent — safe to re-run.
-- ============================================================

CREATE TABLE IF NOT EXISTS breaking_clusters (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    -- The 2h rolling window the cluster was detected in.
    window_start        TIMESTAMPTZ NOT NULL,
    window_end          TIMESTAMPTZ NOT NULL,
    -- Article IDs in this cluster (the burst).
    member_article_ids  UUID[]      NOT NULL,
    -- Top entities from the cluster (denormalized for fast read).
    top_entities        JSONB       NOT NULL DEFAULT '[]',
    -- One-line LLM-written headline summarizing the burst.
    headline            TEXT        NOT NULL,
    -- Distinct sources reporting (signal of multi-corroboration).
    sources_count       INTEGER     NOT NULL DEFAULT 0,
    -- HDBSCAN cluster strength.
    score               REAL        NOT NULL DEFAULT 0.0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Set true when cluster has cooled (>6h since detection or volume drops).
    is_active           BOOLEAN     NOT NULL DEFAULT TRUE
);

-- Fast lookup of active clusters.
CREATE INDEX IF NOT EXISTS breaking_clusters_active_idx
  ON breaking_clusters (is_active, created_at DESC)
  WHERE is_active = TRUE;

-- Member-id reverse lookup ("which cluster does this article belong to?").
CREATE INDEX IF NOT EXISTS breaking_clusters_members_gin_idx
  ON breaking_clusters USING GIN (member_article_ids);

COMMENT ON TABLE breaking_clusters IS
  'Live BREAKING band on /coverage/articles. HDBSCAN-clustered 2h windows, scored by source diversity.';
