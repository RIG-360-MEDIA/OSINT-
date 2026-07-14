-- 143_retire_firehose_columns.sql
-- RETIREMENT of the old store-everything social model. DESTRUCTIVE.
-- DO NOT auto-apply. Run MANUALLY, and ONLY when BOTH are true:
--   (a) keyword cutover is proven on a fresh keyword (rows landing + dedup), and
--   (b) the OLD social pipeline is disabled (beat entries + old collectors/tasks
--       stopped) so nothing writes the dropped columns.
--
-- Drop-safety verified 2026-07-08 by grepping backend/ + products/osint/ (live code):
--   SAFE — referenced ONLY by the retiring pipeline (social_collect/enrich,
--          social_*_scraper/collector, old tests) + historical migrations,
--          NO live reader:
--            watchlist_id, community_id, edit_history, in_reply_to_post_id,
--            quoted_post_id, conversation_root_id, thread_depth, forwarded_from,
--            posted_at_ist  (only social_collect.py:275 + 118_social_substrate.sql)
--   BLOCKED — author_id: STILL used by a LIVE reader,
--            products/osint/backend/keyword_dossier.py lines 146 & 165
--            (JOIN social_authors sa ON sa.id = sp.author_id). Refactor those two
--            queries to sp.author_username FIRST, then drop (bottom block).

BEGIN;

-- 1. Backup (full copy incl. vector + enrichment). The 9 child tables
--    (stances/claims/quotes/events/locations/mentions/metrics/hashtags/edges)
--    CASCADE-delete with the firehose rows below — the keyword model doesn't need
--    the old enrichment; back them up separately here if you do.
CREATE TABLE IF NOT EXISTS social_posts_bak_20260708 AS TABLE social_posts;

-- 2. Delete old firehose rows. Keyword posts carry matched_keyword; old ones do not.
--    Cascades to the 9 child tables via their ON DELETE CASCADE FKs.
DELETE FROM social_posts WHERE matched_keyword IS NULL;

-- 3. Drop old-model columns confirmed unused by any live reader.
--    DROP COLUMN auto-drops the dependent FK/index noted in each comment.
ALTER TABLE social_posts DROP COLUMN IF EXISTS watchlist_id;
ALTER TABLE social_posts DROP COLUMN IF EXISTS community_id;          -- drops FK + idx_social_posts_community
ALTER TABLE social_posts DROP COLUMN IF EXISTS edit_history;
ALTER TABLE social_posts DROP COLUMN IF EXISTS posted_at_ist;         -- IST helper; only the old collector wrote it
-- threading model (reply-chains) — keyword collectors don't produce these:
ALTER TABLE social_posts DROP COLUMN IF EXISTS in_reply_to_post_id;   -- drops idx_social_posts_reply
ALTER TABLE social_posts DROP COLUMN IF EXISTS quoted_post_id;
ALTER TABLE social_posts DROP COLUMN IF EXISTS conversation_root_id;  -- drops idx_social_posts_root
ALTER TABLE social_posts DROP COLUMN IF EXISTS thread_depth;
ALTER TABLE social_posts DROP COLUMN IF EXISTS forwarded_from;

COMMIT;

-- 4. author_id — DONE 2026-07-08. keyword_dossier.py queries 6 & 7 were refactored
--    off the social_authors join to sp.platform + sp.author_username (deployed to
--    osint-backend), so the column is now unused and dropped:
BEGIN;
ALTER TABLE social_posts DROP COLUMN IF EXISTS author_id;               -- drops FK + idx_social_posts_author
COMMIT;
