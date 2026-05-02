-- 039_external_sources.sql
-- CM Page v2 — Phase 3 external data sources.
--
-- Adds per-source raw tables for AGMARKNET (mandi prices), CPCB (AQI),
-- IMD (weather warnings), TGSPDCL (power grid), state welfare portals.
-- Plus the per-district materialised views the atlas layers read from.
--
-- Strictly ADDITIVE. No existing table or view is modified.
--
-- Apply via:
--   docker exec -i rig-postgres psql -U rig -d rig \
--     < scripts/migrations/039_external_sources.sql

-- ── 1. mandi_prices ──────────────────────────────────────────────────────
-- Populated by tasks.collectors.mandi_agmarknet (every 4 hours).
-- Source: AGMARKNET via data.gov.in (free public API).

CREATE TABLE IF NOT EXISTS mandi_prices (
    id            BIGSERIAL   PRIMARY KEY,
    market        TEXT        NOT NULL,            -- 'Khammam', 'Bowenpally', etc.
    district_id   TEXT        REFERENCES districts(id) ON DELETE SET NULL,
    state_code    TEXT        NOT NULL,
    commodity     TEXT        NOT NULL,            -- 'Cotton', 'Chilli (Teja)', 'Paddy (BPT)', ...
    variety       TEXT,                            -- optional sub-variety
    grade         TEXT,                            -- 'FAQ', 'Medium', etc.
    min_price     INTEGER,                         -- in paise per quintal
    max_price     INTEGER,                         -- in paise per quintal
    modal_price   INTEGER,                         -- modal in paise per quintal
    arrival_qty   REAL,                            -- quintals
    recorded_at   DATE        NOT NULL,
    inserted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT mandi_prices_unique UNIQUE (market, commodity, COALESCE(variety, ''), recorded_at)
);

