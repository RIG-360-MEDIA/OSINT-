-- 060_user_breaking_now.sql
-- One-row-per-user current breaking-news pick. Replaces breaking_clusters
-- as the source of truth for the /api/coverage/breaking surface.
--
-- The pick is computed by tasks.coverage.pick_breaking_per_user every
-- 60 minutes. Stickiness is enforced inside the task; the row only
-- changes when the previous winner has rolled out of the candidate
-- window or a higher-tier story has appeared.

BEGIN;

CREATE TABLE IF NOT EXISTS user_breaking_now (
  user_id            uuid PRIMARY KEY,
  article_id         uuid NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  selected_at        timestamptz NOT NULL DEFAULT now(),
  window_started_at  timestamptz NOT NULL,
  source_tier        smallint  NOT NULL,
  relevance_tier     smallint  NOT NULL,
  candidates_count   smallint  NOT NULL,
  near_dup_sources   smallint  NOT NULL DEFAULT 1,
  decision_path      text      NOT NULL,
  reason             text,
  picker_model       text,
  raw_pick_response  jsonb
);

CREATE INDEX IF NOT EXISTS idx_user_breaking_now_article
  ON user_breaking_now(article_id);

COMMENT ON TABLE user_breaking_now IS
  'Single current breaking-news pick per user. Refreshed hourly by tasks.coverage.pick_breaking_per_user. Replaces breaking_clusters.';

COMMIT;
