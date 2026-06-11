// ============================================================================
// TELANGANA MAP DATA — real, from the Hetzner DB (2026-06-02), 47-day window.
//   coverage = distinct articles mentioning the district (article_districts)
//   sup / crit = stance rows (article_stances) on those articles
//   lon/lat   = district centroid (districts.centroid_*)
// Keyed by the GeoJSON `properties.district` name so it joins to the 33-district
// Telangana TopoJSON. Two DB rows map to the Warangal split: WARANGAL→Rural,
// HANUMAKONDA→Urban. Stance is article_stances (NOT register_emotion).
// ============================================================================

export const DISTRICT_DATA = {
  Hyderabad: { coverage: 10618, sup: 4079, crit: 2990, lon: 78.4815, lat: 17.4199 },
  Adilabad: { coverage: 1160, sup: 491, crit: 268, lon: 78.5208, lat: 19.65 },
  Karimnagar: { coverage: 1079, sup: 424, crit: 292, lon: 79.3094, lat: 18.3712 },
  Nizamabad: { coverage: 1045, sup: 421, crit: 226, lon: 78.2313, lat: 18.7434 },
  'Komaram Bheem': { coverage: 999, sup: 446, crit: 227, lon: 79.4881, lat: 19.4419 },
  Nalgonda: { coverage: 848, sup: 206, crit: 200, lon: 78.9845, lat: 16.7468 },
  'Ranga Reddy': { coverage: 417, sup: 167, crit: 106, lon: 78.4228, lat: 17.2171 },
  Khammam: { coverage: 392, sup: 133, crit: 127, lon: 80.354, lat: 17.1083 },
  'Medchal Malkajgiri': { coverage: 347, sup: 131, crit: 73, lon: 78.5469, lat: 17.5246 },
  'Warangal Rural': { coverage: 337, sup: 119, crit: 110, lon: 79.7103, lat: 18.0056 },
  Siddipet: { coverage: 273, sup: 111, crit: 110, lon: 78.8117, lat: 17.9742 },
  Medak: { coverage: 256, sup: 83, crit: 91, lon: 78.2713, lat: 18.0476 },
  'Bhadradri Kothagudem': { coverage: 217, sup: 64, crit: 59, lon: 80.9024, lat: 17.9869 },
  Nirmal: { coverage: 204, sup: 67, crit: 35, lon: 78.1232, lat: 19.0923 },
  Mahabubnagar: { coverage: 196, sup: 69, crit: 72, lon: 77.8591, lat: 16.7381 },
  Sangareddy: { coverage: 186, sup: 55, crit: 63, lon: 77.797, lat: 17.7981 },
  Suryapet: { coverage: 174, sup: 53, crit: 39, lon: 79.8117, lat: 17.1237 },
  Mancherial: { coverage: 136, sup: 34, crit: 40, lon: 79.5549, lat: 18.9369 },
  'Warangal Urban': { coverage: 136, sup: 47, crit: 28, lon: 79.5128, lat: 18.0603 },
  Peddapalli: { coverage: 133, sup: 58, crit: 42, lon: 79.5228, lat: 18.6707 },
  Nagarkurnool: { coverage: 120, sup: 32, crit: 19, lon: 78.6923, lat: 16.3665 },
  'Rajanna Sircilla': { coverage: 117, sup: 37, crit: 26, lon: 78.703, lat: 18.3805 },
  'Yadadri Bhuvanagiri': { coverage: 111, sup: 32, crit: 34, lon: 78.9498, lat: 17.4932 },
  Mahabubabad: { coverage: 90, sup: 18, crit: 9, lon: 79.9691, lat: 17.5453 },
  Kamareddy: { coverage: 87, sup: 28, crit: 9, lon: 77.9751, lat: 18.2898 },
  'Jayashankar Bhupalapally': { coverage: 86, sup: 24, crit: 15, lon: 79.9478, lat: 18.5146 },
  Vikarabad: { coverage: 85, sup: 24, crit: 14, lon: 77.6903, lat: 17.2858 },
  Mulugu: { coverage: 82, sup: 13, crit: 5, lon: 80.2927, lat: 18.2904 },
  Jagtial: { coverage: 68, sup: 18, crit: 14, lon: 78.8464, lat: 18.8862 },
  'Jogulamba Gadwal': { coverage: 56, sup: 17, crit: 9, lon: 77.739, lat: 16.037 },
  Jangaon: { coverage: 41, sup: 14, crit: 9, lon: 79.2787, lat: 17.7601 },
  Narayanpet: { coverage: 39, sup: 10, crit: 5, lon: 77.5229, lat: 16.6334 },
  Wanaparthy: { coverage: 39, sup: 9, crit: 7, lon: 78.0792, lat: 16.2358 },
};

