/**
 * Hardcoded demo data for the Editorial Intelligence brief.
 *
 * This is a *demo* dataset — values are plausible and structured exactly
 * as a real feed would deliver them, so the layout reads as live without
 * fabricating quotations attributable to any specific real person.
 *
 * Persona names are public political figures; quoted strings are framed
 * as paraphrases / characterisations of widely-reported public positions.
 */

export interface DistrictDatum {
  id: string
  name: string
  /** 0..1 — sentiment volatility, drives the sepia heatmap fill. */
  volatility: number
}

export interface MapPin {
  id: string
  /** Display label of the city / district where the pin lands. */
  city: string
  /** District id from telangana-geo.ts — pin renders at that polygon's centroid. */
  districtId: string
  /** Italic-serif annotation rendered in the right-margin column. The roman
   *  numeral that prefixes the annotation is assigned in geographic order
   *  (top to bottom) at render time, so tethers never cross. */
  annotation: string
}

export interface NewsItem {
  source: string
  ageLabel: string
  headline: string
  reach?: string
}

export interface OppositionItem {
  actor: string
  party: 'BRS' | 'BJP' | 'INC' | 'AIMIM'
  channel: string
  ageLabel: string
  summary: string
  sentiment: number
  reach?: string
}

export interface ActionItem {
  priority: 'P0' | 'P1' | 'P2'
  text: string
}

export interface WatchlistEntity {
  label: string
  delta: number | null
  flat?: boolean
}

export interface ThreatPlot {
  label: string
  /** 0..2 → low / med / high */
  likelihood: 0 | 1 | 2
  impact: 0 | 1 | 2
  level: 'LOW' | 'LOW-MED' | 'MED' | 'HIGH'
}

export interface ForecastPoint {
  /** ISO day label e.g. "02 May" */
  day: string
  sentiment: number
  /** Confidence band half-width. */
  band: number
}

export interface TickerEvent {
  time: string
  text: string
}

export const HEADER = {
  briefTitle: 'THE CHIEF MINISTER’S BRIEF',
  region: 'TELANGANA',
  cmName: 'CM A. Revanth Reddy',
  cmParty: 'INC',
  /** Demo timestamp used as "as of" in the live stamp. */
  asOf: '14:37',
  /** Display dateline. */
  dateline: 'Saturday, 02 May 2026',
} as const

export const HERO = {
  eyebrow: 'WHAT CHANGED · SINCE 09:00',
  headline:
    'Opposition has consolidated around Musi rehab — four of the six most-shared posts in Telangana today are critical of the project, three syndicated by BRS-aligned handles.',
  link: 'View source thread',
  /** Sparkline points — sentiment trail from 09:00 to 14:30. */
  sparkline: [-0.26, -0.27, -0.28, -0.29, -0.31, -0.30, -0.32, -0.34],
} as const

export const STATEWIDE_SUMMARY =
  'Statewide sentiment –0.34 — down 0.08 since morning, driven principally by Musi coverage.'

/* ------------------------------------------------------------------ */
/* Telangana districts — 33 districts with hand-tuned heatmap weights. */
/* ------------------------------------------------------------------ */

/**
 * Volatility weights keyed by district id (matches telangana-geo.ts).
 * Source geometry: geoBoundaries gbOpen IND ADM2 (2021) — the post-2019
 * 33-district arrangement, exactly what people expect to see when they
 * look at a map of Telangana today.
 */
