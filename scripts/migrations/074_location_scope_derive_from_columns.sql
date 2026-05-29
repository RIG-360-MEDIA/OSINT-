-- ============================================================================
-- Migration 074 — location_scope derived from city/region/country
-- ============================================================================
-- Problem: article_locations.location_scope is mislabeled "country" in 99.97%
-- of rows (258,962 / 259,047), regardless of whether the row is actually a
-- city, state, country, continent, or unrecognized place.
--
-- The good news: city, region, country columns ARE correctly populated.
-- So we can derive scope from those columns without calling the LLM.
--
-- Rule (priority order, first match wins):
--   1. continent_name in (Africa, Asia, Europe, North America, South America,
--      Oceania, Antarctica)            → "continent"
--   2. city is filled & non-empty       → "city"
--   3. region is filled & non-empty     → "state"
--   4. country is filled & non-empty    → "country"
--   5. nothing filled                   → "unknown"
--
-- Why this is safe:
--   - 100% derivable from existing fields (no LLM, no guessing)
--   - Reversible via backup table
--   - Idempotent (running twice produces same result)
--
-- Trigger: auto-fills location_scope on INSERT/UPDATE of city/region/country
-- so newly-extracted locations also land with correct scope going forward.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. Snapshot for rollback
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS article_locations_scope_backup_20260528 AS
SELECT id, location_scope FROM article_locations;

CREATE INDEX IF NOT EXISTS article_locations_scope_backup_20260528_id_idx
  ON article_locations_scope_backup_20260528 (id);

-- ----------------------------------------------------------------------------
-- 2. Helper function (immutable — safe to use in triggers)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION compute_location_scope(
  p_location_text text,
  p_country       text,
  p_region        text,
  p_city          text
) RETURNS text AS $$
DECLARE
  v_norm_text text;
BEGIN
  v_norm_text := LOWER(TRIM(COALESCE(p_location_text, '')));

  -- Tier 1: explicit continent names
  IF v_norm_text IN (
    'africa','asia','europe','north america','south america',
    'oceania','antarctica','eurasia','middle east'
  ) THEN
    RETURN 'continent';
  END IF;

  -- Tier 2: city wins if filled
  IF p_city IS NOT NULL AND TRIM(p_city) != '' THEN
    RETURN 'city';
  END IF;

  -- Tier 3: region/state
  IF p_region IS NOT NULL AND TRIM(p_region) != '' THEN
    RETURN 'state';
  END IF;

  -- Tier 4: country only
  IF p_country IS NOT NULL AND TRIM(p_country) != '' THEN
    RETURN 'country';
  END IF;

  -- Tier 5: nothing populated
  RETURN 'unknown';
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION compute_location_scope IS
  'Derives location_scope from city/region/country/location_text. See migration 074.';

-- ----------------------------------------------------------------------------
-- 3. Trigger: auto-fill on INSERT or UPDATE of relevant columns
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_set_location_scope() RETURNS trigger AS $$
BEGIN
  NEW.location_scope := compute_location_scope(
    NEW.location_text, NEW.country, NEW.region, NEW.city
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_article_locations_scope ON article_locations;
CREATE TRIGGER trg_article_locations_scope
  BEFORE INSERT OR UPDATE OF location_text, country, region, city
  ON article_locations
  FOR EACH ROW EXECUTE FUNCTION trg_set_location_scope();

-- ----------------------------------------------------------------------------
-- 4. One-time backfill
-- ----------------------------------------------------------------------------
UPDATE article_locations
   SET location_scope = compute_location_scope(location_text, country, region, city);

COMMIT;

-- ============================================================================
-- ROLLBACK (if needed):
--   BEGIN;
--     DROP TRIGGER IF EXISTS trg_article_locations_scope ON article_locations;
--     DROP FUNCTION IF EXISTS trg_set_location_scope();
--     DROP FUNCTION IF EXISTS compute_location_scope(text, text, text, text);
--     UPDATE article_locations l
--        SET location_scope = b.location_scope
--       FROM article_locations_scope_backup_20260528 b
--      WHERE l.id = b.id;
--   COMMIT;
-- ============================================================================
