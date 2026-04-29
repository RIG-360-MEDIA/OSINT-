'use client'

import { useEffect, useState } from 'react'

interface CommandBarProps {
  filingNumber?: string
  state: string | null
  onStateChange: (state: string | null) => void
  windowKey: string
  onWindowChange: (window: string) => void
  paused: boolean
  onPauseToggle: () => void
  lastUpdated: Date | null
  onRefreshAll: () => void
}

const STATES: { code: string | null; label: string }[] = [
  { code: null, label: 'All' },
  { code: 'TG', label: 'Telangana' },
  { code: 'AP', label: 'Andhra Pradesh' },
]

const WINDOWS: { code: string; label: string }[] = [
  { code: '24h', label: '24 hours' },
  { code: '7d', label: '7 days' },
  { code: '30d', label: '30 days' },
]

function fmtAge(d: Date | null): string {
  if (!d) return 'connecting…'
  const ageS = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000))
  if (ageS < 60) return `live · refreshed ${ageS}s ago`
  const min = Math.floor(ageS / 60)
  if (min < 60) return `live · refreshed ${min}m ago`
  const h = Math.floor(min / 60)
  return `refreshed ${h}h ago`
}

export function CMCommandBar({
  filingNumber,
  state,
  onStateChange,
  windowKey,
  onWindowChange,
  paused,
  onPauseToggle,
  lastUpdated,
  onRefreshAll,
}: CommandBarProps) {
  const [tick, setTick] = useState(0)

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 5_000)
    return () => clearInterval(id)
  }, [])

  const today = new Date()
  const dateStr = today.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
  })
  void tick

  return (
    <div
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 20,
        background: 'var(--rig-paper)',
        padding: '16px 0 12px',
        marginBottom: '14px',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: '20px',
          flexWrap: 'wrap',
        }}
      >
        <span className="rig-dateline">
          {filingNumber ? `Filing No. ${filingNumber} · ` : ''}Political Desk · {dateStr}
        </span>
        <div style={{ display: 'flex', gap: '6px' }}>
          {STATES.map((s) => (
            <button
              key={String(s.code)}
              type="button"
              onClick={() => onStateChange(s.code)}
              className="rig-byline"
              style={{
                padding: '4px 10px',
                border: '1px solid var(--rig-ink-4)',
                background: state === s.code ? 'var(--rig-ink)' : 'transparent',
                color: state === s.code ? 'var(--rig-paper)' : 'var(--rig-ink-2)',
                cursor: 'pointer',
                letterSpacing: '0.18em',
              }}
              aria-pressed={state === s.code}
            >
              {s.label}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: '6px' }}>
          {WINDOWS.map((w) => (
            <button
              key={w.code}
              type="button"
              onClick={() => onWindowChange(w.code)}
              className="rig-byline"
              style={{
                padding: '4px 10px',
                border: '1px solid var(--rig-ink-4)',
                background: windowKey === w.code ? 'var(--rig-gold)' : 'transparent',
                color: windowKey === w.code ? 'var(--rig-paper)' : 'var(--rig-ink-2)',
                cursor: 'pointer',
                letterSpacing: '0.18em',
              }}
              aria-pressed={windowKey === w.code}
            >
              {w.label}
            </button>
          ))}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span className="rig-byline" style={{ color: paused ? 'var(--rig-oxblood)' : 'var(--rig-ink-3)' }}>
            {paused ? 'paused' : fmtAge(lastUpdated)}
          </span>
          <button
            type="button"
            onClick={onPauseToggle}
            className="rig-byline"
            style={{
              padding: '4px 10px',
              border: '1px solid var(--rig-ink-4)',
              background: 'transparent',
              cursor: 'pointer',
              color: 'var(--rig-ink-2)',
              letterSpacing: '0.18em',
            }}
            aria-pressed={paused}
          >
            {paused ? 'resume live' : 'pause live'}
          </button>
          <button
            type="button"
            onClick={onRefreshAll}
            className="rig-byline"
            style={{
              padding: '4px 10px',
              border: '1px solid var(--rig-ink-4)',
              background: 'transparent',
              cursor: 'pointer',
              color: 'var(--rig-ink-2)',
              letterSpacing: '0.18em',
            }}
          >
            ↻ refresh all
          </button>
        </div>
      </div>
      <hr className="rig-rule-gold" style={{ marginTop: '12px' }} />
    </div>
  )
}

export default CMCommandBar
