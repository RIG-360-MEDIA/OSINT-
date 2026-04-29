-- P19: Clips pipeline upgrade
--   Stage 1 — robust channel seed list (tiering + quality scoring + auto-deactivate)
--   Stage 2 — video-discovery high-water mark
--   Stage 3 — transcript_source labelling so UI can mark low-confidence rows
--   Stage 4 — region-agnostic entity disambiguation (entity_aliases table)
--   Stage 6 — confidence column for English-summary-first UI policy

-- ── youtube_channels: tiering + quality + HWM ────────────────────────────────
ALTER TABLE youtube_channels
    ADD COLUMN IF NOT EXISTS tier                    TEXT
        CHECK (tier IN ('tier_1', 'tier_2', 'tier_3'))
        DEFAULT 'tier_2',
    ADD COLUMN IF NOT EXISTS poll_priority           INT          DEFAULT 50,
    ADD COLUMN IF NOT EXISTS quality_score           NUMERIC(4,3) DEFAULT 0.500,
    ADD COLUMN IF NOT EXISTS language                TEXT         DEFAULT 'mixed',
    ADD COLUMN IF NOT EXISTS category                TEXT,
    ADD COLUMN IF NOT EXISTS last_yielded_at         TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS consecutive_dry_polls   INT          DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_video_published_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS deactivated_reason      TEXT;

CREATE INDEX IF NOT EXISTS idx_yt_channels_tier_active
    ON youtube_channels (tier, is_active);

-- ── youtube_clips: transcript provenance + raw confidence ────────────────────
ALTER TABLE youtube_clips
    ADD COLUMN IF NOT EXISTS transcript_source TEXT
        CHECK (transcript_source IN ('captions', 'yt_dlp', 'whisper', 'metadata'))
        DEFAULT 'captions',
    ADD COLUMN IF NOT EXISTS confidence        NUMERIC(4,3) DEFAULT 0.600;

CREATE INDEX IF NOT EXISTS idx_yt_clips_video_id_relevance
    ON youtube_clips (video_id, relevance_score DESC, clip_start_seconds);

-- ── entity_aliases: region-agnostic disambiguation rules ─────────────────────
CREATE TABLE IF NOT EXISTS entity_aliases (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name  TEXT NOT NULL,
    alias           TEXT NOT NULL,
    notes           TEXT,
    region          TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (canonical_name, alias)
);

CREATE INDEX IF NOT EXISTS idx_entity_aliases_canonical
    ON entity_aliases (canonical_name);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_alias
    ON entity_aliases (LOWER(alias));

-- Seed Telangana disambiguation (extracted from hardcoded Groq prompt)
INSERT INTO entity_aliases (canonical_name, alias, notes, region) VALUES
    ('K. Chandrashekar Rao', 'KCR',                'ex-CM, BRS founder. NOT KTR.', 'telangana'),
    ('K. Chandrashekar Rao', 'కేసీఆర్',            'Telugu spelling',              'telangana'),
    ('K. Chandrashekar Rao', 'Chandrashekar Rao',  'senior, NOT his son',          'telangana'),
    ('K. Chandrashekar Rao', 'KCR garu',           'respectful',                   'telangana'),
    ('K.T. Rama Rao',        'KTR',                'BRS working president, son of KCR. NOT KCR.', 'telangana'),
    ('K.T. Rama Rao',        'కేటీఆర్',           'Telugu spelling',              'telangana'),
    ('K.T. Rama Rao',        'Tarakarama Rao',     'son of KCR',                   'telangana'),
    ('K.T. Rama Rao',        'Rama Rao',           'son of KCR — NOT KCR himself', 'telangana'),
    ('A. Revanth Reddy',     'Revanth',            'current CM, Congress',         'telangana'),
    ('A. Revanth Reddy',     'రేవంత్',            'Telugu spelling',              'telangana'),
    ('T. Harish Rao',        'Harish Rao',         'BRS, nephew of KCR',           'telangana'),
    ('T. Harish Rao',        'హరీష్ రావు',        'Telugu spelling',              'telangana'),
    ('Uttam Kumar Reddy',    'Uttam',              '',                             'telangana'),
    ('T. Jagga Reddy',       'Jagga Reddy',        '',                             'telangana')
ON CONFLICT (canonical_name, alias) DO NOTHING;

-- ── Backfill tier + priority for existing channels ───────────────────────────
-- tier_1: top yield channels (high-volume Telangana news + party feeds)
UPDATE youtube_channels SET tier='tier_1', poll_priority=90, category='news'
 WHERE channel_name IN (
   'Telangana Velugu','V6 News Telugu','Zee Telugu News','T News Telugu',
   'Raj News Telugu','iNews Telugu','ABN Telugu'
 );
UPDATE youtube_channels SET tier='tier_1', poll_priority=85, category='party'
 WHERE channel_name IN ('BRS Party','Telangana Congress Studio');
UPDATE youtube_channels SET tier='tier_1', poll_priority=85, category='politician'
 WHERE channel_name IN ('K.T. Rama Rao KTR','Harish Rao Thanneeru');

-- tier_3: dry / silent / govt channels — keep but cheap
UPDATE youtube_channels SET tier='tier_3', poll_priority=15
 WHERE channel_id IN (
   SELECT ch.channel_id FROM youtube_channels ch
   LEFT JOIN youtube_clips c ON c.channel_id = ch.channel_id
   GROUP BY ch.channel_id
   HAVING COUNT(c.id) = 0
 );

-- everyone else is tier_2 by default (already set)

-- ── Dedupe seed list (mark obvious dupes inactive) ───────────────────────────
-- Keep the highest-yield instance, deactivate the rest.
WITH dupes AS (
  SELECT channel_id, channel_name,
    ROW_NUMBER() OVER (
      PARTITION BY LOWER(REGEXP_REPLACE(channel_name, '[^a-zA-Z]', '', 'g'))
      ORDER BY (
        SELECT COUNT(*) FROM youtube_clips c WHERE c.channel_id = youtube_channels.channel_id
      ) DESC, channel_name
    ) AS rn
  FROM youtube_channels
)
UPDATE youtube_channels y
   SET is_active = FALSE,
       deactivated_reason = 'duplicate_of_higher_yield'
  FROM dupes d
 WHERE y.channel_id = d.channel_id
   AND d.rn > 1;
