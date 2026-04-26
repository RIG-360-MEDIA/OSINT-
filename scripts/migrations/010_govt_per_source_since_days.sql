-- 010_govt_per_source_since_days.sql
--
-- Adds a per-source since_days override so adapters can declare their
-- own collection window. Daily-cadence portals (RBI press releases,
-- court orders, parliament Q&A) keep the global default of 30 days.
-- Annual / quarterly portals (CAG audit reports, indiabudget,
-- NITI annual reports) get a wider window so we don't drop content
-- that's older than 30 days.
--
-- Behaviour: NULL = inherit GOVT_DEFAULT_SINCE_DAYS env var
--            integer = override (capped at 365 in the orchestrator)

ALTER TABLE govt_document_sources
    ADD COLUMN IF NOT EXISTS since_days_override INT NULL;

-- Wide-window sources (publish quarterly/annually). Bump to 365 so we
-- get last fiscal year's content.
UPDATE govt_document_sources
SET since_days_override = 365
WHERE name IN (
    'CAG India',                -- audit reports, quarterly
    'MoF Notifications',        -- Union Budget docs, annual
    'NITI Aayog Reports',       -- policy papers, quarterly
    'World Bank India',         -- country reports, quarterly
    'IMF India Reports',        -- Article IV, annual
    'ADB India',                -- country strategy papers, annual
    'TS Gazette',               -- gazette volumes, low frequency
    'PRS Bill Tracker'          -- session-bound, not daily
);

-- Daily-cadence sources keep NULL (= 30d default) — no UPDATE needed.

-- Comment column for future readers
COMMENT ON COLUMN govt_document_sources.since_days_override IS
    'NULL = use GOVT_DEFAULT_SINCE_DAYS env var. Set to override per-source.';
