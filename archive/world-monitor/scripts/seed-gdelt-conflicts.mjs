/**
 * seed-gdelt-conflicts.mjs
 *
 * Fetches GDELT v2 real-time 15-minute export files and extracts conflict
 * events (QuadClass=4 Material Conflict) to populate the ACLED conflict key.
 *
 * This supplements ACLED when ACLED's data lags behind the current date.
 * GDELT updates every 15 minutes with global events.
 *
 * Column layout (0-indexed, 61 cols in GDELT v2.1):
 *   1=SQLDATE, 6=Actor1Name, 16=Actor2Name, 26=EventCode,
 *   28=EventRootCode, 29=QuadClass, 30=GoldsteinScale,
 *   52=ActionGeo_FullName, 53=ActionGeo_CountryCode,
 *   56=ActionGeo_Lat, 57=ActionGeo_Long, 60=SOURCEURL
 */

import { inflateRaw } from 'zlib';
import { promisify } from 'util';
const inflateRawAsync = promisify(inflateRaw);

const REDIS_URL   = process.env.UPSTASH_REDIS_REST_URL   || 'http://localhost:8079';
const REDIS_TOKEN = process.env.UPSTASH_REDIS_REST_TOKEN || 'wm-local-token';

const ACLED_KEY       = 'conflict:acled:v1:all:0:0';
const ACLED_STALE_KEY = 'conflict:acled:v1:stale:all:0:0';
const TTL = 3 * 3600; // 3 hours

// QuadClass 4 = Material Conflict (actual violence/fighting)
// QuadClass 3 = Verbal Conflict  (threats/accusations — include for context)
const CONFLICT_QUAD = new Set(['3', '4']);

// Country code → ISO-2 (GDELT uses FIPS-like codes for some countries)
const FIPS_TO_ISO2 = {
  AS: 'AU', CH: 'CN', GM: 'DE', UP: 'UA', RS: 'RU', SY: 'SY',
  IZ: 'IQ', AF: 'AF', PK: 'PK', YM: 'YE', IS: 'IL', LE: 'LB',
  IR: 'IR', SU: 'SD', LY: 'LY', ML: 'ML', NI: 'NG', MZ: 'MZ',
  SF: 'ZA', ET: 'ET', KE: 'KE', TZ: 'TZ', CD: 'CD', CF: 'CF',
  SO: 'SO', MY: 'MM', TH: 'TH', VM: 'VN', BM: 'MM', ID: 'ID',
  PH: 'PH', MX: 'MX', CB: 'KH', MG: 'MG', EI: 'IE', UK: 'GB',
  FR: 'FR', SP: 'ES', IT: 'IT', PL: 'PL', GM: 'DE', TU: 'TR',
  IN: 'IN', BG: 'BG', RO: 'RO', HU: 'HU', EG: 'EG', MA: 'MA',
  MO: 'MA', TN: 'TN', AL: 'AL', GR: 'GR', CY: 'CY', JO: 'JO',
  SA: 'SA', KU: 'KW', BA: 'BH', QA: 'QA', TC: 'AE', OM: 'OM',
  BR: 'BR', AR: 'AR', CO: 'CO', VE: 'VE', PE: 'PE', CI: 'CL',
  CA: 'CA', US: 'US', JA: 'JP', KS: 'KR', KN: 'KP', TW: 'TW',
};

function toIso2(gdeltCode) {
  if (!gdeltCode) return '';
  if (gdeltCode.length === 2) return FIPS_TO_ISO2[gdeltCode] || gdeltCode;
  return gdeltCode.slice(0, 2);
}

// Generate GDELT file URL for a given timestamp
function gdeltUrl(date) {
  const y  = date.getUTCFullYear();
  const mo = String(date.getUTCMonth() + 1).padStart(2, '0');
  const d  = String(date.getUTCDate()).padStart(2, '0');
  const h  = String(date.getUTCHours()).padStart(2, '0');
  // Round minutes to nearest 15
  const m  = String(Math.floor(date.getUTCMinutes() / 15) * 15).padStart(2, '0');
  return `http://data.gdeltproject.org/gdeltv2/${y}${mo}${d}${h}${m}00.export.CSV.zip`;
}

async function downloadAndParse(url) {
  try {
    const resp = await fetch(url, { signal: AbortSignal.timeout(15_000) });
    if (!resp.ok) return [];
    const buf = Buffer.from(await resp.arrayBuffer());

    // Find ZIP local file header (PK\x03\x04)
    let offset = 0;
    while (offset < buf.length - 4) {
      if (buf[offset] === 0x50 && buf[offset+1] === 0x4B &&
          buf[offset+2] === 0x03 && buf[offset+3] === 0x04) {
        const fnLen    = buf.readUInt16LE(offset + 26);
        const extraLen = buf.readUInt16LE(offset + 28);
        const dataStart = offset + 30 + fnLen + extraLen;
        const compSize  = buf.readUInt32LE(offset + 18);
        const decompressed = await inflateRawAsync(buf.slice(dataStart, dataStart + compSize));
        const lines = decompressed.toString('utf8').trim().split('\n');

        const events = [];
        for (const line of lines) {
          const c = line.split('\t');
          if (c.length < 58) continue;
          if (!CONFLICT_QUAD.has(c[29])) continue;

          const lat = parseFloat(c[56]);
          const lon = parseFloat(c[57]);
          if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
          if (lat === 0 && lon === 0) continue;

          const dateStr = c[1]; // YYYYMMDD
          const occurredAt = dateStr.length === 8
            ? new Date(`${dateStr.slice(0,4)}-${dateStr.slice(4,6)}-${dateStr.slice(6,8)}T00:00:00Z`).getTime()
            : Date.now();

          events.push({
            id: `gdelt-${c[0]}`,
            eventType: parseFloat(c[30]) < 0 ? 'Battles' : 'Violence against civilians',
            country: c[52] || '',
            countryCode: toIso2(c[53]),
            location: { latitude: lat, longitude: lon },
            occurredAt,
            fatalities: 0,
            actors: [c[6], c[16]].filter(Boolean),
            source: c[60] ? new URL(c[60]).hostname.replace('www.', '') : 'GDELT',
            admin1: (c[52] || '').split(',')[1]?.trim() || '',
            goldstein: parseFloat(c[30]) || 0,
            quadClass: parseInt(c[29]) || 0,
          });
        }
        return events;
      }
      offset++;
    }
    return [];
  } catch {
    return [];
  }
}

