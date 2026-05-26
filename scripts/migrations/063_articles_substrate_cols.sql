-- 063_articles_substrate_cols.sql
-- Sprint 0 substrate columns on `articles`.
-- Adds the structural + semantic enrichment fields populated by the
-- one-shot trafilatura + Groq pass over the 67k corpus.
--
-- Idempotent. All `IF NOT EXISTS`.

BEGIN;

ALTER TABLE articles
  ADD COLUMN IF NOT EXISTS body_quality            text DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS word_count              integer,
  ADD COLUMN IF NOT EXISTS reading_minutes         smallint,
  ADD COLUMN IF NOT EXISTS article_type            text,
  ADD COLUMN IF NOT EXISTS canonical_url           text,
  ADD COLUMN IF NOT EXISTS language_iso            text,
  ADD COLUMN IF NOT EXISTS substrate_processed_at  timestamptz,
  ADD COLUMN IF NOT EXISTS substrate_status        text DEFAULT 'pending';

COMMENT ON COLUMN articles.body_quality IS
  '''high'' | ''medium'' | ''low'' | ''unknown''. Computed via Unicode-aware junk score.';
COMMENT ON COLUMN articles.article_type IS
  '''news'' | ''opinion'' | ''analysis'' | ''listicle'' | ''horoscope'' | ''recipe'' | '
  '''live_blog'' | ''photo_essay'' | ''interview'' | ''press_release'' | ''other''. '
  'Set by Groq classifier in substrate pass.';
COMMENT ON COLUMN articles.substrate_status IS
  '''pending'' | ''ok'' | ''fetch_failed'' | ''extract_failed'' | ''junk'' | ''skipped''';

CREATE INDEX IF NOT EXISTS idx_articles_substrate_pending
  ON articles(id) WHERE substrate_processed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_articles_body_quality
  ON articles(body_quality);
CREATE INDEX IF NOT EXISTS idx_articles_article_type
  ON articles(article_type);
CREATE INDEX IF NOT EXISTS idx_articles_canonical_url
  ON articles(canonical_url) WHERE canonical_url IS NOT NULL;

COMMIT;
