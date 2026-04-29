-- 009_signals_polish.sql
-- Polish for the Signals (social media) pillar.
-- Idempotent — safe to re-run.
--
-- SIG-6: index on social_monitors(platform, is_active) for the Beat-time
--        "active monitors per platform" query.
-- (SIG-10/14 entity-tagging fix is handled at task layer via
--  tasks.backfill_social_entity_matches; no schema change required because
--  matched_entities[] already exists on social_posts.)

CREATE INDEX IF NOT EXISTS idx_social_monitors_active
  ON social_monitors (platform, is_active)
  WHERE is_active;
