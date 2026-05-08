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
  // Optional English translation of the headline (for non-English source
  // articles in the developing path). When present and different from
  // headline, render below the original.
  display_title?: string | null
  sources_count: number
  volume?: number
  window_start?: string | null
  created_at?: string | null
  // 'breaking' = multi-source validated cluster (red band)
  // 'developing' = single high-relevance tier-1 article in last 60 min,
  //   shown in cyan when no validated cluster exists for the user.
  kind?: 'breaking' | 'developing'
  published_at?: string | null
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

  // Age: prefer published_at when present (developing items), else
  // created_at (clusters). Both are wall-clock; we just pick whichever
  // the backend supplied.
  const anchor = cluster.published_at || cluster.created_at
  const ageMinutes = anchor
    ? Math.max(1, Math.floor((Date.now() - new Date(anchor).getTime()) / 60_000))
    : 0

  const isDeveloping = cluster.kind === 'developing'
  const accent = isDeveloping ? 'var(--onyx-cyan)' : 'var(--onyx-red)'
  const accentBg = isDeveloping
    ? 'rgba(0, 194, 255, 0.04)'
    : 'rgba(255, 45, 45, 0.04)'
  const label = isDeveloping ? 'Developing' : 'Breaking'
  const sourceLine = isDeveloping
    ? `${cluster.sources_count} source · ${ageMinutes}m`
    : `${cluster.sources_count} sources · ${ageMinutes}m`

  return (
    <div
      role="status"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '20px',
        padding: '16px 24px',
        marginTop: '24px',
        border: `1px solid ${accent}`,
        background: accentBg,
        animation: 'onyx-fade-up 0.4s ease both',
      }}
    >
      <span
        style={{
          width: '8px',
          height: '8px',
          background: accent,
          boxShadow: `0 0 12px ${accent}`,
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
          color: accent,
          flexShrink: 0,
        }}
      >
        {label}
      </span>
      {(() => {
        // Dual-line rendering: when display_title is provided AND
        // differs meaningfully from headline, show original first
        // (primary, full-size) and the English translation below in
        // a smaller dimmer line.
        const norm = (s: string) =>
          s.toLowerCase().replace(/[\s\p{P}]+/gu, '').trim()
        const showBoth =
          !!cluster.display_title &&
          cluster.display_title.trim().length > 0 &&
          norm(cluster.display_title) !== norm(cluster.headline)
        return (
          <span
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              gap: '2px',
              minWidth: 0,
            }}
          >
            <span
              style={{
                fontFamily: 'var(--onyx-display)',
                fontSize: '16px',
                color: 'var(--onyx-bone)',
                letterSpacing: '-0.005em',
              }}
            >
              {cluster.headline}
            </span>
            {showBoth && (
              <span
                style={{
                  fontSize: '12px',
                  color: 'var(--onyx-dim)',
                  letterSpacing: '-0.003em',
                }}
              >
                {cluster.display_title}
              </span>
            )}
          </span>
        )
      })()}
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
        {sourceLine}
      </span>
    </div>
  )
}
