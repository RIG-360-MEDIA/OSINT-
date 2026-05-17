/**
 * BreakingBand — cinematic full-width hero alert.
 *
 * Composition (left → right):
 *   • Indicator column (140 × 140) — animated red square chip, label
 *     'BREAKING' or 'DEVELOPING' flickering, radial pulsing glow behind.
 *   • Headline column (flex 1) — primary headline at 28-32px, English
 *     translation underneath at 14px dim if non-English source.
 *   • Source ticker column (260px) — source count chip + horizontal
 *     marquee of source names + age in mono.
 *
 * Atmospheric layers (z-stacked):
 *   • Black panel with red rgba(0.04) wash + scanline animation.
 *   • 2px red gradient bar pulsing along top edge.
 *   • HUD-style L-bracket corners at all four corners.
 *
 * DEVELOPING variant: same structure, indicator + glow in white/bone
 * instead of red, label says 'DEVELOPING'. (No cyan.)
 */

'use client'

import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface BreakingCluster {
  id: string
  headline: string
  why_for_user?: string | null
  display_title?: string | null
  sources_count: number
  volume?: number
  window_start?: string | null
  created_at?: string | null
  kind?: 'breaking' | 'developing'
  published_at?: string | null
  source_name?: string | null
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

  const isDeveloping = cluster.kind === 'developing'
  // Both BREAKING and DEVELOPING use red atmosphere now (per the
  // black/red/white discipline). DEVELOPING differentiates only via
  // typography weight + the label text itself, not via colour.
  const accent = 'var(--onyx-red)'
  const labelText = isDeveloping ? 'Developing' : 'Breaking'

  // Age — use published_at when present (developing items),
  // else created_at (clusters).
  const anchor = cluster.published_at || cluster.created_at
  const ageMinutes = anchor
    ? Math.max(1, Math.floor((Date.now() - new Date(anchor).getTime()) / 60_000))
    : 0
  const ageStr = ageMinutes < 60
    ? `${ageMinutes}M AGO`
    : `${Math.floor(ageMinutes / 60)}H AGO`

  const whyText = (cluster.why_for_user || '').trim()

  // Source list for the ticker. The current API only exposes
  // sources_count + a single source_name on developing items, so use that
  // as the marquee content; for breaking clusters, repeat the count to
  // give the marquee something to scroll. Real cluster sources can be
  // wired in later — the ticker shape is the expensive part to design.
  const tickerNames = cluster.source_name
    ? [cluster.source_name]
    : Array(cluster.sources_count || 1).fill('LIVE FEED')
  const tickerText = tickerNames.join('   ·   ')

  return (
    <div
      role="status"
      style={{
        position: 'relative',
        display: 'grid',
        gridTemplateColumns: '120px minmax(0, 1fr) 220px',
        minHeight: '140px',
        marginTop: '24px',
        background:
          'linear-gradient(180deg, rgba(255, 45, 45, 0.04) 0%, rgba(0, 0, 0, 0.92) 60%)',
        border: `1px solid ${accent}`,
        overflow: 'hidden',
        animation: 'onyx-fade-up 0.5s cubic-bezier(0.2, 0.7, 0.3, 1) both',
      }}
    >
      {/* Top edge — pulsing 2px red beam */}
      <span
        aria-hidden
        style={{
          position: 'absolute',
          top: 0, left: 0, right: 0,
          height: '2px',
          background: `linear-gradient(90deg, transparent 0%, ${accent} 50%, transparent 100%)`,
          animation: 'onyx-pulse-cyan 2s ease-in-out infinite',
        }}
      />

      {/* Scanline overlay */}
      <span
        aria-hidden
        style={{
          position: 'absolute',
          top: 0, left: 0, right: 0,
          height: '2px',
          background: `linear-gradient(90deg, transparent, ${accent}, transparent)`,
          opacity: 0.55,
          animation: 'onyx-scanline 4.5s linear infinite',
          pointerEvents: 'none',
        }}
      />

      {/* HUD-frame corner brackets */}
      {([
        { top: '8px',    left: '8px',    bt: '1px', bl: '1px' },
        { top: '8px',    right: '8px',   bt: '1px', br: '1px' },
        { bottom: '8px', left: '8px',    bb: '1px', bl: '1px' },
        { bottom: '8px', right: '8px',   bb: '1px', br: '1px' },
      ] as Array<Record<string, string>>).map((pos, i) => (
        <span
          key={i}
          aria-hidden
          style={{
            position: 'absolute',
            width: '14px',
            height: '14px',
            borderTop: pos.bt ? `1px solid ${accent}` : undefined,
            borderBottom: pos.bb ? `1px solid ${accent}` : undefined,
            borderLeft: pos.bl ? `1px solid ${accent}` : undefined,
            borderRight: pos.br ? `1px solid ${accent}` : undefined,
            top: pos.top,
            left: pos.left,
            right: pos.right,
            bottom: pos.bottom,
            animation: 'onyx-hud-pulse 3s ease-in-out infinite',
            pointerEvents: 'none',
          }}
        />
      ))}

      {/* INDICATOR column */}
      <div
        style={{
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          borderRight: `1px solid ${accent}`,
        }}
      >
        {/* Radial pulsing glow behind */}
        <span
          aria-hidden
          style={{
            position: 'absolute',
            inset: '20px',
            borderRadius: '50%',
            background: `radial-gradient(circle at center, rgba(255, 45, 45, 0.45) 0%, rgba(255, 45, 45, 0) 70%)`,
            animation: 'onyx-pulse-cyan 1.6s ease-in-out infinite',
            pointerEvents: 'none',
          }}
        />
        <span
          className="onyx-mono"
          style={{
            position: 'relative',
            fontSize: '11px',
            letterSpacing: '0.42em',
            textTransform: 'uppercase',
            color: isDeveloping ? 'var(--onyx-bone)' : accent,
            fontWeight: 600,
            animation: 'onyx-flicker-text 1.2s ease-in-out infinite',
            zIndex: 1,
          }}
        >
          {labelText}
        </span>
      </div>

      {/* HEADLINE column */}
      <div
        style={{
          padding: '20px 28px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          gap: '8px',
          minWidth: 0,
        }}
      >
        <span
          aria-hidden
          style={{
            display: 'block',
            width: '32px',
            height: '1px',
            background: accent,
          }}
        />
        <h2
          style={{
            margin: 0,
            fontFamily: 'var(--onyx-display)',
            fontSize: '26px',
            lineHeight: 1.18,
            letterSpacing: '-0.012em',
            fontWeight: 500,
            color: 'var(--onyx-bone)',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            wordBreak: 'break-word',
          }}
        >
          {cluster.headline}
        </h2>
        {whyText && (
          <p
            style={{
              margin: 0,
              fontFamily: 'var(--onyx-italic)',
              fontStyle: 'italic',
              fontSize: '14px',
              lineHeight: 1.45,
              color: 'var(--onyx-bone-2)',
              maxWidth: '72ch',
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
          >
            {whyText}
          </p>
        )}
        <span
          aria-hidden
          style={{
            display: 'block',
            width: '32px',
            height: '1px',
            background: 'rgba(255, 255, 255, 0.06)',
          }}
        />
      </div>

      {/* SOURCE TICKER column */}
      <div
        style={{
          position: 'relative',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
          padding: '20px 24px',
          borderLeft: '1px solid rgba(255, 255, 255, 0.06)',
        }}
      >
        <span
          className="onyx-mono"
          style={{
            fontSize: '9px',
            letterSpacing: '0.36em',
            textTransform: 'uppercase',
            color: accent,
          }}
        >
          {cluster.sources_count} {cluster.sources_count === 1 ? 'SOURCE' : 'SOURCES'}
        </span>

        {/* Marquee strip */}
        <div
          style={{
            position: 'relative',
            overflow: 'hidden',
            height: '20px',
            opacity: 0.85,
          }}
        >
          <span
            className="onyx-mono"
            style={{
              position: 'absolute',
              whiteSpace: 'nowrap',
              fontSize: '10px',
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              color: 'var(--onyx-bone-2)',
              animation: 'onyx-marquee 18s linear infinite',
              willChange: 'transform',
            }}
          >
            {tickerText}   ·   {tickerText}
          </span>
        </div>

        <span
          className="onyx-mono"
          style={{
            fontSize: '10px',
            letterSpacing: '0.32em',
            textTransform: 'uppercase',
            color: 'var(--onyx-dim)',
          }}
        >
          {ageStr}
        </span>
      </div>
    </div>
  )
}
