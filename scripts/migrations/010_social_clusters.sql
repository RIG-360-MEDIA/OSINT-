-- 010_social_clusters.sql
-- Topic-cluster cache for the Signal Room briefing.
-- Idempotent — safe to re-run.
--
-- Each row = a cluster of similar posts (auto-grouped by labse cosine
-- similarity) with a generated headline + body. Clusters are recomputed
-- on a schedule and replaced wholesale, not incrementally.

CREATE TABLE IF NOT EXISTS social_clusters (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    window_start    timestamptz NOT NULL,
    window_end      timestamptz NOT NULL,
    headline        text NOT NULL,
    summary         text NOT NULL,
    post_count      integer NOT NULL DEFAULT 0,
    platforms       text[] NOT NULL DEFAULT '{}',
    monitor_names   text[] NOT NULL DEFAULT '{}',
    top_entities    text[] NOT NULL DEFAULT '{}',
    avg_sentiment   double precision,
    sentiment_tone  text,                       -- positive | negative | neutral
    representative_post_ids uuid[] NOT NULL DEFAULT '{}',
    sample_languages text[] NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_social_clusters_window
  ON social_clusters (window_end DESC);

CREATE INDEX IF NOT EXISTS idx_social_clusters_post_count
  ON social_clusters (post_count DESC);

-- Mapping post -> cluster (post can only be in one cluster per window).
CREATE TABLE IF NOT EXISTS social_cluster_posts (
    cluster_id  uuid NOT NULL REFERENCES social_clusters(id) ON DELETE CASCADE,
    post_id     uuid NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
    PRIMARY KEY (cluster_id, post_id)
);

CREATE INDEX IF NOT EXISTS idx_social_cluster_posts_post
  ON social_cluster_posts (post_id);
