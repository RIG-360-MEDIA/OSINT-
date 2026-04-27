'use client'

import { useEffect, useState } from 'react'
import { TELANGANA, STABILITY_WEIGHTS } from '../config/telangana'

export interface TelanganaSignals {
  loadedAt: Date | null
  loading: boolean
  error: string | null
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
  stability: {
    score: number  // 0..100, higher = calmer
    label: 'Calm' | 'Watchful' | 'Strained' | 'Critical'
  }
  summary: string  // one-paragraph briefing, templated until LLM lands
}

const initial: TelanganaSignals = {
  loadedAt: null,
  loading: true,
  error: null,
  weather: { tempC: null, maxC: null, minC: null, code: null, label: '—' },
  air: { aqi: null, pm25: null, label: 'Unknown' },
  stability: { score: 50, label: 'Watchful' },
  summary: 'Loading the briefing…',
}

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

const stabilityFromSubsignals = (
  airAqi: number | null,
  maxC: number | null,
): TelanganaSignals['stability'] => {
  // Air-quality sub-score: 0 (hazardous) .. 1 (good)
  const airSub =
    airAqi === null ? 0.6 : Math.max(0, 1 - Math.min(airAqi, 300) / 300)

  // Heat sub-score: comfortable below 30°C, critical at 45°C
  const heatSub =
    maxC === null ? 0.6 : Math.max(0, 1 - Math.max(0, maxC - 30) / 15)

  // Conflict / news sub-scores: stub 1.0 until ACLED + LLM proxies land
  const conflictSub = 1.0
  const newsSub = 1.0

  const w = STABILITY_WEIGHTS
  const composite =
    airSub * w.airQuality +
    heatSub * w.heatStress +
    conflictSub * w.conflictEvents +
    newsSub * w.newsAnomaly

  const score = Math.round(composite * 100)
  const label: TelanganaSignals['stability']['label'] =
    score >= 75 ? 'Calm' : score >= 60 ? 'Watchful' : score >= 40 ? 'Strained' : 'Critical'

  return { score, label }
}

const writeSummary = (s: TelanganaSignals): string => {
  const parts: string[] = []

  if (s.air.aqi !== null) {
    parts.push(
      s.air.label === 'Good'
        ? `Hyderabad air clean (AQI ${s.air.aqi}).`
        : `Hyderabad AQI ${s.air.aqi} — ${s.air.label.toLowerCase()}.`,
    )
  }

  if (s.weather.maxC !== null) {
    if (s.weather.maxC >= 42) {
      parts.push(`Severe heat — high of ${s.weather.maxC}°C forecast.`)
    } else if (s.weather.maxC >= 38) {
      parts.push(`Hot — high of ${s.weather.maxC}°C.`)
    } else if (s.weather.tempC !== null) {
      parts.push(`Temperature ${s.weather.tempC}°C, ${s.weather.label.toLowerCase()}.`)
    }
  }

  // Stub additions until backend proxies land
  parts.push('No major civic incidents reported.')
  parts.push('Local news ticker available on the side.')

  return parts.join(' ')
}

export function useTelanganaSignals(): TelanganaSignals {
  const [state, setState] = useState<TelanganaSignals>(initial)

  useEffect(() => {
    const ctrl = new AbortController()

    const load = async () => {
      try {
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
          weather: {
            tempC: tempC !== null ? Math.round(tempC) : null,
            maxC: maxC !== null ? Math.round(maxC) : null,
            minC: minC !== null ? Math.round(minC) : null,
            code,
            label: wmoLabel(code),
          },
          air: { aqi: aqi !== null ? Math.round(aqi) : null, pm25, label: aqiLabel(aqi) },
          stability: stabilityFromSubsignals(aqi, maxC),
          summary: '',
        }
        next.summary = writeSummary(next)
        setState(next)
      } catch (e) {
        if ((e as Error).name === 'AbortError') return
        setState((prev) => ({
          ...prev,
          loading: false,
          error: (e as Error).message || 'Failed to load briefing',
        }))
      }
    }

    load()
    return () => ctrl.abort()
  }, [])

  return state
}
