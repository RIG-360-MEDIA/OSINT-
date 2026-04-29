-- 032_cm_state_backfill.sql
--
-- D-2 fix — backfill cm_stance_scores.state and cm_spokesperson_quotes.state
-- from the source articles' geo_primary. Audit found 99% of stance rows and
-- 82% of quote rows had empty state, breaking every state-scoped CM endpoint.
--
-- Mapping rule (mirrors backend/routers/cm_queries._STATE_GEO_NEEDLE):
--   geo_primary ILIKE %telangana|hyderabad|tg%        → 'TG'
--   geo_primary ILIKE %andhra pradesh|andhra|vijayawada|visakhapatnam|amaravati|ap% → 'AP'
--   else                                              → leave NULL
--
-- This migration is idempotent: it only updates rows where state IS NULL or
-- empty, so re-running has no effect.

BEGIN;

-- Articles → cm_stance_scores
UPDATE cm_stance_scores s
SET state = 'TG'
FROM articles a
WHERE s.source_kind = 'article'
  AND s.source_id = a.id
  AND (s.state IS NULL OR s.state = '')
  AND (
    LOWER(a.geo_primary) LIKE '%telangana%' OR
    LOWER(a.geo_primary) LIKE '%hyderabad%' OR
    LOWER(a.geo_primary) = 'tg'
  );

UPDATE cm_stance_scores s
SET state = 'AP'
FROM articles a
WHERE s.source_kind = 'article'
  AND s.source_id = a.id
  AND (s.state IS NULL OR s.state = '')
  AND (
    LOWER(a.geo_primary) LIKE '%andhra pradesh%' OR
    LOWER(a.geo_primary) LIKE '%andhra%' OR
    LOWER(a.geo_primary) LIKE '%vijayawada%' OR
    LOWER(a.geo_primary) LIKE '%visakhapatnam%' OR
    LOWER(a.geo_primary) LIKE '%amaravati%' OR
    LOWER(a.geo_primary) = 'ap'
  );

-- Articles → cm_spokesperson_quotes
UPDATE cm_spokesperson_quotes q
SET state = 'TG'
FROM articles a
WHERE q.source_kind = 'article'
  AND q.source_id = a.id
  AND (q.state IS NULL OR q.state = '')
  AND (
    LOWER(a.geo_primary) LIKE '%telangana%' OR
    LOWER(a.geo_primary) LIKE '%hyderabad%' OR
    LOWER(a.geo_primary) = 'tg'
  );

UPDATE cm_spokesperson_quotes q
SET state = 'AP'
FROM articles a
WHERE q.source_kind = 'article'
  AND q.source_id = a.id
  AND (q.state IS NULL OR q.state = '')
  AND (
    LOWER(a.geo_primary) LIKE '%andhra pradesh%' OR
    LOWER(a.geo_primary) LIKE '%andhra%' OR
    LOWER(a.geo_primary) LIKE '%vijayawada%' OR
    LOWER(a.geo_primary) LIKE '%visakhapatnam%' OR
    LOWER(a.geo_primary) LIKE '%amaravati%' OR
    LOWER(a.geo_primary) = 'ap'
  );

-- Quote-quality cleanup — D-24 sentinel sweep + D-4 'null' string fix.
DELETE FROM cm_spokesperson_quotes
WHERE LOWER(TRIM(BOTH ' .''"`' FROM speaker)) IN (
    'the article does not mention a specific named person',
    'no named speaker',
    'no specific named person',
    'no speaker',
    'n/a', 'na', 'none',
    'not specified', 'not mentioned',
    'anonymous', 'anonymous source', 'sources said',
    'unknown speaker', 'various', 'observers',
    'officials', 'officials said'
)
   OR LOWER(speaker) LIKE 'the article%';

UPDATE cm_spokesperson_quotes
SET party = NULL
WHERE LOWER(party) IN ('null', 'none', 'n/a', 'na', '');

-- Canonicalize the BJP / "Bharatiya Janata Party" duplicate (D-4).
UPDATE cm_spokesperson_quotes
SET party = 'BJP'
WHERE party IN ('Bharatiya Janata Party', 'bharatiya janata party');

-- Drop low-confidence Groq-401 stance rows so /api/cm/* read paths don't
-- surface them. They will be re-scored by tasks.cm.tag_stance once the
-- Groq key is rotated (D-8).
DELETE FROM cm_stance_scores
WHERE stance = 'unknown' AND confidence < 0.10;

COMMIT;

-- Sanity counts (run by hand after applying):
-- SELECT state, count(*) FROM cm_stance_scores GROUP BY 1;
-- SELECT state, count(*) FROM cm_spokesperson_quotes GROUP BY 1;
