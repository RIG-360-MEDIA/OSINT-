/**
 * Polling hooks for the CM Page v2 — zero-dep, React-only.
 *
 * The wider repo does not yet bundle React Query, so introducing a
 * QueryClientProvider just for these panels would mean wiring it into
 * the app shell — out of scope for this slice. Instead each hook is a
 * thin `useEffect`-based fetcher that:
 *
 *   - fires once on mount
 *   - polls on the cadence in CADENCE (matches server-side cm_cache TTL)
 *   - cancels on unmount via AbortController
 *   - exposes { data, isLoading, isError, error, refresh, mode }
 *
 * The shape mirrors the slice of React Query we'd want — easy swap-in
 * later. `panelMode` keeps the empty / stale / error fallback logic in
 * one place.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import {
  fetchActions,
  fetchAnalysis,
  fetchAtlasLayer,
  fetchDistrict,
  fetchLead,
  fetchLivePulse,
  fetchMonitor,
  fetchNewsOnChair,
  fetchOpposition,
  fetchOutlook,
  fetchThreats,
  fetchTicker,
  type ActionsResponse,
  type AnalysisResponse,
  type AtlasLayerResponse,
  type DistrictBriefResponse,
  type LeadResponse,
  type LivePulseResponse,
  type MonitorResponse,
  type NewsOnChairResponse,
  type OppositionWatchResponse,
  type OutlookResponse,
  type ThreatsResponse,
  type TickerResponse,
} from './api'

const DEFAULT_STATE = 'TG'

/** Refetch cadences (ms). Stay >= cm_cache server TTL. */
const CADENCE = {
  lead: 60_000,
  newsOnChair: 90_000,
  opposition: 120_000,
  threats: 5 * 60_000,
  outlook: 10 * 60_000,
  monitor: 60_000,
  livePulse: 30_000,
  actions: 60_000,
  analysis: 5 * 60_000,
  atlasLayer: 60_000,
  district: 60_000,
  ticker: 30_000,
} as const

export interface PollResult<T> {
  data: T | undefined
  isLoading: boolean
  isError: boolean
  error: Error | null
  /** Manually re-fetch outside the cadence. */
  refresh: () => void
}

interface PollOpts {
  state?: string
  enabled?: boolean
}

