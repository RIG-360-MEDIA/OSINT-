-- 053_effective_event_date.sql
--
-- PHASE 0 of the data quality plan.
--
-- Adds a derived column `effective_event_date` to article_events that corrects
-- the year-drift bug discovered in v3 extraction. The LLM defaulted to its
-- training-cutoff year (~2024) when the article text mentioned a date without
-- an explicit year nearby. This produced same-event splits (e.g. Twisha
-- Sharma's death clustered as 2024-05-12, 2025-05-12, and 2026-05-12 from
-- articles all collected May 19-20, 2026).
--
-- The clamp uses Option 4 logic — publish-date as anchor:
--   1. If the event is marked is_future → trust the LLM date (we're forecasting)
--   2. If the extracted date is genuinely OLD (> 60 days before publish) → trust
--      the LLM date (it's a real historical reference like "Russia's 2022 invasion")
--   3. If the extracted year is 2+ years before the article's publish year →
--      year drift detected; keep the LLM's month/day but use publish year
--   4. Otherwise → trust the LLM date (within tolerance)
--
-- The original `event_date` column is NOT modified. This is fully reversible
-- by dropping the new column.

BEGIN;

ALTER TABLE article_events
  ADD COLUMN IF NOT EXISTS effective_event_date date;

-- Apply the clamp. JOIN against articles to read published_at.
UPDATE article_events ae
   SET effective_event_date = CASE

       -- Rule 1: future events trust the LLM (we're forecasting)
       WHEN ae.is_future = TRUE
         THEN ae.event_date

       -- Rule 2: genuinely historical references (>60 days before publish) trust LLM
       WHEN ae.event_date IS NOT NULL
            AND ae.event_date < a.published_at::date - INTERVAL '60 days'
         THEN ae.event_date

       -- Rule 3: clear year-drift (extracted year is 2+ years before publish year)
       --        → swap year, keep month/day
       WHEN ae.event_date IS NOT NULL
            AND EXTRACT(YEAR FROM ae.event_date)::int
                < EXTRACT(YEAR FROM a.published_at)::int - 1
            AND ae.event_date >= a.published_at::date - INTERVAL '20 years'
         THEN MAKE_DATE(
                EXTRACT(YEAR FROM a.published_at)::int,
                EXTRACT(MONTH FROM ae.event_date)::int,
                EXTRACT(DAY FROM ae.event_date)::int
              )

       -- Default: trust the LLM (within tolerance, no obvious drift)
       ELSE ae.event_date

     END
  FROM articles a
 WHERE ae.article_id = a.id;

-- Index for cluster queries that filter/order by date
CREATE INDEX IF NOT EXISTS idx_article_events_effective_date
  ON article_events (effective_event_date)
 WHERE effective_event_date IS NOT NULL;

COMMENT ON COLUMN article_events.effective_event_date IS
  'Year-corrected event date. Derived from event_date + articles.published_at '
  'using Option 4 clamp (see scripts/migrations/053). The original event_date '
  'remains untouched. Clustering and brief queries should use '
  'effective_event_date going forward.';

COMMIT;
