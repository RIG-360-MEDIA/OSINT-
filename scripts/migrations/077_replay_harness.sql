-- 077_replay_harness.sql
-- Replay Harness: simulate a clock so a frozen-DB snapshot behaves like live data.
-- Pattern: time-sensitive queries call analytics.now_sim() (and analytics.now_sim_date())
-- instead of NOW() and CURRENT_DATE. When replay_clock.sim_now IS NULL, both functions
-- pass through to the real clock. When sim_now is set, every query sees the world
-- as it would have been at that moment — articles "arrive" at their natural cadence
-- as the clock ticks forward.
--
-- Lives entirely in the analytics.* schema. analytics_user already has RW there
-- per migration 076; no permission changes required.
--
-- Documented in docs/OSINT_BRIEF_ROADMAP.md and products/osint/backend/README.md.

BEGIN;

CREATE TABLE IF NOT EXISTS analytics.replay_clock (
    id         INT         PRIMARY KEY DEFAULT 1,
    sim_now    TIMESTAMPTZ,
    note       TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (id = 1)
);

-- Idempotency: a pre-existing table from an earlier prototype may lack note.
ALTER TABLE analytics.replay_clock ADD COLUMN IF NOT EXISTS note TEXT;

INSERT INTO analytics.replay_clock (id, sim_now, note)
VALUES (1, NULL, 'NULL = pass through to real NOW(); set via analytics.reset_clock(t)')
ON CONFLICT (id) DO NOTHING;

-- Read the simulated time. Returns real NOW() when sim_now IS NULL.
CREATE OR REPLACE FUNCTION analytics.now_sim()
RETURNS TIMESTAMPTZ
LANGUAGE SQL STABLE AS $$
    SELECT COALESCE(sim_now, NOW()) FROM analytics.replay_clock WHERE id = 1
$$;

-- Read the simulated date. Returns real CURRENT_DATE when sim_now IS NULL.
CREATE OR REPLACE FUNCTION analytics.now_sim_date()
RETURNS DATE
LANGUAGE SQL STABLE AS $$
    SELECT COALESCE(sim_now, NOW())::DATE FROM analytics.replay_clock WHERE id = 1
$$;

-- Advance the clock by N minutes. If sim_now is NULL, starts ticking from real NOW().
CREATE OR REPLACE FUNCTION analytics.tick(minutes INT)
RETURNS TIMESTAMPTZ LANGUAGE SQL AS $$
    UPDATE analytics.replay_clock
       SET sim_now    = COALESCE(sim_now, NOW()) + (minutes::TEXT || ' minutes')::INTERVAL,
           updated_at = NOW()
     WHERE id = 1
    RETURNING sim_now
$$;

-- Reset the clock to a specific moment.
CREATE OR REPLACE FUNCTION analytics.reset_clock(target TIMESTAMPTZ)
RETURNS TIMESTAMPTZ LANGUAGE SQL AS $$
    UPDATE analytics.replay_clock
       SET sim_now    = target,
           updated_at = NOW()
     WHERE id = 1
    RETURNING sim_now
$$;

-- Clear the clock: drops back to real NOW() pass-through.
CREATE OR REPLACE FUNCTION analytics.clear_clock()
RETURNS VOID LANGUAGE SQL AS $$
    UPDATE analytics.replay_clock
       SET sim_now    = NULL,
           updated_at = NOW()
     WHERE id = 1
$$;

COMMIT;

-- Smoke check (run manually after applying):
-- SELECT analytics.now_sim();                       -- ≈ NOW() since sim_now is NULL
-- SELECT analytics.reset_clock('2026-05-27 06:00 UTC');
-- SELECT analytics.now_sim();                       -- 2026-05-27 06:00:00+00
-- SELECT analytics.tick(15);                        -- 2026-05-27 06:15:00+00
-- SELECT analytics.clear_clock();                   -- back to real NOW() pass-through
