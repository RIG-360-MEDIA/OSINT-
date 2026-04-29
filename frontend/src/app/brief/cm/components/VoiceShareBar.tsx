'use client'

import type { VoiceShareRow } from '../types'

export function VoiceShareDelta({ rows }: { rows: VoiceShareRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="rig-prose" style={{ fontStyle: 'italic', color: 'var(--rig-ink-3)' }}>
        Insufficient mention volume to compute a share-of-voice delta.
      </p>
    )
  }
  const max = Math.max(...rows.flatMap((r) => [r.share_24h_pct, r.share_7d_pct]), 1)
  return (
    <div>
      {rows.map((r, i) => {
        const w24 = (r.share_24h_pct / max) * 100
        const w7 = (r.share_7d_pct / max) * 100
        const positive = r.delta_pct >= 0
        return (
          <div
            key={`${r.speaker}-${i}`}
            style={{
              display: 'grid',
              gridTemplateColumns: '160px 1fr 80px',
              gap: 12,
              alignItems: 'center',
              padding: '8px 0',
              borderTop: '1px solid var(--rig-ink-4)',
            }}
          >
            <div>
              <div style={{ fontFamily: 'var(--font-serif)', fontSize: 15, color: 'var(--rig-ink)' }}>
                {r.speaker}
              </div>
              {r.party && (
                <span className="rig-byline" style={{ color: 'var(--rig-ink-3)' }}>
                  {r.party}
                </span>
              )}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span className="rig-byline" style={{ width: 30, color: 'var(--rig-ink-3)' }}>
                  7d
                </span>
                <div style={{ flex: 1, height: 6, background: 'var(--rig-paper-2)', border: '1px solid var(--rig-ink-4)' }}>
                  <div style={{ width: `${w7}%`, height: '100%', background: 'var(--rig-ink-3)' }} />
                </div>
                <span className="rig-byline" style={{ width: 40, textAlign: 'right' }}>
                  {r.share_7d_pct.toFixed(1)}%
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span className="rig-byline" style={{ width: 30, color: 'var(--rig-ink-3)' }}>
                  24h
                </span>
                <div style={{ flex: 1, height: 6, background: 'var(--rig-paper-2)', border: '1px solid var(--rig-ink-4)' }}>
                  <div style={{ width: `${w24}%`, height: '100%', background: 'var(--rig-gold)' }} />
                </div>
                <span className="rig-byline" style={{ width: 40, textAlign: 'right' }}>
                  {r.share_24h_pct.toFixed(1)}%
                </span>
              </div>
            </div>
            <span
              className="rig-byline"
              style={{
                color: positive ? 'var(--rig-gold)' : 'var(--rig-oxblood)',
                fontFamily: 'var(--font-mono)',
                fontSize: 14,
                textAlign: 'right',
              }}
            >
              Δ {positive ? '+' : ''}{r.delta_pct.toFixed(1)}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export default VoiceShareDelta
