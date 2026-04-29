-- 011_signal_intel.sql
-- Signal Room intel layer: tiered cadence, relevance scoring,
-- geo/topic seeds, baselines, events, and composed summaries.
-- Idempotent.

-- ── Monitor tier + official flag ──────────────────────────────────────────

ALTER TABLE social_monitors
  ADD COLUMN IF NOT EXISTS tier text
    NOT NULL DEFAULT 'warm'
    CHECK (tier IN ('hot', 'warm', 'cold'));

ALTER TABLE social_monitors
  ADD COLUMN IF NOT EXISTS is_official boolean
    NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_social_monitors_tier_active
  ON social_monitors (tier, is_active)
  WHERE is_active;

-- ── Per-post relevance score ──────────────────────────────────────────────

ALTER TABLE social_posts
  ADD COLUMN IF NOT EXISTS relevance_score integer NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_social_posts_relevance_collected
  ON social_posts (relevance_score DESC, collected_at DESC);

-- ── Geo + topic seeds (user-editable; prefilled with India-monitoring defaults)

CREATE TABLE IF NOT EXISTS social_geo_seeds (
    id    serial PRIMARY KEY,
    term  text NOT NULL UNIQUE,
    kind  text NOT NULL CHECK (kind IN ('country', 'state', 'city', 'region')),
    weight integer NOT NULL DEFAULT 15
);

CREATE TABLE IF NOT EXISTS social_topic_seeds (
    id    serial PRIMARY KEY,
    term  text NOT NULL UNIQUE,
    weight integer NOT NULL DEFAULT 15,
    note  text
);

INSERT INTO social_geo_seeds (term, kind) VALUES
    ('India', 'country'),
    ('Telangana', 'state'),
    ('Andhra Pradesh', 'state'),
    ('Karnataka', 'state'),
    ('Maharashtra', 'state'),
    ('Tamil Nadu', 'state'),
    ('Kerala', 'state'),
    ('West Bengal', 'state'),
    ('Bihar', 'state'),
    ('Uttar Pradesh', 'state'),
    ('Madhya Pradesh', 'state'),
    ('Gujarat', 'state'),
    ('Rajasthan', 'state'),
    ('Punjab', 'state'),
    ('Manipur', 'state'),
    ('Hyderabad', 'city'),
    ('Bengaluru', 'city'),
    ('Bangalore', 'city'),
    ('Mumbai', 'city'),
    ('Chennai', 'city'),
    ('Delhi', 'city'),
    ('New Delhi', 'city'),
    ('Kolkata', 'city'),
    ('Pune', 'city'),
    ('Visakhapatnam', 'city'),
    ('Vijayawada', 'city'),
    ('Warangal', 'city'),
    ('Karimnagar', 'city'),
    ('South Asia', 'region'),
    ('West Asia', 'region')
ON CONFLICT (term) DO NOTHING;

INSERT INTO social_topic_seeds (term, note) VALUES
    ('election', 'electoral process'),
    ('voting', 'electoral process'),
    ('rally', 'political mobilisation'),
    ('protest', 'civil unrest'),
    ('agitation', 'civil unrest'),
    ('strike', 'civil unrest'),
    ('bandh', 'civil unrest'),
    ('riot', 'civil unrest'),
    ('clash', 'civil unrest'),
    ('encounter', 'security incident'),
    ('terror', 'security incident'),
    ('blast', 'security incident'),
    ('explosion', 'security incident'),
    ('arrest', 'security incident'),
    ('raid', 'security incident'),
    ('IT raid', 'enforcement'),
    ('ED raid', 'enforcement'),
    ('CBI', 'enforcement'),
    ('water', 'infrastructure'),
    ('power cut', 'infrastructure'),
    ('outage', 'infrastructure'),
    ('flood', 'natural'),
    ('cyclone', 'natural'),
    ('drought', 'natural'),
    ('heatwave', 'natural'),
    ('reservation', 'policy'),
    ('GST', 'economy'),
    ('inflation', 'economy'),
    ('budget', 'economy'),
    ('tariff', 'economy'),
    ('cabinet', 'governance'),
    ('ordinance', 'governance'),
    ('Supreme Court', 'judiciary'),
    ('High Court', 'judiciary'),
    ('petition', 'judiciary'),
    ('verdict', 'judiciary'),
    ('West Asia', 'foreign'),
    ('Iran', 'foreign'),
    ('Israel', 'foreign'),
    ('China', 'foreign'),
    ('Pakistan', 'foreign')
