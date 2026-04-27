'use client'

import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'
import { TELANGANA, STABILITY_WEIGHTS } from '../config/telangana'

export interface NewsItem {
  source: string
  source_label: string
  title: string
  link: string
  published: string
  summary: string
}

export interface AcledEvent {
  event_date: string
  event_type: string
  sub_event_type?: string
  actor1?: string
  location?: string
  fatalities: number
  notes?: string
}

export interface TelanganaSignals {
  loadedAt: Date | null
  loading: boolean
  error: string | null
  cached: boolean
  source: 'backend' | 'fallback'
  weather: {
    tempC: number | null
    maxC: number | null
    minC: number | null
    code: number | null
    label: string
  }
  air: {
    aqi: number | null
    pm25: number | null
    label: 'Good' | 'Moderate' | 'Unhealthy SG' | 'Unhealthy' | 'Very Unhealthy' | 'Hazardous' | 'Unknown'
  }
  events: AcledEvent[]
  news: NewsItem[]
  stability: {
    score: number
    label: 'Calm' | 'Watchful' | 'Strained' | 'Critical'
  }
  summary: string
}

const initial: TelanganaSignals = {
  loadedAt: null,
  loading: true,
  error: null,
  cached: false,
  source: 'backend',
  weather: { tempC: null, maxC: null, minC: null, code: null, label: '—' },
  air: { aqi: null, pm25: null, label: 'Unknown' },
  events: [],
  news: [],
  stability: { score: 50, label: 'Watchful' },
  summary: 'Loading the briefing…',
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const wmoLabel = (code: number | null): string => {
  if (code === null) return '—'
  if (code === 0) return 'Clear'
  if (code <= 3) return 'Partly cloudy'
  if (code <= 48) return 'Fog'
  if (code <= 67) return 'Rain'
  if (code <= 77) return 'Snow'
  if (code <= 82) return 'Showers'
  if (code <= 86) return 'Snow showers'
  return 'Thunderstorm'
}

const aqiLabel = (aqi: number | null): TelanganaSignals['air']['label'] => {
  if (aqi === null) return 'Unknown'
  if (aqi <= 50) return 'Good'
  if (aqi <= 100) return 'Moderate'
  if (aqi <= 150) return 'Unhealthy SG'
  if (aqi <= 200) return 'Unhealthy'
  if (aqi <= 300) return 'Very Unhealthy'
  return 'Hazardous'
}

const stabilityFallback = (
  airAqi: number | null,
  maxC: number | null,
): TelanganaSignals['stability'] => {
  const airSub = airAqi === null ? 0.6 : Math.max(0, 1 - Math.min(airAqi, 300) / 300)
  const heatSub = maxC === null ? 0.6 : Math.max(0, 1 - Math.max(0, maxC - 30) / 15)
  const w = STABILITY_WEIGHTS
  const composite = airSub * w.airQuality + heatSub * w.heatStress + 1.0 * w.conflictEvents + 1.0 * w.newsAnomaly
  const score = Math.round(composite * 100)
  const label: TelanganaSignals['stability']['label'] =
    score >= 75 ? 'Calm' : score >= 60 ? 'Watchful' : score >= 40 ? 'Strained' : 'Critical'
  return { score, label }
}

const fallbackSummary = (s: TelanganaSignals): string => {
  const parts: string[] = []
  if (s.air.aqi !== null) {
    parts.push(
      s.air.label === 'Good'
        ? `Hyderabad air clean (AQI ${s.air.aqi}).`
        : `Hyderabad AQI ${s.air.aqi} — ${s.air.label.toLowerCase()}.`,
    )
  }
  if (s.weather.maxC !== null) {
    if (s.weather.maxC >= 42) parts.push(`Severe heat — high of ${s.weather.maxC}°C forecast.`)
    else if (s.weather.maxC >= 38) parts.push(`Hot — high of ${s.weather.maxC}°C.`)
    else if (s.weather.tempC !== null) parts.push(`Temperature ${s.weather.tempC}°C, ${s.weather.label.toLowerCase()}.`)
  }
  parts.push('Backend unavailable — local fallback.')
  return parts.join(' ')
}

export function useTelanganaSignals(): TelanganaSignals {
  const [state, setState] = useState<TelanganaSignals>(initial)

  useEffect(() => {
    const ctrl = new AbortController()

    const loadFromBackend = async (): Promise<TelanganaSignals | null> => {
      try {
        const supabase = createClient()
        const { data: { session } } = await supabase.auth.getSession()
        if (!session) return null

        const r = await fetch(`${API_BASE}/api/worldmonitor/telangana/briefing`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
          signal: ctrl.signal,
        })
        if (!r.ok) return null
        const j = await r.json()

        return {
          loadedAt: new Date(),
          loading: false,
          error: null,
          cached: !!j.cached,
          source: 'backend',
          weather: {
            tempC: j.weather?.temp_c !== null && j.weather?.temp_c !== undefined ? Math.round(j.weather.temp_c) : null,
            maxC: j.weather?.max_c !== null && j.weather?.max_c !== undefined ? Math.round(j.weather.max_c) : null,
            minC: j.weather?.min_c !== null && j.weather?.min_c !== undefined ? Math.round(j.weather.min_c) : null,
            code: j.weather?.weather_code ?? null,
            label: wmoLabel(j.weather?.weather_code ?? null),
          },
          air: {
            aqi: j.air?.aqi !== null && j.air?.aqi !== undefined ? Math.round(j.air.aqi) : null,
            pm25: j.air?.pm25 ?? null,
            label: aqiLabel(j.air?.aqi ?? null),
          },
          events: Array.isArray(j.events) ? j.events : [],
          news: Array.isArray(j.news) ? j.news : [],
          stability: j.stability ?? { score: 50, label: 'Watchful' },
          summary: j.summary || '',
        }
      } catch (e) {
        if ((e as Error).name === 'AbortError') return null
        return null
      }
    }

    const loadFallback = async (): Promise<TelanganaSignals> => {
      const weatherUrl =
        `https://api.open-meteo.com/v1/forecast` +
        `?latitude=${TELANGANA.lat}&longitude=${TELANGANA.lon}` +
        `&current=temperature_2m,weather_code` +
        `&daily=temperature_2m_max,temperature_2m_min` +
        `&timezone=${encodeURIComponent(TELANGANA.tz)}` +
        `&forecast_days=1`
      const airUrl =
        `https://air-quality-api.open-meteo.com/v1/air-quality` +
        `?latitude=${TELANGANA.lat}&longitude=${TELANGANA.lon}` +
        `&current=us_aqi,pm2_5`

      const [wRes, aRes] = await Promise.all([
        fetch(weatherUrl, { signal: ctrl.signal }),
        fetch(airUrl, { signal: ctrl.signal }),
      ])
      const w = wRes.ok ? await wRes.json() : null
      const a = aRes.ok ? await aRes.json() : null

      const tempC = w?.current?.temperature_2m ?? null
      const code = w?.current?.weather_code ?? null
      const maxC = w?.daily?.temperature_2m_max?.[0] ?? null
      const minC = w?.daily?.temperature_2m_min?.[0] ?? null
      const aqi = a?.current?.us_aqi ?? null
      const pm25 = a?.current?.pm2_5 ?? null

      const next: TelanganaSignals = {
        loadedAt: new Date(),
        loading: false,
        error: null,
        cached: false,
        source: 'fallback',
        weather: {
          tempC: tempC !== null ? Math.round(tempC) : null,
          maxC: maxC !== null ? Math.round(maxC) : null,
          minC: minC !== null ? Math.round(minC) : null,
          code,
          label: wmoLabel(code),
        },
        air: { aqi: aqi !== null ? Math.round(aqi) : null, pm25, label: aqiLabel(aqi) },
        events: [],
        news: [],
        stability: stabilityFallback(aqi, maxC),
        summary: '',
      }
      next.summary = fallbackSummary(next)
      return next
    }

    const run = async () => {
      const fromBackend = await loadFromBackend()
      if (fromBackend) {
        setState(fromBackend)
        return
      }
      try {
        const fallback = await loadFallback()
        setState(fallback)
      } catch (e) {
        if ((e as Error).name === 'AbortError') return
        setState((p) => ({ ...p, loading: false, error: (e as Error).message }))
      }
    }

    run()
    return () => ctrl.abort()
  }, [])

  return state
}
