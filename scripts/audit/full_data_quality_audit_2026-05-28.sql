-- ============================================================================
-- Full Statistical Data Quality Audit — 2026-05-28
-- Runs every metric needed to grade per-field health across all tables.
-- Output is read by the Python wrapper which formats it into a Markdown report.
-- ============================================================================

\pset format unaligned
\pset fieldsep '|'
\pset tuples_only on

-- ===== SECTION 1: TABLE-LEVEL =====
SELECT '##TABLE_ROWS' AS section;
SELECT relname, n_live_tup
  FROM pg_stat_user_tables
 WHERE relname IN (
   'articles','article_claims','article_quotes','article_locations',
   'article_events','article_numbers','article_stances','article_districts',
   'article_links','article_media','entity_dictionary','sources',
   'article_contradictions','article_tweets'
 )
 ORDER BY n_live_tup DESC;

-- ===== SECTION 2: ARTICLES FIELD QUALITY =====
SELECT '##ARTICLES_FIELDS' AS section;
SELECT
  COUNT(*) AS total_articles,
  COUNT(*) FILTER (WHERE title IS NOT NULL AND title != '')         AS title_filled,
  COUNT(*) FILTER (WHERE body IS NOT NULL AND length(body) > 100)   AS body_substantial,
  AVG(length(body))::int                                            AS avg_body_len,
  COUNT(*) FILTER (WHERE language_iso IS NOT NULL)                  AS lang_filled,
  COUNT(*) FILTER (WHERE byline IS NOT NULL AND byline != '')       AS byline_filled,
  COUNT(*) FILTER (WHERE author_name IS NOT NULL AND author_name != '') AS author_filled,
  COUNT(*) FILTER (WHERE summary_preview IS NOT NULL)               AS prev_filled,
  COUNT(*) FILTER (WHERE summary_snippet IS NOT NULL)               AS snip_filled,
  COUNT(*) FILTER (WHERE summary_executive IS NOT NULL)             AS exec_filled,
  COUNT(*) FILTER (WHERE primary_subject IS NOT NULL)               AS subj_filled,
  COUNT(*) FILTER (WHERE article_type IS NOT NULL)                  AS atype_filled,
  COUNT(*) FILTER (WHERE register_style IS NOT NULL)                AS regstyle_filled,
  COUNT(*) FILTER (WHERE register_emotion IS NOT NULL)              AS regemo_filled,
  COUNT(*) FILTER (WHERE embedding IS NOT NULL)                     AS embed_filled,
  COUNT(*) FILTER (WHERE substrate_status = 'ok')                   AS substrate_ok,
  COUNT(*) FILTER (WHERE extraction_version = 3)                    AS v3_count,
  COUNT(*) FILTER (WHERE published_at IS NOT NULL)                  AS pub_filled,
  COUNT(*) FILTER (WHERE topics IS NOT NULL AND array_length(topics,1) > 0)        AS topics_filled,
  COUNT(*) FILTER (WHERE entities IS NOT NULL AND array_length(entities,1) > 0)    AS entities_filled
FROM articles;

-- Per-language counts (top 10)
SELECT '##ARTICLES_LANG_DIST' AS section;
SELECT language_iso, COUNT(*) AS n
  FROM articles WHERE language_iso IS NOT NULL
 GROUP BY 1 ORDER BY n DESC LIMIT 10;

-- Article_type distribution
SELECT '##ARTICLES_TYPE_DIST' AS section;
SELECT article_type, COUNT(*) AS n
  FROM articles WHERE article_type IS NOT NULL
 GROUP BY 1 ORDER BY n DESC LIMIT 10;

-- Substrate status distribution
SELECT '##ARTICLES_SUBSTRATE_DIST' AS section;
SELECT substrate_status, extraction_version, COUNT(*) AS n
  FROM articles GROUP BY 1,2 ORDER BY n DESC LIMIT 10;

-- Summary length distribution
SELECT '##SUMMARY_LENGTHS' AS section;
SELECT
  'preview'  AS field, MIN(length(summary_preview)),   AVG(length(summary_preview))::int,   MAX(length(summary_preview))
  FROM articles WHERE summary_preview IS NOT NULL
UNION ALL
SELECT 'snippet',   MIN(length(summary_snippet)),   AVG(length(summary_snippet))::int,   MAX(length(summary_snippet))
  FROM articles WHERE summary_snippet IS NOT NULL
