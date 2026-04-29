-- 024_cm_dissent_signals.sql
-- CM Page: intra-coalition contradiction signals.
-- Populated by tasks.cm.score_dissent which runs daily and pairs same-party
-- speakers on the same issue within a 48h window, asking the LLM whether two
-- quotes contradict each other materially. Confidence threshold 0.7 enforced
-- at the read endpoint, not in this table.

CREATE TABLE IF NOT EXISTS cm_dissent_signals (
    id              BIGSERIAL PRIMARY KEY,
    state           TEXT,
    coalition       TEXT NOT NULL CHECK (coalition IN ('ruling','opposition')),
    party           TEXT NOT NULL,
    speakers        TEXT[] NOT NULL,                                  -- canonical names of contradicting speakers
    issue_id        BIGINT REFERENCES cm_issues(id) ON DELETE SET NULL,
    summary         TEXT NOT NULL,                                    -- 1-2 sentences naming the contradiction
    severity        TEXT NOT NULL CHECK (severity IN ('murmur','crack','break')) DEFAULT 'murmur',
    confidence      REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence_urls   TEXT[] NOT NULL DEFAULT '{}',
    quote_ids       BIGINT[] NOT NULL DEFAULT '{}',                   -- references cm_spokesperson_quotes.id
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS cm_dissent_detected_idx
    ON cm_dissent_signals (state, detected_at DESC);

CREATE INDEX IF NOT EXISTS cm_dissent_party_idx
    ON cm_dissent_signals (party, detected_at DESC);

CREATE INDEX IF NOT EXISTS cm_dissent_coalition_idx
    ON cm_dissent_signals (state, coalition, detected_at DESC);

COMMENT ON TABLE cm_dissent_signals IS
  'CM Page: intra-coalition contradictions detected by pairwise LLM compare. severity is a UI-grade label, not a threshold.';
