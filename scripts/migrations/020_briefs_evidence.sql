-- 020_briefs_evidence.sql
-- Persist multi-pillar evidence and per-pillar counts on each brief row.
--
-- Why: the /generate endpoint now retrieves evidence from five pillars
-- (articles, govt docs, social posts, newspaper clippings, video clips)
-- and the BriefWizard frontend renders the structured evidence in four
-- evidence-driven steps. Until now we persisted only the synthesised
-- markdown `content`, so re-loading a brief via /today or /history lost
-- the evidence and the wizard's PRIMARY SOURCES / PRINT PRESS / PUBLIC
-- PULSE / ON THE WIRES steps fell through to empty-state messages.
--
-- Both columns are JSONB; null is allowed for backwards compatibility
-- with briefs generated before this migration ran.

ALTER TABLE briefs
  ADD COLUMN IF NOT EXISTS source_counts JSONB,
  ADD COLUMN IF NOT EXISTS evidence       JSONB;

COMMENT ON COLUMN briefs.source_counts IS
  'Per-pillar counts: {articles, govt_docs, social_posts, newspaper_clippings, video_clips}.';
COMMENT ON COLUMN briefs.evidence IS
  'Structured evidence by pillar: {govt_docs[], social_posts[], newspaper_clippings[], video_clips[]}.';
