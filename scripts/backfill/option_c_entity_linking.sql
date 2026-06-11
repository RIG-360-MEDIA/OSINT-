-- Option C: bulk-populate entity FK columns + add missing entities.
--
-- Two passes per table (canonical_name then aliases). Idempotent.
-- Run order: INSERT missing entities → UPDATE claims/quotes/stances.

\echo === Add Rahul Gandhi (Telangana dict missed national figures) ===
INSERT INTO entity_dictionary (canonical_name, entity_type, aliases)
VALUES ('Rahul Gandhi', 'person',
        ARRAY['Rahul','Mr Rahul Gandhi','Shri Rahul Gandhi','Wayanad MP'])
ON CONFLICT (canonical_name) DO NOTHING;

\echo
\echo === BEFORE: linkage rates per table ===
SELECT 'article_claims  ' AS tbl, COUNT(*) AS total,
       COUNT(subject_entity_id) AS linked,
       ROUND(100.0*COUNT(subject_entity_id)/NULLIF(COUNT(*),0), 2) AS pct
  FROM article_claims
UNION ALL
SELECT 'article_quotes  ', COUNT(*), COUNT(speaker_entity_id),
       ROUND(100.0*COUNT(speaker_entity_id)/NULLIF(COUNT(*),0), 2)
  FROM article_quotes
UNION ALL
SELECT 'article_stances ', COUNT(*), COUNT(actor_entity_id),
       ROUND(100.0*COUNT(actor_entity_id)/NULLIF(COUNT(*),0), 2)
  FROM article_stances;

\echo
\echo === PASS 1: claims canonical_name match ===
UPDATE article_claims c
   SET subject_entity_id = ed.id
  FROM entity_dictionary ed
 WHERE c.subject_entity_id IS NULL
   AND c.subject_text IS NOT NULL
   AND LOWER(TRIM(c.subject_text)) = LOWER(ed.canonical_name);

\echo === PASS 1b: claims alias match ===
UPDATE article_claims c
   SET subject_entity_id = ed.id
  FROM entity_dictionary ed
 WHERE c.subject_entity_id IS NULL
   AND c.subject_text IS NOT NULL
   AND EXISTS (
     SELECT 1 FROM unnest(ed.aliases) AS a
      WHERE LOWER(TRIM(c.subject_text)) = LOWER(TRIM(a))
   );

\echo === PASS 2: quotes canonical match ===
UPDATE article_quotes q
   SET speaker_entity_id = ed.id
  FROM entity_dictionary ed
 WHERE q.speaker_entity_id IS NULL
   AND q.speaker_name IS NOT NULL
   AND LOWER(TRIM(q.speaker_name)) = LOWER(ed.canonical_name);

\echo === PASS 2b: quotes alias match ===
UPDATE article_quotes q
   SET speaker_entity_id = ed.id
  FROM entity_dictionary ed
 WHERE q.speaker_entity_id IS NULL
   AND q.speaker_name IS NOT NULL
   AND EXISTS (
     SELECT 1 FROM unnest(ed.aliases) AS a
      WHERE LOWER(TRIM(q.speaker_name)) = LOWER(TRIM(a))
   );

\echo === PASS 3: stances canonical match ===
UPDATE article_stances s
   SET actor_entity_id = ed.id
  FROM entity_dictionary ed
 WHERE s.actor_entity_id IS NULL
   AND s.actor IS NOT NULL
   AND LOWER(TRIM(s.actor)) = LOWER(ed.canonical_name);

\echo === PASS 3b: stances alias match ===
UPDATE article_stances s
   SET actor_entity_id = ed.id
  FROM entity_dictionary ed
 WHERE s.actor_entity_id IS NULL
   AND s.actor IS NOT NULL
   AND EXISTS (
     SELECT 1 FROM unnest(ed.aliases) AS a
      WHERE LOWER(TRIM(s.actor)) = LOWER(TRIM(a))
   );

\echo
\echo === AFTER: linkage rates per table ===
SELECT 'article_claims  ' AS tbl, COUNT(*) AS total,
       COUNT(subject_entity_id) AS linked,
       ROUND(100.0*COUNT(subject_entity_id)/NULLIF(COUNT(*),0), 2) AS pct
  FROM article_claims
UNION ALL
SELECT 'article_quotes  ', COUNT(*), COUNT(speaker_entity_id),
       ROUND(100.0*COUNT(speaker_entity_id)/NULLIF(COUNT(*),0), 2)
  FROM article_quotes
UNION ALL
SELECT 'article_stances ', COUNT(*), COUNT(actor_entity_id),
       ROUND(100.0*COUNT(actor_entity_id)/NULLIF(COUNT(*),0), 2)
  FROM article_stances;

\echo
\echo === Verify our 4 watched entities are now linked ===
SELECT 'Naidu  - quotes linked' AS who, COUNT(*) AS n FROM article_quotes
  WHERE speaker_entity_id IN
        (SELECT id FROM entity_dictionary WHERE canonical_name ILIKE '%Naidu%')
UNION ALL SELECT 'Rahul  - quotes linked', COUNT(*) FROM article_quotes
  WHERE speaker_entity_id = (SELECT id FROM entity_dictionary WHERE canonical_name='Rahul Gandhi')
UNION ALL SELECT 'Akhilesh - quotes linked', COUNT(*) FROM article_quotes
  WHERE speaker_entity_id IN
        (SELECT id FROM entity_dictionary WHERE canonical_name ILIKE 'Akhilesh Yadav%')
UNION ALL SELECT 'Owaisi - quotes linked', COUNT(*) FROM article_quotes
  WHERE speaker_entity_id IN
        (SELECT id FROM entity_dictionary WHERE canonical_name ILIKE '%Owaisi');
