/**
 * Hardcoded per-district demo data for the District Brief view.
 *
 * Five districts have hand-tuned content (Hyderabad, Khammam, Karimnagar,
 * Warangal, Adilabad — the last as the "quiet day" empty-state archetype).
 * The other 28 inherit a plausible template generated from each district's
 * id, name and statewide volatility weight.
 *
 * Wiring to live data later is a single-file change: replace the
 * `getDistrictBrief(id)` body with a server fetch.
 */

import type { DistrictGeo } from './telangana-geo'
import { TELANGANA_DISTRICTS } from './telangana-geo'
import { DISTRICTS } from './data'

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

export interface NewsItem {
  source: string
  ageLabel: string
  headline: string
  sentiment: number
  reach?: string
}

export interface AcledEvent {
  date: string
  type: 'Protest' | 'Riot' | 'Strategic Development' | 'Violence Against Civilians'
  summary: string
}

export interface MandiPrint {
  market: string
  commodity: string
  /** Display string — already formatted with ₹ */
  price: string
  delta: string
  trend: 'up' | 'down' | 'flat'
}

export interface WelfareMetric {
  scheme: string
  coveragePct: number
  detail: string
}

export interface PowerStatus {
  demand: string
  supply: string
  /** Plain-language status — appears as the prominent line. */
  status: string
  level: 'normal' | 'stressed' | 'shedding'
}

export interface MediaMention {
  channel: string
  timestamp: string
  snippet: string
}

export interface CounterNarrative {
  headline: string
  /** Display deadline — e.g. "12h to respond" */
  deadline: string
  /** P0 / P1 / P2 — visual urgency. */
  priority: 'P0' | 'P1' | 'P2'
}

export interface DistrictFacts {
  hqCity: string
  population: string
  area: string
  mlaCount: number
  mlaSplit: { brs: number; bjp: number; inc: number; other: number }
  notableLandmark: string
}

export interface StabilityBreakdown {
  /** Composite 0-100, higher = more stable. */
  overall: number
  airQuality: number
  heatStress: number
  conflict: number
  newsAnomaly: number
}

export interface DistrictBriefData {
  id: string
  name: string
  facts: DistrictFacts
  stability: StabilityBreakdown
  newsHotspot: {
    count24h: number
    items: ReadonlyArray<NewsItem>
  }
  acled: {
    count7d: number
    events: ReadonlyArray<AcledEvent>
  }
  mandi: ReadonlyArray<MandiPrint>
  welfare: ReadonlyArray<WelfareMetric>
  power: PowerStatus
  liveMedia: {
    tvMentions: ReadonlyArray<MediaMention>
    /** District-relevant Telugu live channels (links provided per-district). */
    channels: ReadonlyArray<{ label: string; url: string }>
  }
  counterNarrative?: CounterNarrative
  /** A one-sentence bottom-line characterisation of the district right now. */
  oneliner: string
}

/* ------------------------------------------------------------------ */
/* Custom rich data for the most-active demo districts                 */
/* ------------------------------------------------------------------ */