ON CONFLICT (term) DO NOTHING;

-- ── Source expansion (idempotent inserts) ─────────────────────────────────

-- Reddit subreddits (warm by default)
INSERT INTO social_monitors (platform, monitor_type, identifier, display_name, is_active, tier)
VALUES
    ('reddit', 'subreddit', 'Andhrapradesh',     'r/Andhrapradesh',    true, 'warm'),
    ('reddit', 'subreddit', 'Karnataka',         'r/Karnataka',        true, 'warm'),
    ('reddit', 'subreddit', 'bangalore',         'r/bangalore',        true, 'warm'),
    ('reddit', 'subreddit', 'mumbai',            'r/mumbai',           true, 'warm'),
    ('reddit', 'subreddit', 'Chennai',           'r/Chennai',          true, 'warm'),
    ('reddit', 'subreddit', 'IndiaSpeaks',       'r/IndiaSpeaks',      true, 'warm'),
    ('reddit', 'subreddit', 'IndianNews',        'r/IndianNews',       true, 'warm'),
    ('reddit', 'subreddit', 'IndianStreetBets',  'r/IndianStreetBets', true, 'cold'),
    ('reddit', 'subreddit', 'IndianHistory',     'r/IndianHistory',    true, 'cold'),
    ('reddit', 'subreddit', 'IndianDefense',     'r/IndianDefense',    true, 'warm'),
    ('reddit', 'subreddit', 'Bharat',            'r/Bharat',           true, 'warm'),
    ('reddit', 'subreddit', 'kerala',            'r/kerala',           true, 'warm'),
    ('reddit', 'subreddit', 'Pune',              'r/Pune',             true, 'cold'),
    ('reddit', 'subreddit', 'IndianStartups',    'r/IndianStartups',   true, 'cold')
ON CONFLICT (platform, identifier) DO UPDATE SET
    is_active = excluded.is_active,
    tier = excluded.tier;

-- Telegram channels (mix of hot=govt + warm=press + cold=topical)
INSERT INTO social_monitors (platform, monitor_type, identifier, display_name, is_active, tier, is_official)
VALUES
    -- HOT: official government channels (15-min cadence)
    ('telegram', 'channel', 'PIB_India',         'Press Information Bureau (Central)', true, 'hot', true),
    ('telegram', 'channel', 'KarnatakaCMO',      'Karnataka CMO',                       true, 'hot', true),
    ('telegram', 'channel', 'MaharashtraCMO',    'Maharashtra CMO',                     true, 'hot', true),
    ('telegram', 'channel', 'TamilNaduCMO',      'Tamil Nadu CMO',                      true, 'hot', true),
    ('telegram', 'channel', 'KeralaCMO',         'Kerala CMO',                          true, 'hot', true),
    ('telegram', 'channel', 'ECISVEEP',          'Election Commission of India',        true, 'hot', true),
    ('telegram', 'channel', 'MEAIndia',          'Ministry of External Affairs',        true, 'hot', true),
    ('telegram', 'channel', 'MoCA_GoI',          'Ministry of Civil Aviation',          true, 'hot', true),
    ('telegram', 'channel', 'RBI_India',         'Reserve Bank of India',               true, 'hot', true),
    ('telegram', 'channel', 'mygovindia',        'MyGov India',                         true, 'hot', true),
    -- WARM: media houses (hourly)
    ('telegram', 'channel', 'NDTV',              'NDTV',                                true, 'warm', false),
    ('telegram', 'channel', 'IndiaToday',        'India Today',                         true, 'warm', false),
    ('telegram', 'channel', 'ANI',               'ANI News',                            true, 'warm', false),
    ('telegram', 'channel', 'thehindu',          'The Hindu',                           true, 'warm', false),
    ('telegram', 'channel', 'TheWire',           'The Wire',                            true, 'warm', false),
    ('telegram', 'channel', 'thequintindia',     'The Quint',                           true, 'warm', false),
    -- WARM: party / opposition channels
    ('telegram', 'channel', 'BJP4India',         'BJP',                                 true, 'warm', false),
    ('telegram', 'channel', 'INCIndia',          'Indian National Congress',            true, 'warm', false)
