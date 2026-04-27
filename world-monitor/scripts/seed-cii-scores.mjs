/**
 * seed-cii-scores.mjs
 * Seeds realistic Country Instability Index (CII) scores into Redis.
 *
 * Why this is needed:
 *   StrategicPosturePanel calls recalcPostureWithVessels() which overwrites the
 *   seeded theater posture using Math.max(airLevel, navalLevel, ciiLevel).
 *   With no ACLED/UCDP event data, Iran CII ≈ 16 (below 70 threshold) → NORM.
 *
 *   ciiLevel: cii >= 85 → 2 (critical), cii >= 70 → 1 (elevated), else 0 (normal)
 *
 * Key: risk:scores:sebuf:stale:v1
 * Shape: { ciiScores: CiiScore[], strategicRisks: StrategicRisk[] }
 */

const REDIS_URL   = process.env.UPSTASH_REDIS_REST_URL  || 'http://localhost:8079';
const REDIS_TOKEN = process.env.UPSTASH_REDIS_REST_TOKEN || 'wm-local-token';
const RISK_KEY    = 'risk:scores:sebuf:stale:v1';
const TTL         = 86400; // 24h

/**
 * CII scores assessed for April 2026 geopolitical situation.
 * Thresholds (from military-surge.ts):
 *   ciiLevel = cii >= 85 ? 2 (critical) : cii >= 70 ? 1 (elevated) : 0 (normal)
 *
 * Theater → country mapping (from recalcPostureWithVessels theaterMap):
 *   iran-theater       → IR
 *   israel-gaza-theater→ IL
 *   taiwan-theater     → TW
 *   korea-theater      → KP
 *   south-china-sea    → CN
 *   baltic-theater     → RU (covers NATO-Russia)
 *   blacksea-theater   → UA
 *   east-med-theater   → SY / LB
 *   yemen-redsea-theater → YE
 */
const NOW = Date.now();