const HYDERABAD: DistrictBriefData = {
  id: 'hyderabad',
  name: 'HYDERABAD',
  facts: {
    hqCity: 'Hyderabad',
    population: '4.0M',
    area: '217 km²',
    mlaCount: 15,
    mlaSplit: { brs: 1, bjp: 3, inc: 4, other: 7 },
    notableLandmark: 'Charminar · Hussain Sagar · Musi River',
  },
  stability: {
    overall: 38,
    airQuality: 32,
    heatStress: 48,
    conflict: 30,
    newsAnomaly: 24,
  },
  newsHotspot: {
    count24h: 184,
    items: [
      { source: 'Eenadu', ageLabel: '23m', headline: 'CM addresses Group-1 row in afternoon presser', sentiment: 0.1, reach: 'reach 412k' },
      { source: 'The Hindu', ageLabel: '1h', headline: 'Musi rehab plan still incomplete, planners say', sentiment: -0.5 },
      { source: 'Telangana Today', ageLabel: '3h', headline: 'Hydra demolitions: HC asks state to clarify rehabilitation policy', sentiment: -0.4 },
      { source: 'Sakshi', ageLabel: '4h', headline: 'Metro Phase-2 ridership crosses pre-COVID baseline', sentiment: 0.4 },
      { source: 'Deccan Chronicle', ageLabel: '5h', headline: 'Old City traffic snarl after VIP movement', sentiment: -0.2 },
    ],
  },
  acled: {
    count7d: 7,
    events: [
      { date: '01 May', type: 'Protest', summary: 'Musi-rehab affected families demonstrate at Indira Park' },
      { date: '29 Apr', type: 'Strategic Development', summary: 'BRS submits memorandum to Raj Bhavan on caste survey' },
      { date: '27 Apr', type: 'Protest', summary: 'Group-1 aspirants gather at Ashok Nagar' },
    ],
  },
  mandi: [
    { market: 'Bowenpally', commodity: 'Tomato', price: '₹14/kg', delta: '–18% vs 30d', trend: 'down' },
    { market: 'Gaddiannaram', commodity: 'Onion', price: '₹22/kg', delta: '+6% vs 30d', trend: 'up' },
    { market: 'Erragadda', commodity: 'Mango', price: '₹95/kg', delta: '+12% vs 30d', trend: 'up' },
  ],
  welfare: [
    { scheme: 'Aasara Pensions', coveragePct: 94, detail: '388,210 of 412,996 beneficiaries paid this month' },
    { scheme: '2BHK Housing', coveragePct: 71, detail: '6,420 units handed over — phase-3 underway' },
    { scheme: 'Kalyana Lakshmi', coveragePct: 89, detail: '1,820 applications cleared in last 30 days' },
  ],
  power: {
    demand: '3,420 MW',
    supply: '3,420 MW',
    status: 'Demand fully met. Peak load 19:00–21:00 expected.',
    level: 'normal',
  },
  liveMedia: {
    tvMentions: [
      { channel: 'TV9 Telugu', timestamp: '14:31', snippet: '“…the Chief Minister will address the Group-1 controversy at his evening press meet…”' },
      { channel: 'V6 News', timestamp: '14:18', snippet: '“…Musi rehab families have arrived at Indira Park demanding a written commitment…”' },
      { channel: 'Sakshi TV', timestamp: '13:54', snippet: '“…High Court bench questions the state on Hydra demolition policy…”' },
    ],
    channels: [
      { label: 'TV9 Telugu', url: 'https://www.youtube.com/@tv9telugulive' },
      { label: 'V6 News', url: 'https://www.youtube.com/@v6news' },
      { label: 'Sakshi TV', url: 'https://www.youtube.com/@sakshitv' },
      { label: '10TV Telugu', url: 'https://www.youtube.com/@10tv' },
    ],
  },
  counterNarrative: {
    headline: 'Musi rehab story crystallising — counter window closes by 18:00',
    deadline: '4h to respond',
    priority: 'P0',
  },
  oneliner:
    'Capital is the centre of gravity today — Musi rehab narrative consolidating, Group-1 presser at 17:30 may decide the day.',
}

