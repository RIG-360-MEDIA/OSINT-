/**
 * CM-focused intelligence sections — six themed text cards plus a live
 * pulse strip. Hardcoded for v1; swapping each export for a server
 * fetch later doesn't change the UI shape.
 */

/* ------------------------------------------------------------------ */
/* News on CM                                                          */
/* ------------------------------------------------------------------ */

export interface CmNewsItem {
  source: string
  ageLabel: string
  text: string
  sentiment: number
}

export const CM_NEWS: ReadonlyArray<CmNewsItem> = [
  { source: 'Eenadu', ageLabel: '23m', text: 'CM addresses Group-1 row in afternoon presser; transparency briefing scheduled.', sentiment: -0.3 },
  { source: 'The Hindu', ageLabel: '1h', text: 'High Court bench questions Hydra demolition policy; orders rehabilitation framework in 7 days.', sentiment: -0.4 },
  { source: 'Sakshi', ageLabel: '2h', text: 'Caste survey deadline extended by ten days; CMO release at 14:00.', sentiment: -0.3 },
  { source: 'Telangana Today', ageLabel: '4h', text: 'Hyderabad Metro Phase-2 ridership crosses pre-COVID baseline.', sentiment: 0.4 },
]

/* ------------------------------------------------------------------ */
/* Opposition Watch                                                    */
/* ------------------------------------------------------------------ */

export interface OppositionItem {
  actor: string
  party: 'BRS' | 'BJP' | 'INC' | 'AIMIM'
  channel: string
  ageLabel: string
  text: string
  reach?: string
}

export const CM_OPPOSITION: ReadonlyArray<OppositionItem> = [
  { actor: 'KTR', party: 'BRS', channel: 'X', ageLabel: '38m', text: 'Characterises Musi project as a scam without a rehabilitation plan.', reach: '14k engagements' },
  { actor: 'Bandi Sanjay', party: 'BJP', channel: 'press', ageLabel: '2h', text: 'Confirms Karimnagar Sunday rally — est. 8,000 attending across 14 districts.' },
  { actor: 'Harish Rao', party: 'BRS', channel: 'press desk', ageLabel: '4h', text: 'Schedules 16:00 press meet on caste-survey extension; counter-narrative drafted.' },
  { actor: 'BRS', party: 'BRS', channel: 'press release', ageLabel: '3h', text: 'Submits memorandum to Raj Bhavan on caste survey roll-out.' },
]

/* ------------------------------------------------------------------ */
/* Actions for the Chair                                               */
/* ------------------------------------------------------------------ */

export interface CmAction {
  priority: 'P0' | 'P1' | 'P2'
  text: string
  deadline?: string
}

export const CM_ACTIONS: ReadonlyArray<CmAction> = [
  { priority: 'P0', text: 'Counter Musi narrative — statement or visit', deadline: 'within 6h · before 18:00' },
  { priority: 'P0', text: 'Field visit to Khammam — cotton + farmer assembly converging', deadline: 'this week' },
  { priority: 'P1', text: 'Authorise Group-1 transparency briefing', deadline: 'before 17:30 today' },
  { priority: 'P1', text: 'Schedule Hydra policy presser', deadline: 'before 5 May BJP rally' },
  { priority: 'P2', text: 'Internal review of southern-belt heat-wave preparedness', deadline: 'by 5 May' },
]

/* ------------------------------------------------------------------ */
/* Monitor List                                                        */
/* ------------------------------------------------------------------ */

export interface MonitorItem {
  label: string
  status: string
  trend: 'up' | 'down' | 'flat' | 'live'
}

export const CM_MONITOR: ReadonlyArray<MonitorItem> = [
  { label: '@KTRBRS posting cadence', status: '↑ +23% this week', trend: 'up' },
  { label: 'Musi project mention volume', status: '↑ +18% in 24h', trend: 'up' },
  { label: 'Hydra commissioner activity', status: '↓ –5%', trend: 'down' },
  { label: 'Caste census discourse', status: '↑ +9%', trend: 'up' },
  { label: 'Khammam farmer assembly', status: '● live now · hour 4', trend: 'live' },
  { label: 'Metro Phase-2 sentiment', status: '→ +0.4 stable', trend: 'flat' },
]

/* ------------------------------------------------------------------ */
/* Threats                                                              */
/* ------------------------------------------------------------------ */

export interface ThreatItem {
  text: string
  level: 'LOW' | 'LOW-MED' | 'MED' | 'HIGH'
  /** Compact characterisation — "MED · spreading" / "LOW · monitoring". */
  posture: string
}

