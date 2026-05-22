/**
 * Polls a fetcher with visibility-aware backoff.
 *
 *   - 5s interval when the tab is visible
 *   - 30s interval when tab is hidden
 *   - Pauses entirely while offline
 *
 * Uses @tanstack/react-query for cache + revalidation.
 */
'use client'

import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

function useVisibility() {
  const [visible, setVisible] = useState(
    typeof document !== 'undefined' ? !document.hidden : true
  )
  useEffect(() => {
    const onChange = () => setVisible(!document.hidden)
    document.addEventListener('visibilitychange', onChange)
    return () => document.removeEventListener('visibilitychange', onChange)
  }, [])
  return visible
}

export interface UseObservePollOpts {
  visibleIntervalMs?: number
  hiddenIntervalMs?: number
  enabled?: boolean
}

export function useObservePoll<T>(
  key: ReadonlyArray<unknown>,
  fetcher: () => Promise<T>,
  opts: UseObservePollOpts = {}
) {
  const {
    visibleIntervalMs = 5000,
    hiddenIntervalMs = 30000,
    enabled = true,
  } = opts
  const visible = useVisibility()
  const interval = visible ? visibleIntervalMs : hiddenIntervalMs

  return useQuery<T>({
    queryKey: [...key, visible ? 'visible' : 'hidden'],
    queryFn: fetcher,
    refetchInterval: interval,
    refetchIntervalInBackground: false,
    staleTime: Math.floor(interval / 2),
    enabled,
  })
}
