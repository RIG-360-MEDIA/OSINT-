-- 091_story_enrichment_structural.sql
-- STEP 3 enrichment, PHASE A (structural) — loader-enrichment-spec §3.
-- ADDITIVE tables keyed by story_id, computed from source rows (computed-not-generated),
-- surfaced-only, run_id-stamped. Core tables untouched. Extraction tables (story_facts/
-- story_quotes/story_stance) ship in a later migration (Phase B), after the divergence design.
--
-- NOTE: the legacy NULL columns on story_clusters (stance_distribution, sentiment,
-- subject_locations, representative_quote, event_type) are DEPRECATED in favor of these
-- tables (single source of truth). Do not wire consumers to those columns.
--
-- Additive + idempotent. FK -> story_clusters(story_id) ON DELETE CASCADE so a re-cluster /
-- orphan-clean drops stale enrichment automatically.

CREATE TABLE IF NOT EXISTS analytics.story_timeline (
  story_id               uuid PRIMARY KEY REFERENCES analytics.story_clusters(story_id) ON DELETE CASCADE,
  first_seen_at          timestamptz,
  last_seen_at           timestamptz,
  peak_at                timestamptz,        -- busiest hour bucket
  peak_articles_per_hour int,
  velocity               numeric,            -- articles/hr over the first 6h (breaking signal)
  span_hours             numeric,
  is_breaking            boolean,
  dormant_since          timestamptz,
  run_id                 bigint,
  computed_at            timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS analytics.story_sources (
  story_id             uuid REFERENCES analytics.story_clusters(story_id) ON DELETE CASCADE,
  source_id            uuid,
  articles_from_source int,
  first_seen_at        timestamptz,          -- per-source first article => pickup latency / who-ran-it-first
  source_tier          text,                 -- (v1: NULL; populated when a source-tier map is wired)
  source_country       text,
  is_canonical_origin  boolean,              -- the source that broke it (earliest first_seen)
  run_id               bigint,
  PRIMARY KEY (story_id, source_id)
);
CREATE INDEX IF NOT EXISTS idx_story_sources_source ON analytics.story_sources(source_id);

CREATE TABLE IF NOT EXISTS analytics.story_geo (
  story_id          uuid PRIMARY KEY REFERENCES analytics.story_clusters(story_id) ON DELETE CASCADE,
  subject_countries jsonb,                   -- [{country, mention_count}] from article geo_primary
  primary_country   text,
  continent         text,                    -- (v1: NULL; needs a country->continent map)
  country_spread    int,
  run_id            bigint
);

-- Coverage status — the data-layer [UNVERIFIED] tag. Lets a consumer tell "no facts found in a
-- well-covered story" from "NLP hasn't processed this story yet". Empty != unknown.
CREATE TABLE IF NOT EXISTS analytics.story_enrichment_status (
  story_id         uuid PRIMARY KEY REFERENCES analytics.story_clusters(story_id) ON DELETE CASCADE,
  members_total    int,
  claims_coverage  numeric,                  -- fraction of members with >=1 article_claims row
  quotes_coverage  numeric,
  stances_coverage numeric,
  geo_coverage     numeric,
  facts_count      int,                      -- populated in Phase B
  quotes_count     int,
  stance_count     int,
  run_id           bigint,
  enriched_at      timestamptz DEFAULT now()
);
