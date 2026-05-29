-- ============================================================================
-- Migration 072 — effective_event_date smart year-fix
-- ============================================================================
-- Problem:
--   article_events.event_date is LLM-extracted and has a year-bias:
--   when the article source omits the year (e.g. "on May 4"), the model
--   defaults to its training-cutoff year (typically 2024). That puts ~33%
--   of fresh news in the wrong year bucket.
--
-- Strategy (validated against 207K rows on 2026-05-28):
--   Compute effective_event_date with a 4-tier rule:
--     Tier 1: LLM date is within ±365 days of publish date → trust LLM
--     Tier 2: wrong year but (LLM month/day + publish year) within ±14 days
--             of publish date → year-corrected (rescues year-bias hallucinations)
--     Tier 3: wrong year and year-fix doesn't help → keep LLM date
--             (these are real past/future events: Artemis 2028, Senegal 2024)
--     Tier 4: LLM gave no date OR no publish_at → fallback to
--             COALESCE(published_at, collected_at)::date
--
-- Why ±14 days (not 60):
--   60d window was tested and would have corrupted ~1,479 real past/future
--   events (election dates, scheduled launches, anniversaries). 14d is
--   tight enough that only same-cycle news gets year-fixed.
--
-- Preserves:
--   - Original event_date column is NEVER modified (audit trail)
--   - Only effective_event_date is written
--
-- Performance:
--   - Backfill on 207K rows: ~30 sec (single UPDATE with JOIN)
--   - Trigger overhead on INSERT: <1 ms (one lookup on articles by PK)
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. Snapshot existing values before any writes (audit + rollback path)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS article_events_eed_backup_20260528 AS
SELECT id, event_date, effective_event_date
  FROM article_events;

CREATE INDEX IF NOT EXISTS article_events_eed_backup_20260528_id_idx
  ON article_events_eed_backup_20260528 (id);

-- ----------------------------------------------------------------------------
-- 2. Helper function: compute effective_event_date from LLM date + publish/collect
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION compute_effective_event_date(
  p_llm_date   date,
  p_publish_at timestamptz,
  p_collect_at timestamptz
) RETURNS date AS $$
DECLARE
  v_anchor    date;
  v_llm_year  int;
  v_anchor_yr int;
  v_corrected date;
BEGIN
  -- Anchor = publish_at if present, else collected_at
  v_anchor := COALESCE(p_publish_at::date, p_collect_at::date);

  -- Tier 4: no LLM date OR no anchor → fallback to anchor
  IF p_llm_date IS NULL OR v_anchor IS NULL THEN
    RETURN v_anchor;
  END IF;

  v_llm_year  := EXTRACT(YEAR FROM p_llm_date)::int;
  v_anchor_yr := EXTRACT(YEAR FROM v_anchor)::int;

  -- Tier 1: LLM date within ±365 days of anchor → trust LLM
  IF ABS(p_llm_date - v_anchor) <= 365 THEN
    RETURN p_llm_date;
  END IF;

  -- Tier 2: try year-correction (keep month/day, swap year to anchor year)
  --         Use interval arithmetic to handle Feb-29 leap-year edge case.
  v_corrected := (p_llm_date + ((v_anchor_yr - v_llm_year) || ' years')::interval)::date;

  IF ABS(v_corrected - v_anchor) <= 14 THEN
    RETURN v_corrected;
  END IF;

  -- Tier 3: year-fix doesn't help — LLM probably extracted a real
  --         past/future event date that doesn't match anchor.
  --         Keep LLM date as-is.
  RETURN p_llm_date;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION compute_effective_event_date IS
  '4-tier rule for resolving LLM-extracted event_date against article publish/collect dates. See migration 072 header for details.';

-- ----------------------------------------------------------------------------
-- 3. Trigger: auto-populate effective_event_date on INSERT/UPDATE
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_set_effective_event_date() RETURNS trigger AS $$
DECLARE
  v_pub  timestamptz;
  v_coll timestamptz;
BEGIN
  -- Skip work if column already explicitly set in same statement
  -- (allows manual override; trigger fills only when NULL)
  IF NEW.effective_event_date IS NOT NULL AND TG_OP = 'INSERT' THEN
    RETURN NEW;
  END IF;

  SELECT published_at, collected_at INTO v_pub, v_coll
    FROM articles WHERE id = NEW.article_id;

  NEW.effective_event_date :=
    compute_effective_event_date(NEW.event_date, v_pub, v_coll);

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_article_events_eed ON article_events;
CREATE TRIGGER trg_article_events_eed
  BEFORE INSERT OR UPDATE OF event_date ON article_events
  FOR EACH ROW EXECUTE FUNCTION trg_set_effective_event_date();

-- ----------------------------------------------------------------------------
-- 4. One-time backfill of existing rows
-- ----------------------------------------------------------------------------
UPDATE article_events e
   SET effective_event_date = compute_effective_event_date(
         e.event_date, a.published_at, a.collected_at
       )
  FROM articles a
 WHERE e.article_id = a.id;

-- ----------------------------------------------------------------------------
-- 5. Index for timeline queries
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS article_events_effective_date_idx
  ON article_events (effective_event_date DESC)
  WHERE effective_event_date IS NOT NULL;

COMMIT;

-- ============================================================================
-- ROLLBACK procedure (if needed):
--   BEGIN;
--     DROP TRIGGER IF EXISTS trg_article_events_eed ON article_events;
--     DROP FUNCTION IF EXISTS trg_set_effective_event_date();
--     DROP FUNCTION IF EXISTS compute_effective_event_date(date, timestamptz, timestamptz);
--     UPDATE article_events e
--        SET effective_event_date = b.effective_event_date
--       FROM article_events_eed_backup_20260528 b
--      WHERE e.id = b.id;
--   COMMIT;
-- ============================================================================
