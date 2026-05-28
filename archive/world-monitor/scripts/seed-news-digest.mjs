/**
 * seed-news-digest.mjs
 * Fetches RSS feeds from host machine and stores a digest in Redis.
 * Source names MUST exactly match src/config/feeds.ts so the client-side
 * enabledNames filter doesn't drop every item.
 */
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const sax = require('sax');

const REDIS_URL   = process.env.UPSTASH_REDIS_REST_URL  || 'http://localhost:8079';
const REDIS_TOKEN = process.env.UPSTASH_REDIS_REST_TOKEN || 'wm-local-token';
const DIGEST_KEY  = 'news:digest:v1:full:en';
const DIGEST_TTL  = 86400; // 24 hours

// Names MUST match src/config/feeds.ts exactly — the client filters by these names.
const FEEDS = [
  // === politics (built JS: BBC World, Guardian World, AP News, Reuters World, CNN World) ===
  { cat: 'politics', name: 'BBC World',      url: 'https://feeds.bbci.co.uk/news/world/rss.xml' },
  { cat: 'politics', name: 'Guardian World', url: 'https://www.theguardian.com/world/rss' },
  { cat: 'politics', name: 'AP News',        url: 'https://feeds.apnews.com/apnews/topnews' },
  { cat: 'politics', name: 'Reuters World',  url: 'https://news.google.com/rss/search?q=site:reuters.com+world&hl=en-US&gl=US&ceid=US:en' },

  // === us (built JS: Reuters US, NPR News, PBS NewsHour, ABC News, CBS News, NBC News, Wall Street Journal, Politico, The Hill) ===
  { cat: 'us', name: 'NPR News',    url: 'https://feeds.npr.org/1001/rss.xml' },
  { cat: 'us', name: 'ABC News',    url: 'https://feeds.abcnews.com/abcnews/topstories' },
  { cat: 'us', name: 'CBS News',    url: 'https://www.cbsnews.com/latest/rss/main' },
  { cat: 'us', name: 'NBC News',    url: 'https://feeds.nbcnews.com/nbcnews/public/news' },
  { cat: 'us', name: 'The Hill',    url: 'https://thehill.com/news/feed' },
  { cat: 'us', name: 'Politico',    url: 'https://rss.politico.com/politics-news.xml' },

  // === europe (built JS: France 24, EuroNews, Le Monde, DW News, Tagesschau, ANSA, NOS Nieuws, SVT Nyheter) ===
  { cat: 'europe', name: 'France 24', url: 'https://www.france24.com/en/rss' },
  { cat: 'europe', name: 'EuroNews',  url: 'https://www.euronews.com/rss?format=xml' },
  { cat: 'europe', name: 'Le Monde',  url: 'https://www.lemonde.fr/en/rss/une.xml' },
  { cat: 'europe', name: 'DW News',   url: 'https://rss.dw.com/xml/rss-en-all' },
  { cat: 'europe', name: 'Tagesschau',url: 'https://www.tagesschau.de/xml/rss2/' },
  { cat: 'europe', name: 'ANSA',      url: 'https://www.ansa.it/sito/notizie/topnews/topnews_rss.xml' },

  // === middleeast (built JS: BBC Middle East, Al Jazeera, Al Arabiya, Guardian ME, BBC Persian, Iran International, Haaretz, Asharq News, The National) ===
  { cat: 'middleeast', name: 'BBC Middle East', url: 'https://feeds.bbci.co.uk/news/world/middle_east/rss.xml' },
  { cat: 'middleeast', name: 'Al Jazeera',      url: 'https://www.aljazeera.com/xml/rss/all.xml' },
  { cat: 'middleeast', name: 'Haaretz',         url: 'https://www.haaretz.com/srv/haaretz-en-rss.xml' },
  { cat: 'middleeast', name: 'The National',    url: 'https://www.thenationalnews.com/arc/outboundfeeds/rss/?outputType=xml' },

  // === africa (built JS: BBC Africa, News24, Africanews, Jeune Afrique, Africa News, Premium Times, Channels TV, Sahel Crisis) ===
  { cat: 'africa', name: 'BBC Africa',    url: 'https://feeds.bbci.co.uk/news/world/africa/rss.xml' },
  { cat: 'africa', name: 'Africanews',    url: 'https://www.africanews.com/feed/rss' },
  { cat: 'africa', name: 'News24',        url: 'https://feeds.news24.com/articles/news24/TopStories/rss' },
  { cat: 'africa', name: 'Africa News',   url: 'https://news.google.com/rss/search?q=(Africa+OR+Nigeria+OR+Kenya+OR+"South+Africa")+when:2d&hl=en-US&gl=US&ceid=US:en' },
  { cat: 'africa', name: 'Premium Times', url: 'https://www.premiumtimesng.com/feed' },

  // === latam (built JS names: BBC Latin America, Reuters LatAm, InSight Crime, Mexico News Daily, Clarín, Primicias, Infobae Americas, El Universo) ===
  { cat: 'latam', name: 'BBC Latin America', url: 'https://feeds.bbci.co.uk/news/world/latin_america/rss.xml' },
  { cat: 'latam', name: 'InSight Crime',     url: 'https://insightcrime.org/feed/' },
  { cat: 'latam', name: 'Mexico News Daily', url: 'https://mexiconewsdaily.com/feed/' },
  { cat: 'latam', name: 'Infobae Americas',  url: 'https://www.infobae.com/arc/outboundfeeds/rss/' },

  // === asia (built JS names: BBC Asia, The Diplomat, South China Morning Post, Reuters Asia, Nikkei Asia, CNA, Asia News, The Hindu) ===
  { cat: 'asia', name: 'BBC Asia',      url: 'https://feeds.bbci.co.uk/news/world/asia/rss.xml' },
  { cat: 'asia', name: 'The Diplomat',  url: 'https://thediplomat.com/feed/' },
  { cat: 'asia', name: 'Asia News',     url: 'https://news.google.com/rss/search?q=(China+OR+Japan+OR+Korea+OR+India+OR+ASEAN)+when:2d&hl=en-US&gl=US&ceid=US:en' },
  { cat: 'asia', name: 'The Hindu',     url: 'https://www.thehindu.com/news/national/feeder/default.rss' },
  { cat: 'asia', name: 'CNA',           url: 'https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml' },

  // === energy ===
  { cat: 'energy', name: 'Oil & Gas',        url: 'https://news.google.com/rss/search?q=(oil+price+OR+OPEC+OR+"natural+gas")+when:2d&hl=en-US&gl=US&ceid=US:en' },
  { cat: 'energy', name: 'Nuclear Energy',   url: 'https://news.google.com/rss/search?q=("nuclear+energy"+OR+uranium+OR+IAEA)+when:3d&hl=en-US&gl=US&ceid=US:en' },
  { cat: 'energy', name: 'Reuters Energy',   url: 'https://news.google.com/rss/search?q=site:reuters.com+(oil+OR+gas+OR+energy+OR+OPEC)+when:3d&hl=en-US&gl=US&ceid=US:en' },
  { cat: 'energy', name: 'Mining & Resources', url: 'https://news.google.com/rss/search?q=(lithium+OR+"rare+earth"+OR+cobalt+OR+mining)+when:3d&hl=en-US&gl=US&ceid=US:en' },

  // === gov (Government) ===
  { cat: 'gov', name: 'White House',  url: 'https://news.google.com/rss/search?q=site:whitehouse.gov+OR+"White+House"+policy+when:3d&hl=en-US&gl=US&ceid=US:en' },
  { cat: 'gov', name: 'State Dept',   url: 'https://news.google.com/rss/search?q=("State+Department"+OR+"Secretary+of+State"+OR+diplomacy)+when:3d&hl=en-US&gl=US&ceid=US:en' },
  { cat: 'gov', name: 'Pentagon',     url: 'https://news.google.com/rss/search?q=(Pentagon+OR+"Defense+Department"+OR+"US+military")+when:3d&hl=en-US&gl=US&ceid=US:en' },
  { cat: 'gov', name: 'UN News',      url: 'https://news.un.org/feed/subscribe/en/news/all/rss.xml' },
  { cat: 'gov', name: 'Federal Reserve', url: 'https://news.google.com/rss/search?q=("Federal+Reserve"+OR+FOMC+OR+"interest+rates")+when:3d&hl=en-US&gl=US&ceid=US:en' },

  // === thinktanks ===
  { cat: 'thinktanks', name: 'Foreign Policy',   url: 'https://foreignpolicy.com/feed/' },
  { cat: 'thinktanks', name: 'Atlantic Council',  url: 'https://www.atlanticcouncil.org/feed/' },
  { cat: 'thinktanks', name: 'War on the Rocks',  url: 'https://warontherocks.com/feed/' },
  { cat: 'thinktanks', name: 'RAND',              url: 'https://news.google.com/rss/search?q=site:rand.org+when:14d&hl=en-US&gl=US&ceid=US:en' },
  { cat: 'thinktanks', name: 'Brookings',         url: 'https://news.google.com/rss/search?q=site:brookings.edu+when:14d&hl=en-US&gl=US&ceid=US:en' },
  { cat: 'thinktanks', name: 'Carnegie',          url: 'https://news.google.com/rss/search?q=site:carnegieendowment.org+when:14d&hl=en-US&gl=US&ceid=US:en' },
  { cat: 'thinktanks', name: 'CSIS',              url: 'https://news.google.com/rss/search?q=site:csis.org+when:14d&hl=en-US&gl=US&ceid=US:en' },
  { cat: 'thinktanks', name: 'Foreign Affairs',   url: 'https://www.foreignaffairs.com/rss.xml' },

  // === tech ===
  { cat: 'tech', name: 'Ars Technica',   url: 'https://feeds.arstechnica.com/arstechnica/technology-lab' },
  { cat: 'tech', name: 'The Verge',      url: 'https://www.theverge.com/rss/index.xml' },
  { cat: 'tech', name: 'MIT Tech Review', url: 'https://www.technologyreview.com/feed/' },
  { cat: 'tech', name: 'Hacker News',    url: 'https://news.ycombinator.com/rss' },
  { cat: 'tech', name: 'TechCrunch',     url: 'https://techcrunch.com/feed/' },

  // === ai ===
  { cat: 'ai', name: 'MIT Tech Review', url: 'https://www.technologyreview.com/topic/artificial-intelligence/feed' },
  { cat: 'ai', name: 'VentureBeat AI',  url: 'https://venturebeat.com/category/ai/feed/' },
  { cat: 'ai', name: 'The Verge AI',    url: 'https://news.google.com/rss/search?q=(artificial+intelligence+OR+LLM+OR+ChatGPT+OR+OpenAI)+when:2d&hl=en-US&gl=US&ceid=US:en' },
  { cat: 'ai', name: 'AI News',         url: 'https://news.google.com/rss/search?q=(AI+model+OR+"machine+learning"+OR+Anthropic+OR+Google+DeepMind)+when:2d&hl=en-US&gl=US&ceid=US:en' },

  // === finance ===
  { cat: 'finance', name: 'CNBC',          url: 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114' },
  { cat: 'finance', name: 'MarketWatch',   url: 'https://feeds.content.dowjones.io/public/rss/mw_topstories' },
  { cat: 'finance', name: 'Reuters Business', url: 'https://news.google.com/rss/search?q=site:reuters.com+(markets+OR+finance+OR+stocks+OR+economy)+when:2d&hl=en-US&gl=US&ceid=US:en' },
  { cat: 'finance', name: 'Financial Times', url: 'https://news.google.com/rss/search?q=site:ft.com+(markets+OR+economy+OR+finance)+when:2d&hl=en-US&gl=US&ceid=US:en' },
  { cat: 'finance', name: 'Yahoo Finance',  url: 'https://finance.yahoo.com/news/rss' },

  // === layoffs ===
  { cat: 'layoffs', name: 'TechCrunch Layoffs', url: 'https://techcrunch.com/tag/layoffs/feed/' },
  { cat: 'layoffs', name: 'Layoffs News',       url: 'https://news.google.com/rss/search?q=(layoffs+OR+"job+cuts"+OR+"workforce+reduction")+when:3d&hl=en-US&gl=US&ceid=US:en' },
  { cat: 'layoffs', name: 'Layoffs.fyi',        url: 'https://news.google.com/rss/search?q=(tech+layoffs+OR+company+layoffs+announced)+when:3d&hl=en-US&gl=US&ceid=US:en' },
];

async function fetchFeed(feed) {
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 10000);
    const res = await fetch(feed.url, {
      signal: ctrl.signal,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*'
      }
    });
    clearTimeout(timer);
    if (!res.ok) { console.log(`  SKIP ${feed.name}: HTTP ${res.status}`); return []; }
    const xml = await res.text();
    const items = parseRSS(xml, feed.name, feed.cat);
    console.log(`  OK  ${feed.name} (${feed.cat}): ${items.length} items`);
    return items;
  } catch (e) {
    console.log(`  ERR ${feed.name}: ${e.message?.substring(0,60)}`);
    return [];
  }
}

