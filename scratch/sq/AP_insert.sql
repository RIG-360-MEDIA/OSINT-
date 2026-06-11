\set ON_ERROR_STOP on
BEGIN;
SELECT count(*) before_total FROM sources;
INSERT INTO sources (name,domain,rss_url,source_type,source_tier,language,country,topics,is_active) VALUES
('Visalandhra','visalaandhra.com','https://visalaandhra.com/feed/','rss',3,'te','IN',ARRAY['general'],true),
('10TV','10tv.in','https://10tv.in/rss','rss',2,'te','IN',ARRAY['general'],true),
('TV5 News Telugu','tv5news.in','https://www.tv5news.in/google_feeds.xml','rss',2,'te','IN',ARRAY['general'],true),
('Tupaki','tupaki.com','https://www.tupaki.com/google_feeds.xml','rss',2,'te','IN',ARRAY['general'],true),
('Telugu Rajyam','telugurajyam.com','https://telugurajyam.com/feed','rss',3,'te','IN',ARRAY['general'],true),
('Greater Andhra','greatandhra.com','https://www.greatandhra.com/feed/','rss',3,'en','IN',ARRAY['general'],true),
('Telugu One','teluguone.com','https://www.teluguone.com/news/rss/politics/politics-39.rss','rss',3,'te','IN',ARRAY['general'],true),
('Telugu Bullet','telugubullet.com','https://telugubullet.com/feed/','rss',3,'te','IN',ARRAY['general'],true),
('News9 Live — Telangana','news9live.com','https://www.news9live.com/feedapi/state/telangana','rss',2,'en','IN',ARRAY['general'],true),
('News9 Live — AP','news9live.com','https://www.news9live.com/feedapi/state/andhra-pradesh','rss',2,'en','IN',ARRAY['general'],true),
('News Meter','newsmeter.in','https://newsmeter.in/google_feeds.xml','rss',2,'en','IN',ARRAY['general'],true),
('Telangana Tribune','telanganatribune.com','https://www.telanganatribune.com/feed/','rss',3,'en','IN',ARRAY['general'],true),
('TFIPOST South','tfipost.com','https://tfipost.com/feed/','rss',3,'en','IN',ARRAY['general'],true),
('Andhra Prabha','andhraprabha.com','https://andhraprabha.com','scrape',2,'te','IN',ARRAY['general'],true),
('Mahaa News','mahaanews.com','https://mahaanews.com','scrape',2,'te','IN',ARRAY['general'],true),
('ABN Andhra Jyothi','abnandhrajyothy.com','https://abnandhrajyothy.com','scrape',1,'te','IN',ARRAY['general'],true),
('Studio N Telugu','studion.tv','https://studion.tv','scrape',3,'te','IN',ARRAY['general'],true),
('ETV Andhra Pradesh','etv.co.in','https://etv.co.in','scrape',1,'te','IN',ARRAY['general'],true),
('RTV Telugu','rtv.in','https://rtv.in','scrape',3,'te','IN',ARRAY['general'],true),
('10TV News','10tvnews.in','https://10tvnews.in','scrape',3,'te','IN',ARRAY['general'],true),
('AP7AM','ap7am.com','https://ap7am.com','scrape',2,'te','IN',ARRAY['general'],true),
('iDream Media News','idreammedia.com','https://idreammedia.com','scrape',3,'te','IN',ARRAY['general'],true),
('SumanTV News','sumantv.com','https://sumantv.com','scrape',3,'te','IN',ARRAY['general'],true),
('Gulte','gulte.com','https://gulte.com','scrape',3,'en','IN',ARRAY['general'],true),
('Telugu Reporter','telugureporter.com','https://telugureporter.com','scrape',3,'te','IN',ARRAY['general'],true),
('Andhra Headlines','andhraheadlines.com','https://andhraheadlines.com','scrape',3,'en','IN',ARRAY['general'],true),
('Times of India — Hyderabad','timesofindia.indiatimes.com','https://timesofindia.indiatimes.com/city/hyderabad','scrape',1,'en','IN',ARRAY['general'],true),
('Times of India — Vijayawada','timesofindia.indiatimes.com','https://timesofindia.indiatimes.com/city/vijayawada','scrape',1,'en','IN',ARRAY['general'],true),
('Times of India — Visakhapatnam','timesofindia.indiatimes.com','https://timesofindia.indiatimes.com/city/visakhapatnam','scrape',1,'en','IN',ARRAY['general'],true),
('Andhra Bhoomi','andhrabhoomi.in','https://andhrabhoomi.in','scrape',2,'te','IN',ARRAY['general'],true),
('Suryaa News','surya.co.in','https://surya.co.in','scrape',2,'te','IN',ARRAY['general'],true),
('Andhra Patrika','andhrapatrika.com','https://andhrapatrika.com','scrape',3,'te','IN',ARRAY['general'],true),
('ABP Desam Telugu','abplive.com','https://abplive.com/news/state/andhra-pradesh-news','scrape',2,'te','IN',ARRAY['general'],true),
('Khabar Live','khabarlive.com','https://khabarlive.com','scrape',3,'en','IN',ARRAY['general'],true),
('Telugu Express','teluguexpress.com','https://teluguexpress.com','scrape',3,'en','IN',ARRAY['general'],true)
ON CONFLICT (domain) DO NOTHING;
SELECT count(*) after_total, count(*) FILTER (WHERE created_at > now()-interval '5 minutes') new_this_batch FROM sources;
COMMIT;
SELECT country, source_type, count(*) FROM sources WHERE created_at > now()-interval '5 minutes' GROUP BY 1,2;