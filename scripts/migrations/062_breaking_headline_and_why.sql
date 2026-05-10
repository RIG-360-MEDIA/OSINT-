-- 062_breaking_headline_and_why.sql
-- Add catchy one-line English headline + why-it-matters-to-this-user
-- columns to user_breaking_now. Both are populated by Groq during the
-- per-user pick task and surfaced directly by /api/coverage/breaking.

BEGIN;

ALTER TABLE user_breaking_now
  ADD COLUMN IF NOT EXISTS headline_one_line text,
  ADD COLUMN IF NOT EXISTS why_for_user      text;

COMMENT ON COLUMN user_breaking_now.headline_one_line IS
  'Groq-summarised English headline, max ~12 words. Replaces raw article '
  'title in the BreakingBand UI. Always present for new picks.';

COMMENT ON COLUMN user_breaking_now.why_for_user IS
  'Plain-English explanation of why this story matters to THIS user, '
  'max ~22 words. Tailored to their role / geo / signal_priorities.';

COMMIT;