const KHAMMAM: DistrictBriefData = {
  id: 'khammam',
  name: 'KHAMMAM',
  facts: {
    hqCity: 'Khammam',
    population: '1.4M',
    area: '4,361 km²',
    mlaCount: 5,
    mlaSplit: { brs: 1, bjp: 0, inc: 4, other: 0 },
    notableLandmark: 'Khammam Fort · Kinnerasani Reservoir',
  },
  stability: {
    overall: 32,
    airQuality: 78,
    heatStress: 28,
    conflict: 18,
    newsAnomaly: 22,
  },
  newsHotspot: {
    count24h: 47,
    items: [
      { source: 'Telangana Today', ageLabel: '38m', headline: 'Farmer assembly at district HQ enters fourth hour, district administration silent', sentiment: -0.7, reach: 'reach 184k' },
      { source: 'Sakshi', ageLabel: '2h', headline: 'Cotton procurement delays widen — fourth weekly slip in a row', sentiment: -0.5 },
      { source: 'Eenadu', ageLabel: '4h', headline: 'BRS MLAs Khammam ZP meeting walkout over irrigation dues', sentiment: -0.3 },
    ],
  },
  acled: {
    count7d: 4,
    events: [
      { date: '02 May', type: 'Protest', summary: 'Farmer assembly at district HQ, ongoing — est. 800 attending' },
      { date: '30 Apr', type: 'Protest', summary: 'Cotton growers demonstrate outside marketing yard' },
      { date: '28 Apr', type: 'Strategic Development', summary: 'BRS MLAs submit memo to Collector on irrigation dues' },
    ],
  },
  mandi: [
    { market: 'Khammam', commodity: 'Cotton (long staple)', price: '₹6,820/q', delta: '–8% vs 30d', trend: 'down' },
    { market: 'Khammam', commodity: 'Chilli (Teja)', price: '₹14,200/q', delta: '+22% vs 30d', trend: 'up' },
    { market: 'Madhira', commodity: 'Paddy (BPT)', price: '₹2,180/q', delta: 'flat', trend: 'flat' },
    { market: 'Sathupalli', commodity: 'Maize', price: '₹1,940/q', delta: '–4% vs 30d', trend: 'down' },
  ],
  welfare: [
    { scheme: 'Rythu Bandhu', coveragePct: 86, detail: '212,400 of 247,000 farmers credited this season' },
    { scheme: 'Aasara Pensions', coveragePct: 92, detail: '143,210 of 155,500 beneficiaries paid' },
    { scheme: 'MGNREGA', coveragePct: 64, detail: '2.1 lakh person-days generated, payment delays in 18 GPs' },
  ],
  power: {
    demand: '584 MW',
    supply: '562 MW',
    status: 'Stress in agricultural feeders — 22 MW shortfall during 12:00–14:00.',
    level: 'stressed',
  },
  liveMedia: {
    tvMentions: [
      { channel: 'TV9 Telugu', timestamp: '14:18', snippet: '“…farmer assembly at Khammam Collectorate enters its fourth hour…”' },
      { channel: 'NTV Telugu', timestamp: '13:42', snippet: '“…cotton procurement delays now in their fourth consecutive week in Khammam…”' },
    ],
    channels: [
      { label: 'TV9 Telugu', url: 'https://www.youtube.com/@tv9telugulive' },
      { label: 'NTV Telugu', url: 'https://www.youtube.com/@ntvtelugu' },
      { label: 'Sakshi TV', url: 'https://www.youtube.com/@sakshitv' },
    ],
  },
  counterNarrative: {
    headline: 'Khammam farmer narrative likely to spread to Mahabubabad and Bhadradri by tomorrow',
    deadline: '12h to respond',
    priority: 'P1',
  },
  oneliner:
    'Eastern agrarian belt is the day’s pressure point — Khammam farmer assembly unresolved, cotton procurement delays compounding.',
}

