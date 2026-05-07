-- ============================================================
-- Migration 038 — coverage_panel_summaries
-- ============================================================
-- Single-row-per-slug cache for the LLM-generated 2–3 line
-- summaries shown on the /coverage hub page panels.
--
-- Refreshed daily by tasks.refresh_coverage_summaries (Celery
-- beat fire at 04:15 UTC). Read by /api/coverage/panels at
-- request time. Falls back to a static seed (inserted below)
-- if Groq is unavailable on first boot.
--
-- Idempotent — safe to re-run.
-- ============================================================

CREATE TABLE IF NOT EXISTS coverage_panel_summaries (
    slug                TEXT        PRIMARY KEY,
    summary             TEXT        NOT NULL,
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    generated_by_model  TEXT        NOT NULL DEFAULT 'llama-3.1-8b-instant',
    source_sample_size  INTEGER     NOT NULL DEFAULT 0,
    CONSTRAINT coverage_panel_summaries_slug_chk
      CHECK (slug IN ('articles', 'newspaper', 'tv', 'social', 'govt'))
);

COMMENT ON TABLE coverage_panel_summaries IS
  'Daily LLM-generated 2-3 line summary per /coverage panel. Cached server-side, refreshed at 04:15 UTC by tasks.refresh_coverage_summaries.';

-- Seed fallback summaries so first page-load isn't empty before
-- the cron has fired once.
INSERT INTO coverage_panel_summaries (slug, summary, source_sample_size)
VALUES
  ('articles',  'A continuous stream of regional and national reporting, scraped from RSS feeds and direct sources, ranked by per-user relevance.', 0),
  ('newspaper', 'Daily editions filed from print and e-paper sources, archived as searchable text alongside the original layout.', 0),
  ('tv',        'Broadcast clips and long-form interviews — transcripts and key moments indexed alongside their video.', 0),
  ('social',    'Reddit and Telegram signals, translated when needed, clustered by topic and weighted by community velocity.', 0),
  ('govt',      'Official orders, circulars, and gazettes from central, state, and district authorities — parsed, chunked, and citable.', 0)
ON CONFLICT (slug) DO NOTHING;
