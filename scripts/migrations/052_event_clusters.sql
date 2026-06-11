-- 052_event_clusters.sql
--
-- Event-first clustering: extract events from articles (already done by v3
-- substrate → article_events), then cluster the EVENTS themselves, not the
-- articles. Stories emerge as chains of related events linked by shared actors.
--
-- Why event-first beats article-clustering:
--   * Events have structured keys (actor, action, date, location). Matching is
--     a 4-field similarity check, not text-embedding kNN.
--   * No same-source-style-bias problem: publisher boilerplate doesn't appear
--     in (actor, event_type, date) tuples.
--   * Articles attach as evidence; stories emerge bottom-up from event chains.

BEGIN;

CREATE TABLE IF NOT EXISTS event_clusters (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  canonical_description text NOT NULL,
  canonical_actors      text[] NOT NULL DEFAULT '{}',
  canonical_event_type  text,
  canonical_date        date,
  is_future             boolean DEFAULT false,
  article_count         integer NOT NULL DEFAULT 0,
  source_count          integer NOT NULL DEFAULT 0,
  confidence_score      real,
  first_seen_at         timestamptz NOT NULL DEFAULT NOW(),
  last_updated_at       timestamptz NOT NULL DEFAULT NOW(),
  is_active             boolean NOT NULL DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_event_clusters_active_date
  ON event_clusters (canonical_date DESC) WHERE is_active;

CREATE INDEX IF NOT EXISTS idx_event_clusters_actors_gin
  ON event_clusters USING gin (canonical_actors);

-- Link article_events to their cluster
ALTER TABLE article_events
  ADD COLUMN IF NOT EXISTS event_cluster_id uuid REFERENCES event_clusters(id);

CREATE INDEX IF NOT EXISTS idx_article_events_cluster
  ON article_events (event_cluster_id) WHERE event_cluster_id IS NOT NULL;

COMMENT ON TABLE event_clusters IS
  'Canonical real-world events that multiple article_events rows describe.';
COMMENT ON COLUMN event_clusters.canonical_actors IS
  'Deduplicated union of actors across all article_events in this cluster.';
COMMENT ON COLUMN article_events.event_cluster_id IS
  'FK to the canonical event this article_events row describes (NULL = unclustered).';

COMMIT;
