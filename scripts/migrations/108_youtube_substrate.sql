-- ============================================================================
-- Migration 108 — YouTube clips substrate parity
-- ============================================================================
-- Brings youtube_clips_v2 up to article-substrate parity so clips feed the
-- SAME analytics as articles/clippings: structured child tables, entity
-- mapping, and a unified content view.
--
-- DESIGN: follows docs/substrate-integration-playbook.md §4 YouTube checklist.
--
-- ISOLATION:
--   * ADD-only. Never ALTERs articles / article_* / clippings / any shared table.
--   * Clip↔entity links live in their OWN matview (youtube_clip_entity_mentions).
--   * Reads entity_lookup / entity_dictionary (shared, read-mostly).
--
-- Idempotent — safe to re-run.
-- ============================================================================

BEGIN;

-- ── A. Substrate columns on youtube_clips_v2 ────────────────────────────────
-- clip_uuid: stable UUID surrogate used by content_items UNION (youtube_clips_v2.id
-- is BIGINT; the union view requires UUID-compatible ids across all arms).
ALTER TABLE youtube_clips_v2
  ADD COLUMN IF NOT EXISTS clip_uuid          UUID NOT NULL DEFAULT gen_random_uuid();

-- Enrichment fields (filled by the substrate enrichment pass).
ALTER TABLE youtube_clips_v2
  ADD COLUMN IF NOT EXISTS segment_type       VARCHAR(30),  -- debate|interview|speech|press_conference|news_report|panel
  ADD COLUMN IF NOT EXISTS speaker            TEXT,         -- null ok (auto-captions have no speaker labels)
  ADD COLUMN IF NOT EXISTS primary_subject    TEXT,
  ADD COLUMN IF NOT EXISTS topic_category     VARCHAR(20),
  ADD COLUMN IF NOT EXISTS topic_fine         VARCHAR(20),
  ADD COLUMN IF NOT EXISTS entities_extracted JSONB,        -- [{name: canonical}] for matview resolution

  -- Substrate lifecycle (mirror articles.substrate_status / extraction_version)
  ADD COLUMN IF NOT EXISTS substrate_status   VARCHAR(16) NOT NULL DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS extraction_version INTEGER     NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS enriched_at        TIMESTAMPTZ;

COMMENT ON COLUMN youtube_clips_v2.clip_uuid IS
  'UUID surrogate for content_items union view (id column is BIGINT).';
COMMENT ON COLUMN youtube_clips_v2.substrate_status IS
  'pending → processing → ok | extract_failed | junk (mirror of articles.substrate_status)';
COMMENT ON COLUMN youtube_clips_v2.speaker IS
  'null is correct and preferred when auto-captions carry no speaker labels.';

-- Unique index on clip_uuid so it can serve as a stable row identifier.
CREATE UNIQUE INDEX IF NOT EXISTS youtube_clips_v2_clip_uuid_idx
  ON youtube_clips_v2 (clip_uuid);

-- Drain index: cheap "next pending clip" lookup for drain_pending_clips.
CREATE INDEX IF NOT EXISTS youtube_clips_v2_substrate_pending_idx
  ON youtube_clips_v2 (created_at)
  WHERE substrate_status = 'pending';

CREATE INDEX IF NOT EXISTS youtube_clips_v2_topic_fine_idx
  ON youtube_clips_v2 (topic_fine);

-- ── B. Substrate-parity child tables ────────────────────────────────────────
-- Mirror the article_* child tables (FK → youtube_clips_v2.id BIGINT,
-- ON DELETE CASCADE). Clips emit claims/quotes/stances/locations from the
-- TRANSCRIPT_SYS prompt (events/numbers are not in the transcript schema).

