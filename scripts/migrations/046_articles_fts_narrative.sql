-- ============================================================
-- Migration 046 — articles full-text search + narrative_frame
-- ============================================================
-- Adds:
--  - articles.fts (tsvector generated column) — for hybrid retrieval
--    (BM25 + vector RRF fusion in rag_engine).
--  - articles.narrative_frame TEXT — Groq-tagged framing label per
--    article ("neutral / critical / celebratory / accusatory / etc").
--    Powers Source comparator.
--
-- ⚠️ RISKY MIGRATION — concurrent index, run outside a transaction.
-- Procedure:
--   1. Apply this file with `psql -v ON_ERROR_STOP=1 -f 046_*.sql`
--      The CREATE INDEX CONCURRENTLY runs after the ALTER (which is
--      a metadata-only change since columns are NULLable / generated).
--   2. Verify: SELECT count(*) FROM pg_indexes
--               WHERE indexname = 'articles_fts_gin_idx';
--
-- Idempotent — safe to re-run.
-- ============================================================

-- ── narrative_frame nullable column (metadata-only ALTER) ───
ALTER TABLE articles
  ADD COLUMN IF NOT EXISTS narrative_frame TEXT;

COMMENT ON COLUMN articles.narrative_frame IS
  'Groq-tagged framing label per article. Used by Source comparator to surface framing diffs.';


-- ── tsvector generated column for full-text search ──────────
-- Postgres 12+ supports GENERATED ... STORED. Indexes title +
-- lead_text_translated (preferred) or lead_text_original. Weights:
--   A = title (highest), B = lead text body.
ALTER TABLE articles
  ADD COLUMN IF NOT EXISTS fts tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english',
                coalesce(lead_text_translated, lead_text_original, '')), 'B')
  ) STORED;

COMMENT ON COLUMN articles.fts IS
  'Generated tsvector for hybrid retrieval. title=A, lead_text=B. Used in BM25 portion of RRF fusion.';


-- ── GIN index — must be CONCURRENTLY (hot table) ────────────
-- We can't run CONCURRENTLY inside a transaction block; the migration
-- runner (psql with ON_ERROR_STOP) processes statements one at a time
-- so this is safe as long as no surrounding BEGIN/COMMIT is added.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE indexname = 'articles_fts_gin_idx'
    ) THEN
        -- Note: CONCURRENTLY can't run inside a DO block (it requires
        -- being a top-level statement). We guard with the check above
        -- and run the actual CREATE outside any block below.
        RAISE NOTICE 'articles_fts_gin_idx will be created next.';
    END IF;
END$$;

-- Top-level (outside DO block) — only runs if missing.
-- Postgres skips silently if it already exists due to IF NOT EXISTS.
CREATE INDEX CONCURRENTLY IF NOT EXISTS articles_fts_gin_idx
  ON articles USING GIN (fts);