const KARIMNAGAR: DistrictBriefData = {
  id: 'karimnagar',
  name: 'KARIMNAGAR',
  facts: {
    hqCity: 'Karimnagar',
    population: '1.0M',
    area: '2,128 km²',
    mlaCount: 4,
    mlaSplit: { brs: 2, bjp: 1, inc: 1, other: 0 },
    notableLandmark: 'Lower Manair Dam · Elgandal Fort',
  },
  stability: {
    overall: 41,
    airQuality: 64,
    heatStress: 38,
    conflict: 30,
    newsAnomaly: 32,
  },
  newsHotspot: {
    count24h: 38,
    items: [
      { source: 'Eenadu', ageLabel: '2h', headline: 'BJP confirms 4 May Karimnagar rally — est. 8,000 attending', sentiment: -0.4, reach: 'reach 220k' },
      { source: 'Telangana Today', ageLabel: '3h', headline: 'Granite mine worker safety inspection ordered after weekend incident', sentiment: -0.3 },
      { source: 'Deccan Chronicle', ageLabel: '5h', headline: 'Lower Manair Dam at 76% — irrigation drawdown to begin', sentiment: 0.2 },
    ],
  },
  acled: {
    count7d: 3,
    events: [
      { date: '04 May', type: 'Strategic Development', summary: 'BJP rally scheduled, est. 8,000 attending — Bandi Sanjay leading' },
      { date: '30 Apr', type: 'Protest', summary: 'Granite mine workers demonstrate after fatal incident' },
    ],
  },
  mandi: [
    { market: 'Karimnagar', commodity: 'Paddy (Kuruva)', price: '₹2,420/q', delta: '+3% vs 30d', trend: 'up' },
    { market: 'Karimnagar', commodity: 'Maize', price: '₹2,010/q', delta: '–2% vs 30d', trend: 'down' },
    { market: 'Jagtial', commodity: 'Turmeric', price: '₹16,400/q', delta: '+8% vs 30d', trend: 'up' },
  ],
  welfare: [
    { scheme: 'Rythu Bandhu', coveragePct: 91, detail: '178,200 of 195,800 farmers credited this season' },
    { scheme: 'Dalit Bandhu', coveragePct: 58, detail: '11,420 households received tranche-2 — phase-3 pending' },
    { scheme: 'Aasara Pensions', coveragePct: 88, detail: '108,400 of 123,200 beneficiaries paid' },
  ],
  power: {
    demand: '412 MW',
    supply: '412 MW',
    status: 'Demand fully met. No load shedding scheduled.',
    level: 'normal',
  },
  liveMedia: {
    tvMentions: [
      { channel: 'V6 News', timestamp: '14:09', snippet: '“…BJP set to mount its largest north Telangana rally on Sunday in Karimnagar…”' },
      { channel: 'ABN Telugu', timestamp: '13:40', snippet: '“…opposition will use Karimnagar to set agenda before the budget session…”' },
    ],
    channels: [
      { label: 'V6 News', url: 'https://www.youtube.com/@v6news' },
      { label: 'ABN Telugu', url: 'https://www.youtube.com/@abntelugu' },
      { label: 'TV9 Telugu', url: 'https://www.youtube.com/@tv9telugulive' },
    ],
  },
  counterNarrative: {
    headline: 'BJP rally narrative may dominate Sunday news cycle — preempt with policy announcement',
    deadline: '36h to respond',
    priority: 'P1',
  },
  oneliner:
    'Karimnagar is opposition-mobilisation territory this week — BJP rally on Sunday will set the north Telangana frame.',
}

const WARANGAL: DistrictBriefData = {
  id: 'warangal',
  name: 'WARANGAL',
  facts: {
    hqCity: 'Warangal',
    population: '0.7M',
    area: '2,175 km²',
    mlaCount: 3,
    mlaSplit: { brs: 2, bjp: 0, inc: 1, other: 0 },
    notableLandmark: 'Warangal Fort · Thousand Pillar Temple',
  },
  stability: {
    overall: 46,
    airQuality: 72,
    heatStress: 42,
    conflict: 34,
    newsAnomaly: 36,
  },
  newsHotspot: {
    count24h: 28,
    items: [
      { source: 'Eenadu', ageLabel: '3h', headline: 'KU non-teaching staff threaten strike over PRC arrears', sentiment: -0.4 },
      { source: 'Telangana Today', ageLabel: '5h', headline: 'Kakatiya Mega Textile Park inaugurated phase-2 — 1,200 jobs', sentiment: 0.5 },
      { source: 'Sakshi', ageLabel: '7h', headline: 'Fort heritage zone encroachment notices issued — 14 structures', sentiment: 0.1 },
    ],
  },
  acled: {
    count7d: 2,
    events: [
      { date: '01 May', type: 'Protest', summary: 'Kakatiya University non-teaching staff demonstration over PRC arrears' },
    ],
  },
  mandi: [
    { market: 'Warangal', commodity: 'Cotton (medium staple)', price: '₹6,640/q', delta: '–6% vs 30d', trend: 'down' },
    { market: 'Warangal', commodity: 'Paddy (Sona)', price: '₹2,260/q', delta: 'flat', trend: 'flat' },
    { market: 'Mahabubabad', commodity: 'Chilli', price: '₹13,800/q', delta: '+18% vs 30d', trend: 'up' },
  ],
  welfare: [
    { scheme: 'Rythu Bandhu', coveragePct: 89, detail: '142,800 of 160,500 farmers credited' },
    { scheme: 'KCR Kit', coveragePct: 96, detail: '4,820 newborn kits issued in last 30 days' },
    { scheme: 'Aasara Pensions', coveragePct: 91, detail: '78,420 of 86,200 beneficiaries paid' },
  ],
  power: {
    demand: '316 MW',
    supply: '316 MW',
    status: 'Demand fully met.',
    level: 'normal',
  },
  liveMedia: {
    tvMentions: [
      { channel: 'TV5 News', timestamp: '12:18', snippet: '“…Kakatiya University staff have given a 72-hour ultimatum on PRC arrears…”' },
    ],
    channels: [
      { label: 'TV5 News', url: 'https://www.youtube.com/@tv5news' },
      { label: 'V6 News', url: 'https://www.youtube.com/@v6news' },
    ],
  },
  oneliner:
    'Mixed signals — textile-park inauguration is a positive, but KU staff ultimatum needs a labour-side response by 72h.',
}

