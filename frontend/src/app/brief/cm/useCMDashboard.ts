'use client'

/**
 * Orchestrator hook for the CM Page. Loads /api/cm/dashboard once for
 * the initial paint, then registers per-section polls at section-specific
 * cadences. Each section exposes its own loading/error/lastUpdated state.
 */
import { useMemo } from 'react'

import {
  CM_ENDPOINTS,
  fetchCMSection,
  fetchDashboard,
} from './api'
import type {
  CMDashboardResponse,
  CMSectionName,
  CounterNarrativesResponse,
  DissentResponse,
  DivergenceResponse,
  HeatmapResponse,
  IssuesResponse,
  PromisesResponse,
  PulseResponse,
  QuotesResponse,
  RiskWindowResponse,
  SilenceResponse,
  SpokespersonsResponse,
  TrajectoryResponse,
  VoiceShareResponse,
} from './types'
import { useLivePoll } from './useLivePoll'

export interface CMFilters {
  state: string | null
  window: string
  paused: boolean
}

const SECTION_CADENCES: Record<CMSectionName, number> = {
  pulse: 30_000,
  issues: 30_000,
  silence: 30_000,
  trajectory: 30_000,
  quotes: 30_000,
  spokespersons: 300_000,
  cabinet_onmessage: 300_000,
  dissent: 300_000,
  voice_share: 300_000,
  language_divergence: 300_000,
  medium_divergence: 300_000,
  heatmap: 3_600_000,
  risk_window: 3_600_000,
  promises: 86_400_000,
  counter_narratives: 86_400_000,
}

const STAGGER_OFFSETS_MS: Record<CMSectionName, number> = {
  pulse: 0,
  issues: 4_000,
  silence: 8_000,
  trajectory: 12_000,
  quotes: 16_000,
  spokespersons: 20_000,
  cabinet_onmessage: 22_000,
  dissent: 24_000,
  voice_share: 28_000,
  language_divergence: 30_000,
  medium_divergence: 32_000,
  heatmap: 60_000,
  risk_window: 90_000,
  promises: 120_000,
  counter_narratives: 150_000,
}

export interface CMDashboardState {
  initial: ReturnType<typeof useLivePoll<CMDashboardResponse>>
  pulse: ReturnType<typeof useLivePoll<PulseResponse>>
  issues: ReturnType<typeof useLivePoll<IssuesResponse>>
  silence: ReturnType<typeof useLivePoll<SilenceResponse>>
  spokespersons: ReturnType<typeof useLivePoll<SpokespersonsResponse>>
  cabinet_onmessage: ReturnType<typeof useLivePoll<SpokespersonsResponse>>
  dissent: ReturnType<typeof useLivePoll<DissentResponse>>
  trajectory: ReturnType<typeof useLivePoll<TrajectoryResponse>>
  heatmap: ReturnType<typeof useLivePoll<HeatmapResponse>>
  promises: ReturnType<typeof useLivePoll<PromisesResponse>>
  counter_narratives: ReturnType<typeof useLivePoll<CounterNarrativesResponse>>
  risk_window: ReturnType<typeof useLivePoll<RiskWindowResponse>>
  quotes: ReturnType<typeof useLivePoll<QuotesResponse>>
  voice_share: ReturnType<typeof useLivePoll<VoiceShareResponse>>
  language_divergence: ReturnType<typeof useLivePoll<DivergenceResponse>>
  medium_divergence: ReturnType<typeof useLivePoll<DivergenceResponse>>
  refreshAll: () => void
}

export function useCMDashboard(token: string | null, filters: CMFilters): CMDashboardState {
  const enabled = Boolean(token)

  const initial = useLivePoll<CMDashboardResponse>({
    fetcher: useMemo(
      () => (signal: AbortSignal) =>
        token
          ? fetchDashboard(token, { state: filters.state, window: filters.window, signal })
          : Promise.reject(new Error('no-token')),
      [token, filters.state, filters.window],
    ),
    intervalMs: 5 * 60_000,
    paused: filters.paused,
    staggerOffsetMs: 0,
    enabled,
  })

  const make = <T,>(name: CMSectionName, mode?: 'attackers' | 'on-message') =>
    useLivePoll<T>({
      fetcher: useMemo(
        () => (signal: AbortSignal) =>
          token
            ? fetchCMSection<T>(CM_ENDPOINTS[name], token, {
                state: filters.state,
                window: filters.window,
                signal,
                mode,
              })
            : Promise.reject(new Error('no-token')),
        // eslint-disable-next-line react-hooks/exhaustive-deps
        [token, filters.state, filters.window, name, mode],
      ),
      intervalMs: SECTION_CADENCES[name],
      paused: filters.paused,
      staggerOffsetMs: STAGGER_OFFSETS_MS[name],
      enabled,
    })

  /* eslint-disable react-hooks/rules-of-hooks */
  const pulse = make<PulseResponse>('pulse')
  const issues = make<IssuesResponse>('issues')
  const silence = make<SilenceResponse>('silence')
  const spokespersons = make<SpokespersonsResponse>('spokespersons', 'attackers')
  const cabinet_onmessage = make<SpokespersonsResponse>('cabinet_onmessage', 'on-message')
  const dissent = make<DissentResponse>('dissent')
  const trajectory = make<TrajectoryResponse>('trajectory')
  const heatmap = make<HeatmapResponse>('heatmap')
  const promises = make<PromisesResponse>('promises')
  const counter_narratives = make<CounterNarrativesResponse>('counter_narratives')
  const risk_window = make<RiskWindowResponse>('risk_window')
  const quotes = make<QuotesResponse>('quotes')
  const voice_share = make<VoiceShareResponse>('voice_share')
  const language_divergence = make<DivergenceResponse>('language_divergence')
  const medium_divergence = make<DivergenceResponse>('medium_divergence')
  /* eslint-enable react-hooks/rules-of-hooks */

  const refreshAll = () => {
    initial.refresh()
    ;[
      pulse, issues, silence, spokespersons, cabinet_onmessage, dissent,
      trajectory, heatmap, promises, counter_narratives, risk_window,
      quotes, voice_share, language_divergence, medium_divergence,
    ].forEach((s) => s.refresh())
  }

  return {
    initial,
    pulse,
    issues,
    silence,
    spokespersons,
    cabinet_onmessage,
    dissent,
    trajectory,
    heatmap,
    promises,
    counter_narratives,
    risk_window,
    quotes,
    voice_share,
    language_divergence,
    medium_divergence,
    refreshAll,
  }
}
