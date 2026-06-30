-- seed_social_watchlist.sql
-- ============================================================================
-- STARTER standing corpus for social collection (the "always-scrape" set).
-- India OSINT focus. Real, well-known public handles/subreddits only — NO
-- fabricated entries (telegram/instagram entries marked (v) were validated to
-- resolve during the build trial; expand with verified handles before relying).
--
-- Idempotent: ON CONFLICT (platform, target_type, target_value) DO NOTHING.
-- priority: 1=hottest (checked first/most), 5=default. source='corpus'.
-- This is a STARTER — curate/extend it; it's data, re-runnable any time.
-- ============================================================================

INSERT INTO social_watchlist (platform, target_type, target_value, label, source, priority) VALUES
-- ── Twitter / X — political leaders + parties + major news (real accounts) ──
('twitter','handle','narendramodi','PM Narendra Modi','corpus',1),
('twitter','handle','RahulGandhi','Rahul Gandhi','corpus',1),
('twitter','handle','AmitShah','Amit Shah','corpus',1),
('twitter','handle','ArvindKejriwal','Arvind Kejriwal','corpus',2),
('twitter','handle','PMOIndia','PMO India','corpus',2),
('twitter','handle','BJP4India','BJP','corpus',2),
('twitter','handle','INCIndia','Indian National Congress','corpus',2),
('twitter','handle','AamAadmiParty','Aam Aadmi Party','corpus',3),
('twitter','handle','ANI','ANI news wire','corpus',2),
('twitter','handle','ndtv','NDTV','corpus',3),
('twitter','handle','the_hindu','The Hindu','corpus',3),
('twitter','handle','IndianExpress','Indian Express','corpus',3),
('twitter','handle','timesofindia','Times of India','corpus',3),
('twitter','keyword','India election','election monitoring','corpus',4),
('twitter','keyword','Bihar election','Bihar politics','corpus',4),

-- ── Reddit — major India subreddits (real) ──
('reddit','subreddit','india','r/india','corpus',2),
('reddit','subreddit','IndiaSpeaks','r/IndiaSpeaks','corpus',2),
('reddit','subreddit','unitedstatesofindia','r/unitedstatesofindia','corpus',3),
('reddit','subreddit','IndianStreetBets','r/IndianStreetBets (markets)','corpus',3),
('reddit','subreddit','bihar','r/bihar','corpus',4),
('reddit','subreddit','Kerala','r/Kerala','corpus',4),
('reddit','subreddit','mumbai','r/mumbai','corpus',4),
('reddit','keyword','Modi','Modi mentions','corpus',4),

-- ── Telegram — validated channels (v); EXPAND with verified handles ──
('telegram','channel','thewire_in','The Wire (v)','corpus',3),
('telegram','channel','ndtv','NDTV (v)','corpus',3),

-- ── Instagram — validated public accounts (v); account-monitoring tier ──
('instagram','handle','narendramodi','PM Narendra Modi IG (v)','corpus',2),
('instagram','handle','ndtv','NDTV IG (v)','corpus',3),
('instagram','handle','indiatoday','India Today IG (v)','corpus',3)
ON CONFLICT (platform, target_type, target_value) DO NOTHING;

-- summary
SELECT platform, count(*) AS targets FROM social_watchlist GROUP BY platform ORDER BY platform;