const ADILABAD: DistrictBriefData = {
  id: 'adilabad',
  name: 'ADILABAD',
  facts: {
    hqCity: 'Adilabad',
    population: '0.7M',
    area: '4,154 km²',
    mlaCount: 2,
    mlaSplit: { brs: 1, bjp: 1, inc: 0, other: 0 },
    notableLandmark: 'Kuntala Waterfalls · Pochera Falls',
  },
  stability: {
    overall: 78,
    airQuality: 88,
    heatStress: 64,
    conflict: 86,
    newsAnomaly: 74,
  },
  newsHotspot: {
    count24h: 4,
    items: [
      { source: 'Telangana Today', ageLabel: '6h', headline: 'Tribal welfare scheme review meeting concludes — no new announcements', sentiment: 0.1 },
    ],
  },
  acled: {
    count7d: 0,
    events: [],
  },
  mandi: [
    { market: 'Adilabad', commodity: 'Cotton', price: '₹6,720/q', delta: '–4% vs 30d', trend: 'down' },
    { market: 'Adilabad', commodity: 'Soybean', price: '₹4,210/q', delta: '+2% vs 30d', trend: 'up' },
  ],
  welfare: [
    { scheme: 'Rythu Bandhu', coveragePct: 84, detail: '62,400 of 74,200 farmers credited' },
    { scheme: 'Aasara Pensions', coveragePct: 86, detail: '46,800 of 54,400 beneficiaries paid' },
  ],
  power: {
    demand: '188 MW',
    supply: '188 MW',
    status: 'Demand fully met.',
    level: 'normal',
  },
  liveMedia: {
    tvMentions: [],
    channels: [
      { label: 'V6 News', url: 'https://www.youtube.com/@v6news' },
    ],
  },
  oneliner:
    'Quiet day across the northern frontier — no events of concern, baseline metrics nominal.',
}

const CUSTOM_DATA: Record<string, DistrictBriefData> = {
  hyderabad: HYDERABAD,
  khammam: KHAMMAM,
  karimnagar: KARIMNAGAR,
  warangal: WARANGAL,
  adilabad: ADILABAD,
}

/* ------------------------------------------------------------------ */
/* Template generator for the other 28 districts                       */
/* ------------------------------------------------------------------ */

const FALLBACK_CHANNELS = [
  { label: 'TV9 Telugu', url: 'https://www.youtube.com/@tv9telugulive' },
  { label: 'V6 News', url: 'https://www.youtube.com/@v6news' },
  { label: 'Sakshi TV', url: 'https://www.youtube.com/@sakshitv' },
]

function pretty(name: string): string {
  // "RAJANNA SIRCILLA" → "Rajanna Sircilla"
  return name
    .toLowerCase()
    .split(' ')
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(' ')
}

