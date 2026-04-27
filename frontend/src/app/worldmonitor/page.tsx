'use client'

import { useState, useEffect } from 'react'
import { useSearchParams, useRouter, usePathname } from 'next/navigation'
import Navigation from '@/components/Navigation'
import { TelanganaBriefing } from './TelanganaBriefing'
import { GlobalView } from './GlobalView'

type Scope = 'telangana' | 'global'

export default function WorldMonitorPage() {
  const params = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()

  // Default scope is Telangana (per product direction). User can toggle to
  // Global to see the embedded WM dashboard.
  const initial: Scope = params.get('scope') === 'global' ? 'global' : 'telangana'
  const [scope, setScope] = useState<Scope>(initial)

  // Keep the URL in sync so reloads / shares preserve the user's choice.
  useEffect(() => {
    const next = scope === 'global' ? 'global' : 'telangana'
    if (params.get('scope') !== next) {
      const sp = new URLSearchParams(params.toString())
      sp.set('scope', next)
      router.replace(`${pathname}?${sp.toString()}`, { scroll: false })
    }
  }, [scope, params, router, pathname])

  return (
    <>
      <Navigation />
      {scope === 'telangana' ? (
        <TelanganaBriefing onSwitchToGlobal={() => setScope('global')} />
      ) : (
        <GlobalView onSwitchToTelangana={() => setScope('telangana')} />
      )}
    </>
  )
}
