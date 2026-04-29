-- 025_cm_promises.sql
-- CM Page: manifesto / public-pledge tracker.
-- Seed rows are loaded ONLY from publicly-published manifestos and speech
-- transcripts with a verifiable source_url. Status starts at 'unknown' and
-- is updated daily by tasks.cm.score_promise_status using RAG-grounded
-- LLM classification. Below-threshold confidence reverts the row to
-- 'unknown' rather than guessing.

CREATE TABLE IF NOT EXISTS cm_promises (
    id                   BIGSERIAL PRIMARY KEY,
    state                TEXT NOT NULL,                                       -- 'TG' / 'AP'
    pledge_text          TEXT NOT NULL,
    pledge_short         TEXT,                                                -- short label for UI
    owner_party          TEXT NOT NULL,                                       -- party that made the pledge
    source               TEXT,                                                -- 'manifesto-2023' / 'public-speech-2024-05-13' / ...
    source_url           TEXT,                                                -- MANDATORY in practice; nullable only for legacy rows
    pledged_at           DATE,                                                -- when the pledge was made
    deadline             DATE,                                                -- self-imposed or implied deadline; nullable
    status               TEXT NOT NULL CHECK (status IN ('kept','in_progress','stalled','broken','unknown')) DEFAULT 'unknown',
    status_confidence    REAL CHECK (status_confidence BETWEEN 0 AND 1),
    last_status_change   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_evidence_url    TEXT,
    exploitation_index   REAL NOT NULL DEFAULT 0,                             -- 0..100, how much opposition is using it
    last_scored_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS cm_promises_state_idx
    ON cm_promises (state, status, deadline);

CREATE INDEX IF NOT EXISTS cm_promises_exploit_idx
    ON cm_promises (state, exploitation_index DESC);

COMMENT ON TABLE cm_promises IS
  'CM Page: pledge ledger. Every row must have a verifiable source_url; new rows must not be added without one.';
