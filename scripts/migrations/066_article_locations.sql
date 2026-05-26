-- 066_article_locations.sql
-- Structured locations mentioned in each article. Powers the Map lens
-- (4A India scope, world scope), hot-zone heatmap (6B), and cross-state
-- spillover detection. Geocoded to country / region / city granularity
-- with optional lat/lng for map rendering.

BEGIN;

CREATE TABLE IF NOT EXISTS article_locations (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  article_id      uuid NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  location_text   text NOT NULL,        -- as mentioned in the body
  country         text,                  -- ISO-3166 alpha-2 OR display name
  region          text,                  -- state / province / equivalent
  city            text,
  lat             numeric(8,5),
  lng             numeric(8,5),
  confidence      numeric(3,2),          -- 0.00 - 1.00 from extractor
  mention_count   smallint NOT NULL DEFAULT 1,
  is_primary      boolean NOT NULL DEFAULT false,  -- the article's primary geo
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_article_locations_article
  ON article_locations(article_id);
CREATE INDEX IF NOT EXISTS idx_article_locations_country
  ON article_locations(country);
CREATE INDEX IF NOT EXISTS idx_article_locations_region
  ON article_locations(region);
CREATE INDEX IF NOT EXISTS idx_article_locations_city
  ON article_locations(city);
CREATE INDEX IF NOT EXISTS idx_article_locations_geo
  ON article_locations(lat, lng) WHERE lat IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_article_locations_primary
  ON article_locations(article_id) WHERE is_primary;

COMMIT;
