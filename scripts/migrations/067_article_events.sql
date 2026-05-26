-- 067_article_events.sql
-- Auto-extracted events + dates from each article body. Powers event
-- timeline auto-assembly (9B) and story-arc trajectory plotting (14A).
-- Each event has a description, an inferred date (when statable), and a
-- confidence — articles can have multiple events.

BEGIN;

CREATE TABLE IF NOT EXISTS article_events (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  article_id         uuid NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  event_date         date,
  event_description  text NOT NULL,
  event_type         text,                  -- 'announcement','meeting','filing','statement','protest','release','other'
  actors             text[],                -- entity names involved
  confidence         numeric(3,2),
  position           smallint,
  created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_article_events_article
  ON article_events(article_id);
CREATE INDEX IF NOT EXISTS idx_article_events_date
  ON article_events(event_date) WHERE event_date IS NOT NULL;

COMMIT;
