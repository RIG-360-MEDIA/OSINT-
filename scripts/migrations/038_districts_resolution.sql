-- 038_districts_resolution.sql
-- CM Page v2 — district-level resolution layer.
--
-- This is the spine for the new CM atlas + district-modal endpoints.
-- Strictly ADDITIVE: every new table is independent of existing CM
-- tables. Nothing here modifies `articles`, `social_posts`,
-- `cm_*`, `assembly_constituencies`, or any existing materialized
-- view.
--
-- What this adds:
--   - districts                — 33-row gazetteer (Telangana for v1).
--                                Multi-tenant ready via state_code.
--   - article_districts        — N:N between articles and districts.
--                                Tagged by tasks.cm.backfill_district_geo
--                                (one-shot) + tasks.cm.tag_article_districts
--                                (live, hooked into nlp_processor in a
--                                follow-up).
--   - social_post_districts    — N:N for social_posts.
--   - acled_events             — sink for the ACLED feed (no historical
--                                storage existed before; worldmonitor
--                                currently fetches live per request).
--
-- What this DOES NOT do:
--   - Doesn't seed `districts`. Apply scripts/seeds/districts_telangana.sql
--     after this migration runs.
--   - Doesn't add a geo_normalize lookup. Migration 032 already backfilled
--     state codes via _STATE_GEO_NEEDLE in cm_queries.py. State-level
--     filtering already works; this layer adds district granularity.
--   - Doesn't touch `video_clips` (known `youtube_clips` ↔ `video_clips`
--     schema mismatch per QA report — clip_districts deferred to a follow-up
--     after that schema is reconciled).
--   - Doesn't touch `govt_documents` (will get document_districts in a
--     follow-up — govt docs already have geo_primary via migration 033, so
--     district resolution is straightforward but not blocking the v1 page).
--
-- Apply via:
--   docker exec -i rig-postgres psql -U rig -d rig \
--     < scripts/migrations/038_districts_resolution.sql

-- ── 1. districts gazetteer ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS districts (
    id            TEXT        PRIMARY KEY,            -- 'karimnagar', 'hyderabad', ...
    state_code    TEXT        NOT NULL,               -- 'TG' / 'AP' / ...
    name          TEXT        NOT NULL,               -- 'KARIMNAGAR' (display)
    hq_city       TEXT        NOT NULL,
    centroid_lat  DOUBLE PRECISION NOT NULL,
    centroid_lon  DOUBLE PRECISION NOT NULL,
    bbox          JSONB,                              -- {minLat, maxLat, minLon, maxLon}
    aliases       TEXT[]      NOT NULL DEFAULT '{}',  -- alternate names matched during NER lookup
    inserted_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS districts_state_idx
    ON districts (state_code, id);

COMMENT ON TABLE districts IS
  'CM Page v2: 33-row gazetteer. Aggregation grain for the atlas heatmap.';

-- ── 2. article_districts (N:N) ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS article_districts (
    article_id    UUID        NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    district_id   TEXT        NOT NULL REFERENCES districts(id) ON DELETE CASCADE,
    mention_count INTEGER     NOT NULL DEFAULT 1 CHECK (mention_count > 0),
    confidence    REAL        NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    is_primary    BOOLEAN     NOT NULL DEFAULT FALSE,
    inserted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (article_id, district_id)
);

CREATE INDEX IF NOT EXISTS article_districts_district_idx
    ON article_districts (district_id, inserted_at DESC);

CREATE INDEX IF NOT EXISTS article_districts_primary_idx
    ON article_districts (district_id, is_primary)
    WHERE is_primary = TRUE;

COMMENT ON TABLE article_districts IS
  'CM Page v2: many-to-many. One article can hit multiple districts; '
  'is_primary flags the highest-confidence district per article.';

-- ── 3. social_post_districts (N:N) ───────────────────────────────────────

CREATE TABLE IF NOT EXISTS social_post_districts (
    post_id       UUID        NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
    district_id   TEXT        NOT NULL REFERENCES districts(id) ON DELETE CASCADE,
    mention_count INTEGER     NOT NULL DEFAULT 1 CHECK (mention_count > 0),
    confidence    REAL        NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    is_primary    BOOLEAN     NOT NULL DEFAULT FALSE,
    inserted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (post_id, district_id)
);

CREATE INDEX IF NOT EXISTS social_post_districts_district_idx
    ON social_post_districts (district_id, inserted_at DESC);

COMMENT ON TABLE social_post_districts IS
  'CM Page v2: per-district tagging for Reddit / Telegram posts. '
  'Twitter is intentionally hidden from UI per memory note but the data '
  'layer remains live, so this table covers all platforms in social_posts.';

-- ── 4. acled_events (historical sink) ────────────────────────────────────

CREATE TABLE IF NOT EXISTS acled_events (
    event_id     TEXT        PRIMARY KEY,             -- ACLED-supplied id
    event_date   DATE        NOT NULL,
    event_type   TEXT        NOT NULL,
    sub_type     TEXT,
    actor1       TEXT,
    actor2       TEXT,
    fatalities   INTEGER     NOT NULL DEFAULT 0 CHECK (fatalities >= 0),
    lat          DOUBLE PRECISION,
    lon          DOUBLE PRECISION,
    state_code   TEXT,                                 -- 'TG' / 'AP' / ...
    district_id  TEXT        REFERENCES districts(id) ON DELETE SET NULL,
    notes        TEXT,
    raw          JSONB,                                -- full ACLED payload for replay
    inserted_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS acled_district_date_idx
    ON acled_events (district_id, event_date DESC);

CREATE INDEX IF NOT EXISTS acled_state_date_idx
    ON acled_events (state_code, event_date DESC);

CREATE INDEX IF NOT EXISTS acled_recent_idx
    ON acled_events (event_date DESC);

COMMENT ON TABLE acled_events IS
  'CM Page v2: ACLED feed sink. Populated by tasks.collectors.acled_sink '
  '(every 6h). Worldmonitor router still fetches live for its briefing; '
  'this table powers the atlas ACLED layer and the district modal panel.';

-- ── 5. district-tagging cursor (resumable backfill state) ────────────────

CREATE TABLE IF NOT EXISTS district_geo_backfill_cursor (
    surface        TEXT        PRIMARY KEY,           -- 'articles' / 'social_posts'
    last_processed UUID,
    rows_done      BIGINT      NOT NULL DEFAULT 0,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE district_geo_backfill_cursor IS
  'CM Page v2: resumable cursor for backfill_district_geo. One row per '
  'surface so the task can pick up after a crash.';