/** Generic polling primitive. */
function usePollingFetch<T>(
  key: string,
  fetcher: (signal: AbortSignal) => Promise<T>,
  intervalMs: number,
  enabled: boolean,
): PollResult<T> {
  const [data, setData] = useState<T | undefined>(undefined)
  const [isLoading, setLoading] = useState<boolean>(enabled)
  const [error, setError] = useState<Error | null>(null)
  const aliveRef = useRef<boolean>(true)
  const ctrlRef = useRef<AbortController | null>(null)

  const run = useCallback(async () => {
    if (!enabled) return
    if (ctrlRef.current) ctrlRef.current.abort()
    const ctrl = new AbortController()
    ctrlRef.current = ctrl
    try {
      const next = await fetcher(ctrl.signal)
      if (aliveRef.current && !ctrl.signal.aborted) {
        setData(next)
        setError(null)
        setLoading(false)
      }
    } catch (err: unknown) {
      // AbortError = component unmount or stale call; ignore.
      if (err instanceof Error && err.name === 'AbortError') return
      if (aliveRef.current) {
        setError(err instanceof Error ? err : new Error(String(err)))
        setLoading(false)
      }
    }
  }, [fetcher, enabled])

  useEffect(() => {
    aliveRef.current = true
    if (!enabled) {
      setLoading(false)
      return () => {
        aliveRef.current = false
      }
    }
    void run()
    const id = window.setInterval(() => {
      void run()
    }, intervalMs)
    return () => {
      aliveRef.current = false
      window.clearInterval(id)
      if (ctrlRef.current) ctrlRef.current.abort()
    }
    // `key` is part of dependency so a layerId / districtId change re-runs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, intervalMs, enabled])

  return { data, isLoading, isError: error !== null, error, refresh: run }
}

/* ------------------------------------------------------------------ */
/* Per-panel hooks                                                     */
/* ------------------------------------------------------------------ */

export function useCMLead(opts: PollOpts = {}): PollResult<LeadResponse> {
  const state = opts.state ?? DEFAULT_STATE
  return usePollingFetch(
    `cm/lead/${state}`,
    (signal) => fetchLead(state, signal),
    CADENCE.lead,
    opts.enabled ?? true,
  )
}

export function useCMNewsOnChair(opts: PollOpts = {}): PollResult<NewsOnChairResponse> {
  const state = opts.state ?? DEFAULT_STATE
  return usePollingFetch(
    `cm/news_on_chair/${state}`,
    (signal) => fetchNewsOnChair(state, signal),
    CADENCE.newsOnChair,
    opts.enabled ?? true,
  )
}

export function useCMOpposition(opts: PollOpts = {}): PollResult<OppositionWatchResponse> {
  const state = opts.state ?? DEFAULT_STATE
  return usePollingFetch(
    `cm/opposition/${state}`,
    (signal) => fetchOpposition(state, signal),
    CADENCE.opposition,
    opts.enabled ?? true,
  )
}

export function useCMThreats(opts: PollOpts = {}): PollResult<ThreatsResponse> {
  const state = opts.state ?? DEFAULT_STATE
  return usePollingFetch(
    `cm/threats/${state}`,
    (signal) => fetchThreats(state, signal),
    CADENCE.threats,
    opts.enabled ?? true,
  )
}

export function useCMOutlook(opts: PollOpts = {}): PollResult<OutlookResponse> {
  const state = opts.state ?? DEFAULT_STATE
  return usePollingFetch(
    `cm/outlook/${state}`,
    (signal) => fetchOutlook(state, signal),
    CADENCE.outlook,
    opts.enabled ?? true,
  )
}

export function useCMMonitor(opts: PollOpts = {}): PollResult<MonitorResponse> {
  const state = opts.state ?? DEFAULT_STATE
  return usePollingFetch(
    `cm/monitor/${state}`,
    (signal) => fetchMonitor(state, signal),
    CADENCE.monitor,
    opts.enabled ?? true,
  )
}

export function useCMLivePulse(opts: PollOpts = {}): PollResult<LivePulseResponse> {
  const state = opts.state ?? DEFAULT_STATE
  return usePollingFetch(
    `cm/live_pulse/${state}`,
    (signal) => fetchLivePulse(state, signal),
    CADENCE.livePulse,
    opts.enabled ?? true,
  )
}

export function useCMActions(opts: PollOpts = {}): PollResult<ActionsResponse> {
  const state = opts.state ?? DEFAULT_STATE
  return usePollingFetch(
    `cm/actions/${state}`,
    (signal) => fetchActions(state, signal),
    CADENCE.actions,
    opts.enabled ?? true,
  )
}

export function useCMAnalysis(opts: PollOpts = {}): PollResult<AnalysisResponse> {
  const state = opts.state ?? DEFAULT_STATE
  return usePollingFetch(
    `cm/analysis/${state}`,
    (signal) => fetchAnalysis(state, signal),
    CADENCE.analysis,
    opts.enabled ?? true,
  )
}

export function useCMAtlasLayer(layerId: string, opts: PollOpts = {}): PollResult<AtlasLayerResponse> {
  const state = opts.state ?? DEFAULT_STATE
  return usePollingFetch(
    `cm/atlas/${layerId}/${state}`,
    (signal) => fetchAtlasLayer(layerId, state, signal),
    CADENCE.atlasLayer,
    (opts.enabled ?? true) && Boolean(layerId),
  )
}

export function useCMDistrict(
  districtId: string | null,
  opts: PollOpts = {},
): PollResult<DistrictBriefResponse> {
  const state = opts.state ?? DEFAULT_STATE
  return usePollingFetch(
    `cm/district/${districtId ?? 'none'}/${state}`,
    (signal) => fetchDistrict(districtId as string, state, signal),
    CADENCE.district,
    (opts.enabled ?? true) && Boolean(districtId),
  )
}

export function useCMTicker(opts: PollOpts = {}): PollResult<TickerResponse> {
  const state = opts.state ?? DEFAULT_STATE
  return usePollingFetch(
    `cm/ticker/${state}`,
    (signal) => fetchTicker(state, signal),
    CADENCE.ticker,
    opts.enabled ?? true,
  )
}

/* ------------------------------------------------------------------ */
/* Mode helper — single source of truth for empty / stale / error UI. */
/* ------------------------------------------------------------------ */

export type PanelMode = 'loading' | 'live' | 'stale' | 'empty' | 'degraded'

export function panelMode<T extends { meta?: { status?: string } }>(
  q: PollResult<T>,
): PanelMode {
  if (q.isLoading) return 'loading'
  if (q.isError) return 'degraded'
  const status = q.data?.meta?.status
  if (status === 'empty') return 'empty'
  if (status === 'stale') return 'stale'
  if (status === 'error') return 'degraded'
  return 'live'
}
