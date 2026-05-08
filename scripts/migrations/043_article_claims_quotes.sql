-- ============================================================
-- Migration 043 — article_claims + article_quotes
-- ============================================================
-- Two extraction tables that power Compare mode, Contradictions,
-- Quote sidebar, and "what has X said about Y" queries.
--
-- Populated incrementally by process_nlp_batch (Groq with strict
-- JSON schema). Backfill of last 30d runs as a one-time Celery
-- task (extract_claims_quotes_backfill) outside this migration.
--
-- Idempotent — safe to re-run.
-- ============================================================

-- ── Factual claims extracted from each article ──────────────
CREATE TABLE IF NOT EXISTS article_claims (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id          UUID        NOT NULL
                                    REFERENCES articles(id) ON DELETE CASCADE,
    claim_text          TEXT        NOT NULL,
    -- Optional structured (subject, predicate, object) triple.
    subject_entity_id   UUID        REFERENCES entity_dictionary(id),
    subject_text        TEXT,
    predicate           TEXT,
    object_text         TEXT,
    -- LLM confidence in extraction (0–1).
    confidence          REAL        NOT NULL DEFAULT 0.5,
    -- Embedding for fast claim-vs-claim similarity (LaBSE for now;
    -- migrate to BGE-M3 1024-dim once retrieval upgrade ships).
    embedding           VECTOR(768),
    extracted_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    extracted_by_model  TEXT        NOT NULL DEFAULT 'llama-3.1-8b-instant'
);

CREATE INDEX IF NOT EXISTS article_claims_article_idx
  ON article_claims (article_id);
CREATE INDEX IF NOT EXISTS article_claims_subject_idx
  ON article_claims (subject_entity_id)
  WHERE subject_entity_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS article_claims_extracted_at_idx
  ON article_claims (extracted_at DESC);

-- HNSW for claim-similarity search (used by contradictions task).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE indexname = 'article_claims_embedding_hnsw_idx'
    ) THEN
        EXECUTE 'CREATE INDEX article_claims_embedding_hnsw_idx
                 ON article_claims USING hnsw (embedding vector_cosine_ops)
                 WHERE embedding IS NOT NULL';
    END IF;
END$$;

COMMENT ON TABLE article_claims IS
  'Factual claims extracted per article. Powers Contradictions, Compare mode, claim-search.';


-- ── Quotes attributed to a speaker ──────────────────────────
CREATE TABLE IF NOT EXISTS article_quotes (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id              UUID        NOT NULL
                                        REFERENCES articles(id) ON DELETE CASCADE,
    speaker_name            TEXT        NOT NULL,
    -- Resolved against entity_dictionary if recognised.
    speaker_entity_id       UUID        REFERENCES entity_dictionary(id),
    quote_text              TEXT        NOT NULL,
    -- Char offsets into full_text_scraped (or lead_text_scraped fallback).
    char_offset_start       INTEGER,
    char_offset_end         INTEGER,
    -- Optional context: was the speaker quoted directly or paraphrased?
    is_direct               BOOLEAN     NOT NULL DEFAULT TRUE,
    extracted_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    extracted_by_model      TEXT        NOT NULL DEFAULT 'llama-3.1-8b-instant'
);

CREATE INDEX IF NOT EXISTS article_quotes_article_idx
  ON article_quotes (article_id);
CREATE INDEX IF NOT EXISTS article_quotes_speaker_entity_idx
  ON article_quotes (speaker_entity_id)
  WHERE speaker_entity_id IS NOT NULL;
-- Trigram index for fuzzy speaker search (CREATE EXTENSION pg_trgm
-- guarded — added in 001_initial_schema.sql or implicitly by pgvector image).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS article_quotes_speaker_trgm_idx
                 ON article_quotes USING GIN (speaker_name gin_trgm_ops)';
    END IF;
END$$;

COMMENT ON TABLE article_quotes IS
  'Attributed quotes per article. Powers Quote sidebar and speaker-scoped retrieval.';


-- ── extraction_status tracker on articles ───────────────────
-- Lets process_nlp_batch skip already-extracted articles cheaply.
ALTER TABLE articles
  ADD COLUMN IF NOT EXISTS claims_extracted     BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS quotes_extracted     BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS articles_claims_pending_idx
  ON articles (collected_at DESC)
  WHERE claims_extracted = FALSE;
