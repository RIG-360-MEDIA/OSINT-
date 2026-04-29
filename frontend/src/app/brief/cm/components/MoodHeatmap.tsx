'use client'

import { useState } from 'react'

import type { HeatmapCell } from '../types'

interface MoodHeatmapProps {
  cells: HeatmapCell[]
}

function moodColor(score: number): string {
  if (score > 0.2) return 'var(--rig-gold)'
  if (score > 0.05) return 'var(--rig-gold-2)'
  if (score < -0.2) return 'var(--rig-oxblood)'
  if (score < -0.05) return 'var(--rig-oxblood-2)'
  return 'var(--rig-paper-3)'
}

/**
 * Tabular heatmap (placeholder for the SVG choropleth — when a verified
 * district SVG is added under data/, swap this list-table for the map).
 * Rendering as a table avoids fabricating geographic shapes; senior
 * officers see the data correctly even before the map asset lands.
 */
export function MoodHeatmap({ cells }: MoodHeatmapProps) {
  const [sortKey, setSortKey] = useState<'name' | 'mood' | 'volume'>('mood')
  if (cells.length === 0) {
    return (
      <p className="rig-prose" style={{ fontStyle: 'italic', color: 'var(--rig-ink-3)' }}>
        Geo signals not yet localised to constituency level.
      </p>
    )
  }

  const sorted = [...cells].sort((a, b) => {
    if (sortKey === 'name') return a.constituency_name.localeCompare(b.constituency_name)
    if (sortKey === 'volume') return b.volume - a.volume
    return a.score - b.score
  })

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 10 }}>
        {(['mood', 'volume', 'name'] as const).map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => setSortKey(k)}
            className="rig-byline"
            style={{
              padding: '3px 8px',
              border: '1px solid var(--rig-ink-4)',
              background: sortKey === k ? 'var(--rig-ink)' : 'transparent',
              color: sortKey === k ? 'var(--rig-paper)' : 'var(--rig-ink-2)',
              cursor: 'pointer',
            }}
          >
            sort by {k}
          </button>
        ))}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 6 }}>
        {sorted.map((c) => (
          <div
            key={c.constituency_code}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '6px 10px',
              border: '1px solid var(--rig-ink-4)',
              background: moodColor(c.score),
            }}
            title={`${c.constituency_name} · score ${c.score.toFixed(2)} · n=${c.volume}`}
          >
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--rig-ink)' }}>
              {c.constituency_code}
            </span>
            <span style={{ fontFamily: 'var(--font-serif)', fontSize: 14, color: 'var(--rig-ink)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {c.constituency_name}
            </span>
            <span className="rig-byline" style={{ color: 'var(--rig-ink-2)' }}>
              {c.score > 0 ? '+' : ''}{(c.score * 100).toFixed(0)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default MoodHeatmap
