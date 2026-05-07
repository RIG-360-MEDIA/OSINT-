/**
 * LiveTicker — single-line marquee of newest items across all five streams.
 *
 * Polls /api/coverage/ticker every 30s, dedupes against the current visible
 * sequence, and renders a continuous marquee. Source tags ([ART], [GOV],
 * [TV], [SOC], [NWP]) are colored cyan; titles are bone; timestamps dim.
 *
 * The marquee animates via the `.onyx-ticker` keyframe. We render the items
 * twice in a row so the loop is seamless (translateX(-50%) wraps cleanly).
 */

'use client'

import { useEffect, useState } from 'react'
import type { CoverageSlug } from './thumbnails'

interface TickerItem {
  slug: CoverageSlug
  title: string
  /** ISO 8601 — server returns snake_case `collected_at`. */
  collected_at: string
}

const TAG: Record<CoverageSlug, string> = {
  articles:  'ART',
  newspaper: 'NWP',
  tv:        'TV',
  social:    'SOC',
  govt:      'GOV',
}

const formatHM = (iso: string): string => {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const h = String(d.getUTCHours()).padStart(2, '0')
  const m = String(d.getUTCMinutes()).padStart(2, '0')
  return `${h}:${m}`
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface TickerResponse {
  items: TickerItem[]
}

export function LiveTicker() {
  const [items, setItems] = useState<TickerItem[]>([])

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/coverage/ticker`, {
          credentials: 'include',
          cache: 'no-store',
        })
        if (!res.ok) return
        const json = (await res.json()) as TickerResponse
        if (cancelled) return
        if (Array.isArray(json.items)) setItems(json.items)
      } catch {
        // Silent — ticker is decorative, never blocks
      }
    }

    load()
    const id = setInterval(load, 30_000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  // Fallback content while loading — keeps the strip from collapsing
  const display = items.length > 0 ? items : Array.from({ length: 5 }).map((_, i): TickerItem => ({
    slug: (['articles', 'newspaper', 'tv', 'social', 'govt'] as CoverageSlug[])[i],
    title: '— awaiting signal —',
    collected_at: new Date().toISOString(),
  }))

  // Duplicate sequence for seamless marquee wrap
  const sequence = [...display, ...display]

  return (
    <div
      style={{
        position: 'relative',
        overflow: 'hidden',
        height: '36px',
        display: 'flex',
        alignItems: 'center',
        borderTop: '1px solid var(--onyx-rule-hair)',
        borderBottom: '1px solid var(--onyx-rule-hair)',
        marginTop: '24px',
        marginBottom: '40px',
        maskImage: 'linear-gradient(to right, transparent 0%, black 6%, black 94%, transparent 100%)',
        WebkitMaskImage: 'linear-gradient(to right, transparent 0%, black 6%, black 94%, transparent 100%)',
      }}
    >
      <div className="onyx-ticker">
        {sequence.map((item, i) => (
          <span
            key={i}
            className="onyx-mono"
            style={{
              fontSize: '11px',
              letterSpacing: '0.18em',
              padding: '0 28px',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '14px',
              whiteSpace: 'nowrap',
            }}
          >
            <span style={{ color: 'var(--onyx-cyan)' }}>[{TAG[item.slug]}]</span>
            <span style={{ color: 'var(--onyx-dim)' }}>{formatHM(item.collected_at)}</span>
            <span style={{ color: 'var(--onyx-bone-2)', textTransform: 'none', letterSpacing: '0.02em' }}>
              {item.title}
            </span>
            <span style={{ color: 'var(--onyx-dim-2)', margin: '0 6px' }}>·</span>
          </span>
        ))}
      </div>
    </div>
  )
}
