-- 049_quote_translation.sql
--
-- Add English-translated columns to article_quotes so the dashboard can
-- show readable English quotes/speaker names even when the source
-- article is Telugu, Bengali, Hindi, etc.
--
-- The extraction Groq call now produces quote_text_en + speaker_name_en
-- alongside the originals. A separate periodic task backfills these for
-- pre-existing rows that have NULL english fields.
--
-- Idempotent: safe to re-run.

BEGIN;

ALTER TABLE article_quotes
  ADD COLUMN IF NOT EXISTS quote_text_en   text,
  ADD COLUMN IF NOT EXISTS speaker_name_en text,
  ADD COLUMN IF NOT EXISTS translated_at   timestamptz;

-- Partial index for the backfill driver: it scans for rows that still
-- need translation. Only the few hundred un-translated rows live here.
CREATE INDEX IF NOT EXISTS idx_article_quotes_pending_translation
  ON article_quotes (extracted_at DESC)
  WHERE quote_text_en IS NULL;

COMMIT;
