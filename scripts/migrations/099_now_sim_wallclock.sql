-- 099_now_sim_wallclock.sql
-- Make analytics.now_sim() track real wall-clock time (2026-06-04).
--
-- now_sim() previously read a stored replay clock: SELECT sim_now FROM analytics.replay_clock
-- WHERE id = 1. That clock was advanced by an external job that died on 2026-05-29, leaving the
-- whole OSINT product pinned 8 days in the past (sim_now frozen at 2026-05-27) while ingestion
-- kept flowing (~13k articles/day). Every OSINT window (relevance 7d, posture/Home 21d) is
-- relative to now_sim(), so the product was ignoring ~90k fresh articles.
--
-- Blast radius: now_sim() is read ONLY by the OSINT backend (+ 2 historical migrations). No
-- other product references it, so switching to wall-clock affects OSINT alone. Reversible.
--
-- ROLLBACK (restore the replay clock):
--   CREATE OR REPLACE FUNCTION analytics.now_sim()
--     RETURNS timestamptz LANGUAGE sql STABLE
--     AS $$ SELECT sim_now FROM analytics.replay_clock WHERE id = 1 $$;

CREATE OR REPLACE FUNCTION analytics.now_sim()
  RETURNS timestamp with time zone
  LANGUAGE sql
  STABLE
  AS $function$ SELECT now() $function$;
