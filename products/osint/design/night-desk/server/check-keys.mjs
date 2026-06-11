// ROBIN-OSINT — API key health check. Loads .env, pings each provider's auth
// endpoint, and reports OK/FAIL per key. NEVER prints key values. Zero deps.
//   run:  node server/check-keys.mjs
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
function loadEnv(p) {
  try {
    for (const l of readFileSync(p, 'utf8').split(/\r?\n/)) {
      const m = l.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
      if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^["']|["']$/g, '');
    }
  } catch { /* no .env */ }
}
loadEnv(join(HERE, '..', '.env'));
loadEnv(join(HERE, '.env'));
const E = (k) => process.env[k];

const TIMEOUT = 12000;
async function http(url, opts = {}) {
  const c = new AbortController();
  const t = setTimeout(() => c.abort(), TIMEOUT);
  try {
    const r = await fetch(url, { ...opts, signal: c.signal });
    return { status: r.status, body: await r.text() };
  } finally { clearTimeout(t); }
}

// Each check pings a cheap auth-validating endpoint. Returns {ok, detail}.
const CHECKS = [
  { key: 'NASA_FIRMS_API_KEY', name: 'NASA FIRMS', run: async (k) => { const r = await http(`https://firms.modaps.eosdis.nasa.gov/api/area/csv/${k}/VIIRS_SNPP_NRT/78,17,79,18/1`); const bad = /invalid/i.test(r.body); return { ok: r.status === 200 && !bad, detail: bad ? 'invalid MAP_KEY' : `HTTP ${r.status}` }; } },
  { key: 'OPENAQ_API_KEY', name: 'OpenAQ', run: async (k) => { const r = await http('https://api.openaq.org/v3/locations?limit=1', { headers: { 'X-API-Key': k } }); return { ok: r.status === 200, detail: `HTTP ${r.status}` }; } },
  { key: 'CLOUDFLARE_API_TOKEN', name: 'Cloudflare Radar', run: async (k) => { const r = await http('https://api.cloudflare.com/client/v4/radar/annotations/outages?limit=1', { headers: { Authorization: `Bearer ${k}` } }); let ok = false; try { ok = JSON.parse(r.body).success === true; } catch { ok = false; } return { ok, detail: `HTTP ${r.status}` }; } },
  { key: 'GROQ_API_KEY', name: 'Groq', run: async (k) => { const r = await http('https://api.groq.com/openai/v1/models', { headers: { Authorization: `Bearer ${k}` } }); return { ok: r.status === 200, detail: `HTTP ${r.status}` }; } },
  { key: 'OPENROUTER_API_KEY', name: 'OpenRouter', run: async (k) => { const r = await http('https://openrouter.ai/api/v1/auth/key', { headers: { Authorization: `Bearer ${k}` } }); return { ok: r.status === 200, detail: `HTTP ${r.status}` }; } },
  { key: 'FRED_API_KEY', name: 'FRED', run: async (k) => { const r = await http(`https://api.stlouisfed.org/fred/series?series_id=GNPCA&file_type=json&api_key=${k}`); return { ok: r.status === 200, detail: `HTTP ${r.status}` }; } },
  { key: 'EIA_API_KEY', name: 'EIA', run: async (k) => { const r = await http(`https://api.eia.gov/v2/?api_key=${k}`); return { ok: r.status === 200, detail: `HTTP ${r.status}` }; } },
  { key: 'FINNHUB_API_KEY', name: 'Finnhub', run: async (k) => { const r = await http(`https://finnhub.io/api/v1/quote?symbol=AAPL&token=${k}`); return { ok: r.status === 200 && !/limit|invalid/i.test(r.body), detail: `HTTP ${r.status}` }; } },
  { key: 'AVIATIONSTACK_API', name: 'AviationStack', run: async (k) => { const r = await http(`https://api.aviationstack.com/v1/flights?access_key=${k}&limit=1`); let ok = r.status === 200; try { if (JSON.parse(r.body).error) ok = false; } catch { /* keep */ } return { ok, detail: `HTTP ${r.status}` }; } },
  { key: 'OPENSKY_CLIENT_ID', name: 'OpenSky OAuth', run: async (k) => { const sec = E('OPENSKY_CLIENT_SECRET'); if (!sec) return { ok: false, detail: 'no client secret' }; const r = await http('https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: `grant_type=client_credentials&client_id=${encodeURIComponent(k)}&client_secret=${encodeURIComponent(sec)}` }); return { ok: r.status === 200, detail: `HTTP ${r.status}` }; } },
  { key: 'ACLED_ACCESS_TOKEN', name: 'ACLED', run: async (k) => { const r = await http('https://acleddata.com/api/acled/read?limit=1', { headers: { Authorization: `Bearer ${k}` } }); return { ok: r.status === 200, detail: `HTTP ${r.status} (verify token form)` }; } },
];

const present = CHECKS.filter((c) => E(c.key));
const absent = CHECKS.filter((c) => !E(c.key)).map((c) => c.key);
process.stdout.write(`\nROBIN-OSINT key health - ${present.length} configured, ${absent.length} not set\n${'-'.repeat(52)}\n`);

const results = await Promise.all(present.map(async (c) => {
  try { return { c, res: await c.run(E(c.key)) }; }
  catch (e) { return { c, res: { ok: false, detail: String((e && e.message) || e) } }; }
}));
for (const { c, res } of results) process.stdout.write(`${res.ok ? 'OK  ' : 'FAIL'}  ${c.name.padEnd(18)} ${res.detail || ''}\n`);
if (E('AISSTREAM_API_KEY')) process.stdout.write(`--    ${'AISStream'.padEnd(18)} stored; WebSocket - validated by the AIS layer at runtime\n`);
if (absent.length) process.stdout.write(`\nnot set (skipped): ${absent.join(', ')}\n`);
process.stdout.write('\n');
