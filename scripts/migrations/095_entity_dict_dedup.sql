-- 095_entity_dict_dedup.sql
-- Entity-dictionary deduplication (2026-06-04): consolidate stray NER variants of the same
-- real entity into ONE canonical row with the variants as aliases. Reversible via `redirected_to`.
--
-- BACKGROUND: NER stores literal extracted spans, so "Revanth Reddy" + "Chief Minister Revanth Reddy"
-- + "A Revanth Reddy" + "CM Revanth Reddy" + "A. Revanth Reddy" all became separate dictionary rows.
-- TRUE total: 813 mentions across 5 rows; the bare row only showed 143 (5.7x undercount). Same
-- problem on every titled politician, "Dr X", "The New York Times" vs "New York Times", and
-- name-order/spacing variants ("B.Y. Raghavendra" vs "B. Y. Raghavendra"; "Tajudeen Abbas" vs
-- "Abbas Tajudeen").
--
-- THIS MIGRATION applies two SAFE tiers + leaves Tier 3 (fuzzy review-queue) for ops:
--   TIER 1 (58 rows): titled-prefix dupes — strip the leading honorific/office regex; if a row
--     with the bare name exists in the same entity_type, redirect the titled one to the bare.
--   TIER 2 (73 rows): trigram similarity = 1.0 mechanical variants (order-swap, dotted vs spaced
--     initials) within the same entity_type — exact same character set, trivially same person.
--
-- REVERSAL (full): UPDATE entity_lookup el SET entity_id = ed.id FROM entity_dictionary ed
--                  WHERE el.entity_id = ed.redirected_to;
--                  ALTER TABLE entity_dictionary DROP COLUMN redirected_to;  -- if desired
--
-- Idempotent: WHERE redirected_to IS NULL guards each redirect. Tier 4 (NER post-processor)
-- ships separately in backend/nlp/nlp_entities.py — prevents NEW articles re-creating dupes.

\set ON_ERROR_STOP on
BEGIN;

-- 1. provenance + reversal column
ALTER TABLE public.entity_dictionary ADD COLUMN IF NOT EXISTS redirected_to uuid;
COMMENT ON COLUMN public.entity_dictionary.redirected_to IS
  'If set, this row is a deprecated duplicate of redirected_to (kept for reversibility/provenance). '
  'Migration 095 (2026-06-04). Reversal: flip entity_lookup pointers back, or DROP this column.';

-- TIER 1: titled-prefix dupes -> redirect to bare
WITH stripped AS (
  SELECT
    id AS titled_id,
    canonical_name AS titled,
    regexp_replace(
      canonical_name,
      '^(Chief Minister|Deputy Chief Minister|Prime Minister|Deputy Prime Minister|President|Vice President|Minister|Senator|Justice|Governor|Mayor|Honourable|Honorable|Hon\.|Speaker|Sri|Shri|Smt|Sm|Dr|Mr|Mrs|Ms|Prof|Capt|Col|Gen|Lt|Maj|Adv|Engr|A|An|The|CM|PM)\.?\s+',
      '', 'i'
    ) AS bare,
    entity_type
  FROM public.entity_dictionary
),
t1 AS (
  SELECT s.titled_id, b.id AS bare_id, s.titled
  FROM stripped s
  JOIN public.entity_dictionary b
    ON lower(b.canonical_name) = lower(s.bare)
   AND b.id <> s.titled_id
   AND b.entity_type = s.entity_type
  WHERE s.titled <> s.bare AND length(s.bare) > 3
)
UPDATE public.entity_dictionary t
SET redirected_to = t1.bare_id
FROM t1
WHERE t.id = t1.titled_id AND t.redirected_to IS NULL;

-- TIER 2: trigram sim=1.0 mechanical variants (order-swap, dotted/spaced initials)
WITH t2 AS (
  SELECT b.id AS bare_id, a.id AS titled_id
  FROM public.entity_dictionary a
  JOIN public.entity_dictionary b
    ON a.id < b.id
   AND a.entity_type = b.entity_type
   AND similarity(a.canonical_name, b.canonical_name) = 1.0
   AND a.canonical_name % b.canonical_name
   AND length(a.canonical_name) > 4
)
UPDATE public.entity_dictionary t
SET redirected_to = t2.bare_id
FROM t2
WHERE t.id = t2.titled_id AND t.redirected_to IS NULL;

-- Flip entity_lookup pointers (read-side resolution: titled-form NER spans now resolve to bare)
UPDATE public.entity_lookup el
SET entity_id = ed.redirected_to
FROM public.entity_dictionary ed
WHERE el.entity_id = ed.id AND ed.redirected_to IS NOT NULL;

-- Copy the deprecated canonical_name into the bare row's aliases (so the in-memory NER dict
-- picks up "Chief Minister Revanth Reddy" -> Revanth at next worker reload)
UPDATE public.entity_dictionary b
SET aliases = (
  SELECT array(
    SELECT DISTINCT x FROM unnest(
      coalesce(b.aliases, ARRAY[]::text[]) ||
      (SELECT array_agg(t.canonical_name) FROM public.entity_dictionary t WHERE t.redirected_to = b.id)
    ) x WHERE x IS NOT NULL AND x <> ''
  )
)
WHERE EXISTS (SELECT 1 FROM public.entity_dictionary t WHERE t.redirected_to = b.id);

COMMIT;

-- AEM refresh (runs ~10s; do separately so the migration TX is short)
-- REFRESH MATERIALIZED VIEW CONCURRENTLY public.article_entity_mentions;
