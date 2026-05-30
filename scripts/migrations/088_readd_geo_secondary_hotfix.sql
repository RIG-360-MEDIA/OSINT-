-- 088_readd_geo_secondary_hotfix.sql
-- =====================================================================
-- EMERGENCY HOTFIX (deploy-free) — stop active corpus degradation.
--
-- SYMPTOM: the baked celery NLP worker still writes articles.geo_secondary,
-- which was DROPPED by scripts/backfill/category_a_fixes.sql. Every fresh
-- article's UPDATE throws UndefinedColumnError (~34/min) -> the article is
-- marked nlp_confidence='error' with NO embedding / entities / topic. This
-- is the original GOAL root cause, reactivated when the LLM-pool restart
-- un-hung the worker.
--
-- WHY THIS FIX: the code fix (nlp_processor no longer writes geo_secondary)
-- is committed but the deploy is blocked (backend baked into the image +
-- 105 dirty files on the Hetzner tree -> a rebuild is unsafe). Re-adding
-- the column with its ORIGINAL type (text[] DEFAULT '{}', per
-- 001_initial_schema.sql) makes the deployed UPDATE succeed again with NO
-- restart and NO code deploy. Nothing READS this column (it was dropped),
-- so writing it is harmless.
--
-- REVERT: once the nlp_processor geo_secondary fix actually deploys,
-- DROP COLUMN geo_secondary again.
-- =====================================================================

BEGIN;
SET LOCAL lock_timeout = '3s';

ALTER TABLE articles ADD COLUMN IF NOT EXISTS geo_secondary text[] DEFAULT '{}';

COMMENT ON COLUMN articles.geo_secondary IS
  'HOTFIX 2026-05-30 (088): re-added to stop UndefinedColumnError from the baked, un-deployed-fix NLP worker. Nothing reads it. DROP again after the nlp_processor geo_secondary fix deploys.';

COMMIT;
