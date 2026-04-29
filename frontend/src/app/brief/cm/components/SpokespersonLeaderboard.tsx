'use client'

import type { SpokespersonRow } from '../types'

interface SpokespersonLeaderboardProps {
  mode: 'attackers' | 'on-message'
  rows: SpokespersonRow[]
  emptyCopy: string
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() || '')
    .join('')
}

export function SpokespersonLeaderboard({ mode, rows, emptyCopy }: SpokespersonLeaderboardProps) {
  if (rows.length === 0) {
    return (
      <p className="rig-prose" style={{ fontStyle: 'italic', color: 'var(--rig-ink-3)' }}>
        {emptyCopy}
      </p>
    )
  }
  const fill = mode === 'attackers' ? 'var(--rig-oxblood)' : 'var(--rig-gold)'
  const max = Math.max(...rows.map((r) => r.score), 1)
  return (
    <ol style={{ listStyle: 'none', padding: 0, margin: 0 }}>
      {rows.map((r, i) => {
        const widthPct = (r.score / max) * 100
        return (
          <li
            key={`${r.speaker}-${i}`}
            style={{
              display: 'grid',
              gridTemplateColumns: '32px 1fr 100px',
              gap: 12,
              padding: '12px 0',
              borderTop: i === 0 ? 'none' : '1px solid var(--rig-ink-4)',
              alignItems: 'center',
            }}
          >
            <div
              aria-hidden
              style={{
                width: 32,
                height: 32,
                borderRadius: 16,
                background: 'var(--rig-paper-2)',
                border: '1px solid var(--rig-ink-4)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: 'var(--rig-ink-2)',
                letterSpacing: '0.06em',
              }}
            >
              {initials(r.speaker)}
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <span style={{ fontFamily: 'var(--font-serif)', fontSize: 16, color: 'var(--rig-ink)' }}>
                  {r.speaker}
                </span>
                {r.party && (
                  <span className="rig-byline" style={{ color: 'var(--rig-ink-3)' }}>
                    {r.party}{r.role ? ` · ${r.role}` : ''}
                  </span>
                )}
              </div>
              <div
                style={{
                  position: 'relative',
                  marginTop: 4,
                  height: 4,
                  background: 'var(--rig-paper-2)',
                  border: '1px solid var(--rig-ink-4)',
                }}
              >
                <div style={{ position: 'absolute', inset: 0, width: `${widthPct}%`, background: fill }} />
              </div>
              {r.latest_quote && (
                <p
                  style={{
                    fontFamily: 'var(--font-serif)',
                    fontStyle: 'italic',
                    fontSize: 13,
                    color: 'var(--rig-ink-3)',
                    margin: '6px 0 0',
                  }}
                >
                  “{r.latest_quote.quote}”
                </p>
              )}
            </div>
            <div style={{ textAlign: 'right' }}>
              <div className="rig-byline" style={{ color: 'var(--rig-ink-2)' }}>
                {mode === 'attackers' ? 'attack score' : 'on-message %'}
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, color: 'var(--rig-ink)' }}>
                {mode === 'attackers'
                  ? r.score.toFixed(0)
                  : `${(r.on_message_rate || 0).toFixed(0)}%`}
              </div>
              <div className="rig-byline" style={{ color: 'var(--rig-ink-3)' }}>
                {r.mentions_24h} / 24h
              </div>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

export default SpokespersonLeaderboard
