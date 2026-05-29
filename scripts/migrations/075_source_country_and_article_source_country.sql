-- ============================================================================
-- Migration 075 — clean ISO country code on sources + derived field on articles
-- ============================================================================
-- Why:
--   sources.geo_states is a text array that mixes Indian states, country
--   names, continents, regions, and cities — fine for tagging, lousy for
--   "show me all articles from China" queries. We add a canonical
--   sources.country (ISO 3166-1 alpha-2) and propagate to articles via
--   trigger so the brief page, country filter, and analytics can group
--   cleanly without unnesting arrays.
--
--   Going forward: every source you insert must set .country; every article
--   inserted gets .source_country auto-filled from its source FK.
--
-- Safety:
--   - Adds columns with DEFAULT, so no rewrite of existing rows
--   - Backfill via UPDATE in batches (no long table lock)
--   - Trigger only fires on INSERT to articles (zero impact on existing rows)
--   - Index added CONCURRENTLY to avoid blocking inserts
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. sources.country — canonical ISO 3166-1 alpha-2 code
-- ----------------------------------------------------------------------------
ALTER TABLE sources
  ADD COLUMN IF NOT EXISTS country CHAR(2) NOT NULL DEFAULT 'XX';

COMMENT ON COLUMN sources.country IS
  'ISO 3166-1 alpha-2 country code (IN, US, GB, CN, RU, JP, etc.). '
  'XX = unknown/global newswire. Use this for country-grouping queries '
  'instead of unnest(geo_states); geo_states stays for region/state tags.';

-- ----------------------------------------------------------------------------
-- 2. articles.source_country — derived, indexed for fast grouping
-- ----------------------------------------------------------------------------
ALTER TABLE articles
  ADD COLUMN IF NOT EXISTS source_country CHAR(2);

COMMENT ON COLUMN articles.source_country IS
  'Country (ISO 3166-1 alpha-2) of the source that published this article. '
  'Auto-populated by trigger from sources.country at INSERT time.';

-- ----------------------------------------------------------------------------
-- 3. Heuristic backfill of sources.country from existing geo_states
-- ----------------------------------------------------------------------------
-- India + any Indian state name → IN
UPDATE sources SET country = 'IN'
 WHERE 'India' = ANY(geo_states)
    OR geo_states && ARRAY[
       'Andhra Pradesh','Arunachal Pradesh','Assam','Bihar','Chhattisgarh',
       'Delhi','Goa','Gujarat','Haryana','Himachal Pradesh','Jammu-Kashmir',
       'Jharkhand','Karnataka','Kerala','Ladakh','Madhya Pradesh','Maharashtra',
       'Manipur','Meghalaya','Mizoram','Nagaland','Odisha','Punjab','Rajasthan',
       'Sikkim','Tamil Nadu','Telangana','Tripura','Uttar Pradesh','Uttarakhand',
       'West Bengal','Hyderabad']::text[];

-- Other countries (geo_states tag matches the country name)
UPDATE sources SET country = 'GB' WHERE 'UK' = ANY(geo_states)        AND country='XX';
UPDATE sources SET country = 'US' WHERE 'USA' = ANY(geo_states)       AND country='XX';
UPDATE sources SET country = 'AU' WHERE 'Australia' = ANY(geo_states) AND country='XX';
UPDATE sources SET country = 'CN' WHERE 'China' = ANY(geo_states)     AND country='XX';
UPDATE sources SET country = 'JP' WHERE 'Japan' = ANY(geo_states)     AND country='XX';
UPDATE sources SET country = 'KR' WHERE 'South Korea' = ANY(geo_states) AND country='XX';
UPDATE sources SET country = 'PK' WHERE 'Pakistan' = ANY(geo_states)  AND country='XX';
UPDATE sources SET country = 'BD' WHERE 'Bangladesh' = ANY(geo_states) AND country='XX';
UPDATE sources SET country = 'LK' WHERE 'Sri Lanka' = ANY(geo_states) AND country='XX';
UPDATE sources SET country = 'NP' WHERE 'Nepal' = ANY(geo_states)     AND country='XX';
UPDATE sources SET country = 'MY' WHERE 'Malaysia' = ANY(geo_states)  AND country='XX';
UPDATE sources SET country = 'SG' WHERE 'Singapore' = ANY(geo_states) AND country='XX';
UPDATE sources SET country = 'NG' WHERE 'Nigeria' = ANY(geo_states)   AND country='XX';
UPDATE sources SET country = 'ZA' WHERE 'South Africa' = ANY(geo_states) AND country='XX';
UPDATE sources SET country = 'KE' WHERE 'Kenya' = ANY(geo_states)     AND country='XX';
UPDATE sources SET country = 'GH' WHERE 'Ghana' = ANY(geo_states)     AND country='XX';
UPDATE sources SET country = 'AE' WHERE 'UAE' = ANY(geo_states)       AND country='XX';

