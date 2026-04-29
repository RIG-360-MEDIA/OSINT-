'use client'

/**
 * Standalone /brief/cm route. Kept for backward compatibility — the
 * preferred entry point is the third toggle on /brief?view=cm. Both
 * render the same <CMSituationRoom> component; only the auth-gate +
 * outer chrome differs.
 */
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

import { createClient } from '@/lib/supabase/client'

import { CMSituationRoom } from './CMSituationRoom'

export default function CMPage() {
  const router = useRouter()
  const [token, setToken] = useState<string | null>(null)
  const [authReady, setAuthReady] = useState(false)

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
    <main style={{ background: 'var(--rig-paper)' }}>
      <CMSituationRoom token={token} />
    </main>
  )
}
