-- 028_cm_constituencies_and_views.sql
-- CM Page: assembly constituencies + materialized views for hot-path reads.
--
-- IMPORTANT: assembly_constituencies seed below is INTENTIONALLY EMPTY.
-- The full ECI roster (Telangana 119 ACs, Andhra Pradesh 175 ACs) must be
-- loaded from a verified source — Election Commission of India PDFs, the
-- Lok Sabha / Vidhan Sabha rosters at https://eci.gov.in/, or the state
-- CEO sites (https://ceotelangana.nic.in/, https://ceoandhra.nic.in/).
-- Do NOT populate this table with hand-typed names; a single misnamed AC
-- breaks heatmap drilldowns.
-- Load via:
--   psql -U rig -d rig -f scripts/seeds/assembly_constituencies_TG.sql
--   psql -U rig -d rig -f scripts/seeds/assembly_constituencies_AP.sql
-- (those seed files are produced by parsing the official roster — see
--  scripts/seeds/README.md).

CREATE TABLE IF NOT EXISTS assembly_constituencies (
    code            TEXT PRIMARY KEY,                         -- ECI code, e.g. 'TG-001', 'AP-042'
    state           TEXT NOT NULL,                            -- 'TG' / 'AP'
    number          INT NOT NULL,                             -- 1..119 (TG) or 1..175 (AP)
    name            TEXT NOT NULL,
    name_te         TEXT,                                     -- Telugu name
    district        TEXT,
    parliamentary   TEXT,                                     -- parent Lok Sabha constituency
    reservation     TEXT CHECK (reservation IN ('GEN','SC','ST')) DEFAULT 'GEN',
    centroid_lat    DOUBLE PRECISION,
    centroid_lon    DOUBLE PRECISION,
    source_url      TEXT,                                     -- where this row was sourced from
    inserted_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT assembly_constituencies_state_number_unique UNIQUE (state, number)
);

CREATE INDEX IF NOT EXISTS assembly_constituencies_state_idx
    ON assembly_constituencies (state, number);

CREATE INDEX IF NOT EXISTS assembly_constituencies_district_idx
    ON assembly_constituencies (state, district);

COMMENT ON TABLE assembly_constituencies IS
  'CM Page: ECI assembly constituency roster. Populate from verified seed only.';

-- ── Materialized views for hot-path reads ─────────────────────────────────

-- Voice share per speaker per state, refreshed every 6h by
-- tasks.cm.refresh_voice_share. Concurrent refresh requires a unique index.
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_cm_voice_share AS
SELECT
    COALESCE(speaker_canonical, speaker)                            AS speaker,
    party,
    state,
    COUNT(*) FILTER (WHERE extracted_at > now() - interval '24 hours')   AS mentions_24h,
    COUNT(*) FILTER (WHERE extracted_at > now() - interval '7 days')     AS mentions_7d,
    AVG(sentiment) FILTER (WHERE extracted_at > now() - interval '24 hours') AS avg_sentiment_24h,
    AVG(sentiment) FILTER (WHERE extracted_at > now() - interval '7 days')   AS avg_sentiment_7d
FROM cm_spokesperson_quotes
WHERE COALESCE(speaker_canonical, speaker) IS NOT NULL
GROUP BY COALESCE(speaker_canonical, speaker), party, state;

CREATE UNIQUE INDEX IF NOT EXISTS mv_cm_voice_share_pk
    ON mv_cm_voice_share (speaker, COALESCE(party, ''), COALESCE(state, ''));

-- Per-issue hourly volume + average stance over the last 7 days. Refreshed
-- by tasks.cm.refresh_trajectory (runs every 30 min during active hours).
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_cm_issue_hourly AS
SELECT
    cie.issue_id,
    date_trunc('hour', a.published_at)                         AS hour,
    COUNT(*)                                                   AS volume,
    AVG(
        CASE s.stance
            WHEN 'opposition_attack'  THEN -1.0
            WHEN 'ruling_supportive'  THEN  1.0
            WHEN 'neutral_factual'    THEN  0.0
            ELSE 0.0
        END * COALESCE(s.confidence, 0.0)
    )                                                          AS avg_stance
FROM cm_issue_evidence cie
JOIN articles a
  ON a.id = cie.source_id
 AND cie.source_kind = 'article'
LEFT JOIN cm_stance_scores s
  ON s.source_id = a.id
 AND s.source_kind = 'article'
WHERE a.published_at > now() - interval '7 days'
GROUP BY cie.issue_id, date_trunc('hour', a.published_at);

CREATE UNIQUE INDEX IF NOT EXISTS mv_cm_issue_hourly_pk
    ON mv_cm_issue_hourly (issue_id, hour);

-- Daily constituency-level mood. Refreshed by
-- tasks.cm.refresh_constituency_heatmap nightly.
-- Constituency-level mood proxy.
-- articles has no direct sentiment column in this deployment; we derive
-- mood from cm_stance_scores joined to articles (only for stance-scored
-- items in the last 24 hours). When cm_stance_scores is empty (fresh
-- cluster, no tasks have run) all mood_proxy values will be NULL — the
-- read endpoint coerces those to 0.
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_cm_constituency_daily AS
SELECT
    ac.code                                            AS constituency_code,
    ac.state                                           AS state,
    ac.name                                            AS name,
    COUNT(a.id)                                        AS volume,
    AVG(
        CASE s.stance
            WHEN 'opposition_attack'  THEN -1.0
            WHEN 'ruling_supportive'  THEN  1.0
            ELSE 0.0
        END * COALESCE(s.confidence, 0.0)
    )                                                  AS mood_proxy,
    NOW()                                              AS computed_at
FROM assembly_constituencies ac
LEFT JOIN articles a
  ON a.geo_primary IS NOT NULL
 AND a.geo_primary ILIKE ('%' || ac.name || '%')
 AND a.published_at > now() - interval '24 hours'
LEFT JOIN cm_stance_scores s
  ON s.source_kind = 'article' AND s.source_id = a.id
GROUP BY ac.code, ac.state, ac.name;

CREATE UNIQUE INDEX IF NOT EXISTS mv_cm_constituency_daily_pk
    ON mv_cm_constituency_daily (constituency_code);

COMMENT ON MATERIALIZED VIEW mv_cm_voice_share IS
  'CM Page: voice-share aggregation. REFRESH MATERIALIZED VIEW CONCURRENTLY mv_cm_voice_share.';
COMMENT ON MATERIALIZED VIEW mv_cm_issue_hourly IS
  'CM Page: 7-day hourly issue volume + stance. Used by trajectory classifier.';
COMMENT ON MATERIALIZED VIEW mv_cm_constituency_daily IS
  'CM Page: per-AC mood proxy. Replace LIKE join with proper geo tagging once geo_primary is normalised.';
