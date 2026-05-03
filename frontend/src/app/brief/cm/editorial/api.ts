/**
 * Typed fetch helpers for the CM Page v2 read API.
 *
 * Every helper points at one endpoint on `cm_v2_router`. The shape of
 * each response mirrors a Pydantic model in
 * `backend/routers/cm_v2_schemas.py`. We do not validate on the client
 * — TypeScript types are advisory; the server contract is the source
 * of truth. If the server returns 5xx the helper rejects, and the
 * caller's React Query hook decides whether to swap in demo data.
 *
 * Auth: every call goes through `apiFetch` (sibling helper) which
 * forwards the Supabase access token. The CM-page endpoints are gated
 * by `require_page("worldmonitor")` server-side.
 */

import type {
  CmAction,
  CmAnalysis,
  CmNewsItem,
  CmPulseMetric,
  MonitorItem,
  OppositionItem,
  OutlookItem,
  ThreatItem,
} from './cm-intel-data'
import type { Headline, TickerEvent } from './data'

const API_BASE_PROD =
  (typeof process !== 'undefined' && process.env?.NEXT_PUBLIC_API_URL) || ''

/** Supabase Bearer token getter — mirrors the pattern used elsewhere
 *  in the brief page (createClient from @/lib/supabase/client → getSession).
 *  Cached for the lifetime of the page so we don't hit IndexedDB on
 *  every poll tick. */
let _cachedToken: string | null = null
let _tokenExpiry = 0
async function getAccessToken(): Promise<string | null> {
  const now = Date.now()
  if (_cachedToken && now < _tokenExpiry) return _cachedToken
  // Browser-only — bail out cleanly during SSR / build.
  if (typeof window === 'undefined') return null
  try {
    // Lazy dynamic import — keeps the supabase client out of the
    // module init path so any error during its load can't crash the
    // page bundle.
    const mod = await import('@/lib/supabase/client')
    const supabase = mod.createClient()
    const { data } = await supabase.auth.getSession()
    const token = data?.session?.access_token ?? null
    if (token) {
      _cachedToken = token
      _tokenExpiry = now + 50 * 60_000
    }
    return token
  } catch {
    return null
  }
}

/** Compact wrapper around `fetch` that:
 *   - includes credentials (Supabase cookie) so the require_page gate works
 *   - throws on non-2xx so React Query treats the call as errored
 *   - times out after 12s (the slowest endpoint, /atlas/layer/stability_composite,
 *     should respond well within this budget)
 */
async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const url = `${API_BASE_PROD}/api/cm${path}`
  const ctrl = new AbortController()
  const t = setTimeout(() => ctrl.abort(), 12000)
  const sig = signal ?? ctrl.signal
  const token = await getAccessToken()
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  try {
    const resp = await fetch(url, {
      cache: 'no-store',
      credentials: 'include',
      headers,
      signal: sig,
    })
    if (!resp.ok) {
      throw new Error(`CM API ${path} failed: ${resp.status} ${resp.statusText}`)
    }
    return (await resp.json()) as T
  } finally {
    clearTimeout(t)
  }
}

/* ------------------------------------------------------------------ */
/* Response shapes — mirror cm_v2_schemas.py                          */
/* ------------------------------------------------------------------ */

export interface MetaInfo {
  /** ISO timestamp of the underlying source row, NOT cache freshness. */
  generated_at?: string | null
  /** 'fresh' / 'stale' / 'empty' / 'error'. The router fills this. */
  status: 'fresh' | 'stale' | 'empty' | 'error'
  /** Optional human-readable reason for stale / error states. */
  note?: string | null
}

export interface LeadResponse {
  meta: MetaInfo
  headlines: ReadonlyArray<Headline>
}

export interface NewsOnChairResponse {
  meta: MetaInfo
  items: ReadonlyArray<CmNewsItem>
}

export interface OppositionWatchResponse {
  meta: MetaInfo
  items: ReadonlyArray<OppositionItem>
}

export interface ThreatsResponse {
  meta: MetaInfo
  items: ReadonlyArray<ThreatItem>
}

export interface OutlookResponse {
  meta: MetaInfo
  items: ReadonlyArray<OutlookItem>
}

export interface MonitorResponse {
  meta: MetaInfo
  items: ReadonlyArray<MonitorItem>
}