export const MAX_COVERAGE = 10618;

// Camera opens framed on Telangana, tilted into 3D.
export const INITIAL_VIEW = { longitude: 79.1, latitude: 17.75, zoom: 6.35, pitch: 48, bearing: -14 };

// Real district co-mention pairs → narrative-spread arcs (top 18 by shared stories).
const ARC_PAIRS = [
  ['Adilabad', 'Komaram Bheem', 918],
  ['Adilabad', 'Nizamabad', 836],
  ['Komaram Bheem', 'Nizamabad', 816],
  ['Karimnagar', 'Nizamabad', 596],
  ['Adilabad', 'Karimnagar', 583],
  ['Karimnagar', 'Komaram Bheem', 573],
  ['Hyderabad', 'Ranga Reddy', 316],
  ['Hyderabad', 'Karimnagar', 290],
  ['Hyderabad', 'Medchal Malkajgiri', 257],
  ['Hyderabad', 'Nizamabad', 243],
  ['Adilabad', 'Hyderabad', 239],
  ['Hyderabad', 'Khammam', 200],
  ['Hyderabad', 'Nalgonda', 196],
  ['Hyderabad', 'Warangal Rural', 178],
  ['Medchal Malkajgiri', 'Ranga Reddy', 171],
  ['Hyderabad', 'Komaram Bheem', 157],
  ['Hyderabad', 'Medak', 127],
  ['Hyderabad', 'Mahabubnagar', 124],
];

export const ARCS = ARC_PAIRS.map(([a, b, n]) => ({
  a, b, n,
  from: [DISTRICT_DATA[a].lon, DISTRICT_DATA[a].lat],
  to: [DISTRICT_DATA[b].lon, DISTRICT_DATA[b].lat],
}));

