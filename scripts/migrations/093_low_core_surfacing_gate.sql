-- 093_low_core_surfacing_gate.sql
-- Ship-blocker fix (2026-06-03): the size x core surfacing gate.
--
-- ROOT CAUSE (proven by the 2026-06-03 diagnostic, not guessed): the §2b template-family
-- suppression only EVALUATES clusters with independent_source_count >= 25. The connecting
-- census found 69/71 surfaced low-core stories escaped *purely* by being under that floor
-- (rescue = 0 cause; tcoh-spare = 2; no logic bug). Two were genuinely incoherent mid-size
-- grab-bags that reached users: NASA "moon base" (n=19, core 0.16) and an exam-results pile
-- (n=52, core 0.21). The under-25 bucket is ~90% legitimate small stories, so the fix is a
-- size x core gate, NOT lowering the §2b source floor (that would bury real n=3 news).
--
-- THE GATE (thresholds locked off the §B distribution; the dead-zone between incoherent and
-- legit was empty, so the line is over-determined):
--   suppress (is_template_family := true) iff
--     cluster is SURFACED   (independent_source_count >= 3 OR rescued_from_story_id NOT NULL)
--     AND entity_core_cov < 0.25     -- C_low  (exam 0.21 caught; JPMorgan 0.37 spared)
--     AND article_count  >= 15       -- N_mid  (NASA 19 caught; largest legit-small n=14 spared)
--     AND NOT vernacular_core_zero   -- carve-out: a vernacular-dominant cluster with core ~ 0
--                                    --   is an NER-on-foreign artifact, not incoherence -> spare it
-- vernacular_core_zero := (English article-count < half the cluster) AND entity_core_cov < 0.05.
-- (Inert on today's corpus -- every mid-size low-core cluster is English -- kept as the guard
--  that stands between us and false-suppressing real non-English news the moment that shifts.)
--
-- SCOPE: surfaced-only. The raw predicate also matches 3 non-surfaced isc=1 wire-dup grab-bags
-- (TotalEnergies+Gaza+Hungary; Lagos+Bengaluru; WorldCup+Syria+tennis) -- genuinely incoherent
-- but already invisible (isc<3). We leave them; broadening to them is safe defense-in-depth but
-- pointless here and would mislabel any real-but-single-source story as a template family.
--
-- REVERSIBLE: no delete, no re-cluster. Flips a metadata flag only. To revert this gate:
--   UPDATE analytics.story_clusters
--      SET is_template_family=false, suppression_reason=NULL
--    WHERE suppression_reason='size-core-gate';
--
-- The durable copy of this gate lives in scripts/maintenance/story_loader.py (runs every load).
-- This migration is the one-shot for the pre-gate live keeper + the schema column. KEEP IN SYNC.
--
-- Additive + idempotent. Safe to re-run.

-- 1. provenance: WHY a cluster is suppressed from surfacing.
ALTER TABLE analytics.story_clusters
  ADD COLUMN IF NOT EXISTS suppression_reason text;

COMMENT ON COLUMN analytics.story_clusters.suppression_reason IS
  'Why is_template_family=true: ''template-family'' (§2b src>=25 low-core / size-cap blob) | '
  '''size-core-gate'' (2026-06-03 size x core grab-bag gate, migration 093) | NULL (surfaced). '
  'Reversible provenance: revert the gate by clearing rows WHERE suppression_reason=''size-core-gate''.';

-- 2. the size x core gate -- flag mid-size low-core grab-bags that escaped §2b's source floor.
--    Runs FIRST so its catches are tagged 'size-core-gate' before the template-family backfill.
UPDATE analytics.story_clusters
SET is_template_family = true,
    suppression_reason = 'size-core-gate',
    updated_at         = now()
WHERE is_template_family = false
  AND (independent_source_count >= 3 OR rescued_from_story_id IS NOT NULL)   -- surfaced set only
  AND entity_core_cov  < 0.25                                               -- C_low
  AND article_count   >= 15                                                 -- N_mid
  AND NOT (                                                                 -- vernacular_core_zero carve-out
        COALESCE((languages->>'en')::int, 0) * 2
          < (SELECT COALESCE(sum(value::int), 0) FROM jsonb_each_text(languages))
        AND entity_core_cov < 0.05
      );

-- 3. backfill provenance for the pre-existing §2b template-families (everything else suppressed).
UPDATE analytics.story_clusters
SET suppression_reason = 'template-family'
WHERE is_template_family = true
  AND suppression_reason IS NULL;
