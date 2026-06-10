-- ============================================================================
-- Migration 107 — clippings substrate parity
-- ============================================================================
-- Brings the newspaper `clippings` table up to article-substrate parity so a
-- clipping ("an article whose body is an OCR'd crop") feeds the SAME analytics
-- as articles: structured child tables, alias-resolved entity mapping, and a
-- unified content view.
--
-- DESIGN: docs/newspaper-clippings-design.md
--
-- ISOLATION (per design §6.1):
--   * ADD-only. Never ALTERs articles / article_* / any substrate table.
--   * Clipping↔entity links live in their OWN matview (clipping_entity_mentions);
--     the article matviews / CM metrics / district rollups stay article-only.
--   * Reads entity_lookup / entity_dictionary (shared, read-mostly) — same as
--     the article path.
--
-- Idempotent — safe to re-run.
-- ============================================================================

BEGIN;

-- ── A. Extraction + provenance columns on clippings ─────────────────────────
-- (the deterministic hybrid-pipeline output + the trust layer)
ALTER TABLE clippings
  ADD COLUMN IF NOT EXISTS subheadline           TEXT,
  ADD COLUMN IF NOT EXISTS byline                 TEXT,
  ADD COLUMN IF NOT EXISTS vision_text            TEXT,
  ADD COLUMN IF NOT EXISTS text_source            VARCHAR(8),   -- ocr | vision | none
  ADD COLUMN IF NOT EXISTS detected_language      VARCHAR(8),
  ADD COLUMN IF NOT EXISTS clip_source            VARCHAR(8),   -- text | body | layout | none
  ADD COLUMN IF NOT EXISTS clipping_image_b64     TEXT,
  ADD COLUMN IF NOT EXISTS extraction_confidence  REAL,
  ADD COLUMN IF NOT EXISTS needs_review           BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS is_notice              BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS is_duplicate           BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS duplicate_of           INTEGER,
  ADD COLUMN IF NOT EXISTS source_pdf_path        TEXT;

-- ── B. Enrichment columns (filled by the SINGLE substrate call) ─────────────
ALTER TABLE clippings
  ADD COLUMN IF NOT EXISTS article_type           VARCHAR(20),
  ADD COLUMN IF NOT EXISTS primary_subject        TEXT,
  ADD COLUMN IF NOT EXISTS headline_translated    TEXT,
  ADD COLUMN IF NOT EXISTS body_text_translated   TEXT,
  ADD COLUMN IF NOT EXISTS summary_preview        TEXT,
  ADD COLUMN IF NOT EXISTS summary_snippet        TEXT,
  ADD COLUMN IF NOT EXISTS summary_executive      TEXT,
  ADD COLUMN IF NOT EXISTS register_style         VARCHAR(20),
  ADD COLUMN IF NOT EXISTS register_emotion       VARCHAR(20),
  ADD COLUMN IF NOT EXISTS register_is_breaking   BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS topic_category         VARCHAR(20),
  ADD COLUMN IF NOT EXISTS topic_fine             VARCHAR(20),
  ADD COLUMN IF NOT EXISTS entities_extracted     JSONB,
  ADD COLUMN IF NOT EXISTS geo_primary            TEXT,
  ADD COLUMN IF NOT EXISTS geo_district           TEXT,
  ADD COLUMN IF NOT EXISTS labse_embedding        VECTOR(768),
  -- Substrate lifecycle (mirror articles.substrate_status / extraction_version)
  ADD COLUMN IF NOT EXISTS substrate_status       VARCHAR(16) NOT NULL DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS extraction_version     INTEGER     NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS enriched_at            TIMESTAMPTZ;

COMMENT ON COLUMN clippings.text_source IS
  'ocr=grounded OCR-in-crop body, vision=unverified Vision retelling, none=unanchored';
COMMENT ON COLUMN clippings.substrate_status IS
  'pending → processing → ok | extract_failed | junk (mirror of articles.substrate_status)';

-- Drain index: cheap "next pending clipping" lookup for enrich_clipping.
CREATE INDEX IF NOT EXISTS clippings_substrate_pending_idx
  ON clippings (collected_at)
  WHERE substrate_status = 'pending';
CREATE INDEX IF NOT EXISTS clippings_topic_fine_idx ON clippings (topic_fine);

