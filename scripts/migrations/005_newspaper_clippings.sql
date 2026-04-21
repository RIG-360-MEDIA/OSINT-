-- P16 Cutting Room — Newspaper clippings pipeline
-- Sources: CareersWave.in PDF directory
-- Extraction: OpenDataLoader PDF (hybrid) with PyMuPDF fallback
-- Display: Visual clippings cropped to article bounding box

CREATE TABLE IF NOT EXISTS newspaper_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    careerswave_url TEXT,
    direct_pdf_url TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    last_scraped_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS newspaper_clippings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Source
    newspaper_id UUID REFERENCES newspaper_sources(id),
    newspaper_name TEXT NOT NULL,
    newspaper_language TEXT DEFAULT 'en',
    edition_date DATE NOT NULL,
    page_number INTEGER,

    -- Article content
    headline TEXT,
    headline_translated TEXT,
    article_text TEXT,
    article_text_translated TEXT,

    -- Visual clipping bounding box (PDF points, [left, bottom, right, top])
    bbox_left FLOAT,
    bbox_bottom FLOAT,
    bbox_right FLOAT,
    bbox_top FLOAT,

    -- Rendered clipping image (base64 PNG)
    clipping_image_b64 TEXT,

    -- Intelligence
    topic_category TEXT,
    geo_primary TEXT,
    entities_extracted JSONB DEFAULT '[]',
    relevance_score FLOAT,
    relevance_explanation TEXT,
    labse_embedding vector(768),

    -- Narrative analysis
    sentiment TEXT,
    narrative_angle TEXT,

    -- Processing
    collected_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(newspaper_id, edition_date, headline)
);

CREATE INDEX IF NOT EXISTS idx_clippings_date
    ON newspaper_clippings(edition_date DESC);

CREATE INDEX IF NOT EXISTS idx_clippings_newspaper
    ON newspaper_clippings(newspaper_id);

CREATE INDEX IF NOT EXISTS idx_clippings_embedding
    ON newspaper_clippings
    USING hnsw (labse_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE labse_embedding IS NOT NULL;

-- Seed Telugu and English newspapers
INSERT INTO newspaper_sources (name, language, careerswave_url, is_active)
VALUES
    ('Eenadu', 'te',
     'https://www.careerswave.in/eenadu-epaper-pdf-free-download/',
     TRUE),
    ('Sakshi', 'te',
     'https://www.careerswave.in/sakshi-epaper-pdf-free-download/',
     TRUE),
    ('Telangana Today', 'en',
     'https://www.careerswave.in/telangana-today-epaper-pdf-free-download/',
     TRUE),
    ('The Hindu', 'en',
     'https://www.careerswave.in/the-hindu-epaper-pdf-free-download/',
     TRUE),
    ('Deccan Chronicle', 'en',
     'https://www.careerswave.in/deccan-chronicle-epaper-pdf-free-download/',
     TRUE),
    ('Times of India', 'en',
     'https://www.careerswave.in/times-of-india-epaper-pdf-free-download/',
     TRUE)
ON CONFLICT DO NOTHING;
