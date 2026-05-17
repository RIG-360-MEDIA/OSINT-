-- 048_breaking_event_quality.sql
--
-- Add event-quality classification fields to breaking_clusters so the
-- /breaking surface can gate on "is this actually a real significant
-- event?" *before* running per-user relevance scoring.
--
-- Background:
-- The original detector clustered any 3+ articles in a 2h window that
-- shared LaBSE-embedding proximity. With eps=0.32 this happily grouped
-- unrelated articles that just shared a geo name (Musi Rejuvenation +
-- BRS-vs-Congress + IPL toss all clustered together because all three
-- mentioned "Telangana"). The existing relevance scorer has no defence
-- against this — a junk cluster scores high if any of its articles
-- match a tracked entity.
--
-- This migration adds:
--   event_type      — coarse classification (crime_incident,
--                     policy_announcement, sports_result, etc.)
--   severity        — low | medium | high | breaking
--   is_real_event   — false when articles in the cluster are NOT
--                     actually reporting one shared event
--   shared_subject  — what the cluster is jointly about (or NULL)
--   classified_at   — when the Groq classifier last ran on this row
--
-- Idempotent: safe to re-run.

BEGIN;

ALTER TABLE breaking_clusters
  ADD COLUMN IF NOT EXISTS event_type     text,
  ADD COLUMN IF NOT EXISTS severity       text,
  ADD COLUMN IF NOT EXISTS is_real_event  boolean,
  ADD COLUMN IF NOT EXISTS shared_subject text,
  ADD COLUMN IF NOT EXISTS classified_at  timestamptz;

-- Composite index for the surface query: only active, real, non-trivial
-- events get pulled. Index supports the most common filter shape.
CREATE INDEX IF NOT EXISTS idx_breaking_clusters_surfaced
  ON breaking_clusters (is_active, is_real_event, severity)
  WHERE is_active = TRUE AND is_real_event = TRUE;

COMMIT;
