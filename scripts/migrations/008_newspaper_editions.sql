-- 008_newspaper_editions.sql
--
-- Caches the per-paper-per-day Drive URL resolved by the careerswave scraper
-- so the Cuttings page can stream the full PDF on demand without hammering
-- careerswave on every "Full edition" click. See plan: Cuttings Newsstand redesign.

CREATE TABLE IF NOT EXISTS newspaper_editions (
    newspaper_id  UUID NOT NULL REFERENCES newspaper_sources(id) ON DELETE CASCADE,
    edition_date  DATE NOT NULL,
    pdf_url       TEXT NOT NULL,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (newspaper_id, edition_date)
);

CREATE INDEX IF NOT EXISTS idx_editions_recent
    ON newspaper_editions (edition_date DESC);
