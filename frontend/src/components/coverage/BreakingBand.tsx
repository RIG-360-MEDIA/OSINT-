/**
 * BreakingBand — red-bordered horizontal band when a breaking cluster
 * is active. Polls /api/coverage/breaking every 60s. Auto-hides when
 * no clusters active.
 */

'use client'

import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface BreakingCluster {
  id: string
  headline: string
  sources_count: number
  volume: number
  window_start: string | null
  created_at: string | null
}

export function BreakingBand() {
  const [cluster, setCluster] = useState<BreakingCluster | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const supabase = createClient()
        const { data: { session } } = await supabase.auth.getSession()
        const token = session?.access_token
        if (!token) return
        const res = await fetch(`${API_BASE}/api/coverage/breaking`, {
          headers: { Authorization: `Bearer ${token}` },
          cache: 'no-store',
        })
        if (!res.ok) return
        const json = await res.json() as { clusters: BreakingCluster[] }
        if (cancelled) return
        setCluster(json.clusters?.[0] || null)
      } catch {
        /* silent */
      }
    }
    void load()
    const id = setInterval(load, 60_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  if (!cluster) return null

  const ageMinutes = cluster.created_at
    ? Math.max(1, Math.floor((Date.now() - new Date(cluster.created_at).getTime()) / 60_000))
    : 0

  return (
    <div
      role="status"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '20px',
        padding: '16px 24px',
        marginTop: '24px',
        border: '1px solid var(--onyx-red)',
        background: 'rgba(255, 45, 45, 0.04)',
        animation: 'onyx-fade-up 0.4s ease both',
      }}
    >
      <span
        style={{
          width: '8px',
          height: '8px',
          background: 'var(--onyx-red)',
          boxShadow: '0 0 12px var(--onyx-red)',
          animation: 'onyx-pulse-cyan 1.2s ease-in-out infinite',
          flexShrink: 0,
        }}
      />
      <span
        className="onyx-mono"
        style={{
          fontSize: '11px',
          letterSpacing: '0.42em',
          textTransform: 'uppercase',
          color: 'var(--onyx-red)',
          flexShrink: 0,
        }}
      >
        Breaking
      </span>
      <span
        style={{
          flex: 1,
          fontFamily: 'var(--onyx-display)',
          fontSize: '16px',
          color: 'var(--onyx-bone)',
          letterSpacing: '-0.005em',
        }}
      >
        {cluster.headline}
      </span>
      <span
        className="onyx-mono"
        style={{
          fontSize: '10px',
          letterSpacing: '0.28em',
          textTransform: 'uppercase',
          color: 'var(--onyx-dim)',
          flexShrink: 0,
        }}
      >
        {cluster.sources_count} sources · {ageMinutes}m
      </span>
    </div>
  )
}
