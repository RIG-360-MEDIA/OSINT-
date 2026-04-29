'use client'

import { useEffect, useRef, useState } from 'react'
import type { MonitorItem } from './types'

const POLL_INTERVAL_MS = 30_000
const MAX_VISIBLE = 20

/** Sort items by timestamp descending (newest first). Items missing a
 * timestamp sink to the end so they don't displace dated items. */
function sortByRecency(items: MonitorItem[]): MonitorItem[] {
  return [...items].sort((a, b) => {
    const ta = a.timestamp ? Date.parse(a.timestamp) : 0
    const tb = b.timestamp ? Date.parse(b.timestamp) : 0
    return tb - ta
  })
}

interface UseLivePillarFeedArgs {
  endpoint: string
  token: string | null
  paused: boolean
  staggerOffsetMs?: number
  normalize: (raw: unknown) => MonitorItem[]
}

interface UseLivePillarFeedResult {
  items: MonitorItem[]
  totalToday: number
  loading: boolean
  error: string | null
  lastUpdated: Date | null
}

/**
 * Polls a pillar feed endpoint at a fixed interval, prepending newly-seen
 * items to the top of the visible list and capping it at MAX_VISIBLE.
 *
 * `totalToday` tracks every distinct item seen since mount, so the UI can
 * show "12 today" when more than the visible window have arrived.
 */
export function useLivePillarFeed({
  endpoint,
  token,
  paused,
  staggerOffsetMs = 0,
  normalize,
}: UseLivePillarFeedArgs): UseLivePillarFeedResult {
  const [items, setItems] = useState<MonitorItem[]>([])
  const [totalToday, setTotalToday] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const seenIdsRef = useRef<Set<string>>(new Set())
  const pausedRef = useRef(paused)
  const tokenRef = useRef(token)
  const normalizeRef = useRef(normalize)

  pausedRef.current = paused
  tokenRef.current = token
  normalizeRef.current = normalize

  useEffect(() => {
    if (!token) return

    let cancelled = false
    let intervalId: ReturnType<typeof setInterval> | null = null
    let kickoffTimeoutId: ReturnType<typeof setTimeout> | null = null

    const tick = async () => {
      if (pausedRef.current) return
      const t = tokenRef.current
      if (!t) return

      try {
        const res = await fetch(endpoint, {
          headers: { Authorization: `Bearer ${t}` },
        })
        if (!res.ok) {
          if (!cancelled) {
            setError(`HTTP ${res.status}`)
            setLoading(false)
          }
          return
        }
        const raw: unknown = await res.json()
        const next = normalizeRef.current(raw)

        if (cancelled) return

        const seen = seenIdsRef.current
        const fresh = next.filter((item) => !seen.has(item.id))
        fresh.forEach((item) => seen.add(item.id))

        if (fresh.length > 0) {
          setItems((prev) => {
            // Always sort by recency so the newest items lead each shelf
            // even when the backend feed returns by score / mixed order.
            const merged = sortByRecency([...fresh, ...prev])
            return merged.slice(0, MAX_VISIBLE)
          })
          setTotalToday((n) => n + fresh.length)
        } else if (items.length === 0 && next.length > 0) {
          // First load with no fresh-vs-seen diff (shouldn't happen, but safe).
          setItems(sortByRecency(next).slice(0, MAX_VISIBLE))
          next.forEach((item) => seen.add(item.id))
          setTotalToday(next.length)
        }

        setError(null)
        setLoading(false)
        setLastUpdated(new Date())
      } catch (err: unknown) {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Network error')
        setLoading(false)
      }
    }

    kickoffTimeoutId = setTimeout(() => {
      void tick()
      intervalId = setInterval(() => {
        void tick()
      }, POLL_INTERVAL_MS)
    }, staggerOffsetMs)

    return () => {
      cancelled = true
      if (kickoffTimeoutId) clearTimeout(kickoffTimeoutId)
      if (intervalId) clearInterval(intervalId)
    }
    // endpoint + token govern lifecycle. paused is consumed via ref so the
    // interval keeps ticking but tick() short-circuits when paused.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, token, staggerOffsetMs])

  return { items, totalToday, loading, error, lastUpdated }
}