ON CONFLICT (platform, identifier) DO UPDATE SET
    is_active = excluded.is_active,
    tier = excluded.tier,
    is_official = excluded.is_official;

-- Backfill: mark existing official channels too
UPDATE social_monitors
   SET is_official = true,
       tier = 'hot'
 WHERE platform = 'telegram'
   AND identifier IN ('MIB_India', 'TelanganaCMO');

-- ── 7-day rolling baselines per entity ────────────────────────────────────

CREATE TABLE IF NOT EXISTS social_entity_baselines (
    id              serial PRIMARY KEY,
    entity          text NOT NULL,
    posts_24h       integer NOT NULL DEFAULT 0,
    posts_7d_mean   double precision NOT NULL DEFAULT 0,
    sentiment_24h   double precision,
    sentiment_7d    double precision,
    sources_24h     integer NOT NULL DEFAULT 0,
    computed_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (entity)
);

CREATE INDEX IF NOT EXISTS idx_baselines_entity ON social_entity_baselines (entity);

-- ── Detected events (rule outputs feeding the daily summary) ──────────────

CREATE TABLE IF NOT EXISTS social_events (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type      text NOT NULL CHECK (event_type IN (
        'SURGE', 'SENTIMENT_SHIFT', 'REPETITION', 'BRIDGE',
        'SILENCE', 'NEW_SUBJECT', 'STATIONARY'
    )),
    subject         text NOT NULL,                   -- entity / cluster id / phrase
    subject_kind    text NOT NULL CHECK (subject_kind IN (
        'entity', 'cluster', 'subject'
    )),
    magnitude       double precision,                -- e.g. 3.2 = "3.2x baseline"
    confidence      text NOT NULL CHECK (confidence IN ('LOW', 'MED', 'HIGH')),
    sources         text[] NOT NULL DEFAULT '{}',
    body            text NOT NULL,                   -- composed paragraph text
    detected_at     timestamptz NOT NULL DEFAULT now(),
    metadata        jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_events_detected
  ON social_events (detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_subject
  ON social_events (subject, subject_kind, detected_at DESC);

-- ── Composed daily/6h summaries ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS social_summaries (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    edition         integer NOT NULL,                -- monotonic counter
    classification  text NOT NULL DEFAULT 'OPEN',
    generated_at    timestamptz NOT NULL DEFAULT now(),
    window_hours    integer NOT NULL DEFAULT 24,
    body            text NOT NULL,                   -- typewriter formatted text
    event_ids       uuid[] NOT NULL DEFAULT '{}',
    sources_used    text[] NOT NULL DEFAULT '{}',
    metadata        jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_summaries_generated
  ON social_summaries (generated_at DESC);

-- ── Topic registry (unified entity / cluster / subject) ───────────────────

CREATE TABLE IF NOT EXISTS social_topics (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind            text NOT NULL CHECK (kind IN ('entity', 'cluster', 'subject')),
    canonical_key   text NOT NULL,                   -- entity name | cluster uuid | subject phrase
    label           text NOT NULL,
    first_seen      timestamptz NOT NULL DEFAULT now(),
    last_seen       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (kind, canonical_key)
);

CREATE INDEX IF NOT EXISTS idx_topics_last_seen
  ON social_topics (last_seen DESC);
