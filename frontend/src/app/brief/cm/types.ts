/**
 * CM Page TypeScript interfaces — mirror of backend/routers/cm_schemas.py.
 *
 * Renames or removed fields here MUST be coordinated with the Pydantic
 * schemas. Adding optional fields is non-breaking.
 */

export type Stance =
  | 'ruling_supportive'
  | 'opposition_attack'
  | 'neutral_factual'
  | 'mixed'
  | 'unknown'

export type PartyKind = 'ruling' | 'opposition' | 'neutral'
export type Trajectory = 'intensifying' | 'steady' | 'fading' | 'unknown'
export type PromiseStatus = 'kept' | 'in_progress' | 'stalled' | 'broken' | 'unknown'
export type RiskKind =
  | 'court'
  | 'parliament'
  | 'festival'
  | 'by_election'
  | 'anniversary'
  | 'deadline'
  | 'protest'
  | 'session'
export type RiskLevel = 'low' | 'med' | 'high'
export type DissentSeverity = 'murmur' | 'crack' | 'break'
export type SilenceSeverity = 'watch' | 'warn' | 'critical'

export interface QuoteRef {
  speaker: string
  party?: string | null
  role?: string | null
  quote: string
  source_url?: string | null
  source_kind?: string | null
  captured_at?: string | null
}

export interface StanceTriad {
  ruling: number
  opposition: number
  neutral: number
  n_ruling: number
  n_opposition: number
  n_neutral: number
}

// I — Pulse
export interface TopicPulse {
  topic: string
  score: number
  delta_7d: number
  n: number
}
export interface RegionPulse {
  region: string
  score: number
  delta_7d: number
  n: number
}
export interface PulseResponse {
  state: string | null
  window: string
  overall: TopicPulse
  by_topic: TopicPulse[]
  by_region: RegionPulse[]
  sample_size: number
  computed_at: string
  cache_hit: boolean
}

// II — Issues
export interface PartyStance {
  party: string
  stance: 'defend' | 'attack' | 'silent' | 'ambiguous'
  confidence: number
}
export interface IssueCard {
  id: number
  label: string
  slug: string
  intensity: number
  intensity_delta_24h: number
  last_mention_at: string | null
  ruling_summary: string | null
  opposition_summary: string | null
  neutral_summary: string | null
  stances: StanceTriad
  party_stances: PartyStance[]
  top_quotes: QuoteRef[]
  evidence_count: number
  trajectory: Trajectory
}
export interface IssuesResponse {
  state: string | null
  issues: IssueCard[]
  generated_at: string
  cache_hit: boolean
}

// III — Silence
export interface SilenceItem {
  issue_id: number | null
  label: string
  started_at: string | null
  age_hours: number
  public_volume_7d: number
  govt_mentions_7d: number
  days_since_govt_statement: number | null
  ministers_named: string[]
  severity: SilenceSeverity
  sample_evidence: QuoteRef[]
}
export interface SilenceResponse {
  state: string | null
  items: SilenceItem[]
  generated_at: string
  cache_hit: boolean
}

// IV — Spokespersons
export interface SpokespersonRow {
  speaker: string
  party?: string | null
  role?: string | null
  score: number
  mentions_24h: number
  mentions_7d: number
  delta_pct: number
  avg_sentiment: number
  on_message_rate?: number | null
  top_topics: string[]
  latest_quote?: QuoteRef | null
}
export interface SpokespersonsResponse {
  state: string | null
  mode: 'attackers' | 'on-message'
  rows: SpokespersonRow[]
  generated_at: string
  cache_hit: boolean
}

// V — Dissent
export interface DissentMember {
  speaker: string
  party: string
  quote: QuoteRef
}
export interface DissentSignal {
  id: number
  coalition: PartyKind
  party: string
  faction?: string | null
  headline: string
  severity: DissentSeverity
  confidence: number
  members: DissentMember[]
  issue_id?: number | null
  evidence_urls: string[]
  detected_at: string
}
export interface DissentResponse {
  state: string | null
  ruling: DissentSignal[]
  opposition: DissentSignal[]
  generated_at: string
  cache_hit: boolean
}

// VI — Trajectory
export interface TrajectoryPoint {
  issue_id: number
  label: string
  series_volume: number[]
  series_sentiment: number[]
  classification: Trajectory
  slope: number
  delta_24h: number
}
export interface TrajectoryResponse {
  state: string | null
  rows: TrajectoryPoint[]
  days: number
  generated_at: string
  cache_hit: boolean
}