UNION ALL
SELECT 'executive', MIN(length(summary_executive)), AVG(length(summary_executive))::int, MAX(length(summary_executive))
  FROM articles WHERE summary_executive IS NOT NULL;

-- ===== SECTION 3: ARTICLE_CLAIMS =====
SELECT '##CLAIMS_FIELDS' AS section;
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE claim_text IS NOT NULL AND claim_text != '')   AS text_filled,
  COUNT(*) FILTER (WHERE subject_text IS NOT NULL AND subject_text != '') AS subj_filled,
  COUNT(*) FILTER (WHERE predicate IS NOT NULL AND predicate != '')     AS pred_filled,
  COUNT(*) FILTER (WHERE object_text IS NOT NULL AND object_text != '') AS obj_filled,
  COUNT(*) FILTER (WHERE subject_entity_id IS NOT NULL)                 AS linked_entity,
  COUNT(*) FILTER (WHERE embedding IS NOT NULL)                         AS embedded,
  AVG(confidence)::numeric(3,2)                                         AS avg_conf,
  AVG(length(claim_text))::int                                          AS avg_text_len
FROM article_claims;

-- ===== SECTION 4: ARTICLE_QUOTES =====
SELECT '##QUOTES_FIELDS' AS section;
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE speaker_name IS NOT NULL AND speaker_name != '') AS spk_filled,
  COUNT(*) FILTER (WHERE speaker_entity_id IS NOT NULL)                 AS spk_linked,
  COUNT(*) FILTER (WHERE quote_text_en IS NOT NULL)                     AS translated,
  COUNT(*) FILTER (WHERE context IS NOT NULL AND context != '')         AS context_filled,
  COUNT(*) FILTER (WHERE is_direct = true)                              AS direct,
  AVG(length(quote_text))::int                                          AS avg_quote_len
FROM article_quotes;

-- ===== SECTION 5: ARTICLE_LOCATIONS =====
SELECT '##LOCATIONS_FIELDS' AS section;
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE location_text IS NOT NULL)  AS text_filled,
  COUNT(*) FILTER (WHERE country IS NOT NULL AND country != '') AS country_filled,
  COUNT(*) FILTER (WHERE region  IS NOT NULL AND region  != '') AS region_filled,
  COUNT(*) FILTER (WHERE city    IS NOT NULL AND city    != '') AS city_filled,
  COUNT(*) FILTER (WHERE location_scope IS NOT NULL) AS scope_filled
FROM article_locations;

SELECT '##LOCATIONS_SCOPE_DIST' AS section;
SELECT location_scope, COUNT(*) AS n
  FROM article_locations WHERE location_scope IS NOT NULL
 GROUP BY 1 ORDER BY n DESC LIMIT 8;

-- ===== SECTION 6: ARTICLE_EVENTS =====
SELECT '##EVENTS_FIELDS' AS section;
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE event_date IS NOT NULL)            AS llm_date_filled,
  COUNT(*) FILTER (WHERE effective_event_date IS NOT NULL)  AS eff_date_filled,
  COUNT(*) FILTER (WHERE event_description IS NOT NULL AND event_description != '') AS desc_filled,
  COUNT(*) FILTER (WHERE event_type IS NOT NULL)            AS type_filled,
  COUNT(*) FILTER (WHERE actors IS NOT NULL AND array_length(actors,1) > 0) AS actors_filled,
  COUNT(*) FILTER (WHERE is_future = true)                  AS future_events,
  COUNT(*) FILTER (WHERE event_cluster_id IS NOT NULL)      AS clustered
FROM article_events;

SELECT '##EVENTS_TYPE_DIST' AS section;
SELECT event_type, COUNT(*) AS n
  FROM article_events WHERE event_type IS NOT NULL
 GROUP BY 1 ORDER BY n DESC LIMIT 10;

-- ===== SECTION 7: ARTICLE_NUMBERS =====
SELECT '##NUMBERS_FIELDS' AS section;
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE value IS NOT NULL AND value != '')   AS val_filled,
  COUNT(*) FILTER (WHERE unit IS NOT NULL AND unit != '')     AS unit_filled,
  COUNT(*) FILTER (WHERE context IS NOT NULL AND context != '') AS context_filled
FROM article_numbers;

