-- ============================================================================
-- Migration 078 — entity_dictionary cleanup + country/source columns + trigram
-- ============================================================================
-- Four operations, safe and reversible:
--
--   0. Alter FKs on article_claims / article_quotes / article_stances from
--      ON DELETE NO ACTION to ON DELETE SET NULL — so deleting garbage
--      entity rows doesn't fail when an article_stance happens to point at
--      a date-string row.
--
--   1. Add `country` (ISO 3166-1 alpha-2) + `source` (provenance) columns
--
--   2. Snapshot then delete garbage rows (numbers, dates, stock tickers,
--      sentences, generic placeholder words)
--
--   3. Install pg_trgm extension + GIN trigram index on canonical_name to
--      make the async FK backfill (scripts/maintenance/backfill_entity_fks.py)
--      run fast.
--
-- Reversible via entity_dictionary_pre078_backup table.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 0. Relax FKs to ON DELETE SET NULL
--    Drop + re-add. Each is a single-statement DDL; idempotent.
-- ----------------------------------------------------------------------------
ALTER TABLE article_claims
  DROP CONSTRAINT IF EXISTS article_claims_subject_entity_id_fkey,
  ADD  CONSTRAINT article_claims_subject_entity_id_fkey
       FOREIGN KEY (subject_entity_id) REFERENCES entity_dictionary(id) ON DELETE SET NULL;

ALTER TABLE article_quotes
  DROP CONSTRAINT IF EXISTS article_quotes_speaker_entity_id_fkey,
  ADD  CONSTRAINT article_quotes_speaker_entity_id_fkey
       FOREIGN KEY (speaker_entity_id) REFERENCES entity_dictionary(id) ON DELETE SET NULL;

ALTER TABLE article_stances
  DROP CONSTRAINT IF EXISTS article_stances_actor_entity_id_fkey,
  ADD  CONSTRAINT article_stances_actor_entity_id_fkey
       FOREIGN KEY (actor_entity_id) REFERENCES entity_dictionary(id) ON DELETE SET NULL;

-- ----------------------------------------------------------------------------
-- 1. Snapshot for rollback
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS entity_dictionary_pre078_backup;
CREATE TABLE entity_dictionary_pre078_backup AS
SELECT * FROM entity_dictionary;

CREATE INDEX entity_dictionary_pre078_backup_id_idx
  ON entity_dictionary_pre078_backup (id);

-- ----------------------------------------------------------------------------
-- 2. Add country + source columns
-- ----------------------------------------------------------------------------
ALTER TABLE entity_dictionary
  ADD COLUMN IF NOT EXISTS country CHAR(2),       -- ISO 3166-1 alpha-2; NULL = unknown/global
  ADD COLUMN IF NOT EXISTS source  TEXT;          -- provenance: 'seed:us_v1', 'llm_extracted', 'wikidata', etc.

COMMENT ON COLUMN entity_dictionary.country IS
  'ISO 3166-1 alpha-2 country code. NULL = unknown/global. Use sources.country style.';
COMMENT ON COLUMN entity_dictionary.source  IS
  'Provenance tag (e.g. seed:us_v1, llm_extracted, wikidata). Lets us re-seed or audit by source.';

-- Backfill: rows with state populated are Indian (the only state-set legacy)
UPDATE entity_dictionary SET country = 'IN'
 WHERE country IS NULL AND state IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 3. Clean garbage rows  (now safe — FKs are ON DELETE SET NULL)
-- ----------------------------------------------------------------------------

-- 3a) Pure number rows (vote counts, populations, etc.)
DELETE FROM entity_dictionary
 WHERE canonical_name ~ '^[\d,.\s]+$';

-- 3b) Date-pattern rows (e.g. "22 June 2015", "2024-06-04")
DELETE FROM entity_dictionary
 WHERE canonical_name ~* '^\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}$'
    OR canonical_name ~  '^\d{4}-\d{2}-\d{2}$';

-- 3c) Stock ticker rows (e.g. ULTRACEMCO.BO, RELIANCE.NS)
DELETE FROM entity_dictionary
 WHERE canonical_name ~ '^[A-Z][A-Z0-9]*\.(BO|NS|BSE|NSE|N|L|HK|SS|SZ|TO|AX|F|DE|PA|MI|MC|ST|SW|OL|HE)$';

-- 3d) Long sentences (≥7 words is almost never an entity)
DELETE FROM entity_dictionary
 WHERE array_length(string_to_array(trim(canonical_name), ' '), 1) >= 7;

-- 3e) Generic placeholder words the LLM uses as fillers
DELETE FROM entity_dictionary
 WHERE LOWER(canonical_name) IN (
   'article','this','it','they','them','none','other','the article',
   'unknown','n/a','na','null'
 );

-- 3f) Empty / whitespace-only rows
DELETE FROM entity_dictionary
 WHERE TRIM(COALESCE(canonical_name, '')) = '';

-- ----------------------------------------------------------------------------
-- 4. Trigram extension + indexes for fast fuzzy matching
-- ----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS entity_dictionary_name_trgm_idx
  ON entity_dictionary USING gin (canonical_name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS entity_dictionary_name_lower_trgm_idx
  ON entity_dictionary USING gin (lower(canonical_name) gin_trgm_ops);

CREATE INDEX IF NOT EXISTS entity_dictionary_country_idx
  ON entity_dictionary (country) WHERE country IS NOT NULL;

CREATE INDEX IF NOT EXISTS entity_dictionary_type_country_idx
  ON entity_dictionary (entity_type, country);

COMMIT;

-- ============================================================================
-- VERIFICATION
-- ============================================================================
--   SELECT 'before', COUNT(*) FROM entity_dictionary_pre078_backup
--   UNION ALL SELECT 'after',  COUNT(*) FROM entity_dictionary;
--   SELECT country, entity_type, COUNT(*) FROM entity_dictionary
--    GROUP BY 1,2 ORDER BY 1 NULLS FIRST, 2;
-- ============================================================================
-- ROLLBACK
-- ============================================================================
--   BEGIN;
--     TRUNCATE entity_dictionary;
--     INSERT INTO entity_dictionary SELECT * FROM entity_dictionary_pre078_backup;
--     ALTER TABLE entity_dictionary DROP COLUMN IF EXISTS country;
--     ALTER TABLE entity_dictionary DROP COLUMN IF EXISTS source;
--   COMMIT;
-- ============================================================================
