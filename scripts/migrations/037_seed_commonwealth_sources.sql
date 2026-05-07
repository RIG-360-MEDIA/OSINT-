-- 037_seed_commonwealth_sources.sql
-- Seed Commonwealth-relevant RSS sources so personas anchored on London,
-- Pacific SIDS, Caribbean, Sub-Saharan Africa, etc. actually have a corpus
-- to score against.
--
-- Pre-fix the corpus was ~95% India-domestic; the Commonwealth Secretariat
-- persona we onboarded for Satinder Bindra ended up with avg tier-3
-- score_final = 0.13 because no source published anything close to their
-- entity / geo set. This migration broadens supply across:
--   - United Kingdom (BBC, Guardian, FT, Telegraph, Sky, Independent, C4)
--   - Pan-Africa (allAfrica regions, Africa Report, ISS Africa)
--   - West / East / Southern Africa (Nigeria, Ghana, Kenya, Uganda,
--     Tanzania, Rwanda, South Africa, Zimbabwe, Zambia, Namibia, Mauritius)
--   - Pacific (RNZ, ABC Pacific, PIR, Fiji, Samoa, Vanuatu, Solomon, PNG,
--     Cook Islands, NZ, Australia)
--   - Caribbean (Jamaica, Trinidad, Guyana, Bahamas, Antigua, Barbados,
--     St Lucia, Cayman, Dominica, BVI)
--   - South Asia Commonwealth (Bangladesh, Pakistan, Sri Lanka, Maldives)
--   - SE Asia Commonwealth (Malaysia, Singapore)
--   - Wire / IGO (Al Jazeera, Reuters, AP)
--   - Foreign-affairs think tanks (Chatham House, Lowy, ECFR, ICG, ODI)
--
-- All inserts are idempotent via ON CONFLICT (domain) DO NOTHING — safe to
-- re-run, safe to apply on a partially-seeded environment.

INSERT INTO sources (name, domain, rss_url, source_type, source_tier, language, geo_states, topics, is_active) VALUES