function parseRSS(xml, source, cat) {
  const items = [];
  let current = null, inItem = false, field = null;
  const parser = sax.parser(false, { lowercase: true });
  parser.onopentag = n => {
    if (n.name === 'item' || n.name === 'entry') { inItem = true; current = { source, cat }; }
    if (inItem) field = n.name;
  };
  parser.onclosetag = n => {
    if ((n === 'item' || n === 'entry') && current?.title) { items.push(current); current = null; inItem = false; }
    field = null;
  };
  parser.ontext = t => {
    if (!inItem || !current || !field) return;
    t = t.trim(); if (!t) return;
    if (field === 'title' && !current.title) current.title = t;
    if ((field === 'link' || field === 'guid') && !current.link && t.startsWith('http')) current.link = t;
    if ((field === 'pubdate' || field === 'published' || field === 'updated') && !current.publishedAt) {
      current.publishedAt = Date.parse(t) || Date.now();
    }
  };
  parser.onattrib = (name, val) => {
    if (inItem && field === 'link' && name === 'href' && !current?.link) {
      if (current) current.link = val;
    }
  };
  parser.oncdata = t => parser.ontext(t);
  try { parser.write(xml).close(); } catch {}
  return items.slice(0, 8);
}

async function redisSet(key, value, ttl) {
  const res = await fetch(`${REDIS_URL}/pipeline`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${REDIS_TOKEN}`, 'Content-Type': 'application/json' },
    body: `[["SET",${JSON.stringify(key)},${JSON.stringify(JSON.stringify(value))},"EX","${ttl}"]]`,
  });
  return res.ok;
}

async function main() {
  console.log('=== News Digest Seed ===');
  console.log(`Fetching ${FEEDS.length} RSS feeds...`);
  const results = await Promise.allSettled(FEEDS.map(fetchFeed));
  const allItems = results.flatMap(r => r.status === 'fulfilled' ? r.value : []);
  console.log(`\nTotal items fetched: ${allItems.length}`);

  const categories = {};
  for (const item of allItems) {
    if (!categories[item.cat]) categories[item.cat] = { items: [] };
    if (categories[item.cat].items.length < 20) {
      categories[item.cat].items.push({
        title: item.title,
        link: item.link || '',
        source: item.source,
        publishedAt: item.publishedAt || Date.now(),
        isAlert: false,
        importanceScore: 30,
        corroborationCount: 1,
        level: 'THREAT_LEVEL_UNSPECIFIED',
        category: item.cat,
      });
    }
  }

  console.log('\nCategory summary:');
  for (const [cat, bucket] of Object.entries(categories)) {
    const sources = [...new Set(bucket.items.map(i => i.source))];
    console.log(`  ${cat}: ${bucket.items.length} items from [${sources.join(', ')}]`);
  }

  const digest = { categories, generatedAt: new Date().toISOString(), feedStatuses: {} };
  const ok = await redisSet(DIGEST_KEY, digest, DIGEST_TTL);
  console.log(`\nRedis write (${DIGEST_KEY}): ${ok ? 'OK' : 'FAILED'}`);
  console.log('=== Done ===');
}

main().catch(e => { console.error(e); process.exit(1); });