// VII — Heatmap
export interface HeatmapCell {
  constituency_code: string
  constituency_name: string
  state: string
  score: number
  volume: number
  top_issue_ids: number[]
}
export interface HeatmapResponse {
  state: string | null
  cells: HeatmapCell[]
  generated_at: string
  cache_hit: boolean
}

// VIII — Promises
export interface PromiseRow {
  id: number
  pledge_text: string
  pledge_short?: string | null
  owner_party: string
  deadline?: string | null
  status: PromiseStatus
  status_confidence?: number | null
  last_status_change: string
  exploitation_index: number
  source_url?: string | null
  last_evidence_url?: string | null
}
export interface PromisesResponse {
  state: string | null
  rows: PromiseRow[]
  generated_at: string
  cache_hit: boolean
}

// IX — Counter-narratives
export interface CounterNarrativeBullet {
  text: string
  cites: string[]                                   // UUIDs of grounding articles
}
export interface CounterNarrativeCard {
  issue_id: number
  issue_label: string
  talking_points: CounterNarrativeBullet[]
  grounding_doc_ids: string[]                       // UUIDs
  grounding_kinds: string[]
  generated_at: string
  model: string
  is_draft: boolean
}
export interface CounterNarrativesResponse {
  state: string | null
  cards: CounterNarrativeCard[]
  generated_at: string
  cache_hit: boolean
}

// X — Risk window
export interface RiskEvent {
  id: number
  event_date: string
  state?: string | null
  kind: RiskKind
  title: string
  description?: string | null
  risk_summary?: string | null
  risk_level: RiskLevel
  source_url?: string | null
}
export interface RiskWindowResponse {
  state: string | null
  days: number
  events: RiskEvent[]
  generated_at: string
  cache_hit: boolean
}

// XI — Quotes
export interface QuoteRow {
  id?: number | null
  speaker: string
  party?: string | null
  role?: string | null
  quote: string
  quote_lang?: string | null
  issue_id?: number | null
  sentiment?: number | null
  stance?: Stance | null
  source_url?: string | null
  source_kind?: string | null
  captured_at?: string | null
}
export interface QuotesResponse {
  state: string | null
  rows: QuoteRow[]
  generated_at: string
  cache_hit: boolean
}

// XII — Voice share
export interface VoiceShareRow {
  speaker: string
  party?: string | null
  share_24h_pct: number
  share_7d_pct: number
  delta_pct: number
  mentions_24h: number
  mentions_7d: number
}
export interface VoiceShareResponse {
  state: string | null
  rows: VoiceShareRow[]
  generated_at: string
  cache_hit: boolean
}

// XIII / XIV — Divergence
export interface DivergenceRow {
  topic: string
  side_a_label: string
  side_b_label: string
  score_a: number
  score_b: number
  delta: number
  flagged: boolean
  sample_a: QuoteRef[]
  sample_b: QuoteRef[]
}
export interface DivergenceResponse {
  state: string | null
  kind: 'language' | 'medium'
  rows: DivergenceRow[]
  generated_at: string
  cache_hit: boolean
}

// Aggregator
export interface CMDashboardResponse {
  state: string | null
  pulse?: PulseResponse | null
  issues?: IssuesResponse | null
  silence?: SilenceResponse | null
  spokespersons?: SpokespersonsResponse | null
  cabinet_onmessage?: SpokespersonsResponse | null
  dissent?: DissentResponse | null
  trajectory?: TrajectoryResponse | null
  heatmap?: HeatmapResponse | null
  promises?: PromisesResponse | null
  counter_narratives?: CounterNarrativesResponse | null
  risk_window?: RiskWindowResponse | null
  quotes?: QuotesResponse | null
  voice_share?: VoiceShareResponse | null
  language_divergence?: DivergenceResponse | null
  medium_divergence?: DivergenceResponse | null
  section_errors: Record<string, string>
  generated_at: string
  cache_hit: boolean
}

export type CMSectionName =
  | 'pulse'
  | 'issues'
  | 'silence'
  | 'spokespersons'
  | 'cabinet_onmessage'
  | 'dissent'
  | 'trajectory'
  | 'heatmap'
  | 'promises'
  | 'counter_narratives'
  | 'risk_window'
  | 'quotes'
  | 'voice_share'
  | 'language_divergence'
  | 'medium_divergence'
