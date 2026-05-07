-- 038_seed_telangana_district_sources.sql
-- Telangana per-district + statewide Telugu / regional source seed.
--
-- Audit (2026-05-06) found only 2 Telugu sources in the corpus, both
-- inactive (Eenadu, Sakshi). 30/33 Telangana districts had ≤20
-- articles/30d; 1 district had zero. Live RSS probe of 130+ candidates
-- returned 43 working feeds. This migration ships those 43.
--
-- Eenadu / Sakshi / Andhra Jyothy do not expose public RSS — those
-- need a Playwright scraper (see backend/collectors/telugu_scraper.py).
--
-- Idempotent via ON CONFLICT (domain) DO NOTHING.

INSERT INTO sources (name, domain, rss_url, source_type, source_tier, language, geo_states, topics, is_active) VALUES

-- ── Telangana Today: per-district tag feeds (33 districts) ──────────────────
('Telangana Today — Hyderabad',         'telanganatoday.com/tag/hyderabad',          'https://www.telanganatoday.com/tag/hyderabad/feed',          'rss', 2, 'en', '{Telangana,Hyderabad}',                  '{politics,general}', true),
('Telangana Today — Rangareddy',        'telanganatoday.com/tag/rangareddy',         'https://www.telanganatoday.com/tag/rangareddy/feed',         'rss', 2, 'en', '{Telangana,Rangareddy}',                 '{politics,general}', true),
('Telangana Today — Medchal',           'telanganatoday.com/tag/medchal',            'https://www.telanganatoday.com/tag/medchal/feed',            'rss', 2, 'en', '{Telangana,Medchal-Malkajgiri,Medchal}', '{politics,general}', true),
('Telangana Today — Sangareddy',        'telanganatoday.com/tag/sangareddy',         'https://www.telanganatoday.com/tag/sangareddy/feed',         'rss', 2, 'en', '{Telangana,Sangareddy}',                 '{politics,general}', true),
('Telangana Today — Vikarabad',         'telanganatoday.com/tag/vikarabad',          'https://www.telanganatoday.com/tag/vikarabad/feed',          'rss', 2, 'en', '{Telangana,Vikarabad}',                  '{politics,general}', true),
('Telangana Today — Karimnagar',        'telanganatoday.com/tag/karimnagar',         'https://www.telanganatoday.com/tag/karimnagar/feed',         'rss', 2, 'en', '{Telangana,Karimnagar}',                 '{politics,general}', true),
('Telangana Today — Peddapalli',        'telanganatoday.com/tag/peddapalli',         'https://www.telanganatoday.com/tag/peddapalli/feed',         'rss', 2, 'en', '{Telangana,Peddapalli}',                 '{politics,general}', true),
('Telangana Today — Jagtial',           'telanganatoday.com/tag/jagtial',            'https://www.telanganatoday.com/tag/jagtial/feed',            'rss', 2, 'en', '{Telangana,Jagtial}',                    '{politics,general}', true),
('Telangana Today — Rajanna Sircilla',  'telanganatoday.com/tag/rajanna-sircilla',   'https://www.telanganatoday.com/tag/rajanna-sircilla/feed',   'rss', 2, 'en', '{Telangana,"Rajanna Sircilla",Sircilla}', '{politics,general}', true),
('Telangana Today — Warangal',          'telanganatoday.com/tag/warangal',           'https://www.telanganatoday.com/tag/warangal/feed',           'rss', 2, 'en', '{Telangana,Warangal}',                   '{politics,general}', true),
('Telangana Today — Hanumakonda',       'telanganatoday.com/tag/hanumakonda',        'https://www.telanganatoday.com/tag/hanumakonda/feed',        'rss', 2, 'en', '{Telangana,Hanumakonda}',                '{politics,general}', true),
('Telangana Today — Mahabubabad',       'telanganatoday.com/tag/mahabubabad',        'https://www.telanganatoday.com/tag/mahabubabad/feed',        'rss', 2, 'en', '{Telangana,Mahabubabad}',                '{politics,general}', true),
('Telangana Today — Mulugu',            'telanganatoday.com/tag/mulugu',             'https://www.telanganatoday.com/tag/mulugu/feed',             'rss', 2, 'en', '{Telangana,Mulugu}',                     '{politics,general}', true),
('Telangana Today — Jayashankar',       'telanganatoday.com/tag/jayashankar',        'https://www.telanganatoday.com/tag/jayashankar/feed',        'rss', 2, 'en', '{Telangana,"Jayashankar Bhupalpally",Jayashankar}', '{politics,general}', true),
('Telangana Today — Jangaon',           'telanganatoday.com/tag/jangaon',            'https://www.telanganatoday.com/tag/jangaon/feed',            'rss', 2, 'en', '{Telangana,Jangaon}',                    '{politics,general}', true),
('Telangana Today — Khammam',           'telanganatoday.com/tag/khammam',            'https://www.telanganatoday.com/tag/khammam/feed',            'rss', 2, 'en', '{Telangana,Khammam}',                    '{politics,general}', true),
('Telangana Today — Bhadradri',         'telanganatoday.com/tag/bhadradri',          'https://www.telanganatoday.com/tag/bhadradri/feed',          'rss', 2, 'en', '{Telangana,"Bhadradri Kothagudem",Bhadradri,Kothagudem}', '{politics,general}', true),
('Telangana Today — Adilabad',          'telanganatoday.com/tag/adilabad',           'https://www.telanganatoday.com/tag/adilabad/feed',           'rss', 2, 'en', '{Telangana,Adilabad}',                   '{politics,general}', true),
('Telangana Today — Mancherial',        'telanganatoday.com/tag/mancherial',         'https://www.telanganatoday.com/tag/mancherial/feed',         'rss', 2, 'en', '{Telangana,Mancherial}',                 '{politics,general}', true),
('Telangana Today — Nirmal',            'telanganatoday.com/tag/nirmal',             'https://www.telanganatoday.com/tag/nirmal/feed',             'rss', 2, 'en', '{Telangana,Nirmal}',                     '{politics,general}', true),
('Telangana Today — Kumram Bheem',      'telanganatoday.com/tag/kumram-bheem-asifabad','https://www.telanganatoday.com/tag/kumram-bheem-asifabad/feed','rss', 2, 'en', '{Telangana,"Kumram Bheem","Kumram Bheem Asifabad",Asifabad}', '{politics,general}', true),
('Telangana Today — Nizamabad',         'telanganatoday.com/tag/nizamabad',          'https://www.telanganatoday.com/tag/nizamabad/feed',          'rss', 2, 'en', '{Telangana,Nizamabad}',                  '{politics,general}', true),
('Telangana Today — Kamareddy',         'telanganatoday.com/tag/kamareddy',          'https://www.telanganatoday.com/tag/kamareddy/feed',          'rss', 2, 'en', '{Telangana,Kamareddy}',                  '{politics,general}', true),
('Telangana Today — Medak',             'telanganatoday.com/tag/medak',              'https://www.telanganatoday.com/tag/medak/feed',              'rss', 2, 'en', '{Telangana,Medak}',                      '{politics,general}', true),
('Telangana Today — Siddipet',          'telanganatoday.com/tag/siddipet',           'https://www.telanganatoday.com/tag/siddipet/feed',           'rss', 2, 'en', '{Telangana,Siddipet}',                   '{politics,general}', true),
('Telangana Today — Yadadri',           'telanganatoday.com/tag/yadadri',            'https://www.telanganatoday.com/tag/yadadri/feed',            'rss', 2, 'en', '{Telangana,"Yadadri Bhuvanagiri",Yadadri,Bhongir}', '{politics,general}', true),
('Telangana Today — Nalgonda',          'telanganatoday.com/tag/nalgonda',           'https://www.telanganatoday.com/tag/nalgonda/feed',           'rss', 2, 'en', '{Telangana,Nalgonda}',                   '{politics,general}', true),
('Telangana Today — Suryapet',          'telanganatoday.com/tag/suryapet',           'https://www.telanganatoday.com/tag/suryapet/feed',           'rss', 2, 'en', '{Telangana,Suryapet}',                   '{politics,general}', true),
('Telangana Today — Mahbubnagar',       'telanganatoday.com/tag/mahbubnagar',        'https://www.telanganatoday.com/tag/mahbubnagar/feed',        'rss', 2, 'en', '{Telangana,Mahbubnagar}',                '{politics,general}', true),
('Telangana Today — Wanaparthy',        'telanganatoday.com/tag/wanaparthy',         'https://www.telanganatoday.com/tag/wanaparthy/feed',         'rss', 2, 'en', '{Telangana,Wanaparthy}',                 '{politics,general}', true),
('Telangana Today — Narayanpet',        'telanganatoday.com/tag/narayanpet',         'https://www.telanganatoday.com/tag/narayanpet/feed',         'rss', 2, 'en', '{Telangana,Narayanpet}',                 '{politics,general}', true),
('Telangana Today — Nagarkurnool',      'telanganatoday.com/tag/nagarkurnool',       'https://www.telanganatoday.com/tag/nagarkurnool/feed',       'rss', 2, 'en', '{Telangana,Nagarkurnool}',               '{politics,general}', true),
('Telangana Today — Jogulamba Gadwal',  'telanganatoday.com/tag/jogulamba',          'https://www.telanganatoday.com/tag/jogulamba/feed',          'rss', 2, 'en', '{Telangana,"Jogulamba Gadwal",Jogulamba,Gadwal}', '{politics,general}', true),

