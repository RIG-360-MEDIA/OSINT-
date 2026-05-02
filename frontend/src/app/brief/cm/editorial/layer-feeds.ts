/**
 * Per-layer side-feed content — what appears next to the map when a
 * given layer is active. Each layer gets its own component shape, so
 * the right side of the atlas is a different reading experience for
 * News Hotspot vs ACLED vs Mandi vs Power, exactly like World Monitor's
 * panel-per-layer pattern.
 *
 * Hardcoded for v1 review. Wiring to live data is a single-file swap.
 */

/* ------------------------------------------------------------------ */
/* News Hotspot                                                        */
/* ------------------------------------------------------------------ */

export interface NewsFeedEntry {
  source: string
  district: string
  ageLabel: string
  headline: string
  sentiment: number
  reach?: string
}

export const NEWS_FEED: ReadonlyArray<NewsFeedEntry> = [
  { source: 'Eenadu', district: 'Hyderabad', ageLabel: '23m', headline: 'CM addresses Group-1 row in afternoon presser', sentiment: 0.1, reach: 'reach 412k' },
  { source: 'Telangana Today', district: 'Khammam', ageLabel: '38m', headline: 'Farmer assembly enters fourth hour, district administration silent', sentiment: -0.7 },
  { source: 'Eenadu', district: 'Karimnagar', ageLabel: '2h', headline: 'BJP confirms 4 May rally — est. 8,000 attending', sentiment: -0.4 },
  { source: 'The Hindu', district: 'Hyderabad', ageLabel: '1h', headline: 'Musi rehab plan still incomplete, planners say', sentiment: -0.5 },
  { source: 'Telangana Today', district: 'Statewide', ageLabel: '3h', headline: 'Hydra demolitions: HC asks state to clarify rehab policy', sentiment: -0.4 },
]

/* ------------------------------------------------------------------ */
/* Sentiment                                                           */
/* ------------------------------------------------------------------ */

export interface SentimentQuote {
  author: string
  channel: string
  district: string
  text: string
  sentiment: number
}

export const SENTIMENT_FEED = {
  statewide: -0.34,
  delta: -0.08,
  topNegativeDistricts: [
    { name: 'Khammam', value: -0.72 },
    { name: 'Hyderabad', value: -0.46 },
    { name: 'Karimnagar', value: -0.38 },
    { name: 'Warangal', value: -0.30 },
  ] as const,
  quotes: [
    { author: 'KTR', channel: 'X', district: 'Hyderabad', text: 'Musi project a scam — where is the rehabilitation plan?', sentiment: -0.7 },
    { author: 'Khammam farmer leader', channel: 'press', district: 'Khammam', text: 'Cotton procurement delays four weeks running. Where is the state?', sentiment: -0.65 },
    { author: 'Bandi Sanjay', channel: 'press', district: 'Karimnagar', text: 'Sunday rally will be the largest in north Telangana this year', sentiment: -0.4 },
  ] as ReadonlyArray<SentimentQuote>,
} as const

/* ------------------------------------------------------------------ */
/* ACLED                                                               */
/* ------------------------------------------------------------------ */

export interface AcledEntry {
  date: string
  type: 'Protest' | 'Riot' | 'Strategic Development' | 'Violence Against Civilians'
  district: string
  summary: string
}

export const ACLED_FEED = {
  total7d: 14,
  breakdown: [
    { type: 'Protest', count: 9 },
    { type: 'Strategic Development', count: 3 },
    { type: 'Riot', count: 2 },
  ] as const,
  events: [
    { date: '02 May', type: 'Protest', district: 'Khammam', summary: 'Farmer assembly at district HQ, ongoing — est. 800 attending' },
    { date: '01 May', type: 'Protest', district: 'Hyderabad', summary: 'Musi-rehab affected families demonstrate at Indira Park' },
    { date: '01 May', type: 'Protest', district: 'Warangal', summary: 'Kakatiya University staff demonstration over PRC arrears' },
    { date: '30 Apr', type: 'Protest', district: 'Karimnagar', summary: 'Granite mine workers demonstrate after fatal incident' },
    { date: '29 Apr', type: 'Strategic Development', district: 'Hyderabad', summary: 'BRS submits memorandum to Raj Bhavan on caste survey' },
  ] as ReadonlyArray<AcledEntry>,
} as const

