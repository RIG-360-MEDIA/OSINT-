-- 100_home_cache_table.sql
-- Per-persona Night Desk Home payload cache (2026-06-04).
--
-- build_home (masthead + THE BRIEFING + PEOPLE TO WATCH + THE SIX) costs ~12-30s on the live
-- window, far too slow to run per request. The osint-backend runs an in-process scheduler
-- (home_cache.py) that recomputes every onboarded persona every 30 min and upserts the JSON
-- payload here; GET /api/brief/home serves the snapshot in ~1ms (lazy-fills on a cold miss,
-- falls back to a stale row if a live compute fails). analytics_user (RW on analytics.*) writes.
-- Idempotent.

CREATE TABLE IF NOT EXISTS analytics.home_cache (
  user_id     uuid PRIMARY KEY,
  payload     jsonb NOT NULL,
  computed_at timestamptz NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE, DELETE ON analytics.home_cache TO analytics_user;