-- ── United Kingdom ─────────────────────────────────────────────────────────
('BBC News — World',          'feeds.bbci.co.uk/news/world',                 'http://feeds.bbci.co.uk/news/world/rss.xml',                              'rss', 1, 'en', '{UK,London,global}',                       '{politics,international,general}',     true),
('BBC News — UK',             'feeds.bbci.co.uk/news/uk',                    'http://feeds.bbci.co.uk/news/uk/rss.xml',                                  'rss', 1, 'en', '{UK,London}',                              '{politics,general}',                    true),
('BBC News — Politics',       'feeds.bbci.co.uk/news/politics',              'http://feeds.bbci.co.uk/news/politics/rss.xml',                            'rss', 1, 'en', '{UK,London}',                              '{politics,governance}',                 true),
('BBC News — Business',       'feeds.bbci.co.uk/news/business',              'http://feeds.bbci.co.uk/news/business/rss.xml',                            'rss', 1, 'en', '{UK,London,global}',                       '{business,economy}',                    true),
('BBC News — Africa',         'feeds.bbci.co.uk/news/world/africa',          'http://feeds.bbci.co.uk/news/world/africa/rss.xml',                        'rss', 1, 'en', '{Africa,Sub-Saharan Africa,global}',       '{politics,international,general}',     true),
('BBC News — Asia',           'feeds.bbci.co.uk/news/world/asia',            'http://feeds.bbci.co.uk/news/world/asia/rss.xml',                          'rss', 1, 'en', '{Asia,South Asia,Southeast Asia,global}',  '{politics,international,general}',     true),
('BBC News — Latin America',  'feeds.bbci.co.uk/news/world/latin_america',   'http://feeds.bbci.co.uk/news/world/latin_america/rss.xml',                 'rss', 1, 'en', '{Latin America,Caribbean,global}',         '{politics,international,general}',     true),
('The Guardian — World',      'theguardian.com/world',                        'https://www.theguardian.com/world/rss',                                    'rss', 1, 'en', '{UK,London,global}',                       '{politics,international,general}',     true),
('The Guardian — UK News',    'theguardian.com/uk-news',                      'https://www.theguardian.com/uk-news/rss',                                  'rss', 1, 'en', '{UK,London}',                              '{politics,general}',                    true),
('The Guardian — Politics',   'theguardian.com/politics',                     'https://www.theguardian.com/politics/rss',                                 'rss', 1, 'en', '{UK,London}',                              '{politics,governance}',                 true),
('The Guardian — Africa',     'theguardian.com/world/africa',                 'https://www.theguardian.com/world/africa/rss',                             'rss', 1, 'en', '{Africa,Sub-Saharan Africa,global}',       '{politics,international,general}',     true),
('The Guardian — Asia Pacific','theguardian.com/world/asia-pacific',          'https://www.theguardian.com/world/asia-pacific/rss',                       'rss', 1, 'en', '{Asia Pacific,Pacific,global}',            '{politics,international,general}',     true),
('The Guardian — Caribbean',  'theguardian.com/world/caribbean',              'https://www.theguardian.com/world/caribbean/rss',                          'rss', 2, 'en', '{Caribbean,global}',                       '{politics,international}',              true),
('The Guardian — Americas',   'theguardian.com/world/americas',               'https://www.theguardian.com/world/americas/rss',                           'rss', 2, 'en', '{Americas,global}',                        '{politics,international}',              true),
('Financial Times — World',   'ft.com/world',                                 'https://www.ft.com/world?format=rss',                                      'rss', 1, 'en', '{UK,London,global}',                       '{business,economy,international}',      true),
('The Telegraph — World',     'telegraph.co.uk/news/world',                   'https://www.telegraph.co.uk/news/world/rss.xml',                           'rss', 2, 'en', '{UK,London,global}',                       '{politics,international,general}',     true),
('The Telegraph — Politics',  'telegraph.co.uk/politics',                     'https://www.telegraph.co.uk/politics/rss.xml',                             'rss', 2, 'en', '{UK,London}',                              '{politics,governance}',                 true),
('Sky News — World',          'feeds.skynews.com/feeds/rss/world',            'https://feeds.skynews.com/feeds/rss/world.xml',                            'rss', 2, 'en', '{UK,London,global}',                       '{politics,international,general}',     true),
('Sky News — UK',             'feeds.skynews.com/feeds/rss/uk',               'https://feeds.skynews.com/feeds/rss/uk.xml',                               'rss', 2, 'en', '{UK,London}',                              '{politics,general}',                    true),
('Sky News — Politics',       'feeds.skynews.com/feeds/rss/politics',         'https://feeds.skynews.com/feeds/rss/politics.xml',                         'rss', 2, 'en', '{UK,London}',                              '{politics,governance}',                 true),
('The Independent — World',   'independent.co.uk/news/world',                 'https://www.independent.co.uk/news/world/rss',                             'rss', 2, 'en', '{UK,London,global}',                       '{politics,international,general}',     true),
('The Independent — Politics','independent.co.uk/news/uk/politics',            'https://www.independent.co.uk/news/uk/politics/rss',                       'rss', 2, 'en', '{UK,London}',                              '{politics,governance}',                 true),
('Channel 4 News',            'channel4.com/news',                            'https://www.channel4.com/news/feed',                                       'rss', 2, 'en', '{UK,London,global}',                       '{politics,international,general}',     true),
('The Conversation — UK',     'theconversation.com/uk',                       'https://theconversation.com/uk/articles.atom',                             'rss', 3, 'en', '{UK,London,global}',                       '{academia,politics,general}',           true),

