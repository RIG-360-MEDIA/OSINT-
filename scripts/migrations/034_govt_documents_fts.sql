-- 034_govt_documents_fts.sql
--
-- Phase 9 audit fix: search currently runs ILIKE '%term%' against
-- title, full_text_translated, and full_text. full_text columns can
-- be up to 50 KB; sequential scan past ~10 k rows is unworkable.
--
-- Add a trigram GIN index on the searched columns so ILIKE turns into
-- an index scan instead of a table scan. pg_trgm ships with Postgres
-- and pgvector — already enabled in this image (used by article search).
--
-- Idempotent: CREATE EXTENSION IF NOT EXISTS, CREATE INDEX IF NOT EXISTS.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Title is small but searched on every request — keep its own index hot.
CREATE INDEX IF NOT EXISTS idx_govt_documents_title_trgm
    ON govt_documents
    USING gin (title gin_trgm_ops);

-- full_text_translated is the primary body column for non-English docs;
-- full_text is the source. Index both so ILIKE on either uses GIN.
CREATE INDEX IF NOT EXISTS idx_govt_documents_full_text_trgm
    ON govt_documents
    USING gin (full_text gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_govt_documents_full_text_translated_trgm
    ON govt_documents
    USING gin (full_text_translated gin_trgm_ops);

COMMIT;
