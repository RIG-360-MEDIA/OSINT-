-- 053b_effective_event_date_fix.sql
--
-- FIX for 053: the original CASE expression's Rule 2 (historical reference)
-- fired before Rule 3 (year drift), so year-drift events were misclassified
-- as historical and never corrected. This migration re-runs the UPDATE with
-- the rules reordered: year-drift FIRST, then historical, then is_future, then
-- default.
--
-- Idempotent — safe to re-run. Overwrites effective_event_date in place.

BEGIN;

UPDATE article_events ae
   SET effective_event_date = CASE

       -- Rule 1: year drift correction (PROMOTED to first)
       -- Triggers when extracted year is 2+ years before publish year AND
       -- within the past 20 years (genuinely historical events stay older).
       WHEN ae.event_date IS NOT NULL
            AND ae.is_future = FALSE
            AND EXTRACT(YEAR FROM ae.event_date)::int
                < EXTRACT(YEAR FROM a.published_at)::int - 1
            AND ae.event_date >= a.published_at::date - INTERVAL '20 years'
         THEN MAKE_DATE(
                EXTRACT(YEAR FROM a.published_at)::int,
                EXTRACT(MONTH FROM ae.event_date)::int,
                EXTRACT(DAY FROM ae.event_date)::int
              )

       -- Rule 2: future events trust the LLM (we're forecasting)
       WHEN ae.is_future = TRUE
         THEN ae.event_date

       -- Rule 3: genuinely historical references trust LLM.
       -- After year-drift correction above, anything still > 60 days before
       -- publish AND > 1 year before publish year is a real historical event.
       WHEN ae.event_date IS NOT NULL
            AND ae.event_date < a.published_at::date - INTERVAL '60 days'
         THEN ae.event_date

       -- Default: trust the LLM (within tolerance, no drift detected)
       ELSE ae.event_date

     END
  FROM articles a
 WHERE ae.article_id = a.id;

COMMIT;