export const DISTRICTS: ReadonlyArray<DistrictDatum> = [
  // Hyderabad belt — highest sentiment volatility
  { id: 'hyderabad', name: 'HYDERABAD', volatility: 0.86 },
  { id: 'khammam', name: 'KHAMMAM', volatility: 0.78 },
  { id: 'warangal', name: 'WARANGAL', volatility: 0.65 },
  { id: 'rangareddy', name: 'RANGAREDDY', volatility: 0.64 },
  { id: 'karimnagar', name: 'KARIMNAGAR', volatility: 0.62 },
  { id: 'hanumakonda', name: 'HANUMAKONDA', volatility: 0.58 },
  { id: 'medak', name: 'MEDAK', volatility: 0.55 },
  { id: 'medchal', name: 'MEDCHAL', volatility: 0.52 },
  // Mid tier
  { id: 'nalgonda', name: 'NALGONDA', volatility: 0.46 },
  { id: 'mahabubabad', name: 'MAHABUBABAD', volatility: 0.42 },
  { id: 'sangareddy', name: 'SANGAREDDY', volatility: 0.42 },
  { id: 'siddipet', name: 'SIDDIPET', volatility: 0.41 },
  { id: 'bhadradri', name: 'BHADRADRI', volatility: 0.39 },
  { id: 'peddapalli', name: 'PEDDAPALLI', volatility: 0.36 },
  { id: 'suryapet', name: 'SURYAPET', volatility: 0.35 },
  { id: 'nizamabad', name: 'NIZAMABAD', volatility: 0.34 },
  { id: 'jangaon', name: 'JANGAON', volatility: 0.33 },
  { id: 'mahbubnagar', name: 'MAHBUBNAGAR', volatility: 0.32 },
  { id: 'rajanna-sircilla', name: 'RAJANNA SIRCILLA', volatility: 0.3 },
  { id: 'jagtial', name: 'JAGTIAL', volatility: 0.28 },
  { id: 'mulugu', name: 'MULUGU', volatility: 0.28 },
  { id: 'yadadri', name: 'YADADRI', volatility: 0.27 },
  { id: 'jayashankar', name: 'JAYASHANKAR', volatility: 0.26 },
  { id: 'kamareddy', name: 'KAMAREDDY', volatility: 0.24 },
  // Calmer rural districts
  { id: 'mancherial', name: 'MANCHERIAL', volatility: 0.22 },
  { id: 'vikarabad', name: 'VIKARABAD', volatility: 0.21 },
  { id: 'nirmal', name: 'NIRMAL', volatility: 0.2 },
  { id: 'nagarkurnool', name: 'NAGARKURNOOL', volatility: 0.2 },
  { id: 'wanaparthy', name: 'WANAPARTHY', volatility: 0.19 },
  { id: 'adilabad', name: 'ADILABAD', volatility: 0.18 },
  { id: 'narayanpet', name: 'NARAYANPET', volatility: 0.18 },
  { id: 'komaram-bheem', name: 'KUMRAM BHEEM', volatility: 0.18 },
  { id: 'jogulamba', name: 'JOGULAMBA', volatility: 0.16 },
]

/* Pins resolve (x, y) from the centroid of their district polygon at render
 * time — keeping data and geometry in lockstep. Roman-numeral markers are
 * also assigned at render time, in top-to-bottom geographic order. */
export const PINS: ReadonlyArray<MapPin> = [
  {
    id: 'karimnagar-rally',
    city: 'Karimnagar',
    districtId: 'karimnagar',
    annotation:
      'Opposition rally scheduled · 4 May · est. 8,000 attending',
  },
  {
    id: 'hyderabad-musi',
    city: 'Hyderabad',
    districtId: 'hyderabad',
    annotation:
      'Musi narrative escalating · 1.2k mentions · four mainstream dailies',
  },
  {
    id: 'khammam-farmer',
    city: 'Khammam',
    districtId: 'khammam',
    annotation:
      'Farmer assembly · 412 mentions · sentiment –0.72 · since 14:18',
  },
]

export const ADDITIONAL_EVENTS_LABEL = '+ 14 more events'

/* ------------------------------------------------------------------ */
/* Right column — desk cards.                                          */
/* ------------------------------------------------------------------ */

export const NEWS_DESK: ReadonlyArray<NewsItem> = [
  {
    source: 'Eenadu',
    ageLabel: '23m',
    headline: 'CM addresses Group-1 row in afternoon presser',
    reach: 'reach 412k',
  },
  {
    source: 'The Hindu',
    ageLabel: '1h',
    headline: 'Musi rehab plan still incomplete, planners say',
  },
  {
    source: 'Sakshi',
    ageLabel: '2h',
    headline: 'Caste survey deadline extended by ten days',
  },
  {
    source: 'Telangana Today',
    ageLabel: '3h',
    headline: 'Hydra demolitions: HC asks state to clarify rehabilitation policy',
  },
]

