-- P17 — Signal Room
-- Reddit / Twitter / Telegram social signal ingestion.

CREATE TABLE IF NOT EXISTS social_monitors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform TEXT NOT NULL
        CHECK (platform IN ('reddit', 'twitter', 'telegram')),
    monitor_type TEXT NOT NULL
        CHECK (monitor_type IN ('account', 'subreddit', 'channel', 'keyword')),
    identifier TEXT NOT NULL,
    display_name TEXT,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    last_collected_at TIMESTAMPTZ,
    follower_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(platform, identifier)
);

CREATE TABLE IF NOT EXISTS social_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    platform TEXT NOT NULL,
    platform_post_id TEXT NOT NULL,
    monitor_id UUID REFERENCES social_monitors(id) ON DELETE SET NULL,

    author_username TEXT,
    author_display_name TEXT,
    author_follower_count INTEGER,

    post_text TEXT NOT NULL,
    post_text_translated TEXT,
    post_language TEXT DEFAULT 'en',
    post_url TEXT,

    upvotes INTEGER DEFAULT 0,
    downvotes INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    share_count INTEGER DEFAULT 0,

    forward_count INTEGER DEFAULT 0,
    forwarded_from TEXT,
    has_document BOOLEAN DEFAULT FALSE,
    document_url TEXT,

    sentiment_score FLOAT,
    matched_entities TEXT[],
    topic_category TEXT,
    labse_embedding vector(768),

    posted_at TIMESTAMPTZ,
    collected_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(platform, platform_post_id)
);

CREATE TABLE IF NOT EXISTS social_sentiment_daily (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    monitor_id UUID REFERENCES social_monitors(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    platform TEXT NOT NULL,
    positive_count INTEGER DEFAULT 0,
    negative_count INTEGER DEFAULT 0,
    neutral_count INTEGER DEFAULT 0,
    avg_sentiment FLOAT,
    post_count INTEGER DEFAULT 0,
    top_entities TEXT[],
    UNIQUE(monitor_id, date)
);

CREATE INDEX IF NOT EXISTS idx_posts_platform
    ON social_posts(platform);

CREATE INDEX IF NOT EXISTS idx_posts_collected
    ON social_posts(collected_at DESC);

CREATE INDEX IF NOT EXISTS idx_posts_monitor
    ON social_posts(monitor_id, collected_at DESC);

CREATE INDEX IF NOT EXISTS idx_posts_embedding
    ON social_posts
    USING hnsw (labse_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE labse_embedding IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_posts_entities
    ON social_posts
    USING gin(matched_entities);

-- Seed monitored sources
INSERT INTO social_monitors
    (platform, monitor_type, identifier, display_name, is_active)
VALUES
    ('reddit',   'subreddit', 'hyderabad',          'r/hyderabad',              TRUE),
    ('reddit',   'subreddit', 'telangana',          'r/telangana',              TRUE),
    ('reddit',   'subreddit', 'india',              'r/india',                  TRUE),
    ('reddit',   'subreddit', 'unitedstatesofindia','r/unitedstatesofindia',    TRUE),
    ('twitter',  'account',   'revanth_anumula',    'Revanth Reddy (CM)',       TRUE),
    ('twitter',  'account',   'KTRTRS',             'KTR (BRS)',                TRUE),
    ('twitter',  'account',   'trspartyonline',     'BRS Official',             TRUE),
    -- Telegram public channels (read via Telethon MTProto, no
    -- membership required)
    ('telegram', 'channel',   'TelanganaCMO',       'Telangana CMO Official',   TRUE),
    ('telegram', 'channel',   'MIB_India',          'Ministry of I&B (Central)',TRUE),
    ('telegram', 'channel',   'YSRCPOfficial',      'YSRCP Official',           TRUE),
    ('telegram', 'channel',   'BRSPartyofficial',   'BRS Party Official',       TRUE),
    ('telegram', 'channel',   'AamAadmiParty',      'Aam Aadmi Party',          TRUE),
    ('telegram', 'channel',   'v6newstelugu',       'V6 News Telugu',           TRUE),
    ('telegram', 'channel',   'scroll_in',          'Scroll.in',                TRUE)
ON CONFLICT (platform, identifier) DO NOTHING;
