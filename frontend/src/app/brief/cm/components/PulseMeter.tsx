'use client'

interface PulseMeterProps {
  label: string
  value: number          // -1 .. +1
  delta?: number
  n?: number
  size?: 'hero' | 'compact'
}

/**
 * Diverging-bar barometer. Center = neutral (0); right (gold) = favorable;
 * left (oxblood) = hostile. Pure CSS — no chart library.
 */
export function PulseMeter({ label, value, delta = 0, n = 0, size = 'compact' }: PulseMeterProps) {
  const clamped = Math.max(-1, Math.min(1, value || 0))
  const pct = (Math.abs(clamped) * 50).toFixed(1)
  const direction = clamped >= 0 ? 'right' : 'left'
  const fill = clamped >= 0 ? 'var(--rig-gold)' : 'var(--rig-oxblood)'

  const heroBar = size === 'hero'
  const trackHeight = heroBar ? 14 : 8
  const fontSize = heroBar ? 18 : 14

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span
          className="rig-byline"
          style={{ color: 'var(--rig-ink-2)', letterSpacing: '0.18em', fontSize: heroBar ? 12 : 10 }}
        >
          {label}
        </span>
        {n > 0 && (
          <span className="rig-byline" style={{ color: 'var(--rig-ink-3)' }}>
            n={n}
          </span>
        )}
      </div>
      <div
        style={{
          position: 'relative',
          width: '100%',
          height: trackHeight,
          background: 'var(--rig-paper-2)',
          border: '1px solid var(--rig-ink-4)',
        }}
        aria-label={`${label}: ${(clamped * 100).toFixed(0)} percent`}
        role="img"
      >
        <div
          style={{
            position: 'absolute',
            top: 0,
            bottom: 0,
            left: '50%',
            width: 1,
            background: 'var(--rig-ink-3)',
          }}
        />
        <div
          style={{
            position: 'absolute',
            top: 0,
            bottom: 0,
            background: fill,
            ...(direction === 'right'
              ? { left: '50%', width: `${pct}%` }
              : { right: '50%', width: `${pct}%` }),
          }}
        />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--font-mono)', fontSize, color: 'var(--rig-ink-2)' }}>
        <span>{(clamped * 100).toFixed(0)}</span>
        {Math.abs(delta) > 0.01 && (
          <span
            className="rig-byline"
            style={{
              color: delta < 0 ? 'var(--rig-oxblood)' : 'var(--rig-gold)',
            }}
          >
            Δ {delta > 0 ? '+' : ''}{(delta * 100).toFixed(0)} vs week
          </span>
        )}
      </div>
    </div>
  )
}

export default PulseMeter
