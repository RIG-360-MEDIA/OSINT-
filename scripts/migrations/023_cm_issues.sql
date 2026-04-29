-- 023_cm_issues.sql
-- CM Page: clustered political flashpoints + their evidence rows.
-- Issues are produced by tasks.cm.cluster_issues (HDBSCAN over LaBSE
-- embeddings + Groq labelling). Evidence is the M:N join between issue and
-- source items, with `side` denormalised from cm_stance_scores so the issue
-- read path is a simple aggregation without re-joining stance.

CREATE TABLE IF NOT EXISTS cm_issues (
    id                          BIGSERIAL PRIMARY KEY,
    label                       TEXT NOT NULL,
    slug                        TEXT NOT NULL UNIQUE,
    state                       TEXT,
    embedding                   vector(768),                          -- LaBSE; same dim as articles.labse_embedding
    first_seen                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    ruling_stance_summary       TEXT,
    opposition_stance_summary   TEXT,
    neutral_summary             TEXT,
    volume_24h                  INT NOT NULL DEFAULT 0,
    volume_7d                   INT NOT NULL DEFAULT 0,
    intensity                   REAL NOT NULL DEFAULT 0,              -- 0..100, computed by trajectory task
    trajectory                  TEXT CHECK (trajectory IN ('intensifying','steady','fading','unknown')) DEFAULT 'unknown',
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS cm_issues_lastseen_idx
    ON cm_issues (state, last_seen DESC);

CREATE INDEX IF NOT EXISTS cm_issues_intensity_idx
    ON cm_issues (state, intensity DESC, last_seen DESC);

-- Vector index requires extension `vector`; safe to create only if available.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS cm_issues_emb_idx ON cm_issues USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)';
    END IF;
END$$;

CREATE TABLE IF NOT EXISTS cm_issue_evidence (
    issue_id     BIGINT NOT NULL REFERENCES cm_issues(id) ON DELETE CASCADE,
    source_kind  TEXT NOT NULL CHECK (source_kind IN ('article','social_post','clip','clipping')),
    source_id    BIGINT NOT NULL,
    side         TEXT CHECK (side IN ('ruling','opposition','neutral')),
    weight       REAL NOT NULL DEFAULT 1.0,
    attached_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (issue_id, source_kind, source_id)
);

CREATE INDEX IF NOT EXISTS cm_evidence_issue_side_idx
    ON cm_issue_evidence (issue_id, side);

CREATE INDEX IF NOT EXISTS cm_evidence_source_idx
    ON cm_issue_evidence (source_kind, source_id);

COMMENT ON TABLE cm_issues IS
  'CM Page: clustered political flashpoints. Centroid embedding stored for issue-merge decisions across runs.';
COMMENT ON TABLE cm_issue_evidence IS
  'CM Page: M:N between issues and source items. side is denormalised from cm_stance_scores at attach time.';
