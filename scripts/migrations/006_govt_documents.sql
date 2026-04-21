-- P15 — Government documents as a first-class intelligence source
-- Pipeline: portal scrape → PDF extract → translate → NLP → chunk → embed
-- Mirrors article schema (geo, topic, entities, LaBSE embedding) plus chunk
-- table for RAG search over long documents.

CREATE TABLE IF NOT EXISTS govt_document_sources (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name               TEXT NOT NULL,
    portal_url         TEXT NOT NULL,
    source_geography   TEXT NOT NULL CHECK (
        source_geography IN ('LOCAL', 'CENTRAL', 'NEIGHBOURING', 'INTERNATIONAL')
    ),
    document_type      TEXT NOT NULL,
    scrape_pattern     TEXT,
    is_active          BOOLEAN     DEFAULT TRUE,
    last_scraped_at    TIMESTAMPTZ,
    created_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS govt_documents (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    source_id              UUID REFERENCES govt_document_sources(id),
    source_name            TEXT NOT NULL,
    source_geography       TEXT NOT NULL,
    document_type          TEXT NOT NULL,

    title                  TEXT NOT NULL,
    document_number        TEXT,
    document_url           TEXT NOT NULL UNIQUE,
    published_at           TIMESTAMPTZ,

    full_text              TEXT,
    full_text_translated   TEXT,
    language_detected      TEXT DEFAULT 'en',
    page_count             INTEGER,

    summary                TEXT,
    topic_category         TEXT,
    geo_primary            TEXT,
    entities_extracted     JSONB DEFAULT '[]',

    labse_embedding        vector(768),

    nlp_processed          BOOLEAN     DEFAULT FALSE,
    collected_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at             TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS govt_document_chunks (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id        UUID REFERENCES govt_documents(id) ON DELETE CASCADE,
    chunk_index        INTEGER NOT NULL,
    chunk_text         TEXT NOT NULL,
    chunk_translated   TEXT,
    labse_embedding    vector(768),
    page_number        INTEGER,
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_docs_geography
    ON govt_documents (source_geography);

CREATE INDEX IF NOT EXISTS idx_docs_collected
    ON govt_documents (collected_at DESC);

CREATE INDEX IF NOT EXISTS idx_docs_type
    ON govt_documents (document_type);

CREATE INDEX IF NOT EXISTS idx_docs_embedding
    ON govt_documents
    USING hnsw (labse_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE labse_embedding IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_chunks_embedding
    ON govt_document_chunks
    USING hnsw (labse_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE labse_embedding IS NOT NULL;

-- Seed initial government sources (Priority 1 portals)
INSERT INTO govt_document_sources
    (name, portal_url, source_geography, document_type, is_active)
VALUES
    ('Telangana GO.Ms Portal',  'https://tggovernment.gov.in',     'LOCAL',   'government_order', TRUE),
    ('Telangana High Court',    'https://tshc.gov.in',             'LOCAL',   'court_order',      TRUE),
    ('PIB Press Releases',      'https://pib.gov.in',              'CENTRAL', 'press_release',    TRUE),
    ('CAG India',               'https://cag.gov.in',              'CENTRAL', 'audit_report',     TRUE),
    ('Ministry of Jal Shakti',  'https://jalshakti-dowr.gov.in',   'CENTRAL', 'ministry_order',   TRUE)
ON CONFLICT DO NOTHING;
