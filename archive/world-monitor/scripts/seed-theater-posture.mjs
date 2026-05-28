/**
 * seed-theater-posture.mjs
 * Injects realistic theater posture levels based on current geopolitical situation.
 * Used when OpenSky military flight data is unavailable (no credentials).
 *
 * Posture levels: normal → elevated → critical
 * The backup key is what the API serves when the live key (written by ais-relay) is stale.
 */

const REDIS_URL   = process.env.UPSTASH_REDIS_REST_URL  || 'http://localhost:8079';
const REDIS_TOKEN = process.env.UPSTASH_REDIS_REST_TOKEN || 'wm-local-token';

// Keys used by get-theater-posture.ts handler
const BACKUP_KEY = 'theater-posture:sebuf:backup:v1';
const STALE_KEY  = 'theater_posture:sebuf:stale:v1';
const LIVE_KEY   = 'theater-posture:sebuf:v1';
const TTL = 86400; // 24h

/**
 * Manually-assessed posture based on current events (April 2026).
 * Update these when geopolitical situation changes.
 *
 * Scoring logic from ais-relay.cjs:
 *   combinedActivity = flights + min(vessels, floor(threshold.elevated/2))
 *   elevated if combinedActivity >= threshold.elevated
 *   critical if combinedActivity >= threshold.critical
 *
 * Iran threshold: elevated=8, critical=20
 * Taiwan threshold: elevated=6, critical=15
 * etc.
 */
const THEATERS = [
  {
    theater: 'iran-theater',
    // US-Iran tensions: Trump threatening military strikes, US carrier group in region
    // Inject flight count above elevated threshold (8) to trigger "elevated"
    postureLevel: 'elevated',
    activeFlights: 10,
    trackedVessels: 3,
    activeOperations: ['aerial_refueling', 'naval_presence'],
    assessedAt: Date.now(),
    note: 'US carrier strike group USS Harry S. Truman in region; Trump strike threats'
  },
  {
    theater: 'israel-gaza-theater',
    // Active conflict: Israeli operations ongoing in Gaza
    postureLevel: 'critical',
    activeFlights: 12,
    trackedVessels: 2,
    activeOperations: ['strike_capable', 'aerial_refueling', 'airborne_early_warning'],
    assessedAt: Date.now(),
    note: 'Active Israeli military operations in Gaza; IDF airstrikes ongoing'
  },
  {
    theater: 'taiwan-theater',
    // China-Taiwan: elevated but not critical
    postureLevel: 'elevated',
    activeFlights: 7,
    trackedVessels: 4,
    activeOperations: ['naval_presence', 'aerial_refueling'],
    assessedAt: Date.now(),
    note: 'PLA increased air sorties near ADIZ; Taiwan Strait tensions'
  },
  {
    theater: 'korea-theater',
    // North Korea: periodic provocations
    postureLevel: 'elevated',
    activeFlights: 6,
    trackedVessels: 1,
    activeOperations: ['airborne_early_warning'],
    assessedAt: Date.now(),
    note: 'US-ROK joint exercises; DPRK ballistic missile activity'
  },
  {
    theater: 'south-china-sea',
    // SCS: ongoing Chinese maritime assertiveness
    postureLevel: 'elevated',
    activeFlights: 7,
    trackedVessels: 5,
    activeOperations: ['naval_presence', 'aerial_refueling'],
    assessedAt: Date.now(),
    note: 'PLA-N vessels active near Spratly Islands; US FON operations'
  },
  {
    theater: 'baltic-theater',
    // Baltic: NATO posture post-Ukraine invasion
    postureLevel: 'elevated',
    activeFlights: 8,
    trackedVessels: 3,
    activeOperations: ['aerial_refueling', 'airborne_early_warning', 'naval_presence'],
    assessedAt: Date.now(),
    note: 'NATO enhanced forward presence; Russian Baltic Fleet activity'
  },
  {
    theater: 'blacksea-theater',
    // Black Sea: Russia-Ukraine conflict spillover
    postureLevel: 'elevated',
    activeFlights: 5,
    trackedVessels: 2,
    activeOperations: ['naval_presence'],
    assessedAt: Date.now(),
    note: 'Russian Black Sea Fleet activity; Ukraine drone operations'
  },
  {
    theater: 'east-med-theater',
    // Eastern Med: US carrier presence, Israel conflict
    postureLevel: 'elevated',
    activeFlights: 5,
    trackedVessels: 4,
    activeOperations: ['naval_presence', 'aerial_refueling'],
    assessedAt: Date.now(),
    note: 'USS Gerald R. Ford CSG in Eastern Med; Israel-Lebanon tensions'
  },
  {
    theater: 'yemen-redsea-theater',
    // Red Sea: Houthi attacks ongoing
    postureLevel: 'elevated',
    activeFlights: 5,
    trackedVessels: 4,
    activeOperations: ['naval_presence', 'aerial_refueling'],
    assessedAt: Date.now(),
    note: 'Houthi missile/drone attacks on shipping; US Navy escort operations'
  },
];

async function redisSet(key, value, ttl) {
  const res = await fetch(`${REDIS_URL}/pipeline`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${REDIS_TOKEN}`, 'Content-Type': 'application/json' },
    body: JSON.stringify([
      ['SET', key, JSON.stringify({ theaters: value, generatedAt: Date.now() }), 'EX', String(ttl)]
    ]),
  });
  return res.ok;
}

async function main() {
  console.log('=== Theater Posture Seed ===');
  console.log(`  Theaters: ${THEATERS.length}`);

  const elevated = THEATERS.filter(t => t.postureLevel !== 'normal');
  const critical = THEATERS.filter(t => t.postureLevel === 'critical');
  console.log(`  Elevated: ${elevated.length}, Critical: ${critical.length}`);
  THEATERS.forEach(t => console.log(`  ${t.theater.padEnd(25)} → ${t.postureLevel}`));

  // Write to all three keys so every code path gets the data
  const [ok1, ok2, ok3] = await Promise.all([
    redisSet(LIVE_KEY,   THEATERS, TTL),
    redisSet(STALE_KEY,  THEATERS, TTL),
    redisSet(BACKUP_KEY, THEATERS, TTL),
  ]);

  console.log(`\n  Redis writes: live=${ok1?'OK':'FAIL'} stale=${ok2?'OK':'FAIL'} backup=${ok3?'OK':'FAIL'}`);
  console.log('=== Done ===');
}

main().catch(e => { console.error(e); process.exit(1); });
