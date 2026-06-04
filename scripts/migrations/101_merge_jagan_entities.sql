-- 101_merge_jagan_entities.sql
-- Merge the fragmented Y. S. Jagan Mohan Reddy entities into one canonical id (2026-06-04).
--
-- The AP principal's #1 rival was split across three non-redirected dictionary ids:
--   72448e52-...  "YS Jagan Mohan Reddy"     (93 mentions)
--   8cf3663e-...  "Y. S. Jagan Mohan Reddy"  (28)  <- chosen canonical (cleanest name; already
--                                                     the target of an existing redirect 33c2e9eb)
--   b104403b-...  "Jagan Mohan Reddy"        (5)
-- Split coverage meant his adverse co-coverage with the principal never aggregated, so PEOPLE
-- TO WATCH couldn't surface him. We follow the established merge convention (cf. 095/096):
-- repoint entity_lookup (the surface->id map the article_entity_mentions matview reads) and the
-- base stance/quote actor FKs, set redirected_to (load_prefs self-heals watchlist ids through
-- it), then refresh the matview. Idempotent — re-running matches no rows.
--
-- NOTE: the companion alias additions for Y. S. Jagan live in the curated body-presence
-- dictionary (products/osint/backend/data/posture_alias_dictionary.json), not in SQL.

-- canonical = 8cf3663e-23f3-4bdd-af8c-c7b6b22f2804 (inlined; runner-agnostic)

-- surface-form -> entity map (drives the AEM matview attribution)
UPDATE entity_lookup SET entity_id = '8cf3663e-23f3-4bdd-af8c-c7b6b22f2804'
 WHERE entity_id IN ('72448e52-f1ae-4963-81f9-65911c080ef3',
                     'b104403b-2535-4999-abbf-984cd22e9041');

-- base actor/speaker FKs
UPDATE article_stances SET actor_entity_id = '8cf3663e-23f3-4bdd-af8c-c7b6b22f2804'
 WHERE actor_entity_id IN ('72448e52-f1ae-4963-81f9-65911c080ef3',
                           'b104403b-2535-4999-abbf-984cd22e9041');

UPDATE article_quotes SET speaker_entity_id = '8cf3663e-23f3-4bdd-af8c-c7b6b22f2804'
 WHERE speaker_entity_id IN ('72448e52-f1ae-4963-81f9-65911c080ef3',
                             'b104403b-2535-4999-abbf-984cd22e9041');

-- mark the dupes redirected (self-heal for watchlists + UI dedup)
UPDATE entity_dictionary SET redirected_to = '8cf3663e-23f3-4bdd-af8c-c7b6b22f2804'
 WHERE id IN ('72448e52-f1ae-4963-81f9-65911c080ef3',
              'b104403b-2535-4999-abbf-984cd22e9041')
   AND redirected_to IS DISTINCT FROM '8cf3663e-23f3-4bdd-af8c-c7b6b22f2804';

-- recompute the derived matview so the merged mentions roll into the canonical
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_matviews WHERE matviewname = 'article_entity_mentions') THEN
    EXECUTE 'REFRESH MATERIALIZED VIEW article_entity_mentions';
  END IF;
END $$;
