-- ============================================================================
-- CATEGORY A — Pure SQL Data Repair Sprint, Day 1
-- All fixes are idempotent and reversible (except column drops, which back up first)
-- Run inside docker exec rig-postgres psql -U rig -d rig
-- ============================================================================

\timing on
\set ON_ERROR_STOP on

-- ────────────────────────────────────────────────────────────────────────────
-- BEFORE counts (baseline so we can verify uplift)
-- ────────────────────────────────────────────────────────────────────────────
\echo '=== BEFORE COUNTS ==='
SELECT
  'quotes_with_entity_id'      AS metric, COUNT(*) AS value FROM article_quotes WHERE speaker_entity_id IS NOT NULL
UNION ALL SELECT 'quotes_total',            COUNT(*) FROM article_quotes
UNION ALL SELECT 'claims_with_entity_id',   COUNT(*) FROM article_claims WHERE subject_entity_id IS NOT NULL
UNION ALL SELECT 'claims_total',            COUNT(*) FROM article_claims
UNION ALL SELECT 'stances_with_entity_id',  COUNT(*) FROM article_stances WHERE actor_entity_id IS NOT NULL
UNION ALL SELECT 'stances_total',           COUNT(*) FROM article_stances
UNION ALL SELECT 'events_bad_dates',        COUNT(*) FROM article_events WHERE event_date < '1990-01-01' OR event_date > '2035-01-01'
UNION ALL SELECT 'canonical_url_redundant', COUNT(*) FROM articles WHERE canonical_url = url
UNION ALL SELECT 'author_name_populated',   COUNT(*) FROM articles WHERE LENGTH(COALESCE(author_name,'')) > 2
UNION ALL SELECT 'byline_populated',        COUNT(*) FROM articles WHERE LENGTH(COALESCE(byline,'')) > 2
UNION ALL SELECT 'flag_mismatch_count',     COUNT(*) FROM articles a WHERE
   (a.claims_extracted=true) <> (a.id IN (SELECT article_id FROM article_claims));

-- ============================================================================
-- A8 — NULL out canonical_url when equal to url (cheap, safe, 63K rows)
-- ============================================================================
\echo '=== A8 — clean up redundant canonical_url ==='
UPDATE articles SET canonical_url = NULL WHERE canonical_url = url;
\echo '  done'
SELECT 'A8 verify: still-populated canonical_url' AS check_name, COUNT(*) AS value
  FROM articles WHERE canonical_url IS NOT NULL;

-- ============================================================================
-- A2 — NULL hallucinated event dates (< 1990 or > 2035)
-- ============================================================================
\echo '=== A2 — NULL hallucinated event_dates ==='
UPDATE article_events SET event_date = NULL
 WHERE event_date IS NOT NULL
   AND (event_date < '1990-01-01' OR event_date > '2035-01-01');
\echo '  done'
SELECT 'A2 verify: remaining bad dates' AS check_name, COUNT(*) AS value
  FROM article_events
 WHERE event_date IS NOT NULL
   AND (event_date < '1990-01-01' OR event_date > '2035-01-01');

-- ============================================================================
-- A7 — Reconcile status flags with reality
-- claims_extracted=TRUE iff article has rows in article_claims
-- quotes_extracted=TRUE iff extractor ran (regardless of whether quotes found)
-- nlp_processed=TRUE iff article has rows in any of claims/quotes/stances
-- ============================================================================
\echo '=== A7 — reconcile claims_extracted flag with reality ==='
UPDATE articles SET claims_extracted = TRUE
 WHERE claims_extracted IS NOT TRUE
   AND id IN (SELECT article_id FROM article_claims);
\echo '  done'

\echo '=== A7 — set nlp_processed=TRUE for articles with any NLP output ==='
UPDATE articles SET nlp_processed = TRUE
 WHERE nlp_processed IS NOT TRUE
   AND id IN (
     SELECT article_id FROM article_claims
     UNION SELECT article_id FROM article_quotes
     UNION SELECT article_id FROM article_stances
   );
\echo '  done'

SELECT 'A7 verify: claims_flag_TRUE_no_rows' AS check_name,
       COUNT(*) AS value FROM articles WHERE claims_extracted=true
         AND id NOT IN (SELECT article_id FROM article_claims);

-- ============================================================================
-- A1 — Entity FK backfill from entity_dictionary (canonical_name + aliases)
-- Uses the same logic as the patched _resolve_entity_id() function.
-- Three updates: speaker_entity_id, subject_entity_id, actor_entity_id.
-- ============================================================================

\echo '=== A1.a — backfill article_quotes.speaker_entity_id ==='
UPDATE article_quotes q
   SET speaker_entity_id = (
     SELECT ed.id FROM entity_dictionary ed
      WHERE LOWER(ed.canonical_name) = LOWER(q.speaker_name)
         OR EXISTS (
            SELECT 1 FROM unnest(ed.aliases) AS a
             WHERE LOWER(a) = LOWER(q.speaker_name)
         )
      ORDER BY (LOWER(ed.canonical_name) = LOWER(q.speaker_name)) DESC,
               (ed.entity_type = 'person') DESC,
               LENGTH(ed.canonical_name) DESC
      LIMIT 1
   )
 WHERE q.speaker_entity_id IS NULL
   AND q.speaker_name IS NOT NULL
   AND LENGTH(q.speaker_name) >= 2;
\echo '  done'