-- ── Pan-Africa & Africa policy ────────────────────────────────────────────
('AllAfrica — Latest',           'allafrica.com',                                       'https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf',           'rss', 1, 'en', '{Africa,Sub-Saharan Africa,global}',           '{politics,international,general}', true),
('AllAfrica — East Africa',      'allafrica.com/eastafrica',                            'https://allafrica.com/tools/headlines/rdf/eastafrica/headlines.rdf',       'rss', 2, 'en', '{East Africa,Sub-Saharan Africa}',             '{politics,international}',          true),
('AllAfrica — West Africa',      'allafrica.com/westafrica',                            'https://allafrica.com/tools/headlines/rdf/westafrica/headlines.rdf',       'rss', 2, 'en', '{West Africa,Sub-Saharan Africa}',             '{politics,international}',          true),
('AllAfrica — Southern Africa',  'allafrica.com/southernafrica',                        'https://allafrica.com/tools/headlines/rdf/southernafrica/headlines.rdf',   'rss', 2, 'en', '{Southern Africa,Sub-Saharan Africa}',         '{politics,international}',          true),
('AllAfrica — Politics',         'allafrica.com/politics',                              'https://allafrica.com/tools/headlines/rdf/politics/headlines.rdf',         'rss', 2, 'en', '{Africa,Sub-Saharan Africa}',                  '{politics,governance}',             true),
('The Africa Report',            'theafricareport.com',                                 'https://www.theafricareport.com/feed/',                                    'rss', 2, 'en', '{Africa,Sub-Saharan Africa,global}',           '{politics,business,international}', true),
('Africa News',                  'africanews.com',                                      'https://www.africanews.com/feed/rss',                                      'rss', 2, 'en', '{Africa,Sub-Saharan Africa,global}',           '{politics,general}',                true),
('ISS Africa',                   'issafrica.org',                                       'https://issafrica.org/iss-today/rss',                                      'rss', 2, 'en', '{Africa,Sub-Saharan Africa}',                  '{security,policy,research}',         true),
('Daily Maverick (South Africa)','dailymaverick.co.za',                                  'https://www.dailymaverick.co.za/dmrss/',                                   'rss', 2, 'en', '{South Africa,Southern Africa}',               '{politics,general}',                true),
('Mail & Guardian (SA)',         'mg.co.za',                                            'https://mg.co.za/feed/',                                                   'rss', 2, 'en', '{South Africa,Southern Africa}',               '{politics,general}',                true),
('News24 (SA)',                  'news24.com',                                          'https://feeds.news24.com/articles/news24/TopStories/rss',                   'rss', 2, 'en', '{South Africa,Southern Africa}',               '{politics,general}',                true),
('IOL (South Africa)',           'iol.co.za',                                           'https://iol.co.za/rss/news',                                                'rss', 2, 'en', '{South Africa,Southern Africa}',               '{politics,general}',                true),

-- ── West Africa ───────────────────────────────────────────────────────────
('Premium Times Nigeria',  'premiumtimesng.com',  'https://www.premiumtimesng.com/feed', 'rss', 2, 'en', '{Nigeria,West Africa}', '{politics,general}',  true),
('Punch Nigeria',          'punchng.com',         'https://punchng.com/feed/',           'rss', 2, 'en', '{Nigeria,West Africa}', '{politics,general}',  true),
('Vanguard Nigeria',       'vanguardngr.com',     'https://www.vanguardngr.com/feed/',   'rss', 2, 'en', '{Nigeria,West Africa}', '{politics,general}',  true),
('Daily Trust Nigeria',    'dailytrust.com',      'https://dailytrust.com/feed/',        'rss', 2, 'en', '{Nigeria,West Africa}', '{politics,general}',  true),
('This Day Nigeria',       'thisdaylive.com',     'https://www.thisdaylive.com/feed/',   'rss', 2, 'en', '{Nigeria,West Africa}', '{politics,general}',  true),
('GhanaWeb',               'ghanaweb.com',        'https://www.ghanaweb.com/GhanaHomePage/rss/news.xml', 'rss', 2, 'en', '{Ghana,West Africa}', '{politics,general}', true),
('Joy Online (Ghana)',     'myjoyonline.com',     'https://www.myjoyonline.com/feed/',   'rss', 2, 'en', '{Ghana,West Africa}',   '{politics,general}',  true),
('Citi Newsroom (Ghana)',  'citinewsroom.com',    'https://citinewsroom.com/feed/',      'rss', 2, 'en', '{Ghana,West Africa}',   '{politics,general}',  true),
('Daily Graphic (Ghana)',  'graphic.com.gh',      'https://www.graphic.com.gh/feed',     'rss', 2, 'en', '{Ghana,West Africa}',   '{politics,general}',  true),

-- ── East Africa ───────────────────────────────────────────────────────────
('Daily Nation (Kenya)',     'nation.africa/kenya',     'https://nation.africa/kenya/rss',                  'rss', 2, 'en', '{Kenya,East Africa}',          '{politics,general}', true),
('The Standard (Kenya)',     'standardmedia.co.ke',     'https://www.standardmedia.co.ke/rss/headlines.php','rss', 2, 'en', '{Kenya,East Africa}',          '{politics,general}', true),
('The Star (Kenya)',         'the-star.co.ke',          'https://www.the-star.co.ke/feed/',                 'rss', 2, 'en', '{Kenya,East Africa}',          '{politics,general}', true),
('The East African',         'theeastafrican.co.ke',    'https://www.theeastafrican.co.ke/feed',            'rss', 2, 'en', '{East Africa,Kenya,Tanzania,Uganda,Rwanda}', '{politics,international}', true),
('The Citizen (Tanzania)',   'thecitizen.co.tz',        'https://www.thecitizen.co.tz/tanzania/rss',        'rss', 2, 'en', '{Tanzania,East Africa}',       '{politics,general}', true),
('Daily Monitor (Uganda)',   'monitor.co.ug',           'https://www.monitor.co.ug/uganda/rss',             'rss', 2, 'en', '{Uganda,East Africa}',         '{politics,general}', true),
('New Vision (Uganda)',      'newvision.co.ug',         'https://www.newvision.co.ug/api/feeds/rss/main',   'rss', 2, 'en', '{Uganda,East Africa}',         '{politics,general}', true),
('The New Times (Rwanda)',   'newtimes.co.rw',          'https://www.newtimes.co.rw/rss',                   'rss', 2, 'en', '{Rwanda,East Africa}',         '{politics,general}', true),

