'use client'

import type { DivergenceRow } from '../types'

interface DivergenceStripsProps {
  rows: DivergenceRow[]
  emptyCopy: string
}

export function DivergenceStrips({ rows, emptyCopy }: DivergenceStripsProps) {
  if (rows.length === 0) {
    return (
      <p className="rig-prose" style={{ fontStyle: 'italic', color: 'var(--rig-ink-3)' }}>
        {emptyCopy}
      </p>
    )
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {rows.map((r, i) => {
        const direction = r.score_a > r.score_b ? 'a' : 'b'
        return (
          <article
            key={`${r.topic}-${i}`}
            style={{
              border: r.flagged ? '1px solid var(--rig-oxblood)' : '1px solid var(--rig-ink-4)',
              background: 'var(--rig-paper-2)',
              padding: 14,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
              <h4 className="rig-headline" style={{ margin: 0, fontSize: 16, fontStyle: 'italic' }}>
                {r.topic}
              </h4>
              <span
                className="rig-byline"
                style={{
                  marginLeft: 'auto',
                  color: r.flagged ? 'var(--rig-oxblood)' : 'var(--rig-ink-3)',
                }}
              >
                Δ {(r.delta * 100).toFixed(0)} {r.flagged ? '· FLAGGED' : ''}
              </span>
            </div>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 40px 1fr',
                gap: 12,
                marginTop: 10,
                alignItems: 'center',
              }}
            >
              <div
                style={{
                  padding: 10,
                  background: direction === 'a' ? 'var(--rig-paper)' : 'var(--rig-paper-3)',
                  border: '1px solid var(--rig-ink-4)',
                }}
              >
                <span className="rig-byline" style={{ color: 'var(--rig-ink-3)' }}>
                  {r.side_a_label}
                </span>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, color: 'var(--rig-ink)' }}>
                  {r.score_a >= 0 ? '+' : ''}{(r.score_a * 100).toFixed(0)}
                </div>
              </div>
              <span className="rig-byline" style={{ textAlign: 'center', color: 'var(--rig-ink-3)' }}>
                vs
              </span>
              <div
                style={{
                  padding: 10,
                  background: direction === 'b' ? 'var(--rig-paper)' : 'var(--rig-paper-3)',
                  border: '1px solid var(--rig-ink-4)',
                }}
              >
                <span className="rig-byline" style={{ color: 'var(--rig-ink-3)' }}>
                  {r.side_b_label}
                </span>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, color: 'var(--rig-ink)' }}>
                  {r.score_b >= 0 ? '+' : ''}{(r.score_b * 100).toFixed(0)}
                </div>
              </div>
            </div>
          </article>
        )
      })}
    </div>
  )
}

export default DivergenceStrips
