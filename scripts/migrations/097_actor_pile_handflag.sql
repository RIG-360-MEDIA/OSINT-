-- 097_actor_pile_handflag.sql
-- Hand-flag the 6 confirmed surfaced actor-piles (2026-06-04).
--
-- BACKGROUND: the co-occurrence diagnostic (docs/plans/story-quality-cooccurrence-2026-06-04.md)
-- ran density / top_pair_share / diversity / entropy across 593 multi-article stories and
-- proved no aggregate signal cleanly separates actor-piles (C) from real mega-events (D) or
-- single coherent events (A) at scale. The anchor check failed (cruise A landed rank 5 of 593;
-- US-Iran D landed rank 1). The actor-pile POPULATION is bounded — Layer 2 (sampled) + this
-- corpus pass identified exactly 6 surfaced piles. Hand-flag by story_id is the right shape:
-- bounded, additive, reversible, no signal-threshold ambiguity. The v2 coherence project (a
-- size-independent metric — Herfindahl over pair frequencies, top-K pair coverage, or
-- community detection on the member-entity graph) ships post-launch.
--
-- THE 6 STORIES (confirmed C-class actor-pile or Nigeria-as-tag in Layer 2 reads):
--   76c64c8e... (1601 articles, "primary elections" — Trump unifies SS shooting / Tulsi / AG)
--   4ded16a6... ( 630, "EU-Mexico raw materials" — Trump unifies Charles UK / Pentagon-Spain)
--   224ee8d1... ( 165, "Party primaries and accountability" — Nigeria-as-tag actor-pile)
--   c0a31ab7... ( 165, "Accord faults deregistration" — Nigeria-as-tag actor-pile)
--   404c6ad8... (  54, "Hyderabad mango festival" — Hyderabad-as-tag disparate lifestyle)
--   2534e314... (  29, "Trump's DOJ ramps up" — Trump policy actor-pile)
--
-- MECHANICS: parallel to size-core-gate (mig 093) and template-family. Sets is_template_family=true
-- + suppression_reason='actor-pile-handflag' + suppressed_at=NOW(). Adds a new audit table that
-- preserves the article_count and top_entity AT FLAG TIME so any future review can see what
-- the story looked like when we flagged it (the cluster may keep growing post-flag).
--
-- REVERSAL (one query, restores everything):
--   UPDATE analytics.story_clusters SET is_template_family=false, suppression_reason=NULL,
--          suppressed_at=NULL WHERE suppression_reason='actor-pile-handflag';
-- (Audit rows in analytics.suppression_audit are retained as provenance — drop separately if
--  desired with DELETE FROM analytics.suppression_audit WHERE suppression_reason='actor-pile-handflag'.)
--
-- INDEPENDENT OF AEM. Ships pre-launch. Idempotent on re-run (guarded by WHERE suppression_reason IS NULL).

\set ON_ERROR_STOP on
BEGIN;

-- 1. Provenance column (when the suppression was applied). Idempotent.
ALTER TABLE analytics.story_clusters ADD COLUMN IF NOT EXISTS suppressed_at timestamptz;
COMMENT ON COLUMN analytics.story_clusters.suppressed_at IS
  'Timestamp the suppression_reason flag was applied. NULL for surfaced stories. Set together '
  'with suppression_reason; cleared together on revert.';

-- 2. Audit table. Captures the AT-FLAG snapshot so the cluster can keep evolving without
--    losing the why-we-flagged-it record. Append-only by convention.
CREATE TABLE IF NOT EXISTS analytics.suppression_audit (
  id                   bigserial PRIMARY KEY,
  story_id             uuid NOT NULL,
  suppression_reason   text NOT NULL,
  suppressed_at        timestamptz NOT NULL DEFAULT now(),
  article_count_at_flag integer,
  independent_source_count_at_flag integer,
  entity_core_cov_at_flag numeric,
  top_entity_at_flag   text,
  representative_title_at_flag text,
  spec_doc             text,
  applied_by           text,
  notes                text
);
CREATE INDEX IF NOT EXISTS idx_supp_audit_story_id ON analytics.suppression_audit (story_id);
CREATE INDEX IF NOT EXISTS idx_supp_audit_reason  ON analytics.suppression_audit (suppression_reason);
COMMENT ON TABLE analytics.suppression_audit IS
  'Append-only audit trail of suppression_reason applications. One row per (story_id, reason). '
  'Snapshots the cluster state AT FLAG TIME so the bookkeeping survives subsequent re-clustering '
  'or growth. Reverting the suppression does NOT delete audit rows by default.';

-- 3. Resolve the 6 prefixes to full UUIDs in scope, then flag.
WITH targets AS (
  SELECT story_id, article_count, independent_source_count, entity_core_cov,
         (SELECT key FROM jsonb_each_text(primary_entities) ORDER BY value::int DESC LIMIT 1) top_ent,
         representative_title
  FROM analytics.story_clusters
  WHERE story_id::text LIKE '4ded16a6%'
     OR story_id::text LIKE '76c64c8e%'
     OR story_id::text LIKE '224ee8d1%'
     OR story_id::text LIKE 'c0a31ab7%'
     OR story_id::text LIKE '404c6ad8%'
     OR story_id::text LIKE '2534e314%'
),
flagged AS (
  UPDATE analytics.story_clusters c
  SET is_template_family = true,
      suppression_reason = 'actor-pile-handflag',
      suppressed_at      = now(),
      updated_at         = now()
  FROM targets t
  WHERE c.story_id = t.story_id
    AND c.suppression_reason IS NULL                      -- idempotency guard
  RETURNING c.story_id, t.article_count, t.independent_source_count,
            t.entity_core_cov, t.top_ent, t.representative_title
)
-- 4. Audit-log one row per newly-flagged story.
INSERT INTO analytics.suppression_audit
  (story_id, suppression_reason, article_count_at_flag, independent_source_count_at_flag,
   entity_core_cov_at_flag, top_entity_at_flag, representative_title_at_flag, spec_doc, applied_by, notes)
SELECT f.story_id, 'actor-pile-handflag',
       f.article_count, f.independent_source_count, f.entity_core_cov, f.top_ent,
       left(f.representative_title, 200),
       'docs/plans/story-quality-cooccurrence-2026-06-04.md',
       'db-chat / migration 097',
       'Hand-flagged C-class actor-pile per Layer 2 ground-truth + corpus-pass confirmation. '
       'Density / top_pair_share signal validation failed at scale (anchor cruise/A and US-Iran/D '
       'ranked alongside Trump-piles); v2 coherence project deferred post-launch. Bounded set of '
       'six was the proven-correct surface fix.'
FROM flagged f;

COMMIT;