\echo '=== A1.b — backfill article_claims.subject_entity_id ==='
UPDATE article_claims c
   SET subject_entity_id = (
     SELECT ed.id FROM entity_dictionary ed
      WHERE LOWER(ed.canonical_name) = LOWER(c.subject_text)
         OR EXISTS (
            SELECT 1 FROM unnest(ed.aliases) AS a
             WHERE LOWER(a) = LOWER(c.subject_text)
         )
      ORDER BY (LOWER(ed.canonical_name) = LOWER(c.subject_text)) DESC,
               (ed.entity_type = 'person') DESC,
               LENGTH(ed.canonical_name) DESC
      LIMIT 1
   )
 WHERE c.subject_entity_id IS NULL
   AND c.subject_text IS NOT NULL
   AND LENGTH(c.subject_text) >= 2;
\echo '  done'

\echo '=== A1.c — backfill article_stances.actor_entity_id ==='
UPDATE article_stances s
   SET actor_entity_id = (
     SELECT ed.id FROM entity_dictionary ed
      WHERE LOWER(ed.canonical_name) = LOWER(s.actor)
         OR EXISTS (
            SELECT 1 FROM unnest(ed.aliases) AS a
             WHERE LOWER(a) = LOWER(s.actor)
         )
      ORDER BY (LOWER(ed.canonical_name) = LOWER(s.actor)) DESC,
               (ed.entity_type = 'person') DESC,
               LENGTH(ed.canonical_name) DESC
      LIMIT 1
   )
 WHERE s.actor_entity_id IS NULL
   AND s.actor IS NOT NULL
   AND LENGTH(s.actor) >= 2;
\echo '  done'

-- ============================================================================
-- A5 — Consolidate author_name → byline (preserve data before dropping column)
-- ============================================================================
\echo '=== A5 — copy author_name into byline where byline is NULL ==='
UPDATE articles
   SET byline = author_name
 WHERE byline IS NULL
   AND author_name IS NOT NULL
   AND LENGTH(author_name) > 2;
\echo '  done'

-- ============================================================================
-- A3, A4, A5 — DROP redundant columns (after data preserved)
-- These are destructive; backup the affected views/permissions first if any
-- ============================================================================

\echo '=== A3, A4, A5 — DROP redundant columns ==='
ALTER TABLE articles DROP COLUMN IF EXISTS inserted_at;
ALTER TABLE articles DROP COLUMN IF EXISTS geo_secondary;
ALTER TABLE articles DROP COLUMN IF EXISTS author_name;
\echo '  done'

-- ============================================================================
-- A6 — geo_primary auto-sync trigger from article_locations
-- (Can't use a true generated column because of subquery; trigger is cleanest)
-- ============================================================================

\echo '=== A6.a — initial sync: populate geo_primary from article_locations ==='
UPDATE articles a
   SET geo_primary = (
     SELECT l.location_text
       FROM article_locations l
      WHERE l.article_id = a.id
        AND l.is_primary = TRUE
      ORDER BY l.mention_count DESC NULLS LAST
      LIMIT 1
   )
 WHERE a.geo_primary IS NULL
   AND EXISTS (SELECT 1 FROM article_locations l WHERE l.article_id = a.id AND l.is_primary = TRUE);
\echo '  initial sync done'

\echo '=== A6.b — create trigger to keep geo_primary in sync ==='
CREATE OR REPLACE FUNCTION sync_geo_primary_from_locations()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE articles a
     SET geo_primary = (
       SELECT l.location_text FROM article_locations l
        WHERE l.article_id = a.id AND l.is_primary = TRUE
        ORDER BY l.mention_count DESC NULLS LAST LIMIT 1
     )
   WHERE a.id = COALESCE(NEW.article_id, OLD.article_id);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_geo_primary ON article_locations;
CREATE TRIGGER trg_sync_geo_primary
AFTER INSERT OR UPDATE OR DELETE ON article_locations
FOR EACH ROW EXECUTE FUNCTION sync_geo_primary_from_locations();
\echo '  trigger installed'

-- ────────────────────────────────────────────────────────────────────────────
-- AFTER counts (verify uplift)
-- ────────────────────────────────────────────────────────────────────────────
\echo '=== AFTER COUNTS ==='
SELECT
  'quotes_with_entity_id'      AS metric, COUNT(*) AS value FROM article_quotes WHERE speaker_entity_id IS NOT NULL
UNION ALL SELECT 'claims_with_entity_id',   COUNT(*) FROM article_claims WHERE subject_entity_id IS NOT NULL
UNION ALL SELECT 'stances_with_entity_id',  COUNT(*) FROM article_stances WHERE actor_entity_id IS NOT NULL
UNION ALL SELECT 'events_bad_dates_remaining', COUNT(*) FROM article_events WHERE event_date IS NOT NULL AND (event_date < '1990-01-01' OR event_date > '2035-01-01')
UNION ALL SELECT 'canonical_url_redundant',    COUNT(*) FROM articles WHERE canonical_url IS NOT NULL AND canonical_url = url
UNION ALL SELECT 'byline_populated',           COUNT(*) FROM articles WHERE LENGTH(COALESCE(byline,'')) > 2
UNION ALL SELECT 'geo_primary_populated',      COUNT(*) FROM articles WHERE geo_primary IS NOT NULL;

\echo '=== columns dropped check ==='
SELECT column_name FROM information_schema.columns
 WHERE table_name='articles' AND column_name IN ('inserted_at','geo_secondary','author_name');
\echo '  (empty result = drops successful)'

\echo '=== Category A complete ==='
