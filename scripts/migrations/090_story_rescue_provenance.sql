-- 090_story_rescue_provenance.sql
-- §2b sub-cluster rescue (build-launch-plan STEP 0): when a flagged template-family blob is
-- split and a buried real story is mined out as its own first-class story, record the blob it
-- was rescued from (lineage). The rescued sub still receives a STABLE story_id via the loader's
-- greedy-Jaccard path (it enters ID-stability as a first-class cluster); this column is
-- provenance only — which suppressed blob it came from.
--
-- Additive + idempotent. Safe to re-run.

ALTER TABLE analytics.story_clusters
  ADD COLUMN IF NOT EXISTS rescued_from_story_id uuid;

COMMENT ON COLUMN analytics.story_clusters.rescued_from_story_id IS
  'If set, this story was rescued by the §2b sub-cluster split from the (suppressed, '
  'is_template_family=true) blob carrying this story_id. NULL for ordinary stories. '
  'Provenance only — the rescued story still gets its own stable story_id.';

-- Find rescued stories / audit a blob''s rescued children.
CREATE INDEX IF NOT EXISTS idx_story_clusters_rescued_from
  ON analytics.story_clusters (rescued_from_story_id)
  WHERE rescued_from_story_id IS NOT NULL;
