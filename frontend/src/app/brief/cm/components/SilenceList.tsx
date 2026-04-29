'use client'

import type { SilenceItem } from '../types'

interface SilenceListProps {
  items: SilenceItem[]
}

const SEV_COPY: Record<SilenceItem['severity'], string> = {
  watch: 'WATCH',
  warn: 'WARN',
  critical: 'CRITICAL',
}

function severityColor(sev: SilenceItem['severity']) {
  if (sev === 'critical') return 'var(--rig-oxblood)'
  if (sev === 'warn') return 'var(--rig-gold-2)'
  return 'var(--rig-ink-3)'
}

export function SilenceList({ items }: SilenceListProps) {
  if (items.length === 0) {
    return (
      <p className="rig-prose" style={{ fontStyle: 'italic', color: 'var(--rig-ink-3)' }}>
        Government voice is matching the public&rsquo;s. No silence gaps detected.
      </p>
    )
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      {items.map((it, i) => {
        const ageH = it.age_hours || 0
        const days = ageH / 24
        const sevPct = Math.min(100, ageH * 2)
        return (
          <div
            key={`${it.label}-${i}`}
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 220px',
              gap: 14,
              padding: '14px 0',
              borderTop: '1px solid var(--rig-ink-4)',
              alignItems: 'center',
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                <span className="rig-byline" style={{ color: severityColor(it.severity) }}>
                  ⚑ {SEV_COPY[it.severity]}
                </span>
                <h4
                  className="rig-headline"
                  style={{ fontSize: 17, margin: 0, fontStyle: 'italic' }}
                >
                  {it.label}
                </h4>
              </div>
              <div className="rig-byline" style={{ color: 'var(--rig-ink-3)', marginTop: 4 }}>
                public volume 7d: {it.public_volume_7d.toLocaleString()} ·
                govt mentions 7d: {it.govt_mentions_7d.toLocaleString()} ·
                {' '}
                {days < 1 ? 'less than a day' : `${days.toFixed(1)} days`} since govt statement
              </div>
            </div>
            <div>
              <div className="rig-byline" style={{ color: 'var(--rig-ink-3)', marginBottom: 4 }}>
                silence severity
              </div>
              <div
                style={{
                  position: 'relative',
                  height: 8,
                  background: 'var(--rig-paper-2)',
                  border: '1px solid var(--rig-ink-4)',
                }}
                aria-label={`severity ${sevPct.toFixed(0)} percent`}
              >
                <div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    width: `${sevPct}%`,
                    background: severityColor(it.severity),
                  }}
                />
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default SilenceList