SELECT '##NUMBERS_UNIT_DIST' AS section;
SELECT unit, COUNT(*) AS n
  FROM article_numbers WHERE unit IS NOT NULL
 GROUP BY 1 ORDER BY n DESC LIMIT 10;

-- ===== SECTION 8: ARTICLE_STANCES =====
SELECT '##STANCES_FIELDS' AS section;
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE actor IS NOT NULL AND actor != '')   AS actor_filled,
  COUNT(*) FILTER (WHERE actor_entity_id IS NOT NULL)         AS actor_linked,
  COUNT(*) FILTER (WHERE stance IS NOT NULL)                  AS stance_filled,
  COUNT(*) FILTER (WHERE intensity IS NOT NULL)               AS intensity_filled,
  AVG(intensity)::numeric(3,2)                                AS avg_intensity
FROM article_stances;

SELECT '##STANCES_DIST' AS section;
SELECT stance, COUNT(*) AS n
  FROM article_stances WHERE stance IS NOT NULL
 GROUP BY 1 ORDER BY n DESC LIMIT 8;

-- ===== SECTION 9: ENTITY_DICTIONARY =====
SELECT '##ENTITIES_FIELDS' AS section;
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE canonical_name IS NOT NULL)         AS canon_filled,
  COUNT(*) FILTER (WHERE entity_type IS NOT NULL)            AS type_filled,
  COUNT(*) FILTER (WHERE wikidata_id IS NOT NULL)            AS wikidata_linked,
  COUNT(*) FILTER (WHERE aliases IS NOT NULL AND array_length(aliases,1) > 0) AS has_aliases
FROM entity_dictionary;

SELECT '##ENTITIES_TYPE_DIST' AS section;
SELECT entity_type, COUNT(*) AS n
  FROM entity_dictionary WHERE entity_type IS NOT NULL
 GROUP BY 1 ORDER BY n DESC LIMIT 10;

-- ===== SECTION 10: SOURCES =====
SELECT '##SOURCES_FIELDS' AS section;
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE active = true)                AS active_count,
  COUNT(*) FILTER (WHERE health_score > 0.5)           AS healthy,
  COUNT(*) FILTER (WHERE health_score = 0)             AS zero_health,
  AVG(health_score)::numeric(3,2)                      AS avg_health,
  COUNT(DISTINCT pillar)                               AS distinct_pillars
FROM sources;

SELECT '##SOURCES_PILLAR_DIST' AS section;
SELECT pillar, COUNT(*) FILTER (WHERE active=true) AS active_n, COUNT(*) AS total_n
  FROM sources GROUP BY 1 ORDER BY total_n DESC LIMIT 12;

-- ===== SECTION 11: RECENT ARTICLE QUALITY (last 6h) =====
SELECT '##RECENT_6H_QUALITY' AS section;
SELECT
  COUNT(*) AS total_recent,
  COUNT(*) FILTER (WHERE summary_preview IS NOT NULL)   AS prev_pct,
  COUNT(*) FILTER (WHERE summary_executive IS NOT NULL) AS exec_pct,
  COUNT(*) FILTER (WHERE primary_subject IS NOT NULL)   AS subj_pct,
  COUNT(*) FILTER (WHERE register_style IS NOT NULL)    AS regstyle_pct,
  COUNT(*) FILTER (WHERE author_name IS NOT NULL)       AS auth_pct,
  COUNT(*) FILTER (WHERE extraction_version = 3)        AS v3_pct
FROM articles
WHERE collected_at > NOW() - INTERVAL '6 hours';

-- ===== SECTION 12: FK INTEGRITY =====
SELECT '##FK_HEALTH' AS section;
SELECT
  (SELECT COUNT(*) FROM article_claims c LEFT JOIN articles a ON a.id=c.article_id WHERE a.id IS NULL) AS orphan_claims,
  (SELECT COUNT(*) FROM article_quotes q LEFT JOIN articles a ON a.id=q.article_id WHERE a.id IS NULL) AS orphan_quotes,
  (SELECT COUNT(*) FROM article_events e LEFT JOIN articles a ON a.id=e.article_id WHERE a.id IS NULL) AS orphan_events,
  (SELECT COUNT(*) FROM article_locations l LEFT JOIN articles a ON a.id=l.article_id WHERE a.id IS NULL) AS orphan_locs;
