-- 085_embedding_provenance.sql
-- =====================================================================
-- Worldwide Phase 0a: per-vector provenance.
--
-- WHY: today there is ZERO provenance on the ~122K LaBSE vectors — we
-- cannot prove which model/revision produced any of them, so we cannot
-- prove the space is internally comparable (the silent-drift risk the
-- Worldwide team flagged). These columns make every FUTURE vector
-- self-describing.
--
-- SAFETY: additive + lock-safe (same shape as 084). ADD COLUMN ... TEXT
-- / timestamptz nullable is metadata-only. NO bulk backfill here — a
-- 122K-row UPDATE would contend with the live writer. Existing rows keep
-- NULL provenance ("pre-instrumentation, revision unknown"); they get
-- stamped by the one-time re-embed (Phase 0c). New embeds are stamped by
-- the NLP / embed-on-collect code.
-- =====================================================================

BEGIN;
SET LOCAL lock_timeout = '3s';

ALTER TABLE articles ADD COLUMN IF NOT EXISTS embedded_at        timestamptz;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS embedding_model    text;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS embedding_revision text;

COMMENT ON COLUMN articles.embedded_at IS
  'When labse_embedding was generated. NULL for pre-2026-05-30 vectors (no record); set going forward by the embed path.';
COMMENT ON COLUMN articles.embedding_model IS
  'Embedding model id, e.g. sentence-transformers/LaBSE. NULL = unknown (pre-provenance).';
COMMENT ON COLUMN articles.embedding_revision IS
  'Pinned HF commit of the embedding model. NULL = unknown (pre-provenance). Mixed non-null values across rows = incomparable vector space -> re-embed required.';

COMMIT;

-- Deferred backfill (run throttled, off-peak — NOT in this migration to
-- avoid a 122K-row write lock). We DO know the model is LaBSE; we do NOT
-- know the historical revision, so stamp model only and leave revision
-- NULL = honestly unknown until Phase 0c re-embed:
-- UPDATE articles SET embedding_model = 'sentence-transformers/LaBSE'
--   WHERE labse_embedding IS NOT NULL AND embedding_model IS NULL;