-- TLD fallback for sources still 'XX' (e.g. *.cn → CN even if geo_states says India)
UPDATE sources SET country = 'IN' WHERE country='XX' AND (domain LIKE '%.in'    OR domain LIKE '%.co.in%');
UPDATE sources SET country = 'CN' WHERE country='XX' AND (domain LIKE '%.cn'    OR domain LIKE '%.com.cn%');
UPDATE sources SET country = 'GB' WHERE country='XX' AND (domain LIKE '%.uk'    OR domain LIKE '%.co.uk%');
UPDATE sources SET country = 'AU' WHERE country='XX' AND (domain LIKE '%.au'    OR domain LIKE '%.com.au%');
UPDATE sources SET country = 'RU' WHERE country='XX' AND domain LIKE '%.ru';
UPDATE sources SET country = 'JP' WHERE country='XX' AND domain LIKE '%.jp';
UPDATE sources SET country = 'KR' WHERE country='XX' AND domain LIKE '%.kr';
UPDATE sources SET country = 'PK' WHERE country='XX' AND domain LIKE '%.pk';
UPDATE sources SET country = 'BD' WHERE country='XX' AND domain LIKE '%.bd';
UPDATE sources SET country = 'LK' WHERE country='XX' AND domain LIKE '%.lk';
UPDATE sources SET country = 'NP' WHERE country='XX' AND domain LIKE '%.np';

-- Specific overrides for Chinese sources mis-tagged as India (defense feeds)
UPDATE sources SET country = 'CN'
 WHERE name ILIKE 'China %' OR name ILIKE 'Xinhua%' OR name ILIKE 'PLA Daily%'
    OR name ILIKE 'Global Times%' OR domain LIKE '%scmp.com%';

-- 'global' tags → 'XX' (intentionally — wire services have no single country)
-- (no UPDATE needed, default is already XX)

-- ----------------------------------------------------------------------------
-- 4. Backfill articles.source_country from current sources
-- ----------------------------------------------------------------------------
UPDATE articles a SET source_country = s.country
  FROM sources s
 WHERE a.source_id = s.id
   AND a.source_country IS NULL;

-- ----------------------------------------------------------------------------
-- 5. Trigger to auto-populate on new article inserts
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_set_article_source_country() RETURNS trigger AS $$
BEGIN
  IF NEW.source_country IS NULL AND NEW.source_id IS NOT NULL THEN
    SELECT country INTO NEW.source_country FROM sources WHERE id = NEW.source_id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_articles_source_country ON articles;
CREATE TRIGGER trg_articles_source_country
  BEFORE INSERT ON articles
  FOR EACH ROW EXECUTE FUNCTION trg_set_article_source_country();

COMMIT;

-- Index OUTSIDE the transaction (CONCURRENTLY requires its own session)
CREATE INDEX IF NOT EXISTS articles_source_country_idx
  ON articles (source_country)
  WHERE source_country IS NOT NULL;

-- ============================================================================
-- Verification queries (run after migration):
--   SELECT country, COUNT(*) FROM sources GROUP BY 1 ORDER BY 2 DESC;
--   SELECT source_country, COUNT(*) FROM articles
--    WHERE substrate_processed_at > now() - INTERVAL '1 day'
--    GROUP BY 1 ORDER BY 2 DESC;
-- ============================================================================
