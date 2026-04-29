-- 035_remove_twitter_signals.sql
-- Remove Twitter from the Signals pillar.
--
-- Rationale: Twitter API free tier returns HTTP 402 Payment Required for
-- user-lookup endpoints, making `tasks.collect_twitter` non-functional.
-- The hourly beat task was running, hitting 402, and reporting "0 new
-- posts" with task success — a fully-silent failure mode.
--
-- This migration:
--   1. Deletes any twitter rows in social_posts (currently 0 — collector
--      never produced any rows because the API tier rejected every call).
--   2. Deletes the 3 twitter rows in social_monitors (KTRTRS,
--      trspartyonline, revanth_anumula).
--
-- Companion code changes (already shipped):
--   - backend/celery_app.py — removed task route + beat schedule entry
--   - backend/tasks/social_task.py — removed collect_twitter task
--   - backend/collectors/social_collector.py — removed Twitter helpers
--   - backend/main.py — /api/health/social no longer reports Twitter
--   - backend/routers/signals_router.py — /feed rejects platform=twitter
--   - frontend/src/app/signals/page.tsx — TopicPost.platform excludes 'twitter'
--
-- Restore via git tag pre-twitter-removal if a paid X tier is procured.

BEGIN;

-- 1. Drop any social_posts that came from Twitter (defensive — should be 0).
DELETE FROM social_cluster_posts cp
USING social_posts sp
WHERE cp.post_id = sp.id
  AND sp.platform = 'twitter';

DELETE FROM social_posts WHERE platform = 'twitter';

-- 2. Drop the 3 twitter monitors.
DELETE FROM social_monitors WHERE platform = 'twitter';

-- 3. Verify zero rows remain.
DO $$
DECLARE
  posts_left  integer;
  mons_left   integer;
BEGIN
  SELECT count(*) INTO posts_left FROM social_posts WHERE platform = 'twitter';
  SELECT count(*) INTO mons_left  FROM social_monitors WHERE platform = 'twitter';
  IF posts_left <> 0 OR mons_left <> 0 THEN
    RAISE EXCEPTION
      'Twitter cleanup incomplete: posts=% monitors=%', posts_left, mons_left;
  END IF;
END $$;

COMMIT;
