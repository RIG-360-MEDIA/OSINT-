/**
 * Client-side access helpers.
 *
 * Wraps `GET /api/me/access` so any client component can ask "can this user
 * see X?" without re-implementing the fetch. The middleware already gates
 * server-side; this hook is for visual hiding (nav links, admin buttons,
 * impersonation banner).
 */
'use client'

import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

// FRONTEND RESET (2026-05-19) — all gated pages were removed.
// PageSlug is kept as a type alias so any client code that still imports it
// keeps compiling; populate with surviving slugs as the new app pages ship.
export type PageSlug = string

export interface Access {
  user_id: string
  email: string
  role: 'user' | 'super_admin'
  allowed_pages: PageSlug[]
  has_profile: boolean
  has_entities: boolean
  is_impersonating: boolean
  real_email: string | null
  target_email: string | null
}

interface UseAccessResult {
  access: Access | null
  loading: boolean
  error: string | null
}

/**
 * Fetches /api/me/access once and caches in component state.
 * Returns `null` while loading or on error — callers should treat null as
 * "no access yet" and render skeletons or hide gated UI.
 */
export function useAccess(): UseAccessResult {
  const [access, setAccess] = useState<Access | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      try {
        const supabase = createClient()
        const { data } = await supabase.auth.getSession()
        if (!data.session) {
          if (!cancelled) {
            setAccess(null)
            setLoading(false)
          }
          return
        }
        const res = await fetch(`${API_BASE}/api/me/access`, {
          headers: { Authorization: `Bearer ${data.session.access_token}` },
          credentials: 'include',
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const body = (await res.json()) as Access
        if (!cancelled) {
          setAccess(body)
          setLoading(false)
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'failed')
          setLoading(false)
        }
      }
    }
    run()
    return () => {
      cancelled = true
    }
  }, [])

  return { access, loading, error }
}

/** True iff the user can see the given page. Super admins always pass. */
export function canSeePage(access: Access | null, slug: PageSlug): boolean {
  if (!access) return false
  if (access.role === 'super_admin') return true
  return access.allowed_pages.includes(slug)
}

/**
 * Same fetch as useAccess() but as a one-shot helper for non-React code
 * (e.g. the impersonation cookie handler in /admin).
 */
export async function fetchAccess(): Promise<Access | null> {
  const supabase = createClient()
  const { data } = await supabase.auth.getSession()
  if (!data.session) return null
  const res = await fetch(`${API_BASE}/api/me/access`, {
    headers: { Authorization: `Bearer ${data.session.access_token}` },
    credentials: 'include',
  })
  if (!res.ok) return null
  return (await res.json()) as Access
}
