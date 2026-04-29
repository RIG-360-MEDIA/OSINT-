'use client'

import type { QuoteRow } from '../types'

export function QuoteCardGrid({ rows }: { rows: QuoteRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="rig-prose" style={{ fontStyle: 'italic', color: 'var(--rig-ink-3)' }}>
        No notable verbatim today.
      </p>
    )
  }
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
        gap: 18,
      }}
    >
      {rows.map((q, i) => (
        <article
          key={`${q.id ?? i}-${i}`}
          style={{
            position: 'relative',
            border: '1px solid var(--rig-ink-4)',
            background: 'var(--rig-paper-2)',
            padding: 18,
          }}
        >
          <span
            aria-hidden
            style={{
              position: 'absolute',
              top: 6,
              left: 12,
              fontFamily: 'var(--font-serif)',
              fontSize: 48,
              color: 'var(--rig-copper)',
              lineHeight: 1,
            }}
          >
            “
          </span>
          <p
            style={{
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              fontSize: 16,
              lineHeight: 1.5,
              color: 'var(--rig-ink)',
              margin: '20px 0 12px',
            }}
          >
            {q.quote}
          </p>
          <div
            className="rig-byline"
            style={{
              color: 'var(--rig-ink-3)',
              borderTop: '1px solid var(--rig-ink-4)',
              paddingTop: 8,
            }}
          >
            — {q.speaker}
            {q.party ? ` · ${q.party}` : ''}
            {q.role ? ` · ${q.role}` : ''}
          </div>
          {q.source_url && (
            <a
              href={q.source_url}
              target="_blank"
              rel="noreferrer"
              className="rig-byline"
              style={{
                marginTop: 6,
                display: 'inline-block',
                color: 'var(--rig-ink-3)',
                textDecoration: 'underline',
              }}
            >
              source ↗
            </a>
          )}
        </article>
      ))}
    </div>
  )
}

export default QuoteCardGrid
