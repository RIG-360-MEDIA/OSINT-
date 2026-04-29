'use client'

import { ReactNode } from 'react'

interface CMSectionProps {
  numeral: string
  title: string
  standfirst?: string
  freshness?: string | null
  error?: string | null
  stale?: boolean
  onRefresh?: () => void
  children: ReactNode
}

/**
 * Roman-numeral-prefixed section wrapper. Mirrors the Movement pattern
 * used by the Intel view but with denser padding and a per-section
 * freshness/error/stale strip.
 */
export function CMSection({
  numeral,
  title,
  standfirst,
  freshness,
  error,
  stale,
  onRefresh,
  children,
}: CMSectionProps) {
  return (
    <section
      style={{
        marginTop: '52px',
        paddingTop: stale ? '8px' : 0,
        borderTop: stale ? '1px solid var(--rig-oxblood)' : 'none',
      }}
      aria-labelledby={`cm-section-${numeral.toLowerCase()}`}
    >
      <header
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: '20px',
          marginBottom: '14px',
          flexWrap: 'wrap',
        }}
      >
        <span
          className="rig-byline"
          style={{
            color: 'var(--rig-gold)',
            fontFamily: 'var(--font-mono)',
            fontWeight: 600,
            letterSpacing: '0.32em',
          }}
        >
          {numeral}
        </span>
        <h2
          id={`cm-section-${numeral.toLowerCase()}`}
          className="rig-headline"
          style={{ fontSize: '28px', margin: 0 }}
        >
          <em>{title}</em>
        </h2>
        {standfirst && (
          <p
            className="rig-byline"
            style={{
              color: 'var(--rig-ink-3)',
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              fontSize: '14px',
              letterSpacing: 'normal',
              textTransform: 'none',
            }}
          >
            {standfirst}
          </p>
        )}
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '12px' }}>
          {freshness && (
            <span className="rig-byline" style={{ color: 'var(--rig-ink-3)' }}>
              {freshness}
            </span>
          )}
          {onRefresh && (
            <button
              onClick={onRefresh}
              type="button"
              className="rig-byline"
              style={{
                background: 'transparent',
                border: '1px solid var(--rig-ink-4)',
                padding: '4px 10px',
                cursor: 'pointer',
                color: 'var(--rig-ink-2)',
                letterSpacing: '0.18em',
              }}
              aria-label={`Refresh ${title}`}
            >
              ↻
            </button>
          )}
        </div>
      </header>
      <hr className="rig-rule-hair" style={{ marginBottom: '18px' }} />
      {error && (
        <div
          className="rig-byline"
          role="alert"
          style={{
            color: 'var(--rig-oxblood)',
            border: '1px solid var(--rig-oxblood)',
            padding: '8px 12px',
            marginBottom: '14px',
            background: 'var(--rig-paper-2)',
          }}
        >
          DESK MEMO · {error}
        </div>
      )}
      {children}
    </section>
  )
}

export default CMSection
