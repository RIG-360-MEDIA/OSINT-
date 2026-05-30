-- ============================================================================
-- Migration 083 — high-precision reclassification of topic_category='OTHER'
-- ============================================================================
-- WHY
--   ~41% of the corpus (50K articles) sits in topic_category='OTHER' because
--   the NLP topic classifier hedges + the 15-bucket taxonomy is coarse. Cricket
--   hides in OTHER (so `exclude: SPORTS` can't mute it); clean finance/legal/
--   entertainment stories hide there too.
--
-- APPROACH (no LLM — heuristic, like migration 077)
--   Reclassify OTHER using ONLY unambiguous-vocabulary buckets. Tested
--   2026-05-30: SPORTS ~92% accurate, ENTERTAINMENT ~94%; semantic buckets
--   (GOVERNANCE/POLITICS/SOCIAL) were DROPPED because keyword rules over-match
--   them badly ("scheme" caught Tollywood + finance + legal). Those need an
--   entity-based or LLM pass instead — see docs.
--
--   Rules run in order; each only touches rows still 'OTHER' (first match wins).
--   Match surface = lower(title + primary_subject) — short, high-signal fields.
--
-- SAFE: topic_category_orig backup column for full rollback. Only touches
--   rows currently 'OTHER'. ~3,800 articles reclassified, high precision.
-- ============================================================================

BEGIN;

-- 1. Backup (reversible)
ALTER TABLE articles ADD COLUMN IF NOT EXISTS topic_category_orig text;
UPDATE articles SET topic_category_orig = topic_category WHERE topic_category_orig IS NULL;

-- 2. SPORTS — cricket / football / specific sports vocab (~92% precision)
UPDATE articles SET topic_category = 'SPORTS'
 WHERE topic_category = 'OTHER'
   AND lower(COALESCE(title,'') || ' ' || COALESCE(primary_subject,'')) ~
       '(\mipl\M|\bcricket\b|\bwicket\b|\bt20\b|test match|\bbatsman\b|\bbowler\b|\binnings\b|premier league|\bfifa\b|\bla liga\b|\bkabaddi\b|world cup)';

-- 3. FINANCE — markets / results (specific, low-ambiguity terms)
UPDATE articles SET topic_category = 'FINANCE'
 WHERE topic_category = 'OTHER'
   AND lower(COALESCE(title,'') || ' ' || COALESCE(primary_subject,'')) ~
       '(\bsensex\b|\bnifty\b|\bipo\b|q[1-4] result|quarterly result|stock market|mutual fund|crore profit|crore loss|net profit|\bearnings\b)';

-- 4. LEGAL — court / criminal-procedure vocab
UPDATE articles SET topic_category = 'LEGAL'
 WHERE topic_category = 'OTHER'
   AND lower(COALESCE(title,'') || ' ' || COALESCE(primary_subject,'')) ~
       '(\bbail\b|\bfir\b|\bverdict\b|acquitted|convicted|charge ?sheet|sentenced to|high court|supreme court|tribunal)';

-- 5. ENTERTAINMENT — film / OTT vocab (~94% precision; catches Telugu/Odia film news)
UPDATE articles SET topic_category = 'ENTERTAINMENT'
 WHERE topic_category = 'OTHER'
   AND lower(COALESCE(title,'') || ' ' || COALESCE(primary_subject,'')) ~
       '(box office|\bott\b|\btrailer\b|\bteaser\b|bollywood|tollywood|web series|first look|movie review|film review)';

COMMIT;

-- ============================================================================
-- VERIFY:
--   SELECT topic_category, COUNT(*) FROM articles
--    WHERE topic_category_orig='OTHER' AND topic_category!='OTHER'
--    GROUP BY 1 ORDER BY 2 DESC;
--   -- spot-check:
--   SELECT topic_category, LEFT(title,60) FROM articles
--    WHERE topic_category_orig='OTHER' AND topic_category!='OTHER'
--    ORDER BY random() LIMIT 20;
--
-- NOT DONE HERE (need entity-based or LLM, see docs):
--   GOVERNANCE / POLITICS / SOCIAL — semantic, keyword rules unsafe.
--
-- ROLLBACK:
--   BEGIN;
--     UPDATE articles SET topic_category = topic_category_orig
--      WHERE topic_category_orig IS NOT NULL;
--     ALTER TABLE articles DROP COLUMN topic_category_orig;
--   COMMIT;
-- ============================================================================