-- HNSW for clipping semantic search / cross-paper near-dup.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'clippings_labse_hnsw_idx') THEN
    EXECUTE 'CREATE INDEX clippings_labse_hnsw_idx
             ON clippings USING hnsw (labse_embedding vector_cosine_ops)
             WHERE labse_embedding IS NOT NULL';
  END IF;
END$$;

-- ── C. Substrate-parity child tables ────────────────────────────────────────
-- Mirror the article_* child tables (FK → clippings, ON DELETE CASCADE) so
-- clippings join the same analytics shapes.

CREATE TABLE IF NOT EXISTS clipping_claims (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clipping_id        UUID NOT NULL REFERENCES clippings(id) ON DELETE CASCADE,
    claim_text         TEXT NOT NULL,
    subject_entity_id  UUID REFERENCES entity_dictionary(id),
    subject_text       TEXT,
    predicate          TEXT,
    object_text        TEXT,
    confidence         REAL NOT NULL DEFAULT 0.5,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS clipping_claims_clip_idx ON clipping_claims (clipping_id);

CREATE TABLE IF NOT EXISTS clipping_quotes (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clipping_id        UUID NOT NULL REFERENCES clippings(id) ON DELETE CASCADE,
    speaker_name       TEXT NOT NULL,
    speaker_entity_id  UUID REFERENCES entity_dictionary(id),
    quote_text         TEXT NOT NULL,
    is_direct          BOOLEAN NOT NULL DEFAULT TRUE,
    context            TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS clipping_quotes_clip_idx ON clipping_quotes (clipping_id);

CREATE TABLE IF NOT EXISTS clipping_stances (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clipping_id     UUID NOT NULL REFERENCES clippings(id) ON DELETE CASCADE,
    actor           TEXT NOT NULL,
    stance          TEXT NOT NULL DEFAULT 'neutral',
    intensity       NUMERIC NOT NULL DEFAULT 0.5,
    actor_entity_id UUID REFERENCES entity_dictionary(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS clipping_stances_clip_idx ON clipping_stances (clipping_id);

CREATE TABLE IF NOT EXISTS clipping_locations (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clipping_id    UUID NOT NULL REFERENCES clippings(id) ON DELETE CASCADE,
    location_text  TEXT NOT NULL,
    country        TEXT,
    region         TEXT,
    city           TEXT,
    lat            NUMERIC,
    lng            NUMERIC,
    confidence     NUMERIC NOT NULL DEFAULT 0.85,
    is_primary     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS clipping_locations_clip_idx ON clipping_locations (clipping_id);

CREATE TABLE IF NOT EXISTS clipping_events (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clipping_id        UUID NOT NULL REFERENCES clippings(id) ON DELETE CASCADE,
    event_date         DATE,
    event_description  TEXT NOT NULL,
    event_type         TEXT,
    actors             TEXT[] NOT NULL DEFAULT '{}',
    confidence         NUMERIC NOT NULL DEFAULT 0.8,
    position           SMALLINT,
    is_future          BOOLEAN NOT NULL DEFAULT FALSE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS clipping_events_clip_idx ON clipping_events (clipping_id);

CREATE TABLE IF NOT EXISTS clipping_numbers (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clipping_id  UUID NOT NULL REFERENCES clippings(id) ON DELETE CASCADE,
    value        TEXT NOT NULL,
    unit         TEXT,
    context      TEXT,
    position     SMALLINT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS clipping_numbers_clip_idx ON clipping_numbers (clipping_id);

-- ── D. clipping_entity_mentions matview (mirror of article_entity_mentions) ──
-- Resolves entities_extracted surface forms → canonical entity_id via
-- entity_lookup (migration 081). Separate matview keeps clipping links OUT of
-- the article matviews (design §6.1).
DROP MATERIALIZED VIEW IF EXISTS clipping_entity_mentions CASCADE;

CREATE MATERIALIZED VIEW clipping_entity_mentions AS
SELECT
    c.id                                              AS clipping_id,
    el.entity_id,
    ed.canonical_name,
    ed.entity_type,
    ed.country,
    array_agg(DISTINCT lower(trim(e.elem->>'name')))  AS surface_forms,
    COUNT(*)                                          AS mention_rows
  FROM clippings c
  CROSS JOIN LATERAL jsonb_array_elements(c.entities_extracted) AS e(elem)
  JOIN entity_lookup     el ON el.name_norm = lower(trim(e.elem->>'name'))
  JOIN entity_dictionary ed ON ed.id        = el.entity_id
 WHERE c.entities_extracted IS NOT NULL
   AND jsonb_typeof(c.entities_extracted) = 'array'
 GROUP BY c.id, el.entity_id, ed.canonical_name, ed.entity_type, ed.country;

CREATE UNIQUE INDEX clipping_entity_mentions_pk
  ON clipping_entity_mentions (clipping_id, entity_id);
CREATE INDEX clipping_entity_mentions_entity_idx  ON clipping_entity_mentions (entity_id);
CREATE INDEX clipping_entity_mentions_country_idx ON clipping_entity_mentions (country) WHERE country IS NOT NULL;
CREATE INDEX clipping_entity_mentions_type_idx    ON clipping_entity_mentions (entity_type);

COMMENT ON MATERIALIZED VIEW clipping_entity_mentions IS
  'Alias-resolved clipping<->entity mapping (mirror of article_entity_mentions). '
  'Kept separate so article matviews / CM metrics stay article-only.';

CREATE OR REPLACE FUNCTION refresh_clipping_entity_mentions() RETURNS void AS $$
BEGIN
  REFRESH MATERIALIZED VIEW CONCURRENTLY clipping_entity_mentions;
END;
$$ LANGUAGE plpgsql;

-- ── E. content_items — unified read view (articles + clippings) ─────────────
-- Any consumer (Brief, Analyst RAG, relevance feed, story clustering) queries
-- ONE place and gets both, discriminated by `src`. Same-entity links + shared
-- LaBSE space mean cross-source queries span both automatically.
CREATE OR REPLACE VIEW content_items AS
  SELECT
    a.id,
    'article'::text        AS src,
    a.title                AS headline,
    a.full_text_scraped    AS body_text,
    a.topic_category,
    a.topic_fine,
    a.language_iso         AS language,
    a.primary_subject,
    a.published_at::date   AS item_date,
    a.entities_extracted,
    a.labse_embedding,
    NULL::double precision AS relevance_score   -- articles score per-user, not on-row
  FROM articles a
  UNION ALL
  SELECT
    c.id,
    'clipping'::text       AS src,
    c.headline,
    c.body_text,
    c.topic_category,
    c.topic_fine,
    COALESCE(c.detected_language, c.language) AS language,
    c.primary_subject,
    c.edition_date         AS item_date,
    c.entities_extracted,
    c.labse_embedding,
    c.relevance_score
  FROM clippings c
  WHERE c.is_notice = FALSE AND c.is_duplicate = FALSE;

COMMENT ON VIEW content_items IS
  'Unified articles + clippings read surface. src discriminator = article|clipping. '
  'Clippings filtered to real news (no notices/teasers). See design §6.5.';

-- Grants for downstream product roles (belt + braces; mirror migration 082).
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analytics_user') THEN
    GRANT SELECT ON clipping_entity_mentions TO analytics_user;
    GRANT SELECT ON content_items TO analytics_user;
    GRANT SELECT ON clipping_claims, clipping_quotes, clipping_stances,
                    clipping_locations, clipping_events, clipping_numbers
          TO analytics_user;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rigwire_app') THEN
    GRANT SELECT ON clipping_entity_mentions TO rigwire_app;
    GRANT SELECT ON content_items TO rigwire_app;
  END IF;
END$$;

COMMIT;

-- ============================================================================
-- VERIFY:
--   SELECT column_name FROM information_schema.columns WHERE table_name='clippings';
--   SELECT COUNT(*) FROM clipping_entity_mentions;
--   SELECT src, COUNT(*) FROM content_items GROUP BY src;
-- ROLLBACK (manual):
--   DROP MATERIALIZED VIEW IF EXISTS clipping_entity_mentions CASCADE;
--   DROP VIEW IF EXISTS content_items;
--   DROP TABLE IF EXISTS clipping_claims, clipping_quotes, clipping_stances,
--                        clipping_locations, clipping_events, clipping_numbers CASCADE;
--   (clippings columns left in place — additive, harmless)
-- ============================================================================
