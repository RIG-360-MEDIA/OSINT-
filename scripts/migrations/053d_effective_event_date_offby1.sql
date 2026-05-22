-- 053d_effective_event_date_offby1.sql
--
-- Add a refinement to catch year-drift cases off by exactly 1 year.
-- Pattern: article published in May 2026, LLM extracted event as May 2025.
-- The month/day match suggests "this month" interpretation but year drifted.
--
-- Heuristic: when (extracted_year = publish_year - 1) AND extracted month
-- equals publish month AND day is within ±15 of publish day, treat as drift
-- and swap to publish year. This catches "May 12, 2025" → "May 12, 2026" for
-- a May 20, 2026 article.
--
-- Why not blanket off-by-1: legitimate end-of-year cases exist (Jan 2 article
-- about a Dec 31 event last year). Those will have month-mismatch and stay put.
--
-- Idempotent — re-runs the FULL clamp, replacing 053c's result.

BEGIN;

UPDATE article_events ae
   SET effective_event_date = CASE

       -- Rule 1: clear year-drift (extracted year ≥ 2 years before publish year)
       WHEN ae.event_date IS NOT NULL
            AND ae.is_future = FALSE
            AND EXTRACT(YEAR FROM ae.event_date)::int
                < EXTRACT(YEAR FROM a.published_at)::int - 1
            AND ae.event_date >= a.published_at::date - INTERVAL '20 years'
            AND NOT (EXTRACT(MONTH FROM ae.event_date)::int = 2
                     AND EXTRACT(DAY FROM ae.event_date)::int = 29)
         THEN MAKE_DATE(
                EXTRACT(YEAR FROM a.published_at)::int,
                EXTRACT(MONTH FROM ae.event_date)::int,
                EXTRACT(DAY FROM ae.event_date)::int
              )

       -- Rule 1.5 (NEW): off-by-1 drift, same month, day within ±15
       WHEN ae.event_date IS NOT NULL
            AND ae.is_future = FALSE
            AND EXTRACT(YEAR FROM ae.event_date)::int
                = EXTRACT(YEAR FROM a.published_at)::int - 1
            AND EXTRACT(MONTH FROM ae.event_date)::int
                = EXTRACT(MONTH FROM a.published_at)::int
            AND ABS(EXTRACT(DAY FROM ae.event_date)::int
                    - EXTRACT(DAY FROM a.published_at)::int) <= 15
            AND NOT (EXTRACT(MONTH FROM ae.event_date)::int = 2
                     AND EXTRACT(DAY FROM ae.event_date)::int = 29)
         THEN MAKE_DATE(
                EXTRACT(YEAR FROM a.published_at)::int,
                EXTRACT(MONTH FROM ae.event_date)::int,
                EXTRACT(DAY FROM ae.event_date)::int
              )

       -- Rule 2: future events trust the LLM
       WHEN ae.is_future = TRUE
         THEN ae.event_date

       -- Rule 3: genuine historical references trust LLM
       WHEN ae.event_date IS NOT NULL
            AND ae.event_date < a.published_at::date - INTERVAL '60 days'
         THEN ae.event_date

       -- Default: trust LLM
       ELSE ae.event_date

     END
  FROM articles a
 WHERE ae.article_id = a.id;

COMMIT;
