-- 113: entity_mention_daily becomes CROSS-PILLAR.
--
-- Until now entity_mention_daily was articles-only (article_claims/quotes/stances
-- actors), so the Mission Control Entity page showed NO newspaper or YouTube-clip
-- entities. This adds an `n_entities` column so the hourly aggregator
-- (entity_mention_task.py, now rewritten) can also fold in each item's
-- entities_extracted list across ALL three pillars (articles + clippings + clips).
--
-- n_entities is kept SEPARATE from the generated n_mentions_total (which stays
-- claims+quotes+stances) to avoid rebuilding that stored generated column and its
-- index; consumers rank by (n_mentions_total + n_entities). See mc main.py.
BEGIN;

ALTER TABLE entity_mention_daily
  ADD COLUMN IF NOT EXISTS n_entities int NOT NULL DEFAULT 0;

-- ranking index that includes the new signal
CREATE INDEX IF NOT EXISTS idx_entity_mention_daily_date_total_ent
  ON entity_mention_daily (date DESC, (n_claims + n_quotes + n_stances + n_entities) DESC);

COMMENT ON COLUMN entity_mention_daily.n_entities IS
  'Count of entities_extracted mentions (articles+clippings+clips) for this entity/day. '
  'Rank by n_mentions_total + n_entities (migration 113).';

COMMIT;