-- ── Southern Africa (more) ────────────────────────────────────────────────
('The Herald (Zimbabwe)',    'herald.co.zw',           'https://www.herald.co.zw/feed/',           'rss', 2, 'en', '{Zimbabwe,Southern Africa}', '{politics,general}', true),
('NewsDay (Zimbabwe)',       'newsday.co.zw',          'https://www.newsday.co.zw/feed/',          'rss', 2, 'en', '{Zimbabwe,Southern Africa}', '{politics,general}', true),
('Times of Zambia',          'times.co.zm',            'https://www.times.co.zm/?feed=rss2',       'rss', 2, 'en', '{Zambia,Southern Africa}',   '{politics,general}', true),
('Lesotho Times',            'lestimes.com',           'https://lestimes.com/feed/',               'rss', 3, 'en', '{Lesotho,Southern Africa}',  '{politics,general}', true),
('The Namibian',             'namibian.com.na',        'https://www.namibian.com.na/feed/',        'rss', 2, 'en', '{Namibia,Southern Africa}',  '{politics,general}', true),
('New Era (Namibia)',        'neweralive.na',          'https://neweralive.na/feed',               'rss', 3, 'en', '{Namibia,Southern Africa}',  '{politics,general}', true),
('L''Express (Mauritius)',    'lexpress.mu',            'https://www.lexpress.mu/rss',              'rss', 2, 'en', '{Mauritius}',                '{politics,general}', true),

-- ── Pacific (Commonwealth + adjacent) ─────────────────────────────────────
('RNZ — Pacific',                  'rnz.co.nz/rss/pacific',         'https://www.rnz.co.nz/rss/pacific.xml',                            'rss', 1, 'en', '{Pacific,New Zealand,Pacific Islands,Pacific Small Island Developing States}', '{politics,international}', true),
('ABC Pacific',                    'abc.net.au/news/pacific',       'https://www.abc.net.au/news/feed/2942460/rss.xml',                 'rss', 2, 'en', '{Pacific,Australia,Pacific Islands}', '{politics,international}', true),
('Pacific Islands Report',         'pireport.org',                  'https://pireport.org/rss.xml',                                     'rss', 2, 'en', '{Pacific,Pacific Islands}',           '{politics,international}', true),
('Fiji Times',                     'fijitimes.com',                 'https://www.fijitimes.com/feed/',                                  'rss', 2, 'en', '{Fiji,Pacific}',                      '{politics,general}',       true),
('Fiji Sun',                       'fijisun.com.fj',                'https://fijisun.com.fj/feed/',                                     'rss', 3, 'en', '{Fiji,Pacific}',                      '{politics,general}',       true),
('Samoa Observer',                 'samoaobserver.ws',              'https://www.samoaobserver.ws/rss',                                 'rss', 3, 'en', '{Samoa,Pacific}',                     '{politics,general}',       true),
('Vanuatu Daily Post',             'dailypost.vu',                  'https://www.dailypost.vu/feed',                                    'rss', 3, 'en', '{Vanuatu,Pacific}',                   '{politics,general}',       true),
('Solomon Star',                   'solomonstarnews.com',           'https://www.solomonstarnews.com/feed',                             'rss', 3, 'en', '{Solomon Islands,Pacific}',           '{politics,general}',       true),
('PNG Post-Courier',               'postcourier.com.pg',            'https://postcourier.com.pg/feed/',                                 'rss', 3, 'en', '{Papua New Guinea,Pacific}',          '{politics,general}',       true),
('The National (PNG)',             'thenational.com.pg',            'https://www.thenational.com.pg/feed/',                             'rss', 3, 'en', '{Papua New Guinea,Pacific}',          '{politics,general}',       true),
('Cook Islands News',              'cookislandsnews.com',           'https://www.cookislandsnews.com/feed/',                            'rss', 3, 'en', '{Cook Islands,Pacific}',              '{politics,general}',       true),
('Stuff (NZ)',                     'stuff.co.nz',                   'https://www.stuff.co.nz/rss',                                      'rss', 1, 'en', '{New Zealand,Pacific}',                '{politics,general}',       true),
('ABC News (Australia) — Top',     'abc.net.au/news',               'https://www.abc.net.au/news/feed/45910/rss.xml',                   'rss', 1, 'en', '{Australia,Pacific}',                  '{politics,general}',       true),
('Sydney Morning Herald',          'smh.com.au',                    'https://www.smh.com.au/rss/feed.xml',                              'rss', 2, 'en', '{Australia,Pacific}',                  '{politics,general}',       true),
('The Age (Australia)',            'theage.com.au',                 'https://www.theage.com.au/rss/feed.xml',                           'rss', 2, 'en', '{Australia,Pacific}',                  '{politics,general}',       true),