function makeTemplateData(district: DistrictGeo, volatility: number): DistrictBriefData {
  const tier: 'high' | 'mid' | 'low' =
    volatility >= 0.55 ? 'high' : volatility >= 0.3 ? 'mid' : 'low'
  const cityName = pretty(district.name)
  const overallStability = Math.round(100 - volatility * 70)

  const newsCount =
    tier === 'high' ? 22 + Math.round(volatility * 30) : tier === 'mid' ? 8 + Math.round(volatility * 14) : 1 + Math.round(volatility * 4)

  const acledCount = tier === 'high' ? 2 : tier === 'mid' ? 1 : 0

  return {
    id: district.id,
    name: district.name,
    facts: {
      hqCity: cityName,
      population: tier === 'low' ? '0.6M' : '0.9M',
      area: '2,400 km²',
      mlaCount: 3,
      mlaSplit:
        tier === 'high'
          ? { brs: 1, bjp: 1, inc: 1, other: 0 }
          : tier === 'mid'
            ? { brs: 2, bjp: 0, inc: 1, other: 0 }
            : { brs: 1, bjp: 1, inc: 0, other: 1 },
      notableLandmark: 'Regional administrative centre',
    },
    stability: {
      overall: overallStability,
      airQuality: tier === 'low' ? 88 : tier === 'mid' ? 70 : 52,
      heatStress: tier === 'low' ? 60 : 44,
      conflict: tier === 'low' ? 92 : tier === 'mid' ? 64 : 36,
      newsAnomaly: tier === 'low' ? 78 : tier === 'mid' ? 56 : 32,
    },
    newsHotspot: {
      count24h: newsCount,
      items:
        tier === 'low'
          ? [
              {
                source: 'Telangana Today',
                ageLabel: '6h',
                headline: `${cityName} development board review meeting — routine`,
                sentiment: 0.1,
              },
            ]
          : tier === 'mid'
            ? [
                {
                  source: 'Eenadu',
                  ageLabel: '2h',
                  headline: `${cityName} water-supply schedule revised for summer peak`,
                  sentiment: -0.1,
                },
                {
                  source: 'Sakshi',
                  ageLabel: '4h',
                  headline: `${cityName} ZP meeting clears two infrastructure proposals`,
                  sentiment: 0.3,
                },
              ]
            : [
                {
                  source: 'Eenadu',
                  ageLabel: '1h',
                  headline: `${cityName} sub-collector convenes review on summer storage`,
                  sentiment: 0.2,
                },
                {
                  source: 'Telangana Today',
                  ageLabel: '3h',
                  headline: `${cityName} farmer associations seek grain-procurement extension`,
                  sentiment: -0.3,
                },
                {
                  source: 'Deccan Chronicle',
                  ageLabel: '5h',
                  headline: `${cityName} traders flag GST compliance issues at chamber meeting`,
                  sentiment: -0.2,
                },
              ],
    },
    acled: {
      count7d: acledCount,
      events:
        acledCount === 0
          ? []
          : [
              {
                date: '30 Apr',
                type: 'Protest' as const,
                summary: `${cityName} associations demonstrate over local demands`,
              },
            ],
    },
    mandi: [
      { market: cityName, commodity: 'Paddy', price: '₹2,180/q', delta: 'flat', trend: 'flat' as const },
      { market: cityName, commodity: 'Cotton', price: '₹6,640/q', delta: '–3% vs 30d', trend: 'down' as const },
    ],
    welfare: [
      { scheme: 'Rythu Bandhu', coveragePct: 85 + Math.round(Math.random() * 10), detail: 'Current season disbursement on track' },
      { scheme: 'Aasara Pensions', coveragePct: 88, detail: 'Monthly cycle in progress' },
      { scheme: 'MGNREGA', coveragePct: tier === 'low' ? 72 : 58, detail: 'Person-days generation on schedule' },
    ],
    power: {
      demand: tier === 'low' ? '180 MW' : '320 MW',
      supply: tier === 'low' ? '180 MW' : '320 MW',
      status: 'Demand fully met. No load shedding scheduled.',
      level: 'normal',
    },
    liveMedia: {
      tvMentions:
        tier === 'low'
          ? []
          : [
              {
                channel: 'V6 News',
                timestamp: '12:30',
                snippet: `"…in ${cityName} district, the local administration is reviewing summer preparedness…"`,
              },
            ],
      channels: FALLBACK_CHANNELS,
    },
    oneliner:
      tier === 'high'
        ? `${cityName} is showing elevated activity — monitor over next 24h.`
        : tier === 'mid'
          ? `${cityName} is on the watchlist — moderate signal volume, no acute issues.`
          : `Quiet day in ${cityName} — baseline metrics nominal, no events of concern.`,
  }
}

/* ------------------------------------------------------------------ */
/* Public API                                                          */
/* ------------------------------------------------------------------ */

export function getDistrictBrief(id: string): DistrictBriefData | null {
  if (CUSTOM_DATA[id]) return CUSTOM_DATA[id]
  const district = TELANGANA_DISTRICTS.find((d) => d.id === id)
  if (!district) return null
  const vol = DISTRICTS.find((v) => v.id === id)?.volatility ?? 0.3
  return makeTemplateData(district, vol)
}

export function listDistrictIds(): string[] {
  return TELANGANA_DISTRICTS.map((d) => d.id)
}