CREATE INDEX IF NOT EXISTS mandi_prices_district_idx
    ON mandi_prices (district_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS mandi_prices_commodity_idx
    ON mandi_prices (commodity, recorded_at DESC);

COMMENT ON TABLE mandi_prices IS
  'CM Page v2: AGMARKNET commodity prices. Populated by '
  'tasks.collectors.mandi_agmarknet (every 4h). Prices in paise per quintal.';

-- ── 2. air_quality_readings ──────────────────────────────────────────────
-- Populated by tasks.collectors.cpcb_aqi (every 30 minutes).
-- Source: app.cpcbccr.com/ccr/ (free public).

CREATE TABLE IF NOT EXISTS air_quality_readings (
    id            BIGSERIAL   PRIMARY KEY,
    station       TEXT        NOT NULL,            -- CPCB station name
    station_code  TEXT,                            -- official CPCB code if available
    district_id   TEXT        REFERENCES districts(id) ON DELETE SET NULL,
    state_code    TEXT        NOT NULL,
    aqi           INTEGER,                         -- 0..500 standard scale
    aqi_category  TEXT,                            -- 'Good' / 'Moderate' / 'Poor' / etc.
    pm25          REAL,                            -- µg/m³
    pm10          REAL,                            -- µg/m³
    no2           REAL,
    so2           REAL,
    co            REAL,
    o3            REAL,
    recorded_at   TIMESTAMPTZ NOT NULL,
    inserted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT air_quality_readings_unique UNIQUE (station, recorded_at)
);

CREATE INDEX IF NOT EXISTS aqi_district_recent_idx
    ON air_quality_readings (district_id, recorded_at DESC);

COMMENT ON TABLE air_quality_readings IS
  'CM Page v2: CPCB live AQI. Populated by tasks.collectors.cpcb_aqi (30m).';

-- ── 3. weather_warnings ──────────────────────────────────────────────────
-- Populated by tasks.collectors.imd_weather (every hour).
-- Source: mausam.imd.gov.in (free public XML).

CREATE TABLE IF NOT EXISTS weather_warnings (
    id            BIGSERIAL   PRIMARY KEY,
    district_id   TEXT        REFERENCES districts(id) ON DELETE SET NULL,
    state_code    TEXT        NOT NULL,
    kind          TEXT        NOT NULL,            -- 'heatwave', 'rain', 'cyclone', 'thunderstorm', 'fog', ...
    severity      TEXT        NOT NULL,            -- 'green', 'yellow', 'orange', 'red'
    headline      TEXT,
    detail        TEXT,
    valid_from    TIMESTAMPTZ NOT NULL,
    valid_to      TIMESTAMPTZ NOT NULL,
    issued_at     TIMESTAMPTZ NOT NULL,
    payload       JSONB,                           -- full IMD bulletin for replay
    inserted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT weather_warnings_unique UNIQUE (district_id, kind, valid_from, valid_to)
);

CREATE INDEX IF NOT EXISTS weather_district_active_idx
    ON weather_warnings (district_id, valid_to DESC);
CREATE INDEX IF NOT EXISTS weather_severity_idx
    ON weather_warnings (severity, valid_to DESC)
    WHERE severity IN ('orange', 'red');

COMMENT ON TABLE weather_warnings IS
  'CM Page v2: IMD warnings. Populated by tasks.collectors.imd_weather (1h).';

-- ── 4. power_grid_status ─────────────────────────────────────────────────
-- Populated by tasks.collectors.tgspdcl_power (every 30 minutes).
-- Source: SCRAPE only (no official API). BRITTLE — needs alerting on
-- parser failure with last-known-good fallback.

CREATE TABLE IF NOT EXISTS power_grid_status (
    id            BIGSERIAL   PRIMARY KEY,
    district_id   TEXT        REFERENCES districts(id) ON DELETE SET NULL,
    state_code    TEXT        NOT NULL,
    demand_mw     INTEGER,
    supply_mw     INTEGER,
    deficit_mw    INTEGER GENERATED ALWAYS AS (supply_mw - demand_mw) STORED,
    feeder_status TEXT,                            -- 'normal' / 'stressed' / 'shedding'
    notes         TEXT,
    recorded_at   TIMESTAMPTZ NOT NULL,
    inserted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT power_grid_unique UNIQUE (district_id, recorded_at)
);

CREATE INDEX IF NOT EXISTS power_district_recent_idx
    ON power_grid_status (district_id, recorded_at DESC);

COMMENT ON TABLE power_grid_status IS
  'CM Page v2: TGSPDCL power state. Populated by '
  'tasks.collectors.tgspdcl_power (30m). SCRAPER — needs parser-failure alerting.';

-- ── 5. welfare_coverage ──────────────────────────────────────────────────
-- Populated by tasks.collectors.welfare_coverage (daily).
-- Sources: data.telangana.gov.in (API where available) + state portal scrape.

CREATE TABLE IF NOT EXISTS welfare_coverage (
    id              BIGSERIAL   PRIMARY KEY,
    scheme          TEXT        NOT NULL,         -- 'Rythu Bandhu' / 'Aasara Pensions' / '2BHK Housing' / ...
    district_id     TEXT        REFERENCES districts(id) ON DELETE SET NULL,
    state_code      TEXT        NOT NULL,
    beneficiaries   INTEGER,                       -- people / households served
    target          INTEGER,                       -- target rolls
    coverage_pct    REAL CHECK (coverage_pct BETWEEN 0 AND 100),
    detail          TEXT,                          -- short narrative ("18 GP delays this cycle")
    cycle_label     TEXT,                          -- 'May 2026', 'Q1 FY26', etc.
    recorded_at     DATE        NOT NULL,
    inserted_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT welfare_coverage_unique UNIQUE (scheme, district_id, recorded_at)
);

CREATE INDEX IF NOT EXISTS welfare_district_recent_idx
    ON welfare_coverage (district_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS welfare_scheme_idx
    ON welfare_coverage (scheme, recorded_at DESC);

COMMENT ON TABLE welfare_coverage IS
  'CM Page v2: per-district scheme coverage. Populated daily.';

-- ── 6. scrape health metadata (so we can render "data degraded" on stale) ─

CREATE TABLE IF NOT EXISTS source_run_health (
    source_id       TEXT        PRIMARY KEY,       -- 'mandi_agmarknet', 'cpcb_aqi', etc.
    last_success_at TIMESTAMPTZ,
    last_failure_at TIMESTAMPTZ,
    last_failure    TEXT,                          -- short error text
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    rows_last_run   INTEGER,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE source_run_health IS
  'CM Page v2: per-scraper health. Read by /api/cm/atlas/layer endpoints '
  'to mark a layer as "data degraded" when last_success_at is stale.';

-- ── 7. Per-district atlas-layer materialised views ───────────────────────
-- Each MV is one (district_id, value) shape so the layer endpoint is a
-- single SELECT per layer. Refreshed by tasks.cm.refresh_atlas_layer_views
-- on cadences appropriate to each source.

-- 7a. News volume × severity, last 24h
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_district_news_volume_24h AS
SELECT
    ad.district_id,
    SUM(ad.confidence)::float                                     AS value,
    COUNT(*)                                                       AS article_count,
    AVG(ad.confidence)::float                                     AS avg_confidence,
    NOW()                                                          AS computed_at
FROM article_districts ad
JOIN articles a ON a.id = ad.article_id
WHERE a.collected_at > NOW() - INTERVAL '24 hours'
GROUP BY ad.district_id;

CREATE UNIQUE INDEX IF NOT EXISTS mv_district_news_volume_24h_pk
    ON mv_district_news_volume_24h (district_id);

-- 7b. Sentiment per district (using cm_stance_scores via article_id)
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_district_sentiment_24h AS
SELECT
    ad.district_id,
    AVG(
        CASE s.stance
            WHEN 'opposition_attack'  THEN -1.0
            WHEN 'ruling_supportive'  THEN  1.0
            WHEN 'neutral_factual'    THEN  0.0
            ELSE 0.0
        END * COALESCE(s.confidence, 0.0)
    )::float                                                       AS value,
    COUNT(*)                                                       AS scored_count,
    NOW()                                                          AS computed_at
FROM article_districts ad
JOIN articles a ON a.id = ad.article_id
LEFT JOIN cm_stance_scores s
       ON s.source_id = a.id AND s.source_kind = 'article'
WHERE a.collected_at > NOW() - INTERVAL '24 hours'
GROUP BY ad.district_id;

CREATE UNIQUE INDEX IF NOT EXISTS mv_district_sentiment_24h_pk
    ON mv_district_sentiment_24h (district_id);

-- 7c. ACLED events per district, last 7 days
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_district_acled_7d AS
SELECT
    district_id,
    COUNT(*)                                                       AS value,
    SUM(fatalities)                                                AS total_fatalities,
    NOW()                                                          AS computed_at
FROM acled_events
WHERE event_date > CURRENT_DATE - INTERVAL '7 days'
  AND district_id IS NOT NULL
GROUP BY district_id;

CREATE UNIQUE INDEX IF NOT EXISTS mv_district_acled_7d_pk
    ON mv_district_acled_7d (district_id);

-- 7d. Mandi volatility per district (max abs % delta from 30d avg)
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_district_mandi_volatility_30d AS
WITH baselines AS (
    SELECT
        district_id, commodity,
        AVG(modal_price)::float AS baseline
    FROM mandi_prices
    WHERE recorded_at > CURRENT_DATE - INTERVAL '30 days'
      AND modal_price IS NOT NULL
      AND district_id IS NOT NULL
    GROUP BY district_id, commodity
), latest AS (
    SELECT DISTINCT ON (district_id, commodity)
        district_id, commodity, modal_price, recorded_at
    FROM mandi_prices
    WHERE district_id IS NOT NULL
    ORDER BY district_id, commodity, recorded_at DESC
)
SELECT
    l.district_id,
    MAX(ABS((l.modal_price - b.baseline) / NULLIF(b.baseline, 0)))::float AS value,
    COUNT(*)                                                              AS commodity_count,
    NOW()                                                                 AS computed_at
FROM latest l
JOIN baselines b USING (district_id, commodity)
WHERE b.baseline > 0
GROUP BY l.district_id;

CREATE UNIQUE INDEX IF NOT EXISTS mv_district_mandi_volatility_30d_pk
    ON mv_district_mandi_volatility_30d (district_id);

-- 7e. Welfare composite — weighted average across schemes
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_district_welfare_coverage AS
WITH latest AS (
    SELECT DISTINCT ON (district_id, scheme)
        district_id, scheme, coverage_pct
    FROM welfare_coverage
    WHERE district_id IS NOT NULL
    ORDER BY district_id, scheme, recorded_at DESC
)
SELECT
    district_id,
    AVG(coverage_pct)::float                                      AS value,
    COUNT(*)                                                       AS schemes_tracked,
    MIN(coverage_pct)::float                                       AS worst_scheme_pct,
    NOW()                                                          AS computed_at
FROM latest
GROUP BY district_id;

CREATE UNIQUE INDEX IF NOT EXISTS mv_district_welfare_coverage_pk
    ON mv_district_welfare_coverage (district_id);

-- 7f. Power stress per district — peak (demand - supply) over last 24h
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_district_power_stress AS
SELECT
    district_id,
    COALESCE(MAX(demand_mw - supply_mw), 0)::float                 AS value,
    AVG(demand_mw - supply_mw)::float                              AS avg_deficit_mw,
    NOW()                                                           AS computed_at
FROM power_grid_status
WHERE district_id IS NOT NULL
  AND recorded_at > NOW() - INTERVAL '24 hours'
GROUP BY district_id;

CREATE UNIQUE INDEX IF NOT EXISTS mv_district_power_stress_pk
    ON mv_district_power_stress (district_id);

-- 7g. Stability composite — AQI 30% + Heat 25% + ACLED 25% + News anomaly 20%
-- Each component normalised to 0..1 (1 = stable). Composite then 0..100.
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_district_stability_composite AS
WITH aqi AS (
    SELECT district_id,
           1.0 - LEAST(1.0, AVG(aqi)::float / 300.0) AS aqi_score
    FROM air_quality_readings
    WHERE recorded_at > NOW() - INTERVAL '24 hours' AND district_id IS NOT NULL
    GROUP BY district_id
), heat AS (
    -- IMD orange/red heatwave warning -> 0; yellow -> 0.5; none -> 1.0
    SELECT district_id,
           CASE
             WHEN MAX(CASE severity WHEN 'red' THEN 4 WHEN 'orange' THEN 3 WHEN 'yellow' THEN 2 ELSE 1 END) >= 3 THEN 0.0
             WHEN MAX(CASE severity WHEN 'red' THEN 4 WHEN 'orange' THEN 3 WHEN 'yellow' THEN 2 ELSE 1 END) = 2 THEN 0.5
             ELSE 1.0
           END AS heat_score
    FROM weather_warnings
    WHERE kind = 'heatwave' AND valid_to > NOW() AND district_id IS NOT NULL
    GROUP BY district_id
), acled AS (
    SELECT district_id,
           1.0 - LEAST(1.0, COUNT(*)::float / 8.0) AS acled_score
    FROM acled_events
    WHERE event_date > CURRENT_DATE - INTERVAL '7 days' AND district_id IS NOT NULL
    GROUP BY district_id
), news AS (
    SELECT district_id,
           1.0 - LEAST(1.0, SUM(confidence)::float / 10.0) AS news_score
    FROM article_districts ad
    JOIN articles a ON a.id = ad.article_id
    WHERE a.collected_at > NOW() - INTERVAL '24 hours'
    GROUP BY district_id
)
SELECT
    d.id                                                            AS district_id,
    (
        0.30 * COALESCE(aqi.aqi_score, 1.0)
      + 0.25 * COALESCE(heat.heat_score, 1.0)
      + 0.25 * COALESCE(acled.acled_score, 1.0)
      + 0.20 * COALESCE(news.news_score, 1.0)
    ) * 100.0                                                       AS value,
    COALESCE(aqi.aqi_score, 1.0)                                    AS aqi_component,
    COALESCE(heat.heat_score, 1.0)                                  AS heat_component,
    COALESCE(acled.acled_score, 1.0)                                AS acled_component,
    COALESCE(news.news_score, 1.0)                                  AS news_component,
    NOW()                                                            AS computed_at
FROM districts d
LEFT JOIN aqi   ON aqi.district_id   = d.id
LEFT JOIN heat  ON heat.district_id  = d.id
LEFT JOIN acled ON acled.district_id = d.id
LEFT JOIN news  ON news.district_id  = d.id;

CREATE UNIQUE INDEX IF NOT EXISTS mv_district_stability_composite_pk
    ON mv_district_stability_composite (district_id);

COMMENT ON MATERIALIZED VIEW mv_district_news_volume_24h        IS 'CM v2 atlas: news-hotspot layer.';
COMMENT ON MATERIALIZED VIEW mv_district_sentiment_24h          IS 'CM v2 atlas: sentiment layer.';
COMMENT ON MATERIALIZED VIEW mv_district_acled_7d               IS 'CM v2 atlas: ACLED layer.';
COMMENT ON MATERIALIZED VIEW mv_district_mandi_volatility_30d   IS 'CM v2 atlas: mandi-volatility layer.';
COMMENT ON MATERIALIZED VIEW mv_district_welfare_coverage       IS 'CM v2 atlas: welfare layer.';
COMMENT ON MATERIALIZED VIEW mv_district_power_stress           IS 'CM v2 atlas: power-stress layer.';
COMMENT ON MATERIALIZED VIEW mv_district_stability_composite    IS 'CM v2 atlas: stability composite (AQI 30 + heat 25 + ACLED 25 + news 20).';
