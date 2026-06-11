-- 051_story_clustering_v2.sql
--
-- Adds v2 columns to story_threads for the new clustering pipeline.
-- Idempotent — safe to re-apply. Does NOT delete legacy data; the
-- cutover script (scripts/cutover_story_clustering.sql) handles that.
--
-- Design choices baked in here:
--   1. seed_article_id  : anchor a thread to one real article (medoid),
--                         replaces drift-prone rolling-mean centroid.
--   2. seed_embedding   : duplicated from the seed article's
--                         labse_embedding so the kNN query stays
--                         single-table. Updated only when the seed is
--                         re-elected by aggregates.refresh().
--   3. confidence_score : LLM-judge confidence on the initial
--                         assignment; drives the nightly re-evaluation
--                         queue.
--   4. cluster_version  : 1 = legacy (old engine), 2 = new pipeline.
--                         Lets us run side-by-side and TRUNCATE only v1.
--   5. last_evaluated_at: when the consolidation sweep last touched
--                         this thread.

BEGIN;

ALTER TABLE story_threads
  ADD COLUMN IF NOT EXISTS seed_article_id    uuid REFERENCES articles(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS seed_embedding     vector(768),
  ADD COLUMN IF NOT EXISTS confidence_score   real,
  ADD COLUMN IF NOT EXISTS cluster_version    smallint,
  ADD COLUMN IF NOT EXISTS last_evaluated_at  timestamptz;

-- Tag any pre-existing rows as legacy v1.
UPDATE story_threads
   SET cluster_version = 1
 WHERE cluster_version IS NULL;

-- New inserts default to v2. Existing rows preserved as v1.
ALTER TABLE story_threads
  ALTER COLUMN cluster_version SET DEFAULT 2,
  ALTER COLUMN cluster_version SET NOT NULL;

-- Fast cosine kNN against active v2 seeds (the hot path on every assignment).
CREATE INDEX IF NOT EXISTS idx_story_threads_seed_v2_active
  ON story_threads
  USING ivfflat (seed_embedding vector_cosine_ops)
  WITH (lists = 50)
  WHERE is_active = TRUE AND cluster_version = 2;

-- Cheap range scan for the consolidation sweep (low-confidence threads).
CREATE INDEX IF NOT EXISTS idx_story_threads_v2_confidence
  ON story_threads (confidence_score, last_evaluated_at)
  WHERE is_active = TRUE AND cluster_version = 2;

-- Cheap scan for "unclustered articles" the new task processes every 5 min.
CREATE INDEX IF NOT EXISTS idx_articles_unclustered_v2
  ON articles (collected_at)
  WHERE thread_id IS NULL AND labse_embedding IS NOT NULL;

COMMENT ON COLUMN story_threads.seed_article_id IS
  'Anchor article (medoid). Replaces the drifting centroid_embedding column.';
COMMENT ON COLUMN story_threads.seed_embedding IS
  'Cached copy of seed article''s labse_embedding for single-table kNN.';
COMMENT ON COLUMN story_threads.confidence_score IS
  'LLM-judge confidence on initial assignment; null for spawned seeds.';
COMMENT ON COLUMN story_threads.cluster_version IS
  '1 = legacy thread_engine.py (TRUNCATE during cutover). 2 = story_clustering/.';
COMMENT ON COLUMN story_threads.last_evaluated_at IS
  'When the consolidation sweep last re-checked this thread.';

COMMIT;