const CII_SCORES = [
  // === CRITICAL (≥85) ===
  {
    // Gaza theater uses 'PS' (Palestinian Territories) per TARGET_NATION_CODES in military-surge.ts
    region: 'PS',
    staticBaseline: 75,
    dynamicScore: 98,
    combinedScore: 90,
    trend: 'TREND_WORSENING',
    computedAt: NOW,
  },
  {
    region: 'IL', // Israel — separate entry for map choropleth
    staticBaseline: 55,
    dynamicScore: 88,
    combinedScore: 78,
    trend: 'TREND_WORSENING',
    computedAt: NOW,
  },
  {
    region: 'UA', // Ukraine — ongoing war
    staticBaseline: 60,
    dynamicScore: 94,
    combinedScore: 87,
    trend: 'TREND_WORSENING',
    computedAt: NOW,
  },
  {
    region: 'YE', // Yemen — Houthi conflict
    staticBaseline: 70,
    dynamicScore: 88,
    combinedScore: 85,
    trend: 'TREND_STABLE',
    computedAt: NOW,
  },

  // === ELEVATED (≥70) ===
  {
    region: 'IR', // Iran — US strike threats, carrier group in region
    staticBaseline: 40,
    dynamicScore: 85,
    combinedScore: 78,
    trend: 'TREND_WORSENING',
    computedAt: NOW,
  },
  {
    region: 'TW', // Taiwan — PLA ADIZ incursions
    staticBaseline: 45,
    dynamicScore: 78,
    combinedScore: 72,
    trend: 'TREND_WORSENING',
    computedAt: NOW,
  },
  {
    region: 'KP', // North Korea — ballistic missile tests
    staticBaseline: 70,
    dynamicScore: 72,
    combinedScore: 75,
    trend: 'TREND_STABLE',
    computedAt: NOW,
  },
  {
    region: 'CN', // China — SCS assertiveness
    staticBaseline: 30,
    dynamicScore: 72,
    combinedScore: 70,
    trend: 'TREND_WORSENING',
    computedAt: NOW,
  },
  {
    region: 'RU', // Russia — Ukraine war + Baltic provocations
    staticBaseline: 45,
    dynamicScore: 82,
    combinedScore: 76,
    trend: 'TREND_STABLE',
    computedAt: NOW,
  },
  {
    region: 'SY', // Syria — ongoing instability, E-Med tensions
    staticBaseline: 75,
    dynamicScore: 68,
    combinedScore: 71,
    trend: 'TREND_IMPROVING',
    computedAt: NOW,
  },
  {
    region: 'LB', // Lebanon — Israel-Lebanon spillover
    staticBaseline: 60,
    dynamicScore: 74,
    combinedScore: 70,
    trend: 'TREND_STABLE',
    computedAt: NOW,
  },
  {
    region: 'SD', // Sudan — civil war ongoing
    staticBaseline: 65,
    dynamicScore: 80,
    combinedScore: 74,
    trend: 'TREND_WORSENING',
    computedAt: NOW,
  },
  {
    region: 'MM', // Myanmar — coup aftermath
    staticBaseline: 55,
    dynamicScore: 74,
    combinedScore: 70,
    trend: 'TREND_STABLE',
    computedAt: NOW,
  },

  // === NORMAL but notable (<70) ===
  {
    region: 'PK', // Pakistan — domestic instability
    staticBaseline: 50,
    dynamicScore: 62,
    combinedScore: 58,
    trend: 'TREND_STABLE',
    computedAt: NOW,
  },
  {
    region: 'AF', // Afghanistan — Taliban control
    staticBaseline: 65,
    dynamicScore: 58,
    combinedScore: 62,
    trend: 'TREND_IMPROVING',
    computedAt: NOW,
  },
  {
    region: 'IQ', // Iraq — militia activity
    staticBaseline: 55,
    dynamicScore: 60,
    combinedScore: 58,
    trend: 'TREND_STABLE',
    computedAt: NOW,
  },
  {
    region: 'LY', // Libya — political fragmentation
    staticBaseline: 60,
    dynamicScore: 55,
    combinedScore: 57,
    trend: 'TREND_STABLE',
    computedAt: NOW,
  },
  {
    region: 'SO', // Somalia — al-Shabaab activity
    staticBaseline: 65,
    dynamicScore: 60,
    combinedScore: 62,
    trend: 'TREND_STABLE',
    computedAt: NOW,
  },
  {
    region: 'ML', // Mali — Sahel instability
    staticBaseline: 60,
    dynamicScore: 62,
    combinedScore: 61,
    trend: 'TREND_WORSENING',
    computedAt: NOW,
  },
  {
    region: 'VE', // Venezuela — political/economic crisis
    staticBaseline: 55,
    dynamicScore: 58,
    combinedScore: 57,
    trend: 'TREND_STABLE',
    computedAt: NOW,
  },
];

/**
 * Strategic risks companion data (used by StrategicRisksPanel).
 * These map to theater regions shown in the UI.
 */
const STRATEGIC_RISKS = [
  {
    id: 'iran-nuclear-escalation',
    title: 'Iran Nuclear Escalation',
    region: 'IR',
    level: 'HIGH',
    probability: 0.35,
    timeframe: 'NEAR_TERM',
    description: 'US-Iran nuclear negotiations stalled; Trump threatening military strikes; USS Harry S. Truman CSG in Arabian Sea',
    updatedAt: NOW,
  },
  {
    id: 'israel-gaza-regional-war',
    title: 'Israel-Gaza Regional Spillover',
    region: 'IL',
    level: 'CRITICAL',
    probability: 0.55,
    timeframe: 'IMMEDIATE',
    description: 'Active IDF operations in Gaza; Hezbollah cross-border exchanges; Iran proxy network activation risk',
    updatedAt: NOW,
  },
  {
    id: 'taiwan-strait-crisis',
    title: 'Taiwan Strait Military Crisis',
    region: 'TW',
    level: 'HIGH',
    probability: 0.25,
    timeframe: 'MEDIUM_TERM',
    description: 'PLA increased ADIZ incursions; Xi-Taiwan rhetoric hardening; US arms sales tensions',
    updatedAt: NOW,
  },
  {
    id: 'ukraine-war-escalation',
    title: 'Ukraine War Escalation',
    region: 'UA',
    level: 'CRITICAL',
    probability: 0.60,
    timeframe: 'IMMEDIATE',
    description: 'Russian offensive ongoing; NATO Article 5 discussions; Ukrainian drone strikes on Russian territory',
    updatedAt: NOW,
  },
  {
    id: 'north-korea-provocation',
    title: 'DPRK Ballistic Missile Provocation',
    region: 'KP',
    level: 'HIGH',
    probability: 0.45,
    timeframe: 'NEAR_TERM',
    description: 'ICBM tests resumed; US-ROK joint exercises ongoing; Kim-Russia military cooperation',
    updatedAt: NOW,
  },
  {
    id: 'scs-naval-clash',
    title: 'South China Sea Naval Incident',
    region: 'CN',
    level: 'HIGH',
    probability: 0.30,
    timeframe: 'NEAR_TERM',
    description: 'PLA-N vessels aggressive near Spratly Islands; US FON operations; Philippines coast guard incidents',
    updatedAt: NOW,
  },
  {
    id: 'houthi-red-sea',
    title: 'Houthi Red Sea Shipping Threat',
    region: 'YE',
    level: 'HIGH',
    probability: 0.70,
    timeframe: 'IMMEDIATE',
    description: 'Houthi missile/drone attacks on commercial shipping; US Navy escort operations; Suez Canal diversion costs',
    updatedAt: NOW,
  },
];

