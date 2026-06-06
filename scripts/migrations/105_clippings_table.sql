-- 105_clippings_table.sql
-- P16 Cutting Room: newspaper article clippings extracted from CareersWave PDFs.
-- Idempotent: safe to run multiple times.

CREATE TABLE IF NOT EXISTS clippings (
    id                   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    newspaper_source_id  UUID         NOT NULL REFERENCES newspaper_sources(id) ON DELETE CASCADE,
    headline             TEXT         NOT NULL,
    body_text            TEXT,
    section              VARCHAR(100),
    language             VARCHAR(10),
    relevance_score      FLOAT,
    page_number          INT          DEFAULT 1,
    bbox                 TEXT,                   -- JSON string "[x0,y0,x1,y1]"
    edition_date         DATE         NOT NULL,
    collected_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Prevent duplicate clippings for the same headline on the same day from the same paper.
CREATE UNIQUE INDEX IF NOT EXISTS clippings_src_date_headline_key
    ON clippings (newspaper_source_id, edition_date, md5(headline));

CREATE INDEX IF NOT EXISTS clippings_edition_date_idx ON clippings (edition_date DESC);
CREATE INDEX IF NOT EXISTS clippings_language_idx     ON clippings (language);
CREATE INDEX IF NOT EXISTS clippings_relevance_idx    ON clippings (relevance_score DESC);
