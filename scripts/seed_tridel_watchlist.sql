-- seed_tridel_watchlist.sql
-- ============================================================================
-- Watchlist for the CORPORATE OSINT product's first client: TRIDEL (Toronto GTA
-- condo developer). All rows tagged client='tridel' → the tridel collector
-- scrapes ONLY these; the india_govt product is untouched (one shared table,
-- separated by `client`; requires migration 119).
--
-- Social platforms only (twitter/reddit/instagram/telegram). ARTICLES + YOUTUBE
-- for Tridel are documented in docs/design/tridel-sources.md — they ingest via
-- the article-source + youtube-channel mechanisms, not social_watchlist.
--
-- Real, discovered handles (docs/design/tridel-sources.md). (verify)-flagged ones
-- from research are omitted here — add after confirming the live profile.
-- Idempotent: ON CONFLICT (platform, target_type, target_value) DO NOTHING.
-- NOTE: UNIQUE is (platform,target_type,target_value) — if a handle is ever
-- shared across clients, add client to the conflict target in a later migration.
-- ============================================================================

INSERT INTO social_watchlist (client, platform, target_type, target_value, label, source, priority) VALUES
-- ── TWITTER: Developers (Direct + Competitor) ──
('tridel','twitter','handle','tridel','Tridel (DIRECT)','corpus',1),
('tridel','twitter','handle','Tridel_Co','Tridel Construction','corpus',2),
('tridel','twitter','handle','TridelCare','Tridel Customer Care','corpus',2),
('tridel','twitter','handle','TheDanielsCorp','Daniels Corporation','corpus',2),
('tridel','twitter','handle','Concord_Adex','Concord Adex','corpus',2),
('tridel','twitter','handle','MenkesLife','Menkes','corpus',2),
('tridel','twitter','handle','greatgulf','Great Gulf','corpus',2),
('tridel','twitter','handle','pembertongroup','Pemberton Group','corpus',3),
('tridel','twitter','handle','canderelgroup','Canderel','corpus',3),
('tridel','twitter','handle','CityzenGroup','Cityzen','corpus',3),
('tridel','twitter','handle','mymadisonhome','Madison Group','corpus',3),
('tridel','twitter','handle','mattamyhomes','Mattamy Homes','corpus',3),
-- ── TWITTER: City Hall (approval deciders) ──
('tridel','twitter','handle','MayorOliviaChow','Mayor Olivia Chow','corpus',1),
('tridel','twitter','handle','gordperks','P&H Cmte Chair Gord Perks','corpus',2),
('tridel','twitter','handle','FrancesNunziata','P&H Vice-Chair / Speaker','corpus',2),
('tridel','twitter','handle','BradMBradford','Cllr Brad Bradford','corpus',2),
('tridel','twitter','handle','vcrisanti','Cllr Vincent Crisanti','corpus',3),
('tridel','twitter','handle','JoshMatlow','Cllr Josh Matlow','corpus',3),
('tridel','twitter','handle','CllrJamaalMyers','Cllr Jamaal Myers','corpus',3),
('tridel','twitter','handle','ausmalik','Deputy Mayor Ausma Malik','corpus',2),
-- ── TWITTER: Economists / analysts (macro sentiment) ──
('tridel','twitter','handle','JohnPasalis','John Pasalis / Realosophy','corpus',2),
('tridel','twitter','handle','BenRabidoux','Ben Rabidoux','corpus',3),
('tridel','twitter','handle','SteveSaretsky','Steve Saretsky','corpus',3),
('tridel','twitter','handle','danielfoch','Daniel Foch','corpus',3),
('tridel','twitter','handle','ronmortgageguy','Ron Butler (mortgage)','corpus',3),
('tridel','twitter','handle','areacode416','Scott Ingram (data)','corpus',3),
('tridel','twitter','handle','RobKavcic','Robert Kavcic / BMO','corpus',3),
('tridel','twitter','handle','BetterDwelling','Better Dwelling','corpus',3),
('tridel','twitter','handle','StephenPunwasi','Stephen Punwasi','corpus',4),
('tridel','twitter','handle','RBC_Economics','RBC Economics','corpus',4),
('tridel','twitter','handle','TD_Economics','TD Economics','corpus',4),
-- ── TWITTER: NIMBY / YIMBY / urbanist (approval politics) ──
('tridel','twitter','handle','MoreNeighbours','More Neighbours (YIMBY)','corpus',3),
('tridel','twitter','handle','toyimby','Toronto YIMBY','corpus',3),
('tridel','twitter','handle','planningtoronto','Social Planning Toronto','corpus',3),
('tridel','twitter','handle','TOenviro','Toronto Environmental Alliance','corpus',4),
('tridel','twitter','handle','GraphicMatt','Matt Elliott / City Hall Watcher','corpus',2),
('tridel','twitter','handle','Sean_YYZ','Sean Marshall (urbanist)','corpus',4),
('tridel','twitter','handle','g_meslin','Gil Meslin (planner)','corpus',3),
('tridel','twitter','handle','shawnmicallef','Shawn Micallef (Star/Spacing)','corpus',4),
('tridel','twitter','handle','bmdoucet','Brian Doucet (academic)','corpus',4),
('tridel','twitter','handle','annexresidents','Annex Residents Assoc (objector)','corpus',3),
('tridel','twitter','handle','PlannerSean','Sean Galbraith (planner)','corpus',4),
-- ── TWITTER: Beat reporters (break stories early) ──
('tridel','twitter','handle','shanedingman','Shane Dingman / Globe RE','corpus',3),
('tridel','twitter','handle','rachyounglai','Rachelle Younglai / Globe','corpus',3),
('tridel','twitter','handle','dmrider','David Rider / Star City Hall','corpus',3),
('tridel','twitter','handle','BenSpurr','Ben Spurr / Star City Hall','corpus',3),
('tridel','twitter','handle','TessKalinowski','Tess Kalinowski / Star RE','corpus',3),
('tridel','twitter','handle','regionomics','Murtaza Haider / FP','corpus',4),
('tridel','twitter','handle','aaltsted','Ari Altstedter / Bloomberg','corpus',4),
('tridel','twitter','handle','interchange42','Craig White / UrbanToronto','corpus',3),
('tridel','twitter','handle','storeyspub','STOREYS','corpus',4),
('tridel','twitter','handle','Urban_Toronto','UrbanToronto','corpus',3),
('tridel','twitter','handle','BNNBloomberg','BNN Bloomberg','corpus',4),
-- ── TWITTER: keywords ──
('tridel','twitter','keyword','Tridel','Tridel mentions','corpus',2),
('tridel','twitter','keyword','Del Zotto','leadership/family','corpus',3),
('tridel','twitter','keyword','Toronto condo','market topic','corpus',4),
('tridel','twitter','keyword','Toronto development charges','regulatory','corpus',4),
-- ── REDDIT: markets + hyper-local (candid reputation/affordability) ──
('tridel','reddit','subreddit','TorontoRealEstate','r/TorontoRealEstate','corpus',2),
('tridel','reddit','subreddit','canadahousing','r/canadahousing','corpus',3),
('tridel','reddit','subreddit','canadahousing2','r/canadahousing2','corpus',3),
('tridel','reddit','subreddit','RealEstateCanada','r/RealEstateCanada','corpus',3),
('tridel','reddit','subreddit','PersonalFinanceCanada','r/PersonalFinanceCanada','corpus',4),
('tridel','reddit','subreddit','toronto','r/toronto','corpus',3),
('tridel','reddit','subreddit','askTO','r/askTO','corpus',4),
('tridel','reddit','subreddit','mississauga','r/mississauga','corpus',4),
('tridel','reddit','subreddit','brampton','r/brampton','corpus',4),
('tridel','reddit','subreddit','Scarborough','r/Scarborough','corpus',4),
('tridel','reddit','subreddit','Etobicoke','r/Etobicoke','corpus',4),
('tridel','reddit','keyword','Tridel','Tridel on Reddit','corpus',3),
-- ── INSTAGRAM: developer brands + influencers ──
('tridel','instagram','handle','tridelcommunities','Tridel IG (DIRECT)','corpus',2),
('tridel','instagram','handle','concordadex','Concord Adex IG','corpus',3),
('tridel','instagram','handle','thedanielscorp','Daniels IG','corpus',3),
('tridel','instagram','handle','menkeslife','Menkes IG','corpus',3),
('tridel','instagram','handle','greatgulf','Great Gulf IG','corpus',3),
('tridel','instagram','handle','pembertongroup','Pemberton IG','corpus',4),
('tridel','instagram','handle','canderelres','Canderel Residential IG','corpus',4),
('tridel','instagram','handle','mattamyhomes','Mattamy IG (active vs X)','corpus',3),
('tridel','instagram','handle','delrentals','Del Condo Rentals (Tridel affil)','corpus',4),
('tridel','instagram','handle','propertyinfluencers','Property Influencers (102K)','corpus',3),
('tridel','instagram','handle','bradjlambrealtyinc','Brad J Lamb Realty','corpus',3),
('tridel','instagram','handle','real.estate.king','Michael Bucci (CRE)','corpus',4),
('tridel','instagram','handle','lindsey.deluce','Lindsey Deluce (CTV)','corpus',4),
('tridel','instagram','handle','thushanthseevaratnam','Toronto realtor team','corpus',4),
('tridel','instagram','handle','alexmckinlaycorey','Toronto agent (Heaps Estrin)','corpus',4),
-- ── TELEGRAM: weak (near-skip; investor flow is private/web) ──
('tridel','telegram','channel','HousingToronto','Toronto homefinder (low volume)','corpus',5)
ON CONFLICT (platform, target_type, target_value) DO NOTHING;

-- summary
SELECT client, platform, count(*) AS targets
FROM social_watchlist GROUP BY client, platform ORDER BY client, platform;
