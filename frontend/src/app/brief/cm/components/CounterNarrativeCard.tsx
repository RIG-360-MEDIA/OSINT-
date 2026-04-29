'use client'

import { useState } from 'react'

import type { CounterNarrativeCard as CNCard } from '../types'

interface CounterNarrativeCardProps {
  card: CNCard
}

export function CounterNarrativeCard({ card }: CounterNarrativeCardProps) {
  const [copied, setCopied] = useState(false)
  const onCopy = async () => {
    const text = card.talking_points.map((t, i) => `${i + 1}. ${t.text}`).join('\n\n')
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch {
      /* ignore */
    }
  }

  return (
    <article
      style={{
        position: 'relative',
        border: '1px solid var(--rig-oxblood)',
        background: 'var(--rig-paper-2)',
        padding: 18,
        overflow: 'hidden',
      }}
    >
      {/* DRAFT diagonal watermark */}
      <div
        aria-hidden
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage:
            'repeating-linear-gradient(135deg, transparent 0 22px, color-mix(in srgb, var(--rig-oxblood) 6%, transparent) 22px 24px)',
          pointerEvents: 'none',
        }}
      />
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span
          className="rig-byline"
          style={{
            color: 'var(--rig-oxblood)',
            border: '1px solid var(--rig-oxblood)',
            padding: '2px 8px',
            letterSpacing: '0.22em',
            fontWeight: 600,
          }}
        >
          DRAFT · NOT FOR ATTRIBUTION
        </span>
        <span className="rig-byline" style={{ color: 'var(--rig-ink-3)' }}>
          {new Date(card.generated_at).toLocaleString('en-IN', { hour12: false })}
        </span>
      </div>
      <h4
        className="rig-headline"
        style={{ margin: '10px 0 12px', fontSize: 18, fontStyle: 'italic' }}
      >
        {card.issue_label}
      </h4>
      <ol style={{ paddingLeft: 18, margin: 0 }}>
        {card.talking_points.map((tp, i) => (
          <li
            key={i}
            style={{
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              fontSize: 15,
              color: 'var(--rig-ink-2)',
              marginBottom: 10,
            }}
          >
            {tp.text}
            {tp.cites.length > 0 && (
              <span className="rig-byline" style={{ color: 'var(--rig-ink-3)', marginLeft: 6 }}>
                [cites: {tp.cites.join(', ')}]
              </span>
            )}
          </li>
        ))}
      </ol>
      <div
        style={{
          marginTop: 12,
          paddingTop: 10,
          borderTop: '1px solid var(--rig-ink-4)',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
        }}
      >
        <span className="rig-byline" style={{ color: 'var(--rig-ink-3)' }}>
          grounding · {card.grounding_doc_ids.length} docs · {card.model}
        </span>
        <button
          type="button"
          onClick={onCopy}
          className="rig-byline"
          style={{
            marginLeft: 'auto',
            background: 'transparent',
            border: '1px solid var(--rig-ink-4)',
            padding: '4px 10px',
            cursor: 'pointer',
            color: 'var(--rig-ink-2)',
          }}
        >
          {copied ? 'copied ✓' : 'copy'}
        </button>
      </div>
    </article>
  )
}

export default CounterNarrativeCard
