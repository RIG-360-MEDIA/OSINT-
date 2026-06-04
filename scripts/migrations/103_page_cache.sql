-- 103_page_cache.sql
-- Generic per-persona page payload cache (2026-06-04) for the heavy pages
-- (War Room ~6s, Analytics ~15s). The osint-backend's 30-min scheduler precomputes
-- each onboarded persona's page payload here; the /api/brief/warroom and /analytics
-- endpoints serve the snapshot instantly (lazy-fill on miss, stale-serve on failure).
-- (Home keeps its own analytics.home_cache from migration 100.) Idempotent.

CREATE TABLE IF NOT EXISTS analytics.page_cache (
  user_id     uuid NOT NULL,
  page        text NOT NULL,
  payload     jsonb NOT NULL,
  computed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, page)
);
GRANT SELECT, INSERT, UPDATE, DELETE ON analytics.page_cache TO analytics_user;
