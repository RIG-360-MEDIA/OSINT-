-- 027_cm_risk_calendar.sql
-- CM Page: 7-day political-risk calendar.
-- Rows are populated from:
--   * govt_documents.kind in ('court_listing','parliament_business')
--   * tasks.cm.refresh_risk_window scheduled events (court_listing,
--     parliament_business) discovered every 6h
--   * a hand-curated seed of festivals, by-poll dates, and political
--     anniversaries that the user adds via SQL or a small admin tool
-- Every row must be backed by a source_url or a documented seed entry —
-- never invent dates.

CREATE TABLE IF NOT EXISTS cm_risk_calendar (
    id            BIGSERIAL PRIMARY KEY,
    event_date    DATE NOT NULL,
    state         TEXT,                                              -- 'TG' / 'AP' / NULL for national
    kind          TEXT NOT NULL CHECK (kind IN ('court','parliament','festival','by_election','anniversary','deadline','protest','session')),
    title         TEXT NOT NULL,
    description   TEXT,
    source_id     BIGINT,                                            -- FK-like reference to govt_documents.id when applicable
    source_kind   TEXT,                                              -- 'govt_document' / 'manual_seed' / ...
    source_url    TEXT,
    risk_summary  TEXT,                                              -- 1-sentence why-this-matters
    risk_level    TEXT NOT NULL CHECK (risk_level IN ('low','med','high')) DEFAULT 'low',
    inserted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Unique on (event_date, kind, title, state-or-empty). Expression index
-- because Postgres doesn't accept COALESCE inside inline UNIQUE constraints.
CREATE UNIQUE INDEX IF NOT EXISTS cm_risk_unique_idx
    ON cm_risk_calendar (event_date, kind, title, (COALESCE(state, '')));

CREATE INDEX IF NOT EXISTS cm_risk_date_idx
    ON cm_risk_calendar (event_date);

CREATE INDEX IF NOT EXISTS cm_risk_state_date_idx
    ON cm_risk_calendar (state, event_date);

CREATE INDEX IF NOT EXISTS cm_risk_kind_date_idx
    ON cm_risk_calendar (kind, event_date);

COMMENT ON TABLE cm_risk_calendar IS
  'CM Page: dated political-risk events. Every row must carry a source_url or be marked source_kind=manual_seed.';
