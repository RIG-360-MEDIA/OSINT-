-- Migration 089 — Story Layer (current-state) for Worldwide + OSINT clustering.
-- Ratifies rig-news/docs/plans/story-clusters-schema-2026-05-30.md.
--
-- §4 decision (2026-05-31): CURRENT-STATE (story_id PK, no bitemporal versioning).
--   Point-in-time reconstruction stays available later by RECOMPUTE (immutable
--   collected_at corpus + deterministic embeddings + clock-injectable job +
--   recorded algo_version), or by adding a snapshot table additively. Choosing
--   current-state forecloses nothing and is kind to the 15 GB box.
--
-- Ratified corrections vs the proposal (verified against live DB 2026-05-31):
--   * members.source_id is uuid  (live sources.id / articles.source_id are uuid), NOT bigint.
--   * sentiment column kept (jsonb NULL) but stays UNPOPULATED — there is no
--     article-level sentiment source in the corpus today.
--   * stance_distribution carries the FULL stance set (article_stances has 8
--     values: neutral/supportive/critical/sympathetic/promotional/defensive/
--     admiration/mocking), not only {critical,neutral,supportive}.
--
-- Lives in analytics (shared cross-product schema). rig-created tables; granted
-- to analytics_user (RW) and rigwire_app (SELECT) to match migrations 076/078/080.

BEGIN;

-- 1. story_clusters — one row per story --------------------------------------
CREATE TABLE IF NOT EXISTS analytics.story_clusters (
    story_id                  uuid PRIMARY KEY,            -- opaque, STABLE across runs
    created_at                timestamptz NOT NULL DEFAULT now(),
    updated_at                timestamptz NOT NULL DEFAULT now(),
    -- lifecycle / stability
    status                    text NOT NULL DEFAULT 'active',   -- active|dormant|archived|merged
    redirected_to             uuid NULL REFERENCES analytics.story_clusters(story_id),
    provisional               boolean NOT NULL DEFAULT false,   -- incremental-attach, not rebuild-confirmed
    run_id                    bigint NOT NULL,                  -- clustering run that last wrote it
    algo_version              text NOT NULL,
    -- time span (OUR clock = collected_at, not feed published_at)
    first_seen_at             timestamptz NOT NULL,
    last_seen_at              timestamptz NOT NULL,
    as_of                     timestamptz NOT NULL,             -- effective clock of the run (now_sim()-aware)
    -- size & sources
    article_count             int NOT NULL DEFAULT 0,
    source_count              int NOT NULL DEFAULT 0,           -- distinct sources after copy-collapse
    independent_source_count  int NULL,                         -- = source_count until ownership map lands (Phase 2)
    -- subject (neutral corpus facts)
    subject_country           text NULL,
    subject_region            text NULL,                        -- continent; NULL => unscoped
    subject_locations         jsonb NULL,                       -- [{country, mention_count}]
    topic                     text NULL,                        -- <- articles.topic_category
    event_type                text NULL,                        -- dominant article_events.event_type
    primary_entities          jsonb NULL,                       -- [{entity_id,name,type,prominence}]
    languages                 jsonb NULL,                       -- {lang: count} from language_iso
    -- rollups
    stance_distribution       jsonb NULL,                       -- {stance: count} full set (article_stances.stance)
    sentiment                 jsonb NULL,                       -- NO article-level source yet -> stays NULL
    representative_quote      jsonb NULL,                       -- {quote_text, quote_text_en, speaker_name, article_id}
    importance_score          numeric NULL,                     -- composite (Phase 2.1); NOT the 3.11 default
    -- representative member (cheap display label)
    representative_article_id uuid NULL,
    representative_title      text NULL
);

-- 2. story_cluster_members — article -> story (hard assignment) ---------------
CREATE TABLE IF NOT EXISTS analytics.story_cluster_members (
    article_id        uuid PRIMARY KEY,                          -- one story per article (hard assignment)
    story_id          uuid NOT NULL REFERENCES analytics.story_clusters(story_id) ON DELETE CASCADE,
    source_id         uuid NULL,                                 -- uuid (ratified); denormalised for source_count
    is_representative boolean NOT NULL DEFAULT false,
    is_canonical      boolean NOT NULL DEFAULT true,             -- canonical node of a wire-copy set
    attach_score      numeric NULL,
    provisional       boolean NOT NULL DEFAULT false,
    added_at          timestamptz NOT NULL DEFAULT now(),
    run_id            bigint NOT NULL
    -- copies resolve via public.articles.duplicate_of; we store canonical nodes.
    -- No cross-schema FK to public.articles (kept decoupled, matches pair_scores/dup_golden).
);

-- 3. story_edges — confirmed graph (audit + relatedness) ---------------------
CREATE TABLE IF NOT EXISTS analytics.story_edges (
    article_a   uuid NOT NULL,            -- stored ordered (a < b) to dedupe
    article_b   uuid NOT NULL,
    score       numeric NOT NULL,
    decided_by  text NOT NULL,            -- 'scorer-high' | 'judge-yes'
    run_id      bigint NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (article_a, article_b),
    CHECK (article_a < article_b)
);
-- analytics.pair_scores is reused UNCHANGED as the feature table.

-- 5. indexes -----------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_story_clusters_region     ON analytics.story_clusters (subject_region);
CREATE INDEX IF NOT EXISTS idx_story_clusters_country    ON analytics.story_clusters (subject_country);
CREATE INDEX IF NOT EXISTS idx_story_clusters_topic      ON analytics.story_clusters (topic);
CREATE INDEX IF NOT EXISTS idx_story_clusters_importance ON analytics.story_clusters (importance_score DESC);
CREATE INDEX IF NOT EXISTS idx_story_clusters_lastseen   ON analytics.story_clusters (last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_story_clusters_status     ON analytics.story_clusters (status);
CREATE INDEX IF NOT EXISTS idx_story_clusters_entities   ON analytics.story_clusters USING gin (primary_entities);
CREATE INDEX IF NOT EXISTS idx_story_clusters_languages  ON analytics.story_clusters USING gin (languages);
CREATE INDEX IF NOT EXISTS idx_story_members_story       ON analytics.story_cluster_members (story_id);
CREATE INDEX IF NOT EXISTS idx_story_members_source      ON analytics.story_cluster_members (source_id);
CREATE INDEX IF NOT EXISTS idx_story_edges_a             ON analytics.story_edges (article_a);
CREATE INDEX IF NOT EXISTS idx_story_edges_b             ON analytics.story_edges (article_b);
CREATE INDEX IF NOT EXISTS idx_story_edges_run           ON analytics.story_edges (run_id);

-- grants (match 076 / 078 / 080) ---------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON analytics.story_clusters        TO analytics_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON analytics.story_cluster_members TO analytics_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON analytics.story_edges           TO analytics_user;
GRANT SELECT ON analytics.story_clusters        TO rigwire_app;
GRANT SELECT ON analytics.story_cluster_members TO rigwire_app;
GRANT SELECT ON analytics.story_edges           TO rigwire_app;

COMMIT;
