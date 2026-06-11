/**
 * Typed fetch helpers for /api/observe/*.
 *
 * Every call carries the supabase session cookie automatically because the
 * backend reads it from the same domain via `credentials: 'include'`.
 *
 * Polling intervals follow the plan: 5s when tab visible, 30s when hidden.
 */
import { createClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

// ── Shared types ───────────────────────────────────────────────────────────

export interface IngestPulse {
  by_hour: Array<{ hour: string; n: number }>
  per_source: Array<{
    source: string
    last_seen: string | null
    n_24h: number
    hours_since: number
  }>
  stalled_sources: Array<{ source: string; last_seen: string | null; hours_since: number }>
  total_24h: number
}

export interface SourceScorecard {
  sources: Array<{
    source: string
    total: number
    v3_ok: number
    has_summary_pct: number
    has_embedding_pct: number
    languages: number
    last_seen: string | null
  }>
}

export interface QualityMonitor {
  judge: {
    sampled: number
    successes: number
    errors: number
    median_scores: Record<string, number>
    p25_scores: Record<string, number>
    source_file?: string
  } | null
  regression: {
    ran_at: string
    gold_size: number
    matched: number
    passed: boolean
    failures: Record<string, number>
    info: Record<string, number>
    source_file?: string
  } | null
  live: {
    v3_ok_total: number
    cliff_500: number
    cliff_1000: number
    null_subject: number
    thin_summary: number
    thin_summary_pct: number
    null_embedding: number
    claims_placeholder: number
    claims_placeholder_pct: number
    claims_total: number
  }
}

export interface GeoHeatmap {
  level: 'country' | 'state' | 'district'
  regions: Array<{ region: string; n: number }>
}

export interface StoryPulse {
  clusters: Array<{
    cluster_id: string
    headline: string
    event_type: string | null
    article_count: number
    source_count: number
    new_24h: number
    importance: number | null
    last_updated: string | null
  }>
}

export interface CrossTab {
  actor: string | null
  rows: Array<{ source: string; week: string | null; n_events: number; n_articles: number }>
}

export interface LiveTail {
  next_cursor: string | null
  articles: Array<{
    aid: string
    source: string
    title: string
    lang: string | null
    collected_at: string | null
    substrate_status: string | null
    extraction_version: number
    summary_len: number
  }>
}

export interface CorpusOverview {
  total_articles: number
  v3_articles: number
  total_sources: number
  languages: number
  articles_24h: number
  active_stories: number
  total_claims: number
  total_quotes: number
  total_events: number
  total_locations: number
}

export interface PipelineHealth {
  t4_backfill: {
    completed: number
    target: number
    pct: number
    running: boolean
  }
  v3_upgrade: {
    v3: number
    v2: number
    pct_v3: number
  }
  latest_regression: {
    passed: boolean
    matched: number
    gold_size: number
    failures: Record<string, number>
    source_file?: string
  } | null
}

export interface BreakingNow {
  items: Array<{
    aid: string
    title: string
    subject: string
    source: string
    lang: string | null
    collected_at: string | null
  }>
}

export interface TopSpeakers {
  speakers: Array<{
    speaker: string
    n_quotes: number
    n_sources: number
    sample_quote: string | null
  }>
}

export interface ArticleTypes {
  article_types: Array<{ type: string; n: number }>
  languages_24h: Array<{ lang: string; n: number }>
  stances: Array<{ stance: string; n: number }>
  top_countries: Array<{ country: string; n: number }>
  entity_dictionary: {
    total: number
    people: number
    locations: number
    orgs: number
    constituencies: number
  }
}

export interface Trending {
  entities: Array<{
    entity: string
    mentions_today: number
    sources_today: number
    baseline_avg: number
    surge_ratio: number | null
    is_new: boolean
    is_surging: boolean
  }>
}

export interface AuditQueue {
  queue: Array<{
    aid: string
    flag: string
    hint: string
    source: string
    title: string
    collected_at: string | null
    existing_verdict: 'correct' | 'wrong' | 'unsure' | null
  }>
}

export type Verdict = 'correct' | 'wrong' | 'unsure'

export interface AuditDecisionBody {
  article_id: string
  field_name: string
  extraction_version: number
  verdict: Verdict
  note?: string | null
}

// ── Fetch helpers ──────────────────────────────────────────────────────────

async function authHeaders(): Promise<HeadersInit> {
  const supabase = createClient()
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function getJson<T>(path: string): Promise<T> {
  const headers = await authHeaders()
  const r = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    headers,
  })
  if (!r.ok) {
    throw new Error(`${r.status} ${r.statusText} on ${path}`)
  }
  return r.json() as Promise<T>
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const headers = await authHeaders()
  const r = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    throw new Error(`${r.status} ${r.statusText} on ${path}`)
  }
  return r.json() as Promise<T>
}

// ── Endpoint wrappers ──────────────────────────────────────────────────────

export const observeApi = {
  ingestPulse: () => getJson<IngestPulse>('/api/observe/ingest-pulse'),
  sourceScorecard: () => getJson<SourceScorecard>('/api/observe/source-scorecard'),
  qualityMonitor: () => getJson<QualityMonitor>('/api/observe/quality-monitor'),
  geoHeatmap: (level: 'country' | 'state' | 'district' = 'country') =>
    getJson<GeoHeatmap>(`/api/observe/geo-heatmap?level=${level}`),
  storyPulse: (limit = 30) => getJson<StoryPulse>(`/api/observe/story-pulse?limit=${limit}`),
  crossTab: (actor: string, days = 30) =>
    getJson<CrossTab>(
      `/api/observe/crosstab?actor=${encodeURIComponent(actor)}&time_window_days=${days}`
    ),
  liveTail: (after?: string, limit = 50) => {
    const q = new URLSearchParams({ limit: String(limit) })
    if (after) q.set('after', after)
    return getJson<LiveTail>(`/api/observe/live-tail?${q.toString()}`)
  },
  auditQueue: (limit = 30) => getJson<AuditQueue>(`/api/observe/audit-queue?limit=${limit}`),
  auditDecision: (body: AuditDecisionBody) =>
    postJson<{ ok: true; id: string; decided_at: string }>(
      '/api/observe/audit-decision',
      body
    ),
  corpusOverview: () => getJson<CorpusOverview>('/api/observe/corpus-overview'),
  pipelineHealth: () => getJson<PipelineHealth>('/api/observe/pipeline-health'),
  trending: (limit = 25) => getJson<Trending>(`/api/observe/trending?limit=${limit}`),
  breakingNow: (limit = 12) => getJson<BreakingNow>(`/api/observe/breaking-now?limit=${limit}`),
  topSpeakers: (limit = 15) => getJson<TopSpeakers>(`/api/observe/top-speakers?limit=${limit}`),
  articleTypes: () => getJson<ArticleTypes>('/api/observe/article-types'),
}
