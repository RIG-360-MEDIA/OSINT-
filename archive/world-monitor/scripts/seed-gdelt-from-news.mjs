/**
 * seed-gdelt-from-news.mjs
 * Seeds the GDELT intel key using articles from our news digest
 * when the GDELT API is rate-limited or unreachable.
 * Format mirrors what seed-gdelt-intel.mjs writes.
 */

const REDIS_URL   = process.env.UPSTASH_REDIS_REST_URL  || 'http://localhost:8079';
const REDIS_TOKEN = process.env.UPSTASH_REDIS_REST_TOKEN || 'wm-local-token';
const CANONICAL_KEY = 'intelligence:gdelt-intel:v1';
const DIGEST_KEY    = 'news:digest:v1:full:en';
const TTL = 86400;

const TOPIC_KEYWORDS = {
  military:  ['military','troop','airstrike','drone','missile','soldier','army','navy','air force','tank','warship','submarine','fighter jet','pentagon','nato','defense','weapon','bomb','strike','combat','war','battle','invasion','siege'],
  cyber:     ['cyber','hack','ransomware','malware','data breach','phishing','APT','vulnerability','exploit','zero-day','security breach','DDoS','trojan','spyware','infosec'],
  nuclear:   ['nuclear','uranium','IAEA','enrichment','plutonium','reactor','warhead','proliferation','atomic','radioactive','radiation','bomb'],
  conflict:  ['conflict','attack','killed','casualties','fighting','clashes','offensive','ceasefire','hostage','insurgent','rebel','militia'],
  sanctions: ['sanctions','embargo','tariff','trade war','export ban','blacklist','freeze assets'],
  economic:  ['inflation','recession','GDP','central bank','interest rate','market crash','unemployment','trade deficit','IMF','World Bank'],
};

async function redisGet(key) {
  const res = await fetch(`${REDIS_URL}/get/${encodeURIComponent(key)}`, {
    headers: { Authorization: `Bearer ${REDIS_TOKEN}` }
  });
  const data = await res.json();
  try { return JSON.parse(data.result); } catch { return data.result; }
}

async function redisSet(key, value, ttl) {
  const body = `[["SET","${key}",${JSON.stringify(JSON.stringify(value))},"EX","${ttl}"]]`;
  const res = await fetch(`${REDIS_URL}/pipeline`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${REDIS_TOKEN}`, 'Content-Type': 'application/json' },
    body,
  });
  return res.ok;
}

function classifyItem(title) {
  const lower = (title || '').toLowerCase();
  for (const [topic, kws] of Object.entries(TOPIC_KEYWORDS)) {
    if (kws.some(kw => lower.includes(kw))) return topic;
  }
  return null;
}

function toGdeltArticle(item) {
  return {
    title: item.title || item.headline || '',
    url: item.link || item.url || '',
    source: item.source || '',
    date: item.publishedAt ? new Date(item.publishedAt).toISOString().replace(/[-:T]/g,'').slice(0,14) : '',
    language: 'English',
  };
}

async function main() {
  console.log('=== GDELT Intel Seed (from news digest) ===');

  const digest = await redisGet(DIGEST_KEY);
  if (!digest) { console.error('  No news digest found — run seed-news-digest.mjs first'); process.exit(1); }

  // Extract all items
  let items = [];
  if (Array.isArray(digest)) {
    items = digest;
  } else if (digest.categories) {
    for (const bucket of Object.values(digest.categories)) {
      if (Array.isArray(bucket.items)) items.push(...bucket.items);
    }
  }

  console.log(`  News items available: ${items.length}`);

  // Classify items into topics
  const topicMap = {};
  for (const item of items) {
    const topic = classifyItem(item.title || item.headline || '');
    if (topic) {
      if (!topicMap[topic]) topicMap[topic] = [];
      topicMap[topic].push(toGdeltArticle(item));
    }
  }

  // Ensure all required topics exist (even if empty)
  const requiredTopics = ['military', 'cyber', 'nuclear', 'conflict', 'sanctions', 'economic'];
  const fetchedAt = new Date().toISOString();

  const topics = requiredTopics.map(id => ({
    id,
    articles: (topicMap[id] || []).slice(0, 10),
    fetchedAt,
  }));

  for (const t of topics) {
    console.log(`  ${t.id}: ${t.articles.length} articles`);
  }

  const populated = topics.filter(t => t.articles.length > 0);
  if (populated.length < 1) { console.error('  No articles classified — check news digest'); process.exit(1); }

  const payload = { topics, fetchedAt };
  const ok = await redisSet(CANONICAL_KEY, payload, TTL);
  console.log(`  Redis write: ${ok ? 'OK' : 'FAILED'}`);
  console.log('=== Done ===');
}

main().catch(e => { console.error(e); process.exit(1); });
