-- 041_districts_multitenant.sql
--
-- Phase 6 of the CM Page v2 plan — open the district-resolution spine
-- to a second tenant (Andhra Pradesh). The original 038 migration
-- created the gazetteer table as plain `districts` with an implicit
-- TG default; Phase 6 makes the multi-tenant intent explicit in the
-- schema and adds AP placeholders.
--
-- Idempotent: every ALTER / CREATE guards on existence so a re-run
-- is a no-op. No data is dropped.
--
-- DO NOT touch the FK columns on article_districts / acled_events /
-- weather_warnings / etc — they reference districts(id) by string id
-- which is already tenant-prefixed (e.g. 'hyderabad', 'visakhapatnam'),
-- so this migration is purely additive.

BEGIN;

-- 1. State-code column: nullable add, then default-fill with 'TG' for
--    every row that came from the 038 seed (all Telangana), then NOT
--    NULL the column. Skipped cleanly on re-run.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'districts' AND column_name = 'state_code'
  ) THEN
    ALTER TABLE districts ADD COLUMN state_code TEXT;
    UPDATE districts SET state_code = 'TG' WHERE state_code IS NULL;
    ALTER TABLE districts ALTER COLUMN state_code SET NOT NULL;
    ALTER TABLE districts ADD CONSTRAINT districts_state_code_chk
      CHECK (state_code IN ('TG', 'AP'));
  END IF;
END$$;

-- 2. Index for the per-state district lookup the cm_v2_router does on
--    every atlas / district call.
CREATE INDEX IF NOT EXISTS districts_state_code_idx ON districts (state_code);

-- 3. assembly_constituencies — same story: add state_code, default-fill
--    TG, then NOT NULL. The seed only ever inserted TG rows.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'assembly_constituencies')
     AND NOT EXISTS (
       SELECT 1 FROM information_schema.columns
       WHERE table_name = 'assembly_constituencies' AND column_name = 'state_code'
     )
  THEN
    ALTER TABLE assembly_constituencies ADD COLUMN state_code TEXT;
    UPDATE assembly_constituencies SET state_code = 'TG' WHERE state_code IS NULL;
    ALTER TABLE assembly_constituencies ALTER COLUMN state_code SET NOT NULL;
    ALTER TABLE assembly_constituencies ADD CONSTRAINT ac_state_code_chk
      CHECK (state_code IN ('TG', 'AP'));
  END IF;
END$$;

CREATE INDEX IF NOT EXISTS ac_state_code_idx ON assembly_constituencies (state_code);

-- 4. cm_political_handles — handles already mix TG and AP actors at
--    the demo level; the column gives the read endpoints a clean
--    filter rather than ILIKE'ing on party text.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'cm_political_handles')
     AND NOT EXISTS (
       SELECT 1 FROM information_schema.columns
       WHERE table_name = 'cm_political_handles' AND column_name = 'state_code'
     )
  THEN
    ALTER TABLE cm_political_handles ADD COLUMN state_code TEXT;
    -- BRS / BJP-TG / Cong-TG → TG; YSRCP / TDP / JSP → AP. Anything
    -- else stays NULL and the read endpoints skip it.
    UPDATE cm_political_handles
       SET state_code = CASE
         WHEN UPPER(party) IN ('BRS', 'INC', 'AIMIM') THEN 'TG'
         WHEN UPPER(party) IN ('YSRCP', 'TDP', 'JSP') THEN 'AP'
         ELSE NULL
       END
       WHERE state_code IS NULL;
  END IF;
END$$;

CREATE INDEX IF NOT EXISTS cm_political_handles_state_idx ON cm_political_handles (state_code);

COMMIT;
