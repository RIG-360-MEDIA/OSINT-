-- ============================================================================
-- Migration 082 — shared alias-resolved article<->entity mapping
-- ============================================================================
-- PROBLEM
--   articles.entities_extracted stores SURFACE FORMS the NER saw in the text
--   ("BRS", "KTR", "Congress") — not canonical names. Every downstream product
--   (relevance engine, brief, analytics_user, rigwire_app) that matches on the
--   canonical name ("Bharat Rashtra Samithi") MISSES these → false zeros.
--
-- FIX (one shared place, not per-product code)
--   A materialized view that resolves every article's surface forms to the
--   CANONICAL entity_id via entity_lookup (the alias-aware table from
--   migration 081: canonical + unambiguous aliases -> entity_id). Now "BRS"
--   and "Bharat Rashtra Samithi" both map to the same entity_id, and every
--   product just joins to this view — no per-product alias logic.
--
-- USAGE
--   "all articles mentioning entity X":
--       SELECT article_id FROM article_entity_mentions WHERE entity_id = :x;
--   "all entities in article Y":
--       SELECT * FROM article_entity_mentions WHERE article_id = :y;
--   "this week's entity coverage by country":
--       SELECT country, COUNT(DISTINCT article_id) FROM article_entity_mentions
--        JOIN articles a ON a.id=article_id WHERE a.published_at > now()-'7d'
--        GROUP BY country;
--
-- NOTE ON COMPLETENESS
--   This view is only as complete as articles.entities_extracted, which the
--   NLP drain is actively repopulating (post geo_secondary fix). Run
--   refresh_article_entity_mentions() AFTER the backlog drain finishes for the
--   first fully-populated snapshot.
--
-- AMBIGUOUS ALIASES (e.g. "Congress" -> INC or US Congress) are intentionally
--   excluded by entity_lookup, so they do not resolve here (better a miss than
--   a wrong link). Products that know their target entity can still alias-expand
--   that specific entity for those cases.
-- ============================================================================

BEGIN;

DROP MATERIALIZED VIEW IF EXISTS article_entity_mentions CASCADE;

CREATE MATERIALIZED VIEW article_entity_mentions AS
SELECT
    a.id                                              AS article_id,
    el.entity_id,
    ed.canonical_name,
    ed.entity_type,
    ed.country,
    array_agg(DISTINCT lower(trim(e.elem->>'name')))  AS surface_forms,
    COUNT(*)                                          AS mention_rows
  FROM articles a
  CROSS JOIN LATERAL jsonb_array_elements(a.entities_extracted) AS e(elem)
  JOIN entity_lookup     el ON el.name_norm = lower(trim(e.elem->>'name'))
  JOIN entity_dictionary ed ON ed.id        = el.entity_id
 WHERE a.entities_extracted IS NOT NULL
   AND jsonb_typeof(a.entities_extracted) = 'array'
 GROUP BY a.id, el.entity_id, ed.canonical_name, ed.entity_type, ed.country;

-- Unique index REQUIRED for REFRESH ... CONCURRENTLY (non-locking refresh)
CREATE UNIQUE INDEX article_entity_mentions_pk
  ON article_entity_mentions (article_id, entity_id);

-- Lookup both directions + by country/type
CREATE INDEX article_entity_mentions_entity_idx  ON article_entity_mentions (entity_id);
CREATE INDEX article_entity_mentions_country_idx ON article_entity_mentions (country) WHERE country IS NOT NULL;
CREATE INDEX article_entity_mentions_type_idx    ON article_entity_mentions (entity_type);

COMMENT ON MATERIALIZED VIEW article_entity_mentions IS
  'Alias-resolved article<->entity mapping. Resolves entities_extracted surface '
  'forms to canonical entity_id via entity_lookup (migration 081). The single '
  'shared surface every product should join to for entity matching. '
  'Refresh via refresh_article_entity_mentions().';

-- Non-locking refresh helper (call after NLP drain / periodically)
CREATE OR REPLACE FUNCTION refresh_article_entity_mentions() RETURNS void AS $$
BEGIN
  REFRESH MATERIALIZED VIEW CONCURRENTLY article_entity_mentions;
END;
$$ LANGUAGE plpgsql;

-- Make sure the downstream product roles can read it (belt + braces; default
-- privileges from 076/080 cover future tables but a matview created now is
-- explicit here).
GRANT SELECT ON article_entity_mentions TO analytics_user;
GRANT SELECT ON article_entity_mentions TO rigwire_app;

COMMIT;

-- ============================================================================
-- VERIFY:
--   SELECT COUNT(*) AS rows, COUNT(DISTINCT article_id) AS articles,
--          COUNT(DISTINCT entity_id) AS entities FROM article_entity_mentions;
--   -- BRS should now resolve to Bharat Rashtra Samithi:
--   SELECT canonical_name, COUNT(DISTINCT article_id)
--     FROM article_entity_mentions WHERE 'brs' = ANY(surface_forms) GROUP BY 1;
-- ROLLBACK:
--   DROP MATERIALIZED VIEW IF EXISTS article_entity_mentions CASCADE;
--   DROP FUNCTION IF EXISTS refresh_article_entity_mentions();
-- ============================================================================
