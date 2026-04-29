'use client'

import type { TrajectoryPoint } from '../types'

interface TrajectorySparklineProps {
  rows: TrajectoryPoint[]
}

const CLASS_COPY: Record<TrajectoryPoint['classification'], { label: string; color: string }> = {
  intensifying: { label: 'INTENSIFYING', color: 'var(--rig-oxblood)' },
  steady:       { label: 'STEADY',       color: 'var(--rig-ink-2)' },
  fading:       { label: 'FADING',       color: 'var(--rig-gold-2)' },
  unknown:      { label: '—',            color: 'var(--rig-ink-3)' },
}

function buildPath(values: number[], width: number, height: number): string {
  if (values.length === 0) return ''
  const max = Math.max(...values, 1)
  const min = 0
  const dx = width / Math.max(values.length - 1, 1)
  return values
    .map((v, i) => {
      const x = i * dx
      const y = height - ((v - min) / (max - min || 1)) * height
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`
    })
    .join(' ')
}

export function TrajectorySparkline({ rows }: TrajectorySparklineProps) {
  if (rows.length === 0) {
    return (
      <p className="rig-prose" style={{ fontStyle: 'italic', color: 'var(--rig-ink-3)' }}>
        Insufficient history to plot trajectories.
      </p>
    )
  }
  return (
    <div>
      {rows.map((r) => {
        const cls = CLASS_COPY[r.classification]
        const path = buildPath(r.series_volume, 220, 22)
        return (
          <div
            key={r.issue_id}
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 240px 110px 90px',
              gap: 12,
              alignItems: 'center',
              padding: '10px 0',
              borderTop: '1px solid var(--rig-ink-4)',
            }}
          >
            <span
              className="rig-headline"
              style={{ fontSize: 15, fontStyle: 'italic', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
              title={r.label}
            >
              {r.label}
            </span>
            <svg width={220} height={22} viewBox="0 0 220 22" aria-label={`${r.label} 14-day trend`}>
              <path d={path} stroke={cls.color} strokeWidth={1.5} fill="none" />
            </svg>
            <span className="rig-byline" style={{ color: cls.color, letterSpacing: '0.16em' }}>
              {cls.label}
            </span>
            <span className="rig-byline" style={{ color: 'var(--rig-ink-3)', textAlign: 'right' }}>
              Δ24h {r.delta_24h > 0 ? '+' : ''}{r.delta_24h.toFixed(0)}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export default TrajectorySparkline
