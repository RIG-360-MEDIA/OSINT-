// ROBIN-OSINT data-source proxy — self-contained, World-Monitor-independent.
// Holds secret API keys SERVER-SIDE (never shipped to the browser) and bypasses
// CORS for public sources. Zero dependencies (Node 18+ built-ins only). It reads
// keys from OUR OWN .env and calls each upstream directly — no WM code, no WM
// services, no WM hosting. Delete World Monitor and this keeps working.
import { createServer } from 'node:http';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const log = (m) => process.stdout.write(`[robin-osint proxy] ${m}\n`);

/** Minimal .env loader (no dotenv dependency). Does not overwrite real env. */
function loadEnv(path) {
  try {
    for (const line of readFileSync(path, 'utf8').split(/\r?\n/)) {
      const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
      if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^["']|["']$/g, '');
    }
  } catch { /* no .env file — rely on the real environment */ }
}
loadEnv(join(HERE, '..', '.env'));
loadEnv(join(HERE, '.env'));

const PORT = Number(process.env.PROXY_PORT || 8788);
const ORIGIN = process.env.PROXY_ALLOW_ORIGIN || '*';
const need = (k) => {
  const v = process.env[k];
  if (!v) throw new Error(`missing env ${k} — add it to night-desk/.env`);
  return v;
};

// Route registry. Keyless entries are proxied only to bypass CORS; keyed entries
// inject a secret from env. Add a source = add one line here.
const ROUTES = {
  // ── keyless (public) ──
  gdelt: { url: (qs) => `https://api.gdeltproject.org/api/v2/doc/doc?${qs}` },
  'gdelt-geo': { url: (qs) => `https://api.gdeltproject.org/api/v2/geo/geo?${qs}` },
  'usgs-quakes': { url: () => 'https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson' },
  worldbank: { url: (qs, sp) => `https://api.worldbank.org/v2/country/${sp.get('iso') || 'all'}/indicator/${sp.get('ind') || 'NY.GDP.MKTP.CD'}?format=json&per_page=400&${qs}` },
  reliefweb: { url: (qs) => `https://api.reliefweb.int/v1/reports?appname=${process.env.RELIEFWEB_APPNAME || 'robin-osint'}&${qs}` },
  ucdp: { url: (qs) => `https://ucdpapi.pcr.uu.se/api/gedevents/24.1?${qs}` },
  // ── keyed (secret injected server-side) ──
  firms: { url: (qs, sp) => `https://firms.modaps.eosdis.nasa.gov/api/area/csv/${need('NASA_FIRMS_API_KEY')}/${sp.get('src') || 'VIIRS_SNPP_NRT'}/${sp.get('area') || 'world'}/${sp.get('days') || '1'}` },
  openaq: { url: (qs) => `https://api.openaq.org/v3/locations?${qs}`, headers: () => ({ 'X-API-Key': need('OPENAQ_API_KEY') }) },
  'cloudflare-outages': { url: () => 'https://api.cloudflare.com/client/v4/radar/annotations/outages', headers: () => ({ Authorization: `Bearer ${need('CLOUDFLARE_API_TOKEN')}` }) },
};

function setCors(res) {
  res.setHeader('Access-Control-Allow-Origin', ORIGIN);
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
}
const readBody = (req) => new Promise((resolve) => { let b = ''; req.on('data', (c) => (b += c)); req.on('end', () => resolve(b)); });
const json = (res, code, obj) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(obj)); };

const server = createServer(async (req, res) => {
  setCors(res);
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }
  const u = new URL(req.url, `http://localhost:${PORT}`);
  if (u.pathname === '/health') return json(res, 200, { ok: true, routes: Object.keys(ROUTES) });

  const name = u.pathname.replace(/^\/api\//, '');
  const route = ROUTES[name];
  if (!route) return json(res, 404, { error: `unknown route '${name}'`, routes: Object.keys(ROUTES) });

  try {
    const sp = u.searchParams;
    const target = route.url(sp.toString(), sp);
    const init = { method: req.method, headers: route.headers ? route.headers() : {} };
    if (req.method === 'POST') { init.body = await readBody(req); init.headers['Content-Type'] = 'application/json'; }
    const upstream = await fetch(target, init);
    const text = await upstream.text();
    res.writeHead(upstream.status, { 'Content-Type': upstream.headers.get('content-type') || 'application/json' });
    res.end(text);
  } catch (e) {
    json(res, 502, { error: String((e && e.message) || e) });
  }
});

server.listen(PORT, () => log(`http://localhost:${PORT} · routes: ${Object.keys(ROUTES).join(', ')}`));
