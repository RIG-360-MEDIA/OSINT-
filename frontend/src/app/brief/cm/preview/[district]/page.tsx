'use client'

/**
 * Dynamic district route: /brief/cm/preview/[district]
 *
 * Auth-gated identically to the parent /brief/cm/preview. Renders the
 * district-focused brief for whatever id the URL carries (e.g.
 * /brief/cm/preview/karimnagar).
 */
import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'

import { createClient } from '@/lib/supabase/client'

import { CMDistrictBrief } from '../../CMDistrictBrief'

export default function CMDistrictPage() {
  const router = useRouter()
  const params = useParams<{ district: string }>()
  const districtId = params?.district ?? ''
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
      <CMDistrictBrief districtId={districtId} token={token} />
    </main>
  )
}