// ── Extra real per-district metrics (2026-06-02 sweep) ───────────────────────
// Raw objects are keyed by DB UPPERCASE district name; mapped to GeoJSON names.
const ISSUE_RAW = { "ADILABAD": { "AGRICULTURE": 90, "FINANCE": 6, "GOVERNANCE": 19, "HEALTH": 29, "INFRASTRUCTURE": 33, "LEGAL": 21, "POLITICS": 163, "SECURITY": 39 }, "BHADRADRI": { "AGRICULTURE": 9, "FINANCE": 4, "GOVERNANCE": 6, "HEALTH": 13, "INFRASTRUCTURE": 13, "LEGAL": 17, "POLITICS": 39, "SECURITY": 16 }, "HANUMAKONDA": { "AGRICULTURE": 4, "FINANCE": 2, "GOVERNANCE": 5, "HEALTH": 11, "INFRASTRUCTURE": 4, "LEGAL": 14, "POLITICS": 16, "SECURITY": 9 }, "HYDERABAD": { "AGRICULTURE": 171, "FINANCE": 209, "GOVERNANCE": 248, "HEALTH": 367, "INFRASTRUCTURE": 365, "LEGAL": 827, "POLITICS": 1644, "SECURITY": 1039 }, "JAGTIAL": { "AGRICULTURE": 7, "FINANCE": 1, "GOVERNANCE": 5, "HEALTH": 2, "LEGAL": 3, "POLITICS": 12, "SECURITY": 1 }, "JANGAON": { "AGRICULTURE": 2, "FINANCE": 1, "GOVERNANCE": 3, "HEALTH": 2, "INFRASTRUCTURE": 1, "LEGAL": 3, "POLITICS": 7, "SECURITY": 2 }, "JAYASHANKAR": { "AGRICULTURE": 7, "FINANCE": 1, "GOVERNANCE": 2, "HEALTH": 6, "INFRASTRUCTURE": 1, "LEGAL": 7, "POLITICS": 20, "SECURITY": 2 }, "JOGULAMBA": { "AGRICULTURE": 3, "FINANCE": 1, "GOVERNANCE": 3, "HEALTH": 3, "INFRASTRUCTURE": 1, "LEGAL": 4, "POLITICS": 13, "SECURITY": 2 }, "KAMAREDDY": { "AGRICULTURE": 3, "FINANCE": 2, "GOVERNANCE": 8, "HEALTH": 2, "INFRASTRUCTURE": 3, "LEGAL": 3, "POLITICS": 18, "SECURITY": 7 }, "KARIMNAGAR": { "AGRICULTURE": 68, "FINANCE": 8, "GOVERNANCE": 23, "HEALTH": 29, "INFRASTRUCTURE": 25, "LEGAL": 35, "POLITICS": 190, "SECURITY": 59 }, "KHAMMAM": { "AGRICULTURE": 33, "FINANCE": 8, "GOVERNANCE": 17, "HEALTH": 18, "INFRASTRUCTURE": 21, "LEGAL": 19, "POLITICS": 58, "SECURITY": 30 }, "KUMRAM BHEEM": { "AGRICULTURE": 73, "FINANCE": 5, "GOVERNANCE": 19, "HEALTH": 29, "INFRASTRUCTURE": 29, "LEGAL": 8, "POLITICS": 141, "SECURITY": 31 }, "MAHABUBABAD": { "AGRICULTURE": 8, "FINANCE": 2, "GOVERNANCE": 7, "HEALTH": 5, "INFRASTRUCTURE": 2, "LEGAL": 2, "POLITICS": 11, "SECURITY": 7 }, "MAHBUBNAGAR": { "AGRICULTURE": 10, "FINANCE": 2, "GOVERNANCE": 6, "HEALTH": 5, "INFRASTRUCTURE": 12, "LEGAL": 10, "POLITICS": 39, "SECURITY": 15 }, "MANCHERIAL": { "AGRICULTURE": 16, "FINANCE": 1, "GOVERNANCE": 2, "HEALTH": 8, "INFRASTRUCTURE": 3, "LEGAL": 11, "POLITICS": 20, "SECURITY": 7 }, "MEDAK": { "AGRICULTURE": 30, "FINANCE": 5, "GOVERNANCE": 7, "HEALTH": 9, "INFRASTRUCTURE": 12, "LEGAL": 11, "POLITICS": 53, "SECURITY": 20 }, "MEDCHAL": { "AGRICULTURE": 3, "FINANCE": 4, "GOVERNANCE": 17, "HEALTH": 17, "INFRASTRUCTURE": 36, "LEGAL": 33, "POLITICS": 46, "SECURITY": 56 }, "MULUGU": { "AGRICULTURE": 1, "FINANCE": 1, "GOVERNANCE": 3, "HEALTH": 8, "INFRASTRUCTURE": 5, "LEGAL": 6, "POLITICS": 9, "SECURITY": 3 }, "NAGARKURNOOL": { "AGRICULTURE": 5, "FINANCE": 3, "GOVERNANCE": 2, "HEALTH": 2, "INFRASTRUCTURE": 14, "LEGAL": 11, "POLITICS": 15, "SECURITY": 7 }, "NALGONDA": { "AGRICULTURE": 27, "FINANCE": 2, "GOVERNANCE": 16, "HEALTH": 17, "INFRASTRUCTURE": 23, "LEGAL": 61, "POLITICS": 178, "SECURITY": 104 }, "NARAYANPET": { "FINANCE": 1, "GOVERNANCE": 2, "HEALTH": 2, "INFRASTRUCTURE": 1, "LEGAL": 1, "POLITICS": 10, "SECURITY": 4 }, "NIRMAL": { "AGRICULTURE": 11, "FINANCE": 10, "GOVERNANCE": 9, "HEALTH": 7, "INFRASTRUCTURE": 9, "LEGAL": 8, "POLITICS": 26, "SECURITY": 14 }, "NIZAMABAD": { "AGRICULTURE": 77, "FINANCE": 7, "GOVERNANCE": 12, "HEALTH": 29, "INFRASTRUCTURE": 29, "LEGAL": 22, "POLITICS": 155, "SECURITY": 46 }, "PEDDAPALLI": { "AGRICULTURE": 6, "FINANCE": 5, "GOVERNANCE": 8, "HEALTH": 4, "INFRASTRUCTURE": 9, "LEGAL": 7, "POLITICS": 31, "SECURITY": 4 }, "RAJANNA SIRCILLA": { "AGRICULTURE": 5, "FINANCE": 1, "GOVERNANCE": 4, "HEALTH": 5, "INFRASTRUCTURE": 3, "LEGAL": 9, "POLITICS": 29, "SECURITY": 7 }, "RANGAREDDY": { "AGRICULTURE": 11, "FINANCE": 5, "GOVERNANCE": 22, "HEALTH": 14, "INFRASTRUCTURE": 60, "LEGAL": 23, "POLITICS": 68, "SECURITY": 36 }, "SANGAREDDY": { "AGRICULTURE": 9, "FINANCE": 2, "GOVERNANCE": 11, "HEALTH": 9, "INFRASTRUCTURE": 16, "LEGAL": 11, "POLITICS": 22, "SECURITY": 19 }, "SIDDIPET": { "AGRICULTURE": 34, "FINANCE": 3, "GOVERNANCE": 5, "HEALTH": 12, "INFRASTRUCTURE": 11, "LEGAL": 11, "POLITICS": 59, "SECURITY": 7 }, "SURYAPET": { "AGRICULTURE": 12, "FINANCE": 3, "GOVERNANCE": 13, "HEALTH": 7, "INFRASTRUCTURE": 4, "LEGAL": 16, "POLITICS": 24, "SECURITY": 13 }, "VIKARABAD": { "AGRICULTURE": 6, "FINANCE": 1, "GOVERNANCE": 4, "HEALTH": 8, "INFRASTRUCTURE": 3, "LEGAL": 2, "POLITICS": 18, "SECURITY": 7 }, "WANAPARTHY": { "AGRICULTURE": 5, "FINANCE": 1, "GOVERNANCE": 2, "LEGAL": 3, "POLITICS": 10, "SECURITY": 3 }, "WARANGAL": { "AGRICULTURE": 24, "FINANCE": 5, "GOVERNANCE": 14, "HEALTH": 13, "INFRASTRUCTURE": 14, "LEGAL": 16, "POLITICS": 58, "SECURITY": 25 }, "YADADRI": { "AGRICULTURE": 10, "FINANCE": 4, "GOVERNANCE": 6, "HEALTH": 2, "INFRASTRUCTURE": 8, "LEGAL": 7, "POLITICS": 25, "SECURITY": 7 } };
const WEEKLY_RAW = { "ADILABAD": { "0": 53, "1": 66, "2": 50, "3": 981, "4": 13, "5": 6 }, "BHADRADRI": { "0": 43, "1": 77, "2": 5, "3": 98, "4": 6 }, "HANUMAKONDA": { "0": 28, "1": 57, "2": 3, "3": 48, "4": 2 }, "HYDERABAD": { "0": 1526, "1": 2395, "2": 379, "3": 4449, "4": 1806, "5": 190, "6": 17 }, "JAGTIAL": { "0": 27, "1": 31, "2": 1, "3": 6, "4": 5 }, "JANGAON": { "0": 14, "1": 20, "3": 7, "4": 2 }, "JAYASHANKAR": { "0": 35, "1": 42, "2": 2, "3": 18, "4": 3 }, "JOGULAMBA": { "0": 14, "1": 22, "2": 1, "3": 19, "5": 1 }, "KAMAREDDY": { "0": 26, "1": 28, "2": 4, "3": 24, "4": 6, "5": 3 }, "KARIMNAGAR": { "0": 93, "1": 160, "2": 35, "3": 775, "4": 27, "5": 4, "6": 1 }, "KHAMMAM": { "0": 82, "1": 104, "2": 14, "3": 181, "4": 18, "5": 5, "6": 1 }, "KUMRAM BHEEM": { "0": 53, "1": 30, "2": 39, "3": 870, "4": 11, "5": 1 }, "MAHABUBABAD": { "0": 26, "1": 42, "3": 22, "4": 3, "5": 1 }, "MAHBUBNAGAR": { "0": 42, "1": 41, "2": 8, "3": 104, "4": 7, "5": 2 }, "MANCHERIAL": { "0": 38, "1": 49, "2": 3, "3": 37, "4": 10, "5": 3 }, "MEDAK": { "0": 59, "1": 78, "2": 6, "3": 117, "4": 8, "5": 3, "6": 1 }, "MEDCHAL": { "0": 89, "1": 107, "2": 8, "3": 110, "4": 37, "5": 4 }, "MULUGU": { "0": 12, "1": 35, "2": 1, "3": 29, "4": 4, "5": 1 }, "NAGARKURNOOL": { "0": 28, "1": 44, "2": 6, "3": 40, "4": 5, "5": 3 }, "NALGONDA": { "0": 54, "1": 206, "2": 62, "3": 523, "4": 14, "5": 4 }, "NARAYANPET": { "0": 20, "1": 12, "2": 2, "3": 6, "4": 3 }, "NIRMAL": { "0": 56, "1": 55, "2": 5, "3": 61, "4": 26, "5": 12, "6": 1 }, "NIZAMABAD": { "0": 51, "1": 76, "2": 47, "3": 860, "4": 15, "5": 2 }, "PEDDAPALLI": { "0": 43, "1": 46, "3": 41, "4": 6, "6": 1 }, "RAJANNA SIRCILLA": { "0": 34, "1": 39, "2": 3, "3": 41, "4": 4, "5": 1 }, "RANGAREDDY": { "0": 103, "1": 110, "2": 10, "3": 161, "4": 41, "5": 7 }, "SANGAREDDY": { "0": 51, "1": 32, "2": 8, "3": 80, "4": 17, "5": 4 }, "SIDDIPET": { "0": 92, "1": 68, "2": 7, "3": 107, "4": 13, "5": 4 }, "SURYAPET": { "0": 34, "1": 73, "2": 6, "3": 63, "4": 4 }, "VIKARABAD": { "0": 32, "1": 21, "2": 2, "3": 29, "4": 2, "5": 3 }, "WANAPARTHY": { "0": 17, "1": 13, "2": 3, "3": 6, "5": 1 }, "WARANGAL": { "0": 59, "1": 94, "2": 10, "3": 157, "4": 13, "5": 10 }, "YADADRI": { "0": 29, "1": 40, "2": 1, "3": 39, "4": 9 } };
const PERSONA_RAW = { "ADILABAD": 12, "BHADRADRI": 4, "HANUMAKONDA": 7, "HYDERABAD": 339, "JAGTIAL": 3, "JANGAON": 2, "JAYASHANKAR": 4, "JOGULAMBA": 3, "KAMAREDDY": 1, "KARIMNAGAR": 25, "KHAMMAM": 8, "KUMRAM BHEEM": 30, "MAHABUBABAD": 1, "MAHBUBNAGAR": 12, "MANCHERIAL": 8, "MEDAK": 13, "MEDCHAL": 21, "MULUGU": 3, "NAGARKURNOOL": 6, "NALGONDA": 6, "NARAYANPET": 4, "NIRMAL": 1, "NIZAMABAD": 11, "PEDDAPALLI": 6, "RAJANNA SIRCILLA": 2, "RANGAREDDY": 36, "SANGAREDDY": 5, "SIDDIPET": 18, "SURYAPET": 11, "VIKARABAD": 9, "WANAPARTHY": 1, "WARANGAL": 15, "YADADRI": 15 };
const OUTLETS_RAW = { "ADILABAD": 22, "BHADRADRI": 17, "HANUMAKONDA": 16, "HYDERABAD": 187, "JAGTIAL": 14, "JANGAON": 9, "JAYASHANKAR": 18, "JOGULAMBA": 16, "KAMAREDDY": 16, "KARIMNAGAR": 25, "KHAMMAM": 23, "KUMRAM BHEEM": 18, "MAHABUBABAD": 13, "MAHBUBNAGAR": 20, "MANCHERIAL": 18, "MEDAK": 23, "MEDCHAL": 33, "MULUGU": 14, "NAGARKURNOOL": 18, "NALGONDA": 22, "NARAYANPET": 13, "NIRMAL": 53, "NIZAMABAD": 26, "PEDDAPALLI": 15, "RAJANNA SIRCILLA": 20, "RANGAREDDY": 39, "SANGAREDDY": 22, "SIDDIPET": 16, "SURYAPET": 20, "VIKARABAD": 15, "WANAPARTHY": 15, "WARANGAL": 29, "YADADRI": 16 };

