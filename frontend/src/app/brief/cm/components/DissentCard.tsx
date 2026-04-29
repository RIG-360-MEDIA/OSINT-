'use client'

import type { DissentSignal } from '../types'

const SEV_COPY: Record<DissentSignal['severity'], { label: string; color: string }> = {
  murmur: { label: 'MURMUR', color: 'var(--rig-gold)' },
  crack: { label: 'CRACK', color: 'var(--rig-oxblood)' },
  break: { label: 'OPEN BREAK', color: 'var(--rig-oxblood-2)' },
}

export function DissentCard({ signal }: { signal: DissentSignal }) {
  const sev = SEV_COPY[signal.severity]
  return (
    <article
      style={{
        border: '1px solid var(--rig-ink-4)',
        background: 'var(--rig-paper-2)',
        padding: 16,
        marginBottom: 12,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span
          aria-hidden
          style={{
            display: 'inline-block',
            width: 8,
            height: 8,
            borderRadius: 4,
            background: sev.color,
          }}
        />
        <span className="rig-byline" style={{ color: sev.color }}>
          {sev.label} · {signal.party}
        </span>
        <span className="rig-byline" style={{ color: 'var(--rig-ink-3)', marginLeft: 'auto' }}>
          conf {(signal.confidence * 100).toFixed(0)}%
        </span>
      </div>
      <h4 className="rig-headline" style={{ margin: '6px 0 8px', fontSize: 17, fontStyle: 'italic' }}>
        {signal.headline}
      </h4>
      {signal.members.length > 0 && (
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {signal.members.map((m, i) => (
            <li
              key={`${m.speaker}-${i}`}
              style={{
                paddingTop: 8,
                marginTop: 8,
                borderTop: '1px solid var(--rig-ink-4)',
              }}
            >
              <span className="rig-byline" style={{ color: 'var(--rig-ink-3)' }}>
                {m.speaker} · {m.party}
              </span>
              <p
                style={{
                  margin: '4px 0 0',
                  fontFamily: 'var(--font-serif)',
                  fontStyle: 'italic',
                  fontSize: 14,
                  color: 'var(--rig-ink-2)',
                }}
              >
                {m.quote.quote ? `“${m.quote.quote}”` : ''}
              </p>
            </li>
          ))}
        </ul>
      )}
    </article>
  )
}

export default DissentCard
