-- 036_brief_quality_scores.sql
-- fix/brief-prod-readiness P2.10
--
-- Brief quality rubric scorecard. Populated daily by
-- ``tasks.score_brief_quality`` (backend/tasks/brief_quality_task.py).
--
-- Each row scores ONE brief on the rubric defined in
-- docs/qa/brief-remediation-plan.md Phase 2 #10:
--
--    citation_density          ≥ 1 cite per prose section
--    citation_validity         every cited [N] resolves to evidence
--    pillar_coverage           non-empty section per pillar with rows
--    article_recency_avg_days  smaller is better
--    article_recency_max_days
--    failure_marker_count      occurrences of "[Generation failed"
--    section_word_counts       jsonb {section_name: word_count}
--    invalid_indexes           jsonb [section_name, [indexes]]
--    overall_score             0.0 - 1.0 weighted aggregate
--
-- The table is append-only — one row per (user_id, brief_date) PRIMARY KEY
-- so the scorecard cron is idempotent: rerunning the task on the same day
-- overwrites the row rather than duplicating it.

CREATE TABLE IF NOT EXISTS brief_quality_scores (
    id                          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                     uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    brief_date                  date        NOT NULL,
    scored_at                   timestamptz NOT NULL DEFAULT now(),

    -- Section completeness
    has_situation_status        boolean     NOT NULL DEFAULT FALSE,
    has_key_developments        boolean     NOT NULL DEFAULT FALSE,
    has_entities_today          boolean     NOT NULL DEFAULT FALSE,
    has_signals_to_watch        boolean     NOT NULL DEFAULT FALSE,
    has_financial_pulse         boolean     NOT NULL DEFAULT FALSE,
    has_source_coverage         boolean     NOT NULL DEFAULT FALSE,

    -- Citation health
    bracket_cites               integer     NOT NULL DEFAULT 0,
    pillar_cites                integer     NOT NULL DEFAULT 0,
    failure_marker_count        integer     NOT NULL DEFAULT 0,
    invalid_indexes             jsonb       NOT NULL DEFAULT '[]'::jsonb,

    -- Recency (article pool that fed the brief)
    article_recency_avg_days    numeric(6,2),
    article_recency_max_days    numeric(6,2),
    articles_within_36h         integer,

    -- Per-section length (used to spot regressions; lib reuses
    -- backend.nlp.brief_validator.count_words at write time).
    section_word_counts         jsonb       NOT NULL DEFAULT '{}'::jsonb,

    -- 0.0 – 1.0 weighted summary. See brief_quality_task._overall.
    overall_score               numeric(4,3),

    UNIQUE (user_id, brief_date)
);

CREATE INDEX IF NOT EXISTS idx_brief_quality_scores_brief_date
    ON brief_quality_scores (brief_date DESC);

CREATE INDEX IF NOT EXISTS idx_brief_quality_scores_overall
    ON brief_quality_scores (overall_score)
    WHERE overall_score IS NOT NULL;

COMMENT ON TABLE brief_quality_scores IS
    'Daily rubric scorecard for the Brief pillar. fix/brief-prod-readiness P2.10.';
