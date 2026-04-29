-- 029_seed_opposition_handles.sql
-- CM Page: opposition spokesperson coverage.
--
-- IMPORTANT — content correctness rule applies here:
-- This migration creates the cm_political_handles registry but does NOT
-- seed Twitter/X handles, YouTube channels, or press URLs. Every handle
-- must be verified against the actual party / individual's official
-- presence before insertion. A wrong handle attributes statements to the
-- wrong person and instantly destroys CM-grade trust.
--
-- After applying this migration, populate via the verified seed file:
--   psql -U rig -d rig -f scripts/seeds/political_handles_TG.sql
--   psql -U rig -d rig -f scripts/seeds/political_handles_AP.sql
-- (those seed files must include source_url for every row pointing to the
--  party's own website / verified social profile.)

CREATE TABLE IF NOT EXISTS cm_political_handles (
    id              BIGSERIAL PRIMARY KEY,
    state           TEXT NOT NULL,                                          -- 'TG' / 'AP'
    coalition       TEXT NOT NULL CHECK (coalition IN ('ruling','opposition','neutral')),
    party           TEXT NOT NULL,
    person_name     TEXT,                                                   -- NULL for party official accounts
    person_role     TEXT,                                                   -- 'CM','Minister','MP','MLA','Spokesperson','Party'
    platform        TEXT NOT NULL CHECK (platform IN ('twitter','youtube','press_rss','press_html','telegram','facebook')),
    handle          TEXT NOT NULL,                                          -- '@KTRBRS' / 'UCxxx' / 'https://...'
    url             TEXT NOT NULL,                                          -- canonical URL of the resource
    verified_url    TEXT,                                                   -- where verification was sourced (party site, official press release, etc.)
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    cadence_minutes INT NOT NULL DEFAULT 60,                                -- collection cadence override
    inserted_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT cm_handles_unique UNIQUE (platform, handle, state)
);

CREATE INDEX IF NOT EXISTS cm_handles_state_idx
    ON cm_political_handles (state, coalition, active);

CREATE INDEX IF NOT EXISTS cm_handles_platform_idx
    ON cm_political_handles (platform, active);

COMMENT ON TABLE cm_political_handles IS
  'CM Page: registry of verified political handles. New rows MUST carry a verified_url.';

-- ── Coalitions map (ruling / opposition lookup per state) ─────────────────
-- Used by backend/nlp/cm/coalitions.py to resolve a party label to its
-- party_kind for the user's currently-selected state. Updated whenever a
-- coalition realigns. Current rows reflect the situation as of 2026-04-28:
--   TG: INC ruling (since Dec 2023); BRS, BJP, AIMIM in opposition.
--   AP: TDP-JSP-BJP alliance ruling (since June 2024); YSRCP, INC in
--       opposition.
-- Verify against the latest CEO / EC of India statement before changing.

CREATE TABLE IF NOT EXISTS cm_coalitions (
    state         TEXT NOT NULL,
    party         TEXT NOT NULL,
    coalition     TEXT NOT NULL CHECK (coalition IN ('ruling','opposition','neutral')),
    since         DATE,
    source_url    TEXT,
    inserted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (state, party)
);

INSERT INTO cm_coalitions (state, party, coalition, since, source_url) VALUES
    -- Telangana — Indian National Congress formed government after Dec 2023
    -- assembly election; Revanth Reddy sworn in as CM on 7 Dec 2023.
    ('TG', 'INC',     'ruling',     DATE '2023-12-07', 'https://eci.gov.in/'),
    ('TG', 'BRS',     'opposition', DATE '2023-12-07', 'https://eci.gov.in/'),
    ('TG', 'BJP',     'opposition', DATE '2023-12-07', 'https://eci.gov.in/'),
    ('TG', 'AIMIM',   'opposition', DATE '2023-12-07', 'https://eci.gov.in/'),
    -- Andhra Pradesh — TDP-led NDA alliance won June 2024 assembly
    -- election; Chandrababu Naidu sworn in as CM on 12 June 2024.
    ('AP', 'TDP',     'ruling',     DATE '2024-06-12', 'https://eci.gov.in/'),
    ('AP', 'JSP',     'ruling',     DATE '2024-06-12', 'https://eci.gov.in/'),
    ('AP', 'BJP',     'ruling',     DATE '2024-06-12', 'https://eci.gov.in/'),
    ('AP', 'YSRCP',   'opposition', DATE '2024-06-12', 'https://eci.gov.in/'),
    ('AP', 'INC',     'opposition', DATE '2024-06-12', 'https://eci.gov.in/')
ON CONFLICT (state, party) DO NOTHING;

COMMENT ON TABLE cm_coalitions IS
  'CM Page: per-state coalition map. Update on every realignment with a verified source_url.';
