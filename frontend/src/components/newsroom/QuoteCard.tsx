'use client'

import { EntityChip } from './EntityChip'
import type { NewsroomEchoItem } from '@/types/newsroom'

interface Props {
  item: NewsroomEchoItem
}

const FRAMING_VARIANT: Record<string, 'live' | 'default'> = {
  adversarial: 'live',
  aligned:     'default',
  neutral:     'default',
}

export function QuoteCard({ item }: Props) {
  const framingLabel = item.framing ?? 'neutral'
  const sentimentMark = item.sentiment != null
    ? item.sentiment > 0.2
      ? '+' + item.sentiment.toFixed(2)
      : item.sentiment < -0.2
        ? item.sentiment.toFixed(2)
        : '0'
    : '—'
  const text = item.text_en ?? item.text_native ?? ''
  return (
    <article
      className="onyx-hud-corners"
      style={{
        position: 'relative',
        background: 'var(--onyx-bg-2)',
        border: '1px solid rgba(168,173,184,0.10)',
        padding: '20px 24px',
        animation: 'onyx-fade-up 0.4s ease',
      }}
    >
      {/* Top row: channel + framing */}
      <header style={{
        display: 'flex', alignItems: 'center', gap: 10,
        marginBottom: 12,
      }}>
        <span style={{
          font: '500 12px/1 var(--onyx-display)',
          color: 'var(--onyx-bone)',
          letterSpacing: '0.04em',
        }}>{item.channel_name}</span>
        <span style={{ flex: 1 }} />
        <EntityChip label={framingLabel} variant={FRAMING_VARIANT[framingLabel] ?? 'default'} />
        <EntityChip label={`SENT ${sentimentMark}`} variant="default" />
      </header>

      {/* Quote body */}
      <blockquote style={{
        margin: 0,
        font: '400 17px/1.5 var(--onyx-italic)',
        fontStyle: 'italic',
        color: 'var(--onyx-bone)',
        borderLeft: '2px solid var(--onyx-red)',
        paddingLeft: 14,
      }}>
        “{text}”
      </blockquote>

      {/* Footer: phonetic + ts */}
      <footer style={{
        display: 'flex', alignItems: 'center', gap: 10,
        marginTop: 12,
        font: '400 9px/1 var(--onyx-mono)',
        color: 'var(--onyx-dim)',
        letterSpacing: '0.18em',
        textTransform: 'uppercase',
      }}>
        {item.was_phonetic && <span style={{ color: 'var(--onyx-red)' }}>phonetic snap</span>}
        <span style={{ flex: 1 }} />
        <span>{new Date(item.created_at).toLocaleString('en-IN')}</span>
      </footer>
    </article>
  )
}
