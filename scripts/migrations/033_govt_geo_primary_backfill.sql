-- 033_govt_geo_primary_backfill.sql
--
-- Phase 9 audit fix: 224 of 233 existing govt_documents rows have
-- geo_primary = NULL because the pre-fix collector wrote whatever
-- tag_geography returned, including NULL when the geocoder bailed.
-- D-14 patches new inserts; this migration backfills the existing rows
-- by falling back to the row's source_geography (CENTRAL/LOCAL/...).
--
-- Idempotent: re-running is a no-op once geo_primary is populated.

BEGIN;

UPDATE govt_documents
SET    geo_primary = source_geography,
       updated_at  = NOW()
WHERE  geo_primary IS NULL
  AND  source_geography IS NOT NULL;

-- Track how many rows were healed for the deploy log.
DO $$
DECLARE
    healed integer;
BEGIN
    SELECT count(*) INTO healed
    FROM   govt_documents
    WHERE  geo_primary = source_geography
      AND  updated_at > NOW() - INTERVAL '1 minute';
    RAISE NOTICE 'govt_documents geo_primary backfill: % rows healed', healed;
END $$;

COMMIT;