-- ── Caribbean (Commonwealth) ──────────────────────────────────────────────
('Jamaica Gleaner',          'jamaica-gleaner.com',     'http://jamaica-gleaner.com/feed',           'rss', 2, 'en', '{Jamaica,Caribbean}',          '{politics,general}', true),
('Jamaica Observer',         'jamaicaobserver.com',     'https://www.jamaicaobserver.com/feed/',     'rss', 2, 'en', '{Jamaica,Caribbean}',          '{politics,general}', true),
('Trinidad Guardian',        'guardian.co.tt',          'https://www.guardian.co.tt/feed',           'rss', 2, 'en', '{Trinidad and Tobago,Caribbean}','{politics,general}', true),
('Stabroek News (Guyana)',   'stabroeknews.com',        'https://www.stabroeknews.com/feed/',        'rss', 2, 'en', '{Guyana,Caribbean}',           '{politics,general}', true),
('Guyana Chronicle',         'guyanachronicle.com',     'https://guyanachronicle.com/feed/',         'rss', 3, 'en', '{Guyana,Caribbean}',           '{politics,general}', true),
('Tribune 242 (Bahamas)',    'tribune242.com',          'https://www.tribune242.com/feed/',          'rss', 3, 'en', '{Bahamas,Caribbean}',          '{politics,general}', true),
('Nassau Guardian',          'thenassauguardian.com',   'https://thenassauguardian.com/feed/',       'rss', 3, 'en', '{Bahamas,Caribbean}',          '{politics,general}', true),
('Antigua Observer',         'antiguaobserver.com',     'https://antiguaobserver.com/feed/',         'rss', 3, 'en', '{Antigua and Barbuda,Caribbean}','{politics,general}', true),
('Barbados Today',           'barbadostoday.bb',        'https://barbadostoday.bb/feed/',            'rss', 3, 'en', '{Barbados,Caribbean}',         '{politics,general}', true),
('St Lucia Times',           'stluciatimes.com',        'https://stluciatimes.com/feed/',            'rss', 3, 'en', '{Saint Lucia,Caribbean}',      '{politics,general}', true),
('Dominica News Online',     'dominicanewsonline.com',  'https://dominicanewsonline.com/feed/',      'rss', 3, 'en', '{Dominica,Caribbean}',         '{politics,general}', true),
('Cayman Compass',           'caymancompass.com',       'https://www.caymancompass.com/feed',        'rss', 3, 'en', '{Cayman Islands,Caribbean}',   '{politics,general}', true),