async function redisSet(key, value, ttl) {
  const resp = await fetch(`${REDIS_URL}/pipeline`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${REDIS_TOKEN}`, 'Content-Type': 'application/json' },
    body: JSON.stringify([['SET', key, JSON.stringify(value), 'EX', String(ttl)]]),
  });
  return resp.ok;
}

async function main() {
  console.log('=== GDELT Conflict Seed ===');

  // Get latest file URL from GDELT
  const lastUpdateTxt = await fetch('http://data.gdeltproject.org/gdeltv2/lastupdate.txt')
    .then(r => r.text()).catch(() => '');
  const latestUrl = lastUpdateTxt.trim().split('\n')[0]?.split(' ')[2]?.trim();
  if (!latestUrl) throw new Error('Could not get GDELT lastupdate.txt');

  // Extract timestamp from URL
  const tsMatch = latestUrl.match(/(\d{14})\.export/);
  if (!tsMatch) throw new Error('Could not parse GDELT timestamp');
  const latestTs = new Date(
    `${tsMatch[1].slice(0,4)}-${tsMatch[1].slice(4,6)}-${tsMatch[1].slice(6,8)}T${tsMatch[1].slice(8,10)}:${tsMatch[1].slice(10,12)}:${tsMatch[1].slice(12,14)}Z`
  );

  // Build list: one file per 3 hours for the past 7 days = 56 files
  const urls = [];
  for (let i = 0; i < 56; i++) {
    const t = new Date(latestTs.getTime() - i * 3 * 60 * 60 * 1000);
    urls.push(gdeltUrl(t));
  }
  // Deduplicate
  const uniqueUrls = [...new Set(urls)];
  console.log(`Fetching ${uniqueUrls.length} GDELT files (7-day coverage, 3h intervals)...`);

  // Fetch in batches of 8
  const BATCH = 8;
  const allEvents = [];
  for (let i = 0; i < uniqueUrls.length; i += BATCH) {
    const batch = uniqueUrls.slice(i, i + BATCH);
    const results = await Promise.all(batch.map(downloadAndParse));
    results.forEach(evts => allEvents.push(...evts));
    process.stdout.write(`  Progress: ${Math.min(i + BATCH, uniqueUrls.length)}/${uniqueUrls.length} files, ${allEvents.length} events so far\r`);
    if (i + BATCH < uniqueUrls.length) await new Promise(r => setTimeout(r, 200));
  }

  console.log(`\nTotal conflict events: ${allEvents.length}`);

  // Deduplicate by id, keep material conflict (quad=4) over verbal
  const seen = new Map();
  for (const e of allEvents) {
    const existing = seen.get(e.id);
    if (!existing || e.quadClass > existing.quadClass) seen.set(e.id, e);
  }
  const deduped = [...seen.values()];

  // Sort by most recent, take top 1000
  deduped.sort((a, b) => b.occurredAt - a.occurredAt);
  const final = deduped.slice(0, 1000);
  console.log(`Deduplicated: ${final.length} unique events`);

  // Show date range
  if (final.length > 0) {
    const oldest = new Date(final[final.length - 1].occurredAt).toISOString().slice(0, 10);
    const newest = new Date(final[0].occurredAt).toISOString().slice(0, 10);
    console.log(`Date range: ${oldest} → ${newest}`);

    // Top countries
    const countryCounts = {};
    final.forEach(e => { countryCounts[e.countryCode] = (countryCounts[e.countryCode] || 0) + 1; });
    const topCountries = Object.entries(countryCounts).sort((a,b)=>b[1]-a[1]).slice(0,8).map(([k,v])=>`${k}:${v}`).join(', ');
    console.log(`Top countries: ${topCountries}`);
  }

  const payload = { events: final, clusters: [], generatedAt: Date.now() };

  const ok1 = await redisSet(ACLED_KEY, payload, TTL);
  const ok2 = await redisSet(ACLED_STALE_KEY, payload, TTL * 4);
  console.log(`Redis write: live=${ok1 ? 'OK' : 'FAIL'} stale=${ok2 ? 'OK' : 'FAIL'}`);
  console.log(`=== Done — ${final.length} conflict events seeded ===`);
}

main().catch(e => { console.error(e); process.exit(1); });
