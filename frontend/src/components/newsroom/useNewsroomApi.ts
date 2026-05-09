'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import { createClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

/** Hook: returns a fetch function that injects the current Supabase JWT. */
export function useAuthedFetch() {
  const tokenRef = useRef<string | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getSession().then(({ data: { session } }) => {
      tokenRef.current = session?.access_token ?? null
      setReady(true)
    })
    const sub = supabase.auth.onAuthStateChange((_e, session) => {
      tokenRef.current = session?.access_token ?? null
    })
    return () => { sub.data.subscription.unsubscribe() }
  }, [])

  const fetcher = useCallback(async <T,>(path: string, init?: RequestInit): Promise<T> => {
    const headers = new Headers(init?.headers)
    if (tokenRef.current) headers.set('Authorization', `Bearer ${tokenRef.current}`)
    const res = await fetch(`${API_BASE}${path}`, { ...init, headers })
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      throw new Error(`${res.status} ${res.statusText} :: ${body.slice(0, 200)}`)
    }
    return res.json() as Promise<T>
  }, [])

  return { ready, fetcher, tokenRef }
}

export const NEWSROOM_API_BASE = API_BASE