export interface LivePulseResponse {
  meta: MetaInfo
  metrics: ReadonlyArray<CmPulseMetric>
}

export interface ActionsResponse {
  meta: MetaInfo
  items: ReadonlyArray<CmAction>
}

export interface AnalysisResponse {
  meta: MetaInfo
  /** Null when no published draft exists yet. */
  column: CmAnalysis | null
}

export interface AtlasLayerCell {
  district_id: string
  /** 0..1 normalised value for choropleth fill. */
  value: number
  /** Optional raw value (count, percentage, °C, MW, etc) for tooltip. */
  raw?: number | null
  /** Optional label / unit, e.g. "8 events" or "AQI 220". */
  label?: string | null
}

export interface AtlasLayerResponse {
  meta: MetaInfo
  layer_id: string
  cells: ReadonlyArray<AtlasLayerCell>
}

export interface DistrictBriefResponse {
  meta: MetaInfo
  district_id: string
  name: string
  news: ReadonlyArray<CmNewsItem>
  opposition: ReadonlyArray<OppositionItem>
  monitor: ReadonlyArray<MonitorItem>
  threats: ReadonlyArray<ThreatItem>
}

export interface TickerResponse {
  meta: MetaInfo
  events: ReadonlyArray<TickerEvent>
}

/* ------------------------------------------------------------------ */
/* Endpoint helpers                                                   */
/* ------------------------------------------------------------------ */

export function fetchLead(state: string = 'TG', signal?: AbortSignal): Promise<LeadResponse> {
  return apiGet<LeadResponse>(`/lead?state=${encodeURIComponent(state)}`, signal)
}

export function fetchNewsOnChair(state: string = 'TG', signal?: AbortSignal): Promise<NewsOnChairResponse> {
  return apiGet<NewsOnChairResponse>(`/news_on_chair?state=${encodeURIComponent(state)}`, signal)
}

export function fetchOpposition(state: string = 'TG', signal?: AbortSignal): Promise<OppositionWatchResponse> {
  return apiGet<OppositionWatchResponse>(`/opposition_watch?state=${encodeURIComponent(state)}`, signal)
}

export function fetchThreats(state: string = 'TG', signal?: AbortSignal): Promise<ThreatsResponse> {
  return apiGet<ThreatsResponse>(`/threats?state=${encodeURIComponent(state)}`, signal)
}

export function fetchOutlook(state: string = 'TG', signal?: AbortSignal): Promise<OutlookResponse> {
  return apiGet<OutlookResponse>(`/outlook?state=${encodeURIComponent(state)}`, signal)
}

export function fetchMonitor(state: string = 'TG', signal?: AbortSignal): Promise<MonitorResponse> {
  return apiGet<MonitorResponse>(`/monitor?state=${encodeURIComponent(state)}`, signal)
}

export function fetchLivePulse(state: string = 'TG', signal?: AbortSignal): Promise<LivePulseResponse> {
  return apiGet<LivePulseResponse>(`/live_pulse?state=${encodeURIComponent(state)}`, signal)
}

export function fetchActions(state: string = 'TG', signal?: AbortSignal): Promise<ActionsResponse> {
  return apiGet<ActionsResponse>(`/actions?state=${encodeURIComponent(state)}`, signal)
}

export function fetchAnalysis(state: string = 'TG', signal?: AbortSignal): Promise<AnalysisResponse> {
  return apiGet<AnalysisResponse>(`/analysis?state=${encodeURIComponent(state)}`, signal)
}

export function fetchAtlasLayer(
  layerId: string,
  state: string = 'TG',
  signal?: AbortSignal,
): Promise<AtlasLayerResponse> {
  const path = `/atlas/layer/${encodeURIComponent(layerId)}?state=${encodeURIComponent(state)}`
  return apiGet<AtlasLayerResponse>(path, signal)
}

export function fetchDistrict(
  districtId: string,
  state: string = 'TG',
  signal?: AbortSignal,
): Promise<DistrictBriefResponse> {
  const path = `/district/${encodeURIComponent(districtId)}?state=${encodeURIComponent(state)}`
  return apiGet<DistrictBriefResponse>(path, signal)
}

export function fetchTicker(state: string = 'TG', signal?: AbortSignal): Promise<TickerResponse> {
  return apiGet<TickerResponse>(`/ticker?state=${encodeURIComponent(state)}`, signal)
}
