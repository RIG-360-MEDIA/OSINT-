-- ============================================================================
-- Migration 081 — stop entity-FK erosion with insert-time linking triggers
-- ============================================================================
-- PROBLEM
--   run_corpus_pass DELETEs + re-INSERTs an article's claims/quotes/stances on
--   every reprocess, and v3 extraction does NOT re-link entities inline. So the
--   subject_entity_id / speaker_entity_id / actor_entity_id values we backfilled
--   via trigram matching get wiped every time the drain touches an article.
--   Observed: claim links decayed 56,411 -> 37,586 in one day.
--
-- FIX (permanent, no timing window)
--   1. entity_lookup — a fast exact-match table (canonical names + UNAMBIGUOUS
--      aliases, lowercased). One B-tree PK lookup per row.
--   2. BEFORE INSERT triggers on the 3 child tables that set the FK from
--      entity_lookup whenever it's NULL. Every newly-inserted claim/quote/
--      stance is linked instantly — so drain re-inserts re-link automatically.
--      Erosion stops at the source.
--   3. One-time backfill to restore the currently-eroded links.
--
-- SCOPE: exact + alias matches (the bulk — "India", "Modi", "BJP", "Donald
--   Trump"). Fuzzy/substring long-tail ("President Bola Tinubu") is left to the
--   periodic trigram backfill script; those are the minority and the trigger
--   keeps the high-value exact links permanently fresh.
--
-- SAFETY: triggers only set the FK when it's NULL (never override an explicit
--   value); ambiguous aliases (same alias -> 2+ entities) are excluded so we
--   never mis-link. FKs are already ON DELETE SET NULL (migrations 078/079).
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. entity_lookup — exact-match surface
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS entity_lookup;
CREATE TABLE entity_lookup (
  name_norm  text PRIMARY KEY,                 -- lower(trim(name))
  entity_id  uuid NOT NULL REFERENCES entity_dictionary(id) ON DELETE CASCADE
);

CREATE OR REPLACE FUNCTION refresh_entity_lookup() RETURNS void AS $$
BEGIN
  TRUNCATE entity_lookup;

  -- Canonical names first (canonical_name is UNIQUE -> no ambiguity).
  INSERT INTO entity_lookup (name_norm, entity_id)
  SELECT lower(trim(canonical_name)), id
    FROM entity_dictionary
   WHERE canonical_name IS NOT NULL
     AND length(trim(canonical_name)) >= 3
  ON CONFLICT (name_norm) DO NOTHING;

  -- Aliases: only those NOT already a canonical name AND mapping to exactly
  -- one entity (drop ambiguous aliases like "Congress" -> {INC, US Congress}).
  -- NOTE: uuid has no MIN(); HAVING COUNT(DISTINCT)=1 guarantees a single
  -- entity_id per name_norm, so array_agg(DISTINCT ...)[1] picks that one.
  INSERT INTO entity_lookup (name_norm, entity_id)
  SELECT a.name_norm, (array_agg(DISTINCT a.entity_id))[1]
    FROM (
      SELECT lower(trim(al)) AS name_norm, id AS entity_id
        FROM entity_dictionary, unnest(aliases) AS al
       WHERE al IS NOT NULL AND length(trim(al)) >= 3
    ) a
   WHERE NOT EXISTS (SELECT 1 FROM entity_lookup el WHERE el.name_norm = a.name_norm)
   GROUP BY a.name_norm
  HAVING COUNT(DISTINCT a.entity_id) = 1
  ON CONFLICT (name_norm) DO NOTHING;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION refresh_entity_lookup IS
  'Rebuilds entity_lookup from entity_dictionary (canonical + unambiguous aliases). '
  'Call after seeding new entities (scripts/entity_seeds/load_seeds.py).';

SELECT refresh_entity_lookup();

-- ----------------------------------------------------------------------------
-- 2. insert-time linking triggers (only fill when FK is NULL)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_link_claim_entity() RETURNS trigger AS $$
BEGIN
  IF NEW.subject_entity_id IS NULL AND NEW.subject_text IS NOT NULL THEN
    SELECT entity_id INTO NEW.subject_entity_id
      FROM entity_lookup WHERE name_norm = lower(trim(NEW.subject_text));
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION trg_link_quote_entity() RETURNS trigger AS $$
BEGIN
  IF NEW.speaker_entity_id IS NULL AND NEW.speaker_name IS NOT NULL THEN
    SELECT entity_id INTO NEW.speaker_entity_id
      FROM entity_lookup WHERE name_norm = lower(trim(NEW.speaker_name));
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION trg_link_stance_entity() RETURNS trigger AS $$
BEGIN
  IF NEW.actor_entity_id IS NULL AND NEW.actor IS NOT NULL THEN
    SELECT entity_id INTO NEW.actor_entity_id
      FROM entity_lookup WHERE name_norm = lower(trim(NEW.actor));
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_link_claim_entity ON article_claims;
CREATE TRIGGER trg_link_claim_entity BEFORE INSERT ON article_claims
  FOR EACH ROW EXECUTE FUNCTION trg_link_claim_entity();

DROP TRIGGER IF EXISTS trg_link_quote_entity ON article_quotes;
CREATE TRIGGER trg_link_quote_entity BEFORE INSERT ON article_quotes
  FOR EACH ROW EXECUTE FUNCTION trg_link_quote_entity();

DROP TRIGGER IF EXISTS trg_link_stance_entity ON article_stances;
CREATE TRIGGER trg_link_stance_entity BEFORE INSERT ON article_stances
  FOR EACH ROW EXECUTE FUNCTION trg_link_stance_entity();

COMMIT;

-- ----------------------------------------------------------------------------
-- 3. One-time backfill (outside the txn so it can be re-run safely)
--    Restores the eroded links on existing rows from entity_lookup.
-- ----------------------------------------------------------------------------
UPDATE article_claims c SET subject_entity_id = el.entity_id
  FROM entity_lookup el
 WHERE c.subject_entity_id IS NULL AND c.subject_text IS NOT NULL
   AND el.name_norm = lower(trim(c.subject_text));

UPDATE article_quotes q SET speaker_entity_id = el.entity_id
  FROM entity_lookup el
 WHERE q.speaker_entity_id IS NULL AND q.speaker_name IS NOT NULL
   AND el.name_norm = lower(trim(q.speaker_name));

UPDATE article_stances s SET actor_entity_id = el.entity_id
  FROM entity_lookup el
 WHERE s.actor_entity_id IS NULL AND s.actor IS NOT NULL
   AND el.name_norm = lower(trim(s.actor));

-- ============================================================================
-- VERIFY:
--   SELECT COUNT(*) FROM entity_lookup;
--   SELECT COUNT(*) FILTER (WHERE subject_entity_id IS NOT NULL) FROM article_claims;
-- TEST the trigger:
--   INSERT INTO article_claims (article_id, claim_text, subject_text)
--   VALUES ('<some-uuid>', 'test', 'Narendra Modi') RETURNING subject_entity_id;  -- should be non-null
-- ROLLBACK:
--   DROP TRIGGER trg_link_claim_entity ON article_claims; (+ quote/stance)
--   DROP FUNCTION trg_link_claim_entity(), trg_link_quote_entity(), trg_link_stance_entity(), refresh_entity_lookup();
--   DROP TABLE entity_lookup;
-- ============================================================================
