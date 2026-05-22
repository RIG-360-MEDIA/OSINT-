-- 053c_effective_event_date_leap_fix.sql
--
-- FIX for 053b: MAKE_DATE(2026, 2, 29) errors because 2026 isn't a leap year.
-- When an LLM-extracted date is Feb 29 (only valid in leap years) and we try
-- to swap year to a non-leap target, MAKE_DATE raises. The whole UPDATE
-- transaction then rolls back, so no corrections land.
--
-- Fix: exclude Feb 29 from Rule 3. Those events keep their LLM date. ~365
-- events per leap year affected — acceptable trade-off versus blocking the
-- entire 43K-event correction.
--
-- Idempotent — safe to re-run.

BEGIN;

UPDATE article_events ae
   SET effective_event_date = CASE

       -- Rule 1: year drift correction (FIRST, with leap-year guard)
       WHEN ae.event_date IS NOT NULL
            AND ae.is_future = FALSE
            AND EXTRACT(YEAR FROM ae.event_date)::int
                < EXTRACT(YEAR FROM a.published_at)::int - 1
            AND ae.event_date >= a.published_at::date - INTERVAL '20 years'
            AND NOT (
              EXTRACT(MONTH FROM ae.event_date)::int = 2
              AND EXTRACT(DAY FROM ae.event_date)::int = 29
            )
         THEN MAKE_DATE(
                EXTRACT(YEAR FROM a.published_at)::int,
                EXTRACT(MONTH FROM ae.event_date)::int,
                EXTRACT(DAY FROM ae.event_date)::int
              )

       -- Rule 2: future events trust the LLM
       WHEN ae.is_future = TRUE
         THEN ae.event_date

       -- Rule 3: genuine historical references trust LLM (after drift fix above)
       WHEN ae.event_date IS NOT NULL
            AND ae.event_date < a.published_at::date - INTERVAL '60 days'
         THEN ae.event_date

       -- Default: trust LLM
       ELSE ae.event_date

     END
  FROM articles a
 WHERE ae.article_id = a.id;

COMMIT;