/* ------------------------------------------------------------------ */
/* Mandi                                                                */
/* ------------------------------------------------------------------ */

export interface CommodityMover {
  commodity: string
  market: string
  district: string
  price: string
  delta: string
  trend: 'up' | 'down' | 'flat'
}

export const MANDI_FEED = {
  topMovers: [
    { commodity: 'Chilli (Teja)', market: 'Khammam', district: 'Khammam', price: '₹14,200/q', delta: '+22%', trend: 'up' },
    { commodity: 'Tomato', market: 'Bowenpally', district: 'Hyderabad', price: '₹14/kg', delta: '–18%', trend: 'down' },
    { commodity: 'Turmeric', market: 'Jagtial', district: 'Jagtial', price: '₹16,400/q', delta: '+8%', trend: 'up' },
    { commodity: 'Cotton', market: 'Khammam', district: 'Khammam', price: '₹6,820/q', delta: '–8%', trend: 'down' },
    { commodity: 'Mango', market: 'Erragadda', district: 'Hyderabad', price: '₹95/kg', delta: '+12%', trend: 'up' },
  ] as ReadonlyArray<CommodityMover>,
  volatileMarkets: ['Khammam', 'Bowenpally', 'Jagtial'] as const,
} as const

/* ------------------------------------------------------------------ */
/* Welfare                                                              */
/* ------------------------------------------------------------------ */

export const WELFARE_FEED = {
  statewide: [
    { scheme: 'Aasara Pensions', coveragePct: 91 },
    { scheme: 'Rythu Bandhu', coveragePct: 87 },
    { scheme: '2BHK Housing', coveragePct: 64 },
    { scheme: 'MGNREGA', coveragePct: 71 },
  ] as const,
  bestCovered: [
    { district: 'Hyderabad', scheme: 'Aasara', value: 94 },
    { district: 'Karimnagar', scheme: 'Rythu Bandhu', value: 91 },
    { district: 'Sangareddy', scheme: 'Aasara', value: 93 },
  ] as const,
  atRisk: [
    { district: 'Khammam', scheme: 'MGNREGA', value: 64 },
    { district: 'Bhadradri', scheme: '2BHK', value: 48 },
    { district: 'Mahbubnagar', scheme: 'Aasara', value: 78 },
  ] as const,
} as const

/* ------------------------------------------------------------------ */
/* Power                                                                */
/* ------------------------------------------------------------------ */

export const POWER_FEED = {
  statewide: {
    demand: '9,420 MW',
    supply: '9,398 MW',
    deficit: '–22 MW',
    peakWindow: '19:00 – 21:00',
  },
  stressed: [
    { district: 'Khammam', demand: 584, supply: 562, deficit: -22, note: 'Agri feeders 12:00–14:00' },
    { district: 'Mahabubabad', demand: 268, supply: 260, deficit: -8, note: 'Industrial cluster' },
    { district: 'Bhadradri', demand: 222, supply: 220, deficit: -2, note: 'Margin tight' },
  ] as const,
} as const

/* ------------------------------------------------------------------ */
/* Stability                                                            */
/* ------------------------------------------------------------------ */

export const STABILITY_FEED = {
  statewide: 52,
  delta: -3,
  mostStable: [
    { district: 'Adilabad', score: 78 },
    { district: 'Komaram Bheem', score: 76 },
    { district: 'Nirmal', score: 74 },
  ] as const,
  mostStressed: [
    { district: 'Khammam', score: 32 },
    { district: 'Hyderabad', score: 38 },
    { district: 'Karimnagar', score: 41 },
  ] as const,
  componentWeights: [
    { name: 'Air quality', weight: 30 },
    { name: 'Heat stress', weight: 25 },
    { name: 'Conflict events', weight: 25 },
    { name: 'News anomaly', weight: 20 },
  ] as const,
} as const
