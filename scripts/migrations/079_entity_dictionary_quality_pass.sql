-- ============================================================================
-- Migration 079 — entity_dictionary quality pass
-- ============================================================================
-- Cleanup follow-up to migration 078. Targets the 5 quality issues we
-- found after the seed-load + backfill pass:
--
--   1. Generic-noun "entities" (police, government, court, officials,
--      farmers, etc.) — LLM-extracted as if they were named entities;
--      they should never have been linked. Deleting them auto-NULLs the
--      ~3,000 useless FKs via ON DELETE SET NULL (migration 078).
--
--   2. Sean Parnell — only confirmed casualty of the state-column
--      backfill (his state="Alaska" got him tagged country=IN).
--      Re-tag US.
--
--   3. "Brent crude" subject_text linked to "Brent Mickelberg" person —
--      classic surname-trigram collision. NULL out those 56 wrong links.
--
--   4. Subject_texts ending in school/hospital/university/etc. that got
--      linked to a city via substring tier-2 (e.g. "Hyderabad Public
--      School" → "Hyderabad"). NULL those out.
--
--   5. Snapshot for rollback as always.
--
-- Reversible via entity_dictionary_pre079_backup.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. Snapshot
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS entity_dictionary_pre079_backup;
CREATE TABLE entity_dictionary_pre079_backup AS
SELECT * FROM entity_dictionary;
CREATE INDEX entity_dictionary_pre079_backup_id_idx
  ON entity_dictionary_pre079_backup (id);

-- ----------------------------------------------------------------------------
-- 2. Delete generic-noun entities (don't touch seeded compound roles like
--    "Prime Minister of India" — those use a unique compound canonical_name)
-- ----------------------------------------------------------------------------
DELETE FROM entity_dictionary
 WHERE LOWER(canonical_name) IN (
   -- People-as-roles (generic)
   'police','police department','government','the government','administration',
   'cabinet','officials','official','an official','an officer','authorities',
   'spokesperson','spokesman','spokeswoman','press secretary','minister',
   'ministers','chairman','chairperson','chair','president','prime minister',
   'pm','vice president','vp','ceo','cfo','coo','cto','chief','head','director',
   'secretary','leader','leaders','member','members','staff','employee',
   'employees','expert','experts','analyst','analysts','source','sources',
   'researcher','researchers','scientist','scientists','engineer','engineers',
   'doctor','doctors','nurse','nurses','teacher','teachers','student',
   'students','journalist','journalists','reporter','reporters','investigator',
   'investigators','prosecutor','prosecutors','farmer','farmers','worker',
   'workers','party workers','volunteer','volunteers','protester','protesters',
   'demonstrator','demonstrators','citizen','citizens','people','residents',
   'resident','victim','victims','witness','witnesses','suspect','suspects',
   'attacker','attackers','soldier','soldiers','troop','troops','rebel',
   'rebels','militant','militants','insurgent','insurgents','organizer',
   'organizers','consultant','consultants',
   -- Generic orgs / refs
   'court','top court','the court','high court','lower court','the centre',
   'centre','the company','company','the firm','the bank','the agency',
   'the ministry','the department','the office','the school','school',
   'the hospital','hospital','the university','university','the institute',
   'institute',
   -- Pronouns / placeholders the LLM should never extract
   'they','them','it','this','that','others','someone','everyone','anyone',
   'nobody','everybody','anybody',
   -- Generic items
   'man','woman','men','women','child','children','people','folks','crowd',
   'study','report','incident','project','initiative','budget','plan','event',
   'campaign','program','scheme','meeting','session','operation'
 );

-- ----------------------------------------------------------------------------
-- 3. Fix the Sean Parnell country contamination
-- ----------------------------------------------------------------------------
UPDATE entity_dictionary
   SET country = 'US'
 WHERE canonical_name = 'Sean Parnell' AND country = 'IN';

-- ----------------------------------------------------------------------------
-- 4. NULL out the Brent crude → Brent Mickelberg wrong links
-- ----------------------------------------------------------------------------
UPDATE article_claims
   SET subject_entity_id = NULL
 WHERE subject_entity_id IN (
   SELECT id FROM entity_dictionary WHERE canonical_name = 'Brent Mickelberg'
 ) AND LOWER(subject_text) LIKE 'brent crude%';

-- Same defensive fix on quotes (probably none, but be safe)
UPDATE article_quotes
   SET speaker_entity_id = NULL
 WHERE speaker_entity_id IN (
   SELECT id FROM entity_dictionary WHERE canonical_name = 'Brent Mickelberg'
 ) AND LOWER(speaker_name) LIKE 'brent crude%';

-- ----------------------------------------------------------------------------
-- 5. NULL out org-suffix subjects that got substring-linked to locations
--    Pattern: subject_text ends in School/Hospital/etc. but was matched to
--    an entity_type='location' via substring tier-2.
-- ----------------------------------------------------------------------------
UPDATE article_claims c
   SET subject_entity_id = NULL
  FROM entity_dictionary ed
 WHERE c.subject_entity_id = ed.id
   AND ed.entity_type = 'location'
   AND LOWER(c.subject_text) ~ '\m(school|hospital|hotel|university|college|institute|foundation|airport|stadium|club|society|association|federation|trust|board|committee)\s*$';

UPDATE article_quotes q
   SET speaker_entity_id = NULL
  FROM entity_dictionary ed
 WHERE q.speaker_entity_id = ed.id
   AND ed.entity_type = 'location'
   AND LOWER(q.speaker_name) ~ '\m(school|hospital|hotel|university|college|institute|foundation|airport|stadium|club|society|association|federation|trust|board|committee)\s*$';

COMMIT;

-- ============================================================================
-- VERIFICATION
-- ============================================================================
--   SELECT 'before', COUNT(*) FROM entity_dictionary_pre079_backup;
--   SELECT 'after',  COUNT(*) FROM entity_dictionary;
--
--   -- Confirm Sean Parnell fix:
--   SELECT canonical_name, country FROM entity_dictionary WHERE canonical_name='Sean Parnell';
--
--   -- Confirm Brent crude un-linked:
--   SELECT COUNT(*) FROM article_claims
--    WHERE LOWER(subject_text) LIKE 'brent crude%' AND subject_entity_id IS NULL;
-- ============================================================================
-- ROLLBACK
-- ============================================================================
--   BEGIN;
--     TRUNCATE entity_dictionary;
--     INSERT INTO entity_dictionary SELECT * FROM entity_dictionary_pre079_backup;
--   COMMIT;
-- ============================================================================
