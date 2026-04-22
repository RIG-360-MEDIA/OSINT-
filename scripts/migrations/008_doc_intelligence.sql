-- P15+ — Document Intelligence layer for Government Documents
-- Adds intel_json, intrinsic importance, action posture, geography,
-- per-user relevance scoring (mirrors user_article_relevance), audit
-- trail for collection runs, and source health tracking.
-- All ALTERs use IF NOT EXISTS to remain idempotent.

-- ============================================================
-- ALTER: govt_documents — intelligence enrichment columns
-- ============================================================
ALTER TABLE govt_documents
    ADD COLUMN IF NOT EXISTS intel_json             JSONB   DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS intrinsic_importance   FLOAT   DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS document_nature        TEXT,
    ADD COLUMN IF NOT EXISTS action_posture         TEXT,
    ADD COLUMN IF NOT EXISTS geography_affected     JSONB   DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS financial_magnitude_inr BIGINT,
    ADD COLUMN IF NOT EXISTS effective_date         DATE,
    ADD COLUMN IF NOT EXISTS winners                JSONB   DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS losers                 JSONB   DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS enforcement_strength   TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'govt_documents_intrinsic_importance_check'
    ) THEN
        ALTER TABLE govt_documents
            ADD CONSTRAINT govt_documents_intrinsic_importance_check
            CHECK (intrinsic_importance BETWEEN 0.0 AND 1.0);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'govt_documents_document_nature_check'
    ) THEN
        ALTER TABLE govt_documents
            ADD CONSTRAINT govt_documents_document_nature_check
            CHECK (document_nature IN (
                'ORDER','NOTIFICATION','CIRCULAR','GAZETTE','POLICY',
                'AMENDMENT','TENDER','JUDGMENT','AUDIT_REPORT','BUDGET',
                'RTI_RESPONSE','COMMITTEE_REPORT','BILL','MINUTES','OTHER'
            ));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'govt_documents_action_posture_check'
    ) THEN
        ALTER TABLE govt_documents
            ADD CONSTRAINT govt_documents_action_posture_check
            CHECK (action_posture IN (
                'NEW_POLICY','EXPANSION','RESTRICTION','REPEAL','EXEMPTION',
                'PUNITIVE','REWARD','INVESTIGATION','TRANSPARENCY',
                'ROUTINE_ADMIN','OTHER'
            ));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'govt_documents_enforcement_strength_check'
    ) THEN
        ALTER TABLE govt_documents
            ADD CONSTRAINT govt_documents_enforcement_strength_check
            CHECK (enforcement_strength IN ('BINDING','ADVISORY','ASPIRATIONAL',NULL));
    END IF;
END$$;

-- ============================================================
-- ALTER: govt_document_chunks — citation offsets + section heading
-- (page_number already exists from migration 006)
-- ============================================================
ALTER TABLE govt_document_chunks
    ADD COLUMN IF NOT EXISTS section_heading TEXT,
    ADD COLUMN IF NOT EXISTS start_char      INTEGER,
    ADD COLUMN IF NOT EXISTS end_char        INTEGER;

-- ============================================================
-- TABLE: user_govt_doc_relevance
-- Per-user scoring for govt documents (mirrors user_article_relevance)
-- ============================================================
CREATE TABLE IF NOT EXISTS user_govt_doc_relevance (
    id                      UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID    NOT NULL
                                    REFERENCES users(id) ON DELETE CASCADE,
    doc_id                  UUID    NOT NULL
                                    REFERENCES govt_documents(id) ON DELETE CASCADE,
    score_stage1            FLOAT   NOT NULL DEFAULT 0.0,
    score_final             FLOAT   NOT NULL DEFAULT 0.0,
    relevance_tier          INTEGER NOT NULL DEFAULT 0
                                    CHECK (relevance_tier BETWEEN 0 AND 3),
    relevance_explanation   TEXT,
    urgency                 TEXT
                                    CHECK (urgency IN ('HIGH','MEDIUM','LOW',NULL)),
    suggested_action        TEXT,
    why_it_matters          TEXT,
    sentiment_for_user      TEXT
                                    CHECK (sentiment_for_user IN (
                                        'FOR_USER','AGAINST_USER','NEUTRAL',NULL
                                    )),
    matched_entity_names    TEXT[],
    geo_match_strength      FLOAT       DEFAULT 0.0,
    computed_at             TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, doc_id)
);

-- ============================================================
-- TABLE: govt_collection_runs
-- Audit trail for portal scrape runs (denormalized source_name
-- so audit history survives source deletion).
-- ============================================================
CREATE TABLE IF NOT EXISTS govt_collection_runs (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id           UUID        REFERENCES govt_document_sources(id) ON DELETE SET NULL,
    source_name         TEXT        NOT NULL,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at         TIMESTAMPTZ,
    status              TEXT        NOT NULL DEFAULT 'running'
                                    CHECK (status IN ('running','completed','failed')),
    urls_discovered     INTEGER     DEFAULT 0,
    urls_filtered_junk  INTEGER     DEFAULT 0,
    pdfs_downloaded     INTEGER     DEFAULT 0,
    pdfs_extracted      INTEGER     DEFAULT 0,
    docs_inserted       INTEGER     DEFAULT 0,
    docs_failed         INTEGER     DEFAULT 0,
    error_summary       TEXT
);

-- ============================================================
-- ALTER: govt_document_sources — health tracking
-- (is_active and last_scraped_at already exist from 006)
-- ============================================================
ALTER TABLE govt_document_sources
    ADD COLUMN IF NOT EXISTS health_score         FLOAT   DEFAULT 1.0,
    ADD COLUMN IF NOT EXISTS consecutive_failures INTEGER DEFAULT 0;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'govt_document_sources_health_score_check'
    ) THEN
        ALTER TABLE govt_document_sources
            ADD CONSTRAINT govt_document_sources_health_score_check
            CHECK (health_score BETWEEN 0.0 AND 1.0);
    END IF;
END$$;

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_ugdr_user_score
    ON user_govt_doc_relevance (user_id, score_final DESC);

CREATE INDEX IF NOT EXISTS idx_ugdr_user_tier
    ON user_govt_doc_relevance (user_id, relevance_tier, score_final DESC);

CREATE INDEX IF NOT EXISTS idx_govt_docs_intrinsic
    ON govt_documents (intrinsic_importance DESC)
    WHERE intrinsic_importance > 0;

CREATE INDEX IF NOT EXISTS idx_govt_docs_effective_date
    ON govt_documents (effective_date DESC)
    WHERE effective_date IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_govt_docs_nature
    ON govt_documents (document_nature)
    WHERE document_nature IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_collection_runs_source
    ON govt_collection_runs (source_id, started_at DESC);
