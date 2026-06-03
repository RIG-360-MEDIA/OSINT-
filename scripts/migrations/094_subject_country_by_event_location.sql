-- 094_subject_country_by_event_location.sql
-- F-3 (2026-06-03): subject_country by EVENT location, not source-country (audit #3).
--
-- ROOT CAUSE: subject_country was mode(source_country) = a COVERAGE bias. The MV Hondius cruise
-- read subject_country=IN because Indian outlets covered it heavily, though the event is in Spain.
-- Validation (read-only, on the surfaced corpus) showed article_locations (geocoded per-article,
-- is_primary) is net-better than source-country (2 errors vs 5 on a 14-story sample; 86% coverage),
-- so the fix derives subject_country from the dominant EVENT location.
--
-- DESIGN (validated; see entity-picker / F-3 thread):
--   * aggregation = NAIVE top is_primary count  (confidence*mention weighting backfired badly:
--     cruise -> Sierra Leone, Guthrie -> Morocco)
--   * margin-guard = override ONLY on clear plurality: top count >= 2 AND top >= 2x runner-up.
--     This kills the mentioned-not-subject tail (Putin-in-Delhi stays IN not China; Modi-Nordic
--     stays IN not Norway).
--   * ISO map = hand-built + verified off the 68 distinct dominant event-countries in the corpus.
--     A name NOT in the map keeps the old source-country value (surface-when-unsure: a wrong ISO
--     is worse than the old known value).
--   * subject_region (geo_primary mode) is LEFT ALONE -- it is content-derived and mostly correct
--     (the cruise's "Tenerife" is more specific than "Spain"); only the source-biased COUNTRY field
--     is fixed.
--
-- This mirrors story_loader._subject_country (the durable path, runs every load). Display-only field;
-- entity_core_cov + is_template_family are untouched, so the §2b + size x core gates are unaffected.
-- Idempotent (only sets where the value differs). One-shot for the pre-fix live keeper.

BEGIN;

CREATE TEMP TABLE _iso094(name text PRIMARY KEY, code char(2)) ON COMMIT DROP;
INSERT INTO _iso094 VALUES
('India','IN'),('United States','US'),('United Kingdom','GB'),('Nigeria','NG'),('China','CN'),
('Australia','AU'),('France','FR'),('Iran','IR'),('Italy','IT'),('Ukraine','UA'),
('Democratic Republic of the Congo','CD'),('Russia','RU'),('Spain','ES'),('Pakistan','PK'),
('Singapore','SG'),('Cuba','CU'),('Sri Lanka','LK'),('Canada','CA'),('Norway','NO'),('Mexico','MX'),
('Nepal','NP'),('Colombia','CO'),('Hungary','HU'),('Brazil','BR'),('South Africa','ZA'),
('Bangladesh','BD'),('Germany','DE'),('South Korea','KR'),('Kenya','KE'),('Turkey','TR'),
('Austria','AT'),('Ghana','GH'),('Greece','GR'),('Indonesia','ID'),('Japan','JP'),('Laos','LA'),
('Namibia','NA'),('Netherlands','NL'),('North Korea','KP'),('Philippines','PH'),('Saudi Arabia','SA'),
('Sudan','SD'),('Thailand','TH'),('Uganda','UG'),('United Arab Emirates','AE'),('Romania','RO'),
('Lebanon','LB'),('Cameroon','CM'),('Senegal','SN'),('Jamaica','JM'),('Israel','IL'),('Ethiopia','ET'),
('South Sudan','SS'),('Eswatini','SZ'),('Estonia','EE'),('Belarus','BY'),('Switzerland','CH'),
('Taiwan','TW'),('Vatican City','VA'),('Denmark','DK'),('Myanmar','MM'),('Vietnam','VN'),('Morocco','MA'),
('Czech Republic','CZ'),('Mali','ML'),('Malaysia','MY'),('Zimbabwe','ZW'),('Poland','PL');

WITH loc AS (
  SELECT m.story_id, al.country, count(*) c
  FROM analytics.story_clusters c
  JOIN analytics.story_cluster_members m ON m.story_id = c.story_id
  JOIN public.article_locations al ON al.article_id = m.article_id AND al.is_primary
  WHERE c.is_template_family = false
    AND (c.independent_source_count >= 3 OR c.rescued_from_story_id IS NOT NULL)
    AND al.country IS NOT NULL AND al.country <> ''
  GROUP BY 1, 2),
r AS (SELECT story_id, country, c, row_number() OVER (PARTITION BY story_id ORDER BY c DESC) rn FROM loc),
agg AS (SELECT story_id,
               max(country) FILTER (WHERE rn=1) top1,
               max(c)       FILTER (WHERE rn=1) c1,
               COALESCE(max(c) FILTER (WHERE rn=2), 0) c2
        FROM r WHERE rn <= 2 GROUP BY 1),
ovr AS (SELECT a.story_id, i.code FROM agg a JOIN _iso094 i ON i.name = a.top1
        WHERE a.c1 >= 2 AND a.c1 >= 2 * a.c2)               -- min support + clear plurality
UPDATE analytics.story_clusters c
SET subject_country = o.code, updated_at = now()
FROM ovr o
WHERE c.story_id = o.story_id AND c.subject_country IS DISTINCT FROM o.code;

COMMIT;
