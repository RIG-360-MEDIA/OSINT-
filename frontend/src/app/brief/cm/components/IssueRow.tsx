'use client'

import { useState } from 'react'

import type { IssueCard, QuoteRef } from '../types'

interface IssueRowProps {
  issue: IssueCard
  onTrace?: (issue: IssueCard) => void
}

function StanceChip({ value, label }: { value: number; label: string }) {
  const tint =
    value >= 0.15
      ? 'var(--rig-gold)'
      : value <= -0.15
        ? 'var(--rig-oxblood)'
        : 'var(--rig-ink-3)'
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
      <span className="rig-byline" style={{ color: 'var(--rig-ink-3)' }}>
        {label}
      </span>
      <span style={{ color: tint, fontFamily: 'var(--font-mono)', fontSize: 14 }}>
        {value >= 0 ? '+' : ''}{(value * 100).toFixed(0)}
      </span>
    </div>
  )
}

function QuoteLine({ q }: { q: QuoteRef }) {
  return (
    <div style={{ marginTop: 8 }}>
      <p
        style={{
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontSize: 15,
          color: 'var(--rig-ink-2)',
          margin: 0,
        }}
      >
        “{q.quote}”
      </p>
      <span className="rig-byline" style={{ color: 'var(--rig-ink-3)' }}>
        — {q.speaker}{q.party ? ` · ${q.party}` : ''}{q.role ? ` · ${q.role}` : ''}
      </span>
    </div>
  )
}

export function IssueRow({ issue, onTrace }: IssueRowProps) {
  const [open, setOpen] = useState(false)
  const intensityPct = Math.max(0, Math.min(100, issue.intensity || 0))

  const ruling = issue.top_quotes.filter((q) => q.party && /(BJP|TDP|JSP|INC)/i.test(q.party || '')).slice(0, 2)
  const opposition = issue.top_quotes.filter((q) => q.party && /(BRS|YSRCP)/i.test(q.party || '')).slice(0, 2)
  const neutral = issue.top_quotes.slice(0, 2)

  return (
    <article
      style={{
        borderTop: '1px solid var(--rig-rule-hair, rgba(0,0,0,0.1))',
        padding: '14px 0',
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          background: 'transparent',
          border: 'none',
          padding: 0,
          cursor: 'pointer',
          textAlign: 'left',
          width: '100%',
        }}
        aria-expanded={open}
      >
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, flexWrap: 'wrap' }}>
          <span className="rig-byline" style={{ color: 'var(--rig-gold)' }}>
            ISSUE · {String(issue.id).padStart(2, '0')}
          </span>
          <h3
            className="rig-headline"
            style={{ fontSize: 19, margin: 0, fontStyle: 'italic' }}
          >
            {issue.label}
          </h3>
          <span
            className="rig-byline"
            style={{
              marginLeft: 'auto',
              color:
                issue.trajectory === 'intensifying'
                  ? 'var(--rig-oxblood)'
                  : issue.trajectory === 'fading'
                    ? 'var(--rig-gold-2)'
                    : 'var(--rig-ink-3)',
            }}
          >
            {issue.trajectory.toUpperCase()}
          </span>
        </div>
        <div
          style={{
            position: 'relative',
            marginTop: 8,
            height: 6,
            background: 'var(--rig-paper-2)',
            border: '1px solid var(--rig-ink-4)',
          }}
        >
          <div
            style={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              left: 0,
              width: `${intensityPct}%`,
              background: 'var(--rig-oxblood)',
            }}
          />
        </div>
        <div style={{ marginTop: 6, display: 'flex', gap: 16 }}>
          <StanceChip value={issue.stances.ruling || 0} label="ruling" />
          <StanceChip value={issue.stances.opposition || 0} label="opposition" />
          <StanceChip value={issue.stances.neutral || 0} label="neutral" />
          <span className="rig-byline" style={{ marginLeft: 'auto', color: 'var(--rig-ink-3)' }}>
            evidence · {issue.evidence_count}
          </span>
        </div>
      </button>

      {open && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 24,
            marginTop: 16,
          }}
        >
          <div>
            <span className="rig-byline" style={{ color: 'var(--rig-gold)' }}>
              ruling stance
            </span>
            <p className="rig-prose" style={{ marginTop: 6 }}>
              {issue.ruling_summary || '—'}
            </p>
            {ruling.map((q, i) => (
              <QuoteLine key={`r-${i}`} q={q} />
            ))}
          </div>
          <div>
            <span className="rig-byline" style={{ color: 'var(--rig-oxblood)' }}>
              opposition stance
            </span>
            <p className="rig-prose" style={{ marginTop: 6 }}>
              {issue.opposition_summary || '—'}
            </p>
            {opposition.map((q, i) => (
              <QuoteLine key={`o-${i}`} q={q} />
            ))}
          </div>
          <div>
            <span className="rig-byline" style={{ color: 'var(--rig-ink-3)' }}>
              neutral framing
            </span>
            <p className="rig-prose" style={{ marginTop: 6 }}>
              {issue.neutral_summary || '—'}
            </p>
            {neutral.map((q, i) => (
              <QuoteLine key={`n-${i}`} q={q} />
            ))}
          </div>
          <div style={{ gridColumn: '1 / -1', marginTop: 8 }}>
            {issue.party_stances.length > 0 && (
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                {issue.party_stances.map((p) => (
                  <span
                    key={p.party}
                    className="rig-byline"
                    style={{
                      padding: '3px 8px',
                      border: '1px solid var(--rig-ink-4)',
                      color:
                        p.stance === 'attack'
                          ? 'var(--rig-oxblood)'
                          : p.stance === 'defend'
                            ? 'var(--rig-gold)'
                            : 'var(--rig-ink-3)',
                    }}
                  >
                    {p.party}: {p.stance}
                  </span>
                ))}
              </div>
            )}
            {onTrace && (
              <button
                type="button"
                className="rig-byline"
                onClick={() => onTrace(issue)}
                style={{
                  marginTop: 12,
                  background: 'transparent',
                  border: '1px solid var(--rig-ink-4)',
                  padding: '6px 14px',
                  cursor: 'pointer',
                  color: 'var(--rig-ink-2)',
                }}
              >
                trace this issue →
              </button>
            )}
          </div>
        </div>
      )}
    </article>
  )
}

export default IssueRow
