'use client'

/**
 * Isolated preview route for the new "Editorial Intelligence" CM brief.
 *
 * This route exists alongside the production CM situation room at
 * /brief/cm and the embedded toggle at /brief?view=cm — neither of
 * those is touched by this preview.
 *
 * Purpose: ship the visual demo to production so the CM can react to
 * the final-look design without the demo data replacing real intel
 * for any other user. Auth-gated identically to /brief/cm so it
 * cannot be discovered by an anonymous visitor.
 */
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

import { createClient } from '@/lib/supabase/client'

import { CMEditorialBrief } from '../CMEditorialBrief'

export default function CMPreviewPage() {
  const router = useRouter()
  const [token, setToken] = useState<string | null>(null)
  const [authReady, setAuthReady] = useState<boolean>(false)

  useEffect(() => {
    let alive = true
    const supa = createClient()
    void supa.auth.getSession().then(({ data }) => {
      if (!alive) return
      const t = data.session?.access_token || null
      if (!t) {
        router.replace('/login')
        return
      }
      setToken(t)
      setAuthReady(true)
    })
    const { data: sub } = supa.auth.onAuthStateChange((_event, session) => {
      if (!alive) return
      const t = session?.access_token || null
      if (!t) {
        router.replace('/login')
      } else {
        setToken(t)
      }
    })
    return () => {
      alive = false
      sub.subscription.unsubscribe()
    }
  }, [router])

  if (!authReady) {
    return (
      <main style={{ padding: '60px 24px', textAlign: 'center' }}>
        <span className="rig-byline" style={{ color: 'var(--rig-ink-3)' }}>
          authorising…
        </span>
      </main>
    )
  }

  return (
    <main style={{ background: 'var(--rig-paper, #faf8f3)' }}>
      <CMEditorialBrief token={token} />
    </main>
  )
}