export const OPPOSITION_DESK: ReadonlyArray<OppositionItem> = [
  {
    actor: 'KTR',
    party: 'BRS',
    channel: 'X',
    ageLabel: '38m',
    summary: 'Characterises Musi project as a scam, calls for white paper',
    sentiment: -0.7,
    reach: '14k engagements',
  },
  {
    actor: 'Bandi Sanjay',
    party: 'BJP',
    channel: 'press',
    ageLabel: '2h',
    summary: 'Karimnagar rally announced, 4 May, est. 8k attending',
    sentiment: -0.4,
  },
  {
    actor: 'Harish Rao',
    party: 'BRS',
    channel: 'press meet',
    ageLabel: '4h',
    summary: 'Counter-narrative on caste survey extension at 16:00 briefing',
    sentiment: -0.3,
  },
]

export const VOICE_SHARE = {
  label: 'VOICE SHARE · 24h',
  parts: [
    { party: 'BRS', value: 41 },
    { party: 'BJP', value: 22 },
    { party: 'INC', value: 37 },
  ],
} as const

export const ACTIONS: ReadonlyArray<ActionItem> = [
  { priority: 'P0', text: 'Counter Musi narrative within 6h' },
  { priority: 'P1', text: 'Field visit to Khammam this week' },
  { priority: 'P1', text: 'Authorise Group-1 transparency briefing' },
  { priority: 'P2', text: 'Schedule Hydra policy presser before 5 May' },
]

export const WATCHLIST: ReadonlyArray<WatchlistEntity> = [
  { label: '@KTRBRS', delta: 23 },
  { label: 'Musi project', delta: 18 },
  { label: 'Hydra commissioner', delta: -5 },
  { label: 'Caste census', delta: 9 },
  { label: 'Metro Phase-2', delta: null, flat: true },
]

export const THREATS: ReadonlyArray<ThreatPlot> = [
  { label: 'Agrarian unrest', likelihood: 1, impact: 2, level: 'MED' },
  { label: 'MLA defection rumour', likelihood: 0, impact: 2, level: 'LOW' },
  { label: 'Communal flare-up', likelihood: 0, impact: 2, level: 'LOW' },
  { label: 'Hydra litigation', likelihood: 1, impact: 1, level: 'LOW-MED' },
]

export const FORECAST_NARRATIVE =
  'Opposition push expected to peak around 5 May; counter-narrative window closes by 18:00 today.'

export const FORECAST_CAPTION =
  'Sentiment outlook –0.41 ± 0.06 · forecast renewed every 6h.'

export const FORECAST_POINTS: ReadonlyArray<ForecastPoint> = [
  { day: '02 May', sentiment: -0.34, band: 0.04 },
  { day: '03 May', sentiment: -0.36, band: 0.05 },
  { day: '04 May', sentiment: -0.39, band: 0.05 },
  { day: '05 May', sentiment: -0.42, band: 0.06 },
  { day: '06 May', sentiment: -0.41, band: 0.06 },
  { day: '07 May', sentiment: -0.39, band: 0.06 },
  { day: '08 May', sentiment: -0.37, band: 0.07 },
]

export const TICKER_EVENTS: ReadonlyArray<TickerEvent> = [
  { time: '14:31', text: 'KTR post on Musi · –0.7 sentiment · 14k reach' },
  { time: '14:28', text: 'BJP plans Karimnagar rally 4 May' },
  { time: '14:22', text: 'NDTV publishes Hydra explainer' },
  { time: '14:18', text: 'Eenadu front-page editorial on caste survey' },
  { time: '14:09', text: 'Khammam district officer reports farmer sit-in continues' },
  { time: '13:54', text: 'Telangana Today: HC bench questions Hydra policy' },
  { time: '13:41', text: 'Harish Rao schedules 16:00 press meet' },
]
