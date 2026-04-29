'use client'

import type { RiskEvent, RiskKind, RiskLevel } from '../types'

const KIND_COLOR: Record<RiskKind, string> = {
  court: 'var(--rig-oxblood)',
  parliament: 'var(--rig-gold)',
  by_election: 'var(--rig-oxblood-2)',
  festival: 'var(--rig-ink-3)',
  anniversary: 'var(--rig-ink-4)',
  deadline: 'var(--rig-copper)',
  protest: 'var(--rig-oxblood)',
  session: 'var(--rig-gold-2)',
}

const LEVEL_BORDER: Record<RiskLevel, string> = {
  high: '2px solid var(--rig-oxblood)',
  med: '1px solid var(--rig-ink)',
  low: '1px solid var(--rig-ink-4)',
}

function dayKey(d: string): string {
  return d.slice(0, 10)
}

export function RiskCalendar({ events, days = 7 }: { events: RiskEvent[]; days?: number }) {
  if (events.length === 0) {
    return (
      <p className="rig-prose" style={{ fontStyle: 'italic', color: 'var(--rig-ink-3)' }}>
        No flagged events in the next seven days.
      </p>
    )
  }
  const today = new Date()
  const cols: { date: Date; key: string }[] = []
  for (let i = 0; i < days; i++) {
    const d = new Date(today)
    d.setDate(today.getDate() + i)
    cols.push({ date: d, key: d.toISOString().slice(0, 10) })
  }
  const byDay: Record<string, RiskEvent[]> = {}
  for (const ev of events) {
    const k = dayKey(ev.event_date)
    byDay[k] = byDay[k] || []
    byDay[k].push(ev)
  }

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${days}, 1fr)`,
        gap: 8,
      }}
    >
      {cols.map((col) => (
        <div
          key={col.key}
          style={{
            border: '1px solid var(--rig-ink-4)',
            background: 'var(--rig-paper-2)',
            padding: 8,
            minHeight: 120,
          }}
        >
          <div className="rig-byline" style={{ color: 'var(--rig-ink-3)', marginBottom: 6 }}>
            {col.date.toLocaleDateString('en-IN', { weekday: 'short', day: '2-digit', month: 'short' })}
          </div>
          {(byDay[col.key] || []).map((ev) => (
            <div
              key={ev.id}
              title={`${ev.kind} · ${ev.risk_level} · ${ev.risk_summary || ''}`}
              style={{
                padding: '4px 6px',
                marginBottom: 4,
                background: 'var(--rig-paper)',
                border: LEVEL_BORDER[ev.risk_level],
                borderLeft: `4px solid ${KIND_COLOR[ev.kind] || 'var(--rig-ink-3)'}`,
              }}
            >
              <div className="rig-byline" style={{ color: KIND_COLOR[ev.kind] }}>
                {ev.kind.toUpperCase()} · {ev.risk_level.toUpperCase()}
              </div>
              <div style={{ fontFamily: 'var(--font-serif)', fontSize: 13, color: 'var(--rig-ink)' }}>
                {ev.title}
              </div>
              {ev.source_url && (
                <a
                  className="rig-byline"
                  href={ev.source_url}
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: 'var(--rig-ink-3)', textDecoration: 'underline' }}
                >
                  source
                </a>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

export default RiskCalendar