async function redisSet(key, value, ttl) {
  const body = JSON.stringify([
    ['SET', key, JSON.stringify(value), 'EX', String(ttl)]
  ]);
  const res = await fetch(`${REDIS_URL}/pipeline`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${REDIS_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    console.error(`  Redis error ${res.status}: ${text.substring(0, 120)}`);
  }
  return res.ok;
}

async function main() {
  console.log('=== CII Scores Seed ===');

  const critical = CII_SCORES.filter(s => s.combinedScore >= 85);
  const elevated = CII_SCORES.filter(s => s.combinedScore >= 70 && s.combinedScore < 85);
  const normal   = CII_SCORES.filter(s => s.combinedScore < 70);

  console.log(`  Regions: ${CII_SCORES.length} total`);
  console.log(`  Critical (≥85): ${critical.map(s => s.region).join(', ')}`);
  console.log(`  Elevated (≥70): ${elevated.map(s => s.region).join(', ')}`);
  console.log(`  Normal   (<70): ${normal.map(s => s.region).join(', ')}`);
  console.log(`  Strategic risks: ${STRATEGIC_RISKS.length}`);

  const payload = {
    ciiScores: CII_SCORES,
    strategicRisks: STRATEGIC_RISKS,
    generatedAt: new Date().toISOString(),
    source: 'seed-cii-scores.mjs',
  };

  // Write to both live and stale keys so every code path gets data
  const LIVE_KEY  = 'risk:scores:sebuf:v1';
  const STALE_KEY = 'risk:scores:sebuf:stale:v1';

  const [ok1, ok2] = await Promise.all([
    redisSet(LIVE_KEY,  payload, TTL),
    redisSet(STALE_KEY, payload, TTL),
  ]);

  console.log(`\n  Redis writes: live=${ok1 ? 'OK' : 'FAIL'} stale=${ok2 ? 'OK' : 'FAIL'}`);

  if (ok1 || ok2) {
    console.log('\n  Expected theater posture after client recalc:');
    console.log('    iran-theater        → ELEVATED (IR score 78 ≥ 70)');
    console.log('    israel-gaza-theater → CRITICAL  (PS score 90 ≥ 85)');
    console.log('    taiwan-theater      → ELEVATED (TW score 72 ≥ 70)');
    console.log('    korea-theater       → ELEVATED (KP score 75 ≥ 70)');
    console.log('    south-china-sea     → ELEVATED (CN score 70 ≥ 70)');
    console.log('    baltic-theater      → ELEVATED (RU score 76 ≥ 70)');
    console.log('    blacksea-theater    → CRITICAL  (UA score 87 ≥ 85)');
    console.log('    east-med-theater    → ELEVATED (SY/LB scores ≥ 70)');
    console.log('    yemen-redsea-theater→ CRITICAL  (YE score 85 ≥ 85)');
  }

  console.log('=== Done ===');
}

main().catch(e => { console.error(e); process.exit(1); });
