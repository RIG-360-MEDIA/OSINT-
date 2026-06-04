-- 098_f1_rep_title_upgrade.sql
-- F-1 representative-title upgrade (2026-06-04). The earlier F-1 (commit a628507) re-picked
-- on the loose "rep article's entities include core_ent" criterion, which left clusters like
-- US-Iran on a niche analytical piece ("Has the US-Iran ceasefire reset the clock on War
-- Powers Act deadline?") even though tier-1 breaking-news headlines ("Again, US launches new
-- strikes on Iran", Daily Post 2026-06-01) sat ignored. The new picker layers source_tier and
-- recency on top of on-core.
--
-- THE NEW PICKER (per docs/plans/prelaunch-fix-punchlist-2026-06-03.md F-1):
--   eligible member = English (language_detected ~ '^en') AND title length 25-95 AND
--                     ON-CORE (title OR primary_subject contains the cluster's top_ent as a
--                     word-boundary match; top_ent = highest-count key in primary_entities,
--                     which already excludes the F-2 DISPLAY_STOP list).
--   rank by:           source_tier ASC NULLS LAST, published_at DESC NULLS LAST, length(title) ASC
--   replace current rep WHEN: a candidate exists AND it ranks strictly above the current rep
--                            (by tier first, then recency). If current rep IS the top-ranked
--                            candidate, leave it.
--   if no on-core candidate exists: keep current rep (legitimately-low-core stories — concept
--                                  subjects like "hantavirus" where the entity-core gate can't
--                                  measure the story; F-2 spared them, F-1 does too).
--
-- SCOPE: all multi-article clusters (article_count >= 2). Display-only — touches
-- representative_article_id and representative_title; entity_core_cov, is_template_family,
-- and the gate signals are untouched.
--
-- REVERSIBILITY: two new columns store the previous values for rows actually changed.
--   Revert = UPDATE analytics.story_clusters
--             SET representative_article_id = prev_representative_article_id_f1,
--                 representative_title      = prev_representative_title_f1
--             WHERE prev_representative_article_id_f1 IS NOT NULL;
--
-- IDEMPOTENT: re-running picks the same winner for the same data; the WHERE-clause guards
-- against repeated audit-column overwrites.

\set ON_ERROR_STOP on
BEGIN;

-- 1. Audit columns (provenance + reversal)
ALTER TABLE analytics.story_clusters ADD COLUMN IF NOT EXISTS prev_representative_article_id_f1 uuid;
ALTER TABLE analytics.story_clusters ADD COLUMN IF NOT EXISTS prev_representative_title_f1     text;
COMMENT ON COLUMN analytics.story_clusters.prev_representative_article_id_f1 IS
  'F-1 (mig 098) provenance: previous representative_article_id, written ONLY on rows whose '
  'rep was replaced by the on-core + tier-1 + recency picker. NULL otherwise. Revert: copy back.';

-- 2. Compute new pick per cluster (CTE chain)
WITH top_ent_per AS (
  SELECT c.story_id,
         lower(coalesce(
           (SELECT key FROM jsonb_each_text(c.primary_entities) ORDER BY value::int DESC LIMIT 1),
           '')) AS top_ent
  FROM analytics.story_clusters c
  WHERE c.article_count >= 2 AND c.primary_entities IS NOT NULL AND c.primary_entities <> '{}'::jsonb
),
candidates AS (
  SELECT te.story_id, te.top_ent, m.article_id,
         a.title, a.source_tier, a.published_at, length(a.title) tlen,
         row_number() OVER (
           PARTITION BY te.story_id
           ORDER BY a.source_tier ASC NULLS LAST, a.published_at DESC NULLS LAST, length(a.title) ASC, a.id
         ) AS rk
  FROM top_ent_per te
  JOIN analytics.story_cluster_members m USING (story_id)
  JOIN articles a ON a.id = m.article_id
  WHERE te.top_ent <> ''
    AND a.language_detected ~* '^en'
    AND a.title IS NOT NULL
    AND length(a.title) BETWEEN 25 AND 95
    AND (lower(a.title) ~ ('\m' || te.top_ent || '\M')
      OR lower(coalesce(a.primary_subject, '')) ~ ('\m' || te.top_ent || '\M'))
),
winners AS (
  SELECT story_id, article_id AS new_rid, title AS new_title
  FROM candidates WHERE rk = 1
),
changes AS (
  -- Replace ONLY when the new pick differs from the current rep
  SELECT w.story_id, w.new_rid, w.new_title, c.representative_article_id AS old_rid, c.representative_title AS old_title
  FROM winners w
  JOIN analytics.story_clusters c USING (story_id)
  WHERE c.representative_article_id IS DISTINCT FROM w.new_rid
)
-- 3. Apply + save provenance (only on rows actually changing)
UPDATE analytics.story_clusters c
SET prev_representative_article_id_f1 =
      CASE WHEN c.prev_representative_article_id_f1 IS NULL THEN c.representative_article_id
           ELSE c.prev_representative_article_id_f1 END,
    prev_representative_title_f1 =
      CASE WHEN c.prev_representative_title_f1 IS NULL THEN c.representative_title
           ELSE c.prev_representative_title_f1 END,
    representative_article_id = ch.new_rid,
    representative_title      = left(ch.new_title, 300),
    updated_at                = now()
FROM changes ch
WHERE c.story_id = ch.story_id;

COMMIT;
