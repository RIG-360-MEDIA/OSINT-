-- 055_cluster_importance.sql — T5: event-cluster importance scoring.
--
-- importance_score is a 0-10 scalar refreshed every 30 min by
-- backend/tasks/cluster_importance_task.py. Formula:
--   0.4 * 10*log10(source_count+1)/log10(31)
-- + 0.3 * 10*log10(article_count+1)/log10(101)
-- + 0.2 * 10*novelty_score   (1 - exp(-days_since_first_seen / 3))
-- + 0.1 * 10*velocity_score  (articles_in_last_6h / prior_18h, clipped 0..1)
--
-- Together capped at 10.0 and clipped at 0.0.

BEGIN;

ALTER TABLE event_clusters
  ADD COLUMN IF NOT EXISTS importance_score real,
  ADD COLUMN IF NOT EXISTS importance_updated_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_event_clusters_importance
  ON event_clusters (importance_score DESC NULLS LAST)
  WHERE is_active = TRUE;

COMMIT;