-- ── South Asia (Commonwealth) ─────────────────────────────────────────────
('The Daily Star (Bangladesh)','thedailystar.net',     'https://www.thedailystar.net/frontpage/rss.xml', 'rss', 2, 'en', '{Bangladesh,South Asia}',  '{politics,general}', true),
('Dhaka Tribune',             'dhakatribune.com',       'https://www.dhakatribune.com/feed',              'rss', 2, 'en', '{Bangladesh,South Asia}',  '{politics,general}', true),
('Dawn (Pakistan)',           'dawn.com',               'https://www.dawn.com/feeds/home',                'rss', 1, 'en', '{Pakistan,South Asia}',    '{politics,general}', true),
('The News International (Pakistan)','thenews.com.pk', 'https://www.thenews.com.pk/rss/1/1',             'rss', 2, 'en', '{Pakistan,South Asia}',    '{politics,general}', true),
('Express Tribune (Pakistan)','tribune.com.pk',         'https://tribune.com.pk/feed/',                   'rss', 2, 'en', '{Pakistan,South Asia}',    '{politics,general}', true),
('The Island (Sri Lanka)',    'island.lk',              'https://island.lk/feed/',                        'rss', 2, 'en', '{Sri Lanka,South Asia}',   '{politics,general}', true),
('Daily Mirror (Sri Lanka)',  'dailymirror.lk',         'https://www.dailymirror.lk/rss-feeds/main',      'rss', 2, 'en', '{Sri Lanka,South Asia}',   '{politics,general}', true),
('Maldives Independent',      'maldivesindependent.com','https://maldivesindependent.com/feed',           'rss', 3, 'en', '{Maldives,South Asia}',    '{politics,general}', true),
('Sun Online (Maldives)',     'en.sun.mv',              'https://en.sun.mv/rss',                          'rss', 3, 'en', '{Maldives,South Asia}',    '{politics,general}', true),
('Kuensel (Bhutan)',          'kuenselonline.com',      'https://kuenselonline.com/feed/',                'rss', 3, 'en', '{Bhutan,South Asia}',      '{politics,general}', true),

-- ── SE Asia (Commonwealth) ────────────────────────────────────────────────
('Channel News Asia',           'channelnewsasia.com',     'https://www.channelnewsasia.com/rssfeeds/8395986',         'rss', 1, 'en', '{Singapore,Southeast Asia}', '{politics,international}', true),
('The Straits Times (Singapore)','straitstimes.com',        'https://www.straitstimes.com/news/world/rss.xml',          'rss', 2, 'en', '{Singapore,Southeast Asia}', '{politics,international}', true),
('The Star (Malaysia)',         'thestar.com.my',          'https://www.thestar.com.my/rss/news',                       'rss', 2, 'en', '{Malaysia,Southeast Asia}',  '{politics,general}',       true),
('Malay Mail',                  'malaymail.com',           'https://www.malaymail.com/feed/news',                       'rss', 2, 'en', '{Malaysia,Southeast Asia}',  '{politics,general}',       true),
('Malaysiakini',                'malaysiakini.com',        'https://www.malaysiakini.com/rss',                          'rss', 2, 'en', '{Malaysia,Southeast Asia}',  '{politics,general}',       true),

-- ── Wire / Pan-international ──────────────────────────────────────────────
('Al Jazeera English',     'aljazeera.com',          'https://www.aljazeera.com/xml/rss/all.xml',     'rss', 1, 'en', '{global}', '{politics,international,general}', true),
('AP News — Top',          'feeds.apnews.com/topnews','https://feeds.apnews.com/apf-topnews',          'rss', 1, 'en', '{global}', '{politics,international,general}', true),

-- ── Foreign-affairs think tanks ───────────────────────────────────────────
('Chatham House',          'chathamhouse.org',       'https://www.chathamhouse.org/rss',              'rss', 2, 'en', '{global,UK,London}',   '{policy,research,international}', true),
('Lowy Interpreter',       'lowyinstitute.org',      'https://www.lowyinstitute.org/the-interpreter/rss.xml', 'rss', 2, 'en', '{global,Asia Pacific,Pacific}', '{policy,research,international}', true),
('European Council on Foreign Relations','ecfr.eu',  'https://ecfr.eu/feed/',                         'rss', 3, 'en', '{Europe,global}',      '{policy,research,international}', true),
('International Crisis Group','crisisgroup.org',     'https://www.crisisgroup.org/crisiswatch/rss',   'rss', 2, 'en', '{global}',             '{security,policy,research}',      true),
('ODI',                    'odi.org',                'https://odi.org/en/rss',                        'rss', 3, 'en', '{global}',             '{policy,research,development}',   true),
('Brookings',              'brookings.edu',          'https://www.brookings.edu/feed/',               'rss', 2, 'en', '{global,United States}','{policy,research,international}', true)

ON CONFLICT (domain) DO NOTHING;

-- Quick sanity: how many got inserted?
DO $$
DECLARE
  n_total int;
  n_active int;
BEGIN
  SELECT count(*) INTO n_total  FROM sources WHERE source_type = 'rss';
  SELECT count(*) INTO n_active FROM sources WHERE source_type = 'rss' AND is_active = true;
  RAISE NOTICE '037: rss-source totals — total=%, active=%', n_total, n_active;
END $$;