export const CM_THREATS: ReadonlyArray<ThreatItem> = [
  { text: 'Agrarian unrest spreading from Khammam to Mahabubabad and Bhadradri', level: 'MED', posture: 'spreading · 24h window' },
  { text: 'MLA defection rumours around three BRS MLAs ahead of budget session', level: 'LOW', posture: 'low likelihood · high impact' },
  { text: 'Communal tension chatter on Telegram channels in old Hyderabad', level: 'LOW', posture: 'monitoring · keyword anomaly' },
  { text: 'Hydra litigation could expand to rehabilitation policy challenge', level: 'LOW-MED', posture: '7-day window per HC order' },
]

/* ------------------------------------------------------------------ */
/* Future Outlook                                                      */
/* ------------------------------------------------------------------ */

export interface OutlookItem {
  when: string
  text: string
}

export const CM_OUTLOOK: ReadonlyArray<OutlookItem> = [
  { when: '4 May · Sun', text: 'BJP Karimnagar rally — est. 8,000. Set agenda before. Counter-window closes Sat 23:59.' },
  { when: '5–6 May', text: 'Opposition push expected to peak; statewide sentiment forecast –0.41 ± 0.06.' },
  { when: '5 May', text: 'Heat-wave advisory peak in southern districts. Visible disaster preparedness statement advisable.' },
  { when: '8 May · 7-day', text: 'Voice-share forecast: BRS 42% (+1pp), BJP 23% (+1pp), INC 35% (–2pp).' },
]

/* ------------------------------------------------------------------ */
/* Live Pulse                                                          */
/* ------------------------------------------------------------------ */

export interface CmPulseMetric {
  label: string
  value: string
  delta?: string
  trend?: 'up' | 'down' | 'flat'
}

/* ------------------------------------------------------------------ */
/* Analysis column — pure editorial prose, structured like a column.   */
/* ------------------------------------------------------------------ */

export interface CmAnalysis {
  /** "Analysis · 14:37 IST" — the kicker. */
  eyebrow: string
  /** "By the Strategy Desk" — byline. */
  byline: string
  /** Big serif title. */
  headline: string
  /** Italic deck (1 line, 12-22 words). */
  deck: string
  /** Body paragraphs — 4 to 6 short paragraphs. */
  paragraphs: ReadonlyArray<string>
  /** Mid-piece pull-quote. */
  pullQuote: string
  /** End-note line at the foot. */
  endnote: string
}

export const CM_ANALYSIS: CmAnalysis = {
  eyebrow: 'Analysis · 14:37 IST',
  byline: 'By the Strategy Desk',
  headline: 'The Musi window closes today.',
  deck: 'Three desks have flagged it; what the next six hours reveal will set the next seven days.',
  paragraphs: [
    'The Musi rehabilitation story has been simmering for nearly three weeks. It consolidated overnight, when four of the six most-shared posts in Telangana turned critical of the project, three of them syndicated by BRS-aligned handles. By midday, three mainstream dailies had adopted the framing.',
    'The sequence matters. BRS desks took the lead, but it is the BJP that found the symbolic opening — not on the project itself but on the absence of a published rehabilitation plan. That gap is the gravitational centre of every critical post the system has surfaced today.',
    'Counter-narratives die in the absence of evidence. The Group-1 transparency briefing scheduled for 17:30 will read, on its arrival, either as substance or as misdirection. The window for the former closes by 18:00; after that, the day belongs to whoever owns the silence.',
    'Khammam is not Musi, but in the public imagination both are now in the same ledger. The cotton procurement delays — four weeks running — supply the second beat to a story the opposition has already rehearsed. A field visit this week is no longer optional.',
    'The eighteen-hundred-hour cliff matters less, ultimately, than the seven days that follow. By Sunday in Karimnagar, the BJP rally will set a new frame for north Telangana. Today’s response is the only lever we still have to bend that arc.',
  ],
  pullQuote: 'Counter-narratives die in the absence of evidence. By 18:00, the day belongs to whoever owns the silence.',
  endnote: 'Filed 14:37 IST · revisable upon CMO release · circulation: principal secretariat',
}

export const CM_PULSE: ReadonlyArray<CmPulseMetric> = [
  { label: 'Mentions / hour', value: '312', delta: '▲ +14% vs avg', trend: 'up' },
  { label: 'Statewide sentiment', value: '–0.34', delta: '▼ –0.08 since 09:00', trend: 'down' },
  { label: 'Active alerts', value: '3', delta: 'P0 · P1 · P1', trend: 'flat' },
  { label: 'Opposition voice-share', value: 'BRS 41%', delta: '▲ +6pp', trend: 'up' },
  { label: 'Counter-narrative window', value: '4h', delta: 'closes 18:00', trend: 'down' },
  { label: 'Last refresh', value: '14:37', delta: '6h forecast cycle', trend: 'flat' },
]
