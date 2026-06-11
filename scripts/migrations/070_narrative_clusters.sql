-- Migration 070 — narrative clusters (Stage 0 output)
--
-- A cluster is a set of recent articles that LaBSE-cluster together at
-- cosine sim >= 0.78. Each cluster is a candidate "story" that downstream
-- stages (frame router, triangulation, lede/body/critic/revision) operate on.
--
-- Lifecycle: clusters are RECOMPUTED on every Stage 0 run (typically every
-- 1-3 hours). Old clusters are not deleted — they're soft-archived via
-- `superseded_at` once a re-run produces an overlapping set.

BEGIN;

CREATE TABLE IF NOT EXISTS narrative_clusters (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    superseded_at       TIMESTAMPTZ,
    lookback_hours      INT  NOT NULL,
    avg_internal_sim    FLOAT4 NOT NULL,
    member_count        INT  NOT NULL,
    -- Frame is populated by Stage 1 (frame router). NULL means not yet routed.
    narrative_frame     TEXT,
    -- Seed article: the most-collected-recent member, useful for previews.
    seed_article_id     UUID REFERENCES articles(id) ON DELETE SET NULL,
    -- Stage 2 output (one of "triangulated", "interrogated", "abandoned")
    pass_status         TEXT,
    -- Stage 6 output (the final draft) — pointer kept here for fast lookup.
    final_draft_id      UUID,
    CONSTRAINT narrative_clusters_member_count_chk CHECK (member_count >= 2),
    CONSTRAINT narrative_clusters_sim_chk         CHECK (avg_internal_sim BETWEEN 0 AND 1)
);

CREATE INDEX IF NOT EXISTS narrative_clusters_created_idx
    ON narrative_clusters (created_at DESC);
CREATE INDEX IF NOT EXISTS narrative_clusters_frame_idx
    ON narrative_clusters (narrative_frame)
    WHERE narrative_frame IS NOT NULL;
CREATE INDEX IF NOT EXISTS narrative_clusters_active_idx
    ON narrative_clusters (created_at DESC)
    WHERE superseded_at IS NULL;

CREATE TABLE IF NOT EXISTS narrative_cluster_members (
    cluster_id  UUID NOT NULL REFERENCES narrative_clusters(id) ON DELETE CASCADE,
    article_id  UUID NOT NULL REFERENCES articles(id)           ON DELETE CASCADE,
    PRIMARY KEY (cluster_id, article_id)
);

CREATE INDEX IF NOT EXISTS narrative_cluster_members_article_idx
    ON narrative_cluster_members (article_id);

-- Stage 3+ output is the final article draft.
CREATE TABLE IF NOT EXISTS narrative_drafts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_id          UUID NOT NULL REFERENCES narrative_clusters(id) ON DELETE CASCADE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Each stage emits a draft. Latest revision is the "final" if status='ready'.
    revision            INT  NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'in_progress',  -- in_progress|critiqued|ready|rejected
    lede                TEXT,
    body                TEXT,
    headline            TEXT,
    -- Five-critic scores 0-1 (low = problem, high = good). NULL until critics run.
    score_specificity    FLOAT4,
    score_rhythm         FLOAT4,
    score_stance         FLOAT4,
    score_narrative_grav FLOAT4,
    score_anti_recap     FLOAT4,
    critic_notes_json    JSONB,
    word_count           INT,
    CONSTRAINT narrative_drafts_rev_chk CHECK (revision >= 0)
);

CREATE INDEX IF NOT EXISTS narrative_drafts_cluster_idx
    ON narrative_drafts (cluster_id, revision DESC);
CREATE INDEX IF NOT EXISTS narrative_drafts_status_idx
    ON narrative_drafts (status, created_at DESC);

COMMIT;
