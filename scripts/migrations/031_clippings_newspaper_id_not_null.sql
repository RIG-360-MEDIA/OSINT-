-- 031_clippings_newspaper_id_not_null.sql
--
-- Defect D1 (Cuttings audit, 2026-04-28).
-- newspaper_clippings.newspaper_id is the FK back to newspaper_sources;
-- every clipping must come from a known source. The original migration
-- (005_newspaper_clippings.sql) left it nullable, which (a) silently
-- weakened the UNIQUE (newspaper_id, edition_date, headline) constraint
-- because NULLs do not collide, and (b) allowed orphan rows that the
-- /papers and /feed queries can never surface.
--
-- Verified before applying: production has zero NULL newspaper_id rows
-- (557/557 populated as of 2026-04-28). Migration is therefore a
-- no-data-loss tightening.
--
-- D2 (TEXT enums on topic_category / geo_primary) and D3 (nullable
-- labse_embedding backfill) are deferred — see docs/qa/cuttings-audit-report.md.

DO $$
BEGIN
    -- Idempotency guard: only run if the column is still nullable.
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'newspaper_clippings'
          AND column_name  = 'newspaper_id'
          AND is_nullable  = 'YES'
    ) THEN
        -- Belt-and-braces: refuse to tighten if NULL rows somehow exist.
        IF EXISTS (
            SELECT 1 FROM newspaper_clippings WHERE newspaper_id IS NULL
        ) THEN
            RAISE EXCEPTION
                'Cannot apply 031: % NULL newspaper_id rows present',
                (SELECT COUNT(*) FROM newspaper_clippings WHERE newspaper_id IS NULL);
        END IF;

        ALTER TABLE newspaper_clippings
            ALTER COLUMN newspaper_id SET NOT NULL;
    END IF;
END $$;