-- ── Statewide Telugu / Telangana-focused outlets ────────────────────────────
('HMTV',                       'hmtvlive.com',                'https://www.hmtvlive.com/feed/',                        'rss', 2, 'en', '{Telangana,"Andhra Pradesh"}', '{politics,general}',  true),
('Namasthe Telangana',         'ntnews.com',                  'https://www.ntnews.com/feed',                           'rss', 2, 'te', '{Telangana,Hyderabad}',        '{politics,general}',  true),
('V6 Velugu',                  'v6velugu.com',                'https://www.v6velugu.com/feed/',                        'rss', 2, 'te', '{Telangana,Hyderabad}',        '{politics,general}',  true),
('Mana Telangana',             'manatelangana.news',          'https://www.manatelangana.news/feed/',                  'rss', 2, 'te', '{Telangana,Hyderabad}',        '{politics,general}',  true),
('Telangana Tribune',          'telanganatribune.com',        'https://www.telanganatribune.com/feed/',                'rss', 3, 'en', '{Telangana,Hyderabad}',        '{politics,general}',  true),
('Munsif Daily',               'munsifdaily.com',             'https://munsifdaily.com/feed/',                         'rss', 3, 'ur', '{Telangana,Hyderabad}',        '{politics,general}',  true),

-- ── National wires that publish Telangana-specific feeds ────────────────────
('The Hindu — Andhra Pradesh', 'thehindu.com/news/states/andhra-pradesh', 'https://www.thehindu.com/news/states/andhra-pradesh/feeder/default.rss', 'rss', 1, 'en', '{"Andhra Pradesh",Telangana}', '{politics,general}', true),
('Times of India — Hyderabad', 'timesofindia.indiatimes.com/hyderabad',   'https://timesofindia.indiatimes.com/rssfeeds/8021716.cms',               'rss', 1, 'en', '{Telangana,Hyderabad}',        '{politics,general}', true),
('Indian Express — Telangana', 'indianexpress.com/section/india/telangana',     'https://indianexpress.com/section/india/telangana/feed/',         'rss', 1, 'en', '{Telangana}',                  '{politics,general}', true),
('Indian Express — AP',        'indianexpress.com/section/india/andhra-pradesh','https://indianexpress.com/section/india/andhra-pradesh/feed/',    'rss', 1, 'en', '{"Andhra Pradesh",Telangana}', '{politics,general}', true),
('ZeeNews — Telangana (Hindi)','zeenews.india.com/hindi/rss/telangana',         'https://zeenews.india.com/hindi/rss/telangana-news.xml',          'rss', 2, 'hi', '{Telangana}',                  '{politics,general}', true),
('News18 — Telangana (Hindi)', 'hindi.news18.com/rss/telangana',                'https://hindi.news18.com/rss/telangana-news.xml',                 'rss', 2, 'hi', '{Telangana}',                  '{politics,general}', true),
('News18 Telugu',              'telugu.news18.com',                             'https://telugu.news18.com/rss/news.xml',                          'rss', 2, 'te', '{Telangana,"Andhra Pradesh"}', '{politics,general}', true),

-- ── Telugu wires (statewide, useful when district edition unavailable) ──────
('Telugu 360',                 'telugu360.com',               'https://www.telugu360.com/feed/',                       'rss', 2, 'en', '{Telangana,"Andhra Pradesh"}', '{politics,general}', true),
('AP Herald',                  'apherald.com',                'https://www.apherald.com/feed/',                        'rss', 3, 'en', '{Telangana,"Andhra Pradesh"}', '{politics,general}', true)

ON CONFLICT (domain) DO NOTHING;

-- Reactivate Eenadu / Sakshi roots (they may have been disabled because RSS
-- went dark; the Playwright scraper will pick them up via HTML parsing).
UPDATE sources SET is_active = TRUE
WHERE domain IN ('eenadu.net', 'sakshi.com')
  AND is_active = FALSE;

DO $$
DECLARE
  rss_total int; tg_district_total int;
BEGIN
  SELECT count(*) INTO rss_total FROM sources WHERE source_type='rss' AND is_active = true;
  SELECT count(*) INTO tg_district_total FROM sources WHERE domain LIKE 'telanganatoday.com/tag/%';
  RAISE NOTICE '038: rss active = %, telangana district feeds = %', rss_total, tg_district_total;
END $$;
