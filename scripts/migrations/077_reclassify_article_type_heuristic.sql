-- ============================================================================
-- Migration 077 — heuristic re-classification of article_type='other'
-- ============================================================================
-- Substrate's article_type classifier hedges aggressively to "other" (28-68%
-- of corpus depending on window). The same substrate run extracted reliable
-- secondary signals — register_style, topic_category, body length, title
-- patterns — that we can use to confidently re-assign type WITHOUT
-- re-running the LLM.
--
-- This migration:
--   1. Backs up current article_type → article_type_orig (reversible)
--   2. Re-assigns "other" rows using cascade rules
--   3. Leaves genuinely-ambiguous rows as "other"
--
-- Safe: read-only on every field except article_type. No data deletion.
--   Original values preserved in article_type_orig column.
-- ============================================================================

BEGIN;

-- 1. Backup column (only on first run; safe to skip if exists)
ALTER TABLE articles
  ADD COLUMN IF NOT EXISTS article_type_orig text;

UPDATE articles
   SET article_type_orig = article_type
 WHERE article_type_orig IS NULL;

-- 2. Cascade rules — apply in order. First match wins per row.

-- Rule A: long body + analytical register → 'analysis'
UPDATE articles
   SET article_type = 'analysis'
 WHERE article_type = 'other'
   AND register_style = 'analytical'
   AND length(full_text_scraped) > 2000;

-- Rule B: polemical / editorial register → 'opinion'
UPDATE articles
   SET article_type = 'opinion'
 WHERE article_type = 'other'
   AND register_style IN ('polemical', 'editorial', 'sensational')
   AND length(full_text_scraped) > 800;

-- Rule C: factual register + reasonable body + non-notice title → 'news'
-- (Revised after spot-check 2026-05-28: original required topic_category IN
-- explicit news list, but the topic classifier ALSO hedges to 'OTHER', so
-- many real news articles (e.g. "China-Russia unite", "Court fines DeviantArt")
-- were getting left behind. Allow OTHER + NULL too — title patterns + body
-- length filter remove the truly-not-news cases.)
UPDATE articles
   SET article_type = 'news'
 WHERE article_type = 'other'
   AND (register_style IN ('factual','analytical','neutral') OR register_style IS NULL)
   AND length(full_text_scraped) BETWEEN 250 AND 10000
   AND (
        topic_category IS NULL
        OR topic_category IN (
            'POLITICS','SECURITY','INTERNATIONAL','LEGAL','BUSINESS',
            'HEALTH','SPORTS','ENTERTAINMENT','TECH','SCIENCE',
            'ECONOMY','SOCIETY','SOCIAL','EDUCATION','ENVIRONMENT',
            'INFRASTRUCTURE','GOVERNMENT','AGRICULTURE','CULTURE',
            'OTHER'  -- allow topic-classifier-hedged rows through
        )
   )
   AND COALESCE(title, '') !~* '\m(court [ivx]+|tender notice|notice of|schedule of|public notice|earnings call|stock quote|rapid recap)\M';

-- Rule D: very long body + factual = explainer
UPDATE articles
   SET article_type = 'explainer'
 WHERE article_type = 'other'
   AND register_style = 'factual'
   AND length(full_text_scraped) > 5000;

-- Rule E: rest stays as 'other' — these are genuinely ambiguous
--         (court notices, viral curiosities, aggregator pages, etc.)

COMMIT;

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================
--
-- Before vs after distribution:
--   SELECT article_type_orig, article_type, COUNT(*)
--     FROM articles
--    WHERE article_type_orig = 'other'
--    GROUP BY 1, 2 ORDER BY 3 DESC;
--
-- Spot-check 10 reclassified rows:
--   SELECT title, article_type_orig, article_type, register_style,
--          topic_category, length(full_text_scraped) AS body_len
--     FROM articles
--    WHERE article_type_orig = 'other' AND article_type != 'other'
--    ORDER BY random() LIMIT 10;
--
-- Spot-check 10 rows STILL marked 'other' (sanity — confirm these are
-- genuinely ambiguous):
--   SELECT title, article_type, register_style, topic_category
--     FROM articles
--    WHERE article_type = 'other'
--    ORDER BY random() LIMIT 10;
--
-- ============================================================================
-- ROLLBACK procedure (if reclassification is wrong)
-- ============================================================================
--   BEGIN;
--   UPDATE articles
--      SET article_type = article_type_orig
--    WHERE article_type_orig IS NOT NULL;
--   ALTER TABLE articles DROP COLUMN article_type_orig;
--   COMMIT;
-- ============================================================================