CREATE TABLE IF NOT EXISTS youtube_clip_claims (
    id          UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    clip_id     BIGINT  NOT NULL REFERENCES youtube_clips_v2(id) ON DELETE CASCADE,
    claim_text  TEXT    NOT NULL,
    subject_text TEXT,
    predicate   TEXT,
    object_text TEXT,
    confidence  REAL    NOT NULL DEFAULT 0.5,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS youtube_clip_claims_clip_idx ON youtube_clip_claims (clip_id);

CREATE TABLE IF NOT EXISTS youtube_clip_quotes (
    id              UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    clip_id         BIGINT  NOT NULL REFERENCES youtube_clips_v2(id) ON DELETE CASCADE,
    speaker_name    TEXT    NOT NULL,
    quote_text      TEXT    NOT NULL,
    is_direct       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS youtube_clip_quotes_clip_idx ON youtube_clip_quotes (clip_id);

CREATE TABLE IF NOT EXISTS youtube_clip_stances (
    id          UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    clip_id     BIGINT  NOT NULL REFERENCES youtube_clips_v2(id) ON DELETE CASCADE,
    actor       TEXT    NOT NULL,
    target      TEXT,               -- who/what the stance is directed at (YouTube-specific)
    stance      TEXT    NOT NULL DEFAULT 'neutral',
    intensity   NUMERIC NOT NULL DEFAULT 0.5,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS youtube_clip_stances_clip_idx ON youtube_clip_stances (clip_id);

CREATE TABLE IF NOT EXISTS youtube_clip_locations (
    id             UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    clip_id        BIGINT  NOT NULL REFERENCES youtube_clips_v2(id) ON DELETE CASCADE,
    location_text  TEXT    NOT NULL,
    country        TEXT,
    region         TEXT,
    city           TEXT,
    is_primary     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS youtube_clip_locations_clip_idx ON youtube_clip_locations (clip_id);

-- ── C. youtube_clip_entity_mentions matview ──────────────────────────────────
-- Resolves matched_entity (already canonical at insert) → entity_id via
-- entity_lookup. Separate matview keeps clip links OUT of article matviews.
-- Uses matched_entity directly (not entities_extracted JSONB) since it is
-- validated canonical at extraction time — no JSONB traversal needed.
DROP MATERIALIZED VIEW IF EXISTS youtube_clip_entity_mentions CASCADE;

CREATE MATERIALIZED VIEW youtube_clip_entity_mentions AS
SELECT
    yc.id                   AS clip_id,
    el.entity_id,
    ed.canonical_name,
    ed.entity_type,
    ed.country,
    lower(trim(yc.matched_entity)) AS surface_form,
    1                       AS mention_rows
  FROM youtube_clips_v2 yc
  JOIN entity_lookup     el ON el.name_norm = lower(trim(yc.matched_entity))
  JOIN entity_dictionary ed ON ed.id        = el.entity_id;

CREATE UNIQUE INDEX youtube_clip_entity_mentions_pk
  ON youtube_clip_entity_mentions (clip_id, entity_id);
CREATE INDEX youtube_clip_entity_mentions_entity_idx  ON youtube_clip_entity_mentions (entity_id);
CREATE INDEX youtube_clip_entity_mentions_country_idx ON youtube_clip_entity_mentions (country) WHERE country IS NOT NULL;
CREATE INDEX youtube_clip_entity_mentions_type_idx    ON youtube_clip_entity_mentions (entity_type);

COMMENT ON MATERIALIZED VIEW youtube_clip_entity_mentions IS
  'Canonical entity mapping for YouTube clips (matched_entity → entity_id). '
  'Separate from article/clipping matviews — keeps CM metrics article-only.';

CREATE OR REPLACE FUNCTION refresh_youtube_clip_entity_mentions() RETURNS void AS $$
BEGIN
  REFRESH MATERIALIZED VIEW CONCURRENTLY youtube_clip_entity_mentions;
END;
$$ LANGUAGE plpgsql;

-- ── D. content_items — add 'clip' arm ────────────────────────────────────────
-- Extends the articles+clippings union with YouTube clips.
-- clip_uuid (UUID) is used as the id to match the article/clipping UUID arms.
-- Clips with substrate_status='junk'/'extract_failed' are excluded — only
-- clips with useful data (pending/processing/ok) appear.
CREATE OR REPLACE VIEW content_items AS
  SELECT
    a.id,
    'article'::text         AS src,
    a.title                 AS headline,
    a.full_text_scraped     AS body_text,
    a.topic_category,
    a.topic_fine,
    a.language_iso          AS language,
    a.primary_subject,
    a.published_at::date    AS item_date,
    a.entities_extracted,
    a.labse_embedding,
    NULL::double precision  AS relevance_score
  FROM articles a

  UNION ALL

  SELECT
    c.id,
    'clipping'::text        AS src,
    c.headline,
    c.body_text,
    c.topic_category,
    c.topic_fine,
    COALESCE(c.detected_language, c.language) AS language,
    c.primary_subject,
    c.edition_date          AS item_date,
    c.entities_extracted,
    c.labse_embedding,
    c.relevance_score
  FROM clippings c
  WHERE c.is_notice = FALSE AND c.is_duplicate = FALSE

  UNION ALL

  SELECT
    yc.clip_uuid            AS id,
    'clip'::text            AS src,
    yc.video_title          AS headline,
    yc.transcript_segment   AS body_text,
    yc.topic_category,
    yc.topic_fine,
    yc.transcript_language  AS language,
    COALESCE(yc.primary_subject, yc.matched_entity) AS primary_subject,
    yc.video_published_at::date AS item_date,
    yc.entities_extracted,
    yc.labse_embedding,
    yc.relevance_score::double precision
  FROM youtube_clips_v2 yc
  WHERE yc.substrate_status NOT IN ('junk', 'extract_failed');

COMMENT ON VIEW content_items IS
  'Unified articles + clippings + YouTube clips read surface. '
  'src discriminator = article|clipping|clip. '
  'Clippings: no notices/dupes. Clips: no junk/failed. See playbook §4.';

-- Grants for downstream product roles.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analytics_user') THEN
    GRANT SELECT ON youtube_clip_entity_mentions TO analytics_user;
    GRANT SELECT ON content_items TO analytics_user;
    GRANT SELECT ON youtube_clip_claims, youtube_clip_quotes,
                    youtube_clip_stances, youtube_clip_locations
          TO analytics_user;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rigwire_app') THEN
    GRANT SELECT ON youtube_clip_entity_mentions TO rigwire_app;
    GRANT SELECT ON content_items TO rigwire_app;
  END IF;
END$$;

COMMIT;

-- ============================================================================
-- VERIFY:
--   SELECT column_name FROM information_schema.columns WHERE table_name='youtube_clips_v2' ORDER BY ordinal_position;
--   SELECT COUNT(*) FROM youtube_clip_entity_mentions;
--   SELECT src, COUNT(*) FROM content_items GROUP BY src;
-- ROLLBACK (manual):
--   DROP MATERIALIZED VIEW IF EXISTS youtube_clip_entity_mentions CASCADE;
--   CREATE OR REPLACE VIEW content_items AS ... (restore 2-arm articles+clippings version)
--   DROP TABLE IF EXISTS youtube_clip_claims, youtube_clip_quotes,
--                        youtube_clip_stances, youtube_clip_locations CASCADE;
--   (youtube_clips_v2 columns left in place — additive, harmless)
-- ============================================================================