// GeoJSON district name → DB name (only ones that differ; else UPPERCASE).
const GEO2DB = {
  'Komaram Bheem': 'KUMRAM BHEEM', 'Ranga Reddy': 'RANGAREDDY', 'Medchal Malkajgiri': 'MEDCHAL',
  'Warangal Rural': 'WARANGAL', 'Warangal Urban': 'HANUMAKONDA', 'Bhadradri Kothagudem': 'BHADRADRI',
  'Jogulamba Gadwal': 'JOGULAMBA', 'Jayashankar Bhupalapally': 'JAYASHANKAR',
  'Yadadri Bhuvanagiri': 'YADADRI', 'Mahabubnagar': 'MAHBUBNAGAR',
};
const dbKey = (geo) => GEO2DB[geo] || geo.toUpperCase();
const byGeo = (fn) => Object.fromEntries(Object.keys(DISTRICT_DATA).map((g) => [g, fn(dbKey(g), g)]));

export const ISSUE_KEYS = ['POLITICS', 'SECURITY', 'LEGAL', 'AGRICULTURE', 'GOVERNANCE', 'INFRASTRUCTURE', 'HEALTH', 'FINANCE'];
export const WEEK_LABELS = ['6w ago', '5w', '4w', '3w', '2w', 'this wk']; // oldest → newest

// Per-GeoJSON-name metric tables (computed once, immutable).
export const ISSUE = byGeo((k) => ISSUE_RAW[k] || {});
export const WEEKLY = byGeo((k) => { const w = WEEKLY_RAW[k] || {}; return [5, 4, 3, 2, 1, 0].map((i) => w[i] || 0); });
export const PERSONA = byGeo((k) => PERSONA_RAW[k] || 0);
export const OUTLETS = byGeo((k) => OUTLETS_RAW[k] || 0);
