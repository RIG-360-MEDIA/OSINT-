'use client'

/**
 * Generalised polling hook for CM Page sections. Mirrors the lifecycle
 * of `monitor/useLivePillarFeed` (kickoff stagger, paused-via-ref so
 * interval keeps ticking, abort on unmount) but generic over response
 * shape and without the dedupe/visibility cap that's specific to a
 * pillar shelf.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

export interface UseLivePollArgs<T> {
  fetcher: (signal: AbortSignal) => Promise<T>
  intervalMs: number
  paused?: boolean
  staggerOffsetMs?: number
  enabled?: boolean
}

export interface UseLivePollResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  lastUpdated: Date | null
  refresh: () => void
}

export function useLivePoll<T>({
  fetcher,
  intervalMs,
  paused = false,
  staggerOffsetMs = 0,
  enabled = true,
}: UseLivePollArgs<T>): UseLivePollResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const pausedRef = useRef(paused)
  pausedRef.current = paused

  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  const tick = useCallback(async (controller: AbortController) => {
    if (pausedRef.current) return
    try {
      const next = await fetcherRef.current(controller.signal)
      if (controller.signal.aborted) return
      setData(next)
      setLastUpdated(new Date())
      setError(null)
    } catch (exc) {
      if (controller.signal.aborted) return
      setError((exc as Error)?.message || 'Unknown error')
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }, [])

  const manualRefreshRef = useRef<() => void>(() => undefined)

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return undefined
    }

    const controller = new AbortController()
    let intervalId: ReturnType<typeof setInterval> | null = null
    let kickoffTimeoutId: ReturnType<typeof setTimeout> | null = null

    manualRefreshRef.current = () => {
      void tick(controller)
    }

    kickoffTimeoutId = setTimeout(() => {
      if (controller.signal.aborted) return
      void tick(controller)
      intervalId = setInterval(() => {
        if (controller.signal.aborted) return
        void tick(controller)
      }, intervalMs)
    }, Math.max(0, staggerOffsetMs))

    return () => {
      controller.abort()
      if (kickoffTimeoutId) clearTimeout(kickoffTimeoutId)
      if (intervalId) clearInterval(intervalId)
    }
  }, [enabled, intervalMs, staggerOffsetMs, tick])

  const refresh = useCallback(() => {
    manualRefreshRef.current()
  }, [])

  return { data, loading, error, lastUpdated, refresh }
}
