-- 039_seed_telangana_social_monitors.sql
-- Reddit + Telegram monitors for Telangana coverage. The article corpus
-- alone undercounts hyperlocal voice; social fills districts that don't
-- have Telugu paper coverage and gives sentiment / chatter signal.
--
-- Most Telangana districts don't have viable district-specific subs/
-- channels — adding them would create dead monitors that cost cycles.
-- This migration seeds only what's confirmed live.
--
-- Idempotent: ON CONFLICT (platform, identifier) DO NOTHING.

INSERT INTO social_monitors (platform, monitor_type, identifier, display_name, description, tier, is_official, is_active) VALUES

-- ── Reddit ─────────────────────────────────────────────────────────────────
('reddit', 'subreddit', 'hyderabad',          'r/Hyderabad',          'Hyderabad city subreddit (largest)',                  'hot',  false, true),
('reddit', 'subreddit', 'Telangana',          'r/Telangana',          'Telangana state subreddit',                           'hot',  false, true),
('reddit', 'subreddit', 'india_news',         'r/india_news',         'Pan-India news subreddit, often Telangana-tagged',   'warm', false, true),
('reddit', 'subreddit', 'IndiaSpeaks',        'r/IndiaSpeaks',        'Politics-heavy Indian subreddit',                     'warm', false, true),
('reddit', 'subreddit', 'india',              'r/india',              'India subreddit; broad capture, Telangana subset',   'warm', false, true),
('reddit', 'subreddit', 'NewToTelangana',     'r/NewToTelangana',     'Telangana newcomer / city subreddit',                 'cold', false, true),
('reddit', 'subreddit', 'telugu',             'r/telugu',             'Telugu-language subreddit',                           'cold', false, true),
('reddit', 'subreddit', 'IndiaInvestments',   'r/IndiaInvestments',   'Captures financial Telangana stories (RBI/markets)', 'warm', false, true),

-- ── Telegram ───────────────────────────────────────────────────────────────
-- Channel identifiers are the @username form (without @). Bot collector
-- resolves to chat_id at first poll.
('telegram', 'channel', 'TelanganaToday',          'Telangana Today',         'Official paper channel — statewide news',        'hot',  true,  true),
('telegram', 'channel', 'PIBHyderabad',            'PIB Hyderabad',           'Govt of India press releases for Telangana',     'hot',  true,  true),
('telegram', 'channel', 'TelanganaCMO',            'Telangana CMO',           'CM Office channel',                              'hot',  true,  true),
('telegram', 'channel', 'INCTelangana',            'Congress Telangana',      'Telangana Congress party channel',               'warm', true,  true),
('telegram', 'channel', 'BRSparty',                'BRS Party',               'BRS (Bharat Rashtra Samithi) party channel',     'warm', true,  true),
('telegram', 'channel', 'BJP4Telangana',           'BJP Telangana',           'Telangana BJP unit',                             'warm', true,  true),
('telegram', 'channel', 'eenaduwebdesk',           'Eenadu web desk',         'Eenadu Telegram digest',                         'warm', false, true),
('telegram', 'channel', 'v6news',                  'V6 News',                 'V6 News Telugu channel',                         'warm', false, true)

ON CONFLICT (platform, identifier) DO NOTHING;

DO $$
DECLARE
  reddit_n int; tg_n int;
BEGIN
  SELECT count(*) INTO reddit_n FROM social_monitors WHERE platform='reddit';
  SELECT count(*) INTO tg_n     FROM social_monitors WHERE platform='telegram';
  RAISE NOTICE '039: reddit monitors = %, telegram monitors = %', reddit_n, tg_n;
END $$;
