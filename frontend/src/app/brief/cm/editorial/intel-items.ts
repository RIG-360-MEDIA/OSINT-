/**
 * Live intelligence feed items.
 *
 * Each item is one card in the Intelligence Feed — a single piece of
 * incoming intel: when, where, what category, what priority, the
 * actual statement, and where it came from. No charts, no widgets.
 * Simple text. Hardcoded for v1; the live system replaces this list
 * with a streamed feed and the UI doesn't change.
 */

export type IntelCategory =
  | 'BREAKING'
  | 'ALERT'
  | 'WATCH'
  | 'COURT'
  | 'OPPOSITION'
  | 'POLITICAL'
  | 'POWER'
  | 'WEATHER'
  | 'MARKET'
  | 'WELFARE'
  | 'LABOUR'
  | 'METRO'
  | 'INDUSTRIAL'
  | 'POSITIVE'
  | 'INTEL'
  | 'ACTION'

export type IntelPriority = 'P0' | 'P1' | 'P2' | 'INFO'

export interface IntelItem {
  /** Local time stamp shown on the card. */
  time: string
  /** District or "Statewide". */
  district: string
  category: IntelCategory
  priority: IntelPriority
  /** The intelligence statement — 2-3 lines, plain editorial sentences. */
  text: string
  /** Where the signal came from — outlet, desk, dashboard, etc. */
  source: string
}

export const INTEL_FEED: ReadonlyArray<IntelItem> = [
  {
    time: '14:36',
    district: 'Khammam',
    category: 'BREAKING',
    priority: 'P0',
    text: 'Farmer assembly enters fourth hour at district HQ — district administration silent on response.',
    source: 'Telangana Today · 412 mentions',
  },
  {
    time: '14:34',
    district: 'Hyderabad',
    category: 'ALERT',
    priority: 'P0',
    text: 'Musi narrative consolidating — four of the six most-shared posts in Telangana today are critical of the project, three syndicated by BRS-aligned handles.',
    source: 'aggregated · 8 outlets · reach 1.2M',
  },
  {
    time: '14:31',
    district: 'Statewide',
    category: 'ACTION',
    priority: 'P0',
    text: 'For the Chair: counter-Musi narrative window closes by 18:00 today. Statement or visit window narrowing.',
    source: 'CM strategy desk',
  },
  {
    time: '14:28',
    district: 'Karimnagar',
    category: 'WATCH',
    priority: 'P1',
    text: 'BJP Sunday rally now estimated at 8,000 attending. Bus permits requested across 14 districts.',
    source: 'Eenadu · field',
  },
  {
    time: '14:22',
    district: 'Hyderabad',
    category: 'COURT',
    priority: 'P1',
    text: 'High Court bench questions Hydra demolition policy. Orders state to clarify rehabilitation framework within seven days.',
    source: 'NDTV · The Hindu',
  },
  {
    time: '14:18',
    district: 'Khammam',
    category: 'ALERT',
    priority: 'P0',
    text: 'Cotton procurement delays now four weeks running. Pushback widening to Mahabubabad and Bhadradri.',
    source: 'Sakshi · field',
  },
  {
    time: '14:09',
    district: 'Statewide',
    category: 'POLITICAL',
    priority: 'P1',
    text: 'Caste-survey extension by ten days announced. Opposition desks already framing it as a stalling tactic.',
    source: 'CMO release · 14:00',
  },
  {
    time: '13:54',
    district: 'Hyderabad',
    category: 'OPPOSITION',
    priority: 'P1',
    text: 'Harish Rao schedules 16:00 press meet on caste-survey extension. Counter-narrative draft circulating.',
    source: 'BRS press desk',
  },
  {
    time: '13:42',
    district: 'Bhadradri',
    category: 'POWER',
    priority: 'P2',
    text: 'Feeder margin dropped to 2 MW. Advisory issued for industrial cluster ahead of 19:00 peak window.',
    source: 'TS Transco',
  },
  {
    time: '13:30',
    district: 'Warangal',
    category: 'LABOUR',
    priority: 'P2',
    text: 'Kakatiya University non-teaching staff give 72-hour PRC arrears ultimatum. Strike vote pending.',
    source: 'TV5',
  },
  {
    time: '13:22',
    district: 'Hyderabad',
    category: 'METRO',
    priority: 'INFO',
    text: 'Phase-2 ridership crosses pre-COVID baseline. Sentiment +0.4 across three outlets — quiet positive.',
    source: 'HMRL',
  },
  {
    time: '13:08',
    district: 'Karimnagar',
    category: 'INDUSTRIAL',
    priority: 'P2',
    text: 'Granite mine safety inspection ordered following weekend fatal incident. Worker associations watching.',
    source: 'Eenadu',
  },
  {
    time: '12:54',
    district: 'Mahbubnagar',
    category: 'WEATHER',
    priority: 'P1',
    text: 'IMD heat-wave advisory for southern belt — Mahbubnagar, Nagarkurnool, Wanaparthy — through 5 May.',
    source: 'IMD bulletin',
  },
  {
    time: '12:40',
    district: 'Khammam',
    category: 'WELFARE',
    priority: 'P1',
    text: 'MGNREGA payment delays flagged in 18 gram panchayats. Scheme coverage drops to 64% in district.',
    source: 'NREGA dashboard',
  },
  {
    time: '12:18',
    district: 'Warangal',
    category: 'POSITIVE',
    priority: 'INFO',
    text: 'Kakatiya Mega Textile Park phase-2 inaugurated. 1,200 jobs, sentiment +0.5 across three outlets.',
    source: 'Telangana Today',
  },
  {
    time: '12:02',
    district: 'Statewide',
    category: 'INTEL',
    priority: 'INFO',
    text: 'Reservoir levels — Nagarjuna Sagar 76%, Srisailam 81%, Mid Manair 82%. All within seasonal norm.',
    source: 'TSWRA',
  },
  {
    time: '11:48',
    district: 'Hyderabad',
    category: 'OPPOSITION',
    priority: 'P1',
    text: 'KTR characterises Musi project as a scam without a rehabilitation plan. 14k engagements in 90 minutes.',
    source: 'X · KTR official',
  },
  {
    time: '11:32',
    district: 'Statewide',
    category: 'ACTION',
    priority: 'P1',
    text: 'For the Chair: field visit to Khammam this week. Cotton + farmer assembly converging — visible response advisable.',
    source: 'CM strategy desk',
  },
]
