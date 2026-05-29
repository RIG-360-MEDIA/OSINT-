-- ============================================================================
-- Migration 073 — entity_type + article_numbers.unit normalization
-- ============================================================================
-- Problem 1: entity_dictionary.entity_type has 3 spellings of "organization":
--   organization (2,495), org (10), organisation (1)
--
-- Problem 2: article_numbers.unit has many duplicates differing only by
--   singular/plural OR symbol vs code OR formatting:
--     year/years, month/months, day/days, hour/hours, minute/minutes,
--     time/times, person/people, dollars/USD, ₹/INR, %/percent,
--     per cent/percent, kilometre/km
--
-- Strategy:
--   - Snapshot both tables' affected columns to backup tables (reversible)
--   - Single transactional UPDATE per field with clean canonicalization
--   - Idempotent: re-running this migration is safe (matched rows are 0)
--
-- Decisions (what we DON'T merge — left intentionally separate):
--   - crore, lakh, INR, rupees → different magnitudes, keep distinct
--   - currency → generic "some currency", keep distinct
--   - USD, AUD, GBP, NGN, EUR etc → already canonical
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. Snapshots for rollback
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entity_dictionary_type_backup_20260528 AS
SELECT id, entity_type FROM entity_dictionary
 WHERE entity_type IN ('org', 'organisation');

CREATE TABLE IF NOT EXISTS article_numbers_unit_backup_20260528 AS
SELECT id, unit FROM article_numbers
 WHERE unit IN ('year','month','day','hour','minute','time','person',
                'dollars','₹','%','per cent','kilometre');

-- ----------------------------------------------------------------------------
-- 2. Entity-type dedupe (org / organisation → organization)
-- ----------------------------------------------------------------------------
UPDATE entity_dictionary
   SET entity_type = 'organization'
 WHERE entity_type IN ('org', 'organisation');

-- ----------------------------------------------------------------------------
-- 3. Unit normalization (article_numbers.unit)
-- ----------------------------------------------------------------------------
-- Singular → plural (consistency)
UPDATE article_numbers SET unit = 'years'   WHERE unit = 'year';
UPDATE article_numbers SET unit = 'months'  WHERE unit = 'month';
UPDATE article_numbers SET unit = 'days'    WHERE unit = 'day';
UPDATE article_numbers SET unit = 'hours'   WHERE unit = 'hour';
UPDATE article_numbers SET unit = 'minutes' WHERE unit = 'minute';
UPDATE article_numbers SET unit = 'times'   WHERE unit = 'time';
UPDATE article_numbers SET unit = 'people'  WHERE unit = 'person';

-- Symbol → ISO/canonical code
UPDATE article_numbers SET unit = 'USD'     WHERE unit = 'dollars';
UPDATE article_numbers SET unit = 'INR'     WHERE unit = '₹';
UPDATE article_numbers SET unit = 'percent' WHERE unit IN ('%', 'per cent');
UPDATE article_numbers SET unit = 'km'      WHERE unit = 'kilometre';

COMMIT;

-- ============================================================================
-- ROLLBACK procedure (if ever needed):
--   BEGIN;
--     -- Restore entity types
--     UPDATE entity_dictionary e
--        SET entity_type = b.entity_type
--       FROM entity_dictionary_type_backup_20260528 b
--      WHERE e.id = b.id;
--     -- Restore units
--     UPDATE article_numbers n
--        SET unit = b.unit
--       FROM article_numbers_unit_backup_20260528 b
--      WHERE n.id = b.id;
--   COMMIT;
-- ============================================================================
