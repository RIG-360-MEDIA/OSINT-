'use client'

import type { MonitorItem, Pillar } from './types'
import { PILLAR_KICKER } from './types'
import { useLivePillarFeed } from './useLivePillarFeed'
import {
  ArticleCard,
  ClipCard,
  DocumentCard,
  NewspaperCard,
  SocialCard,
} from './cards'

interface MonitorStripeProps {
  pillar: Pillar
  endpoint: string
  token: string | null
  paused: boolean
  staggerOffsetMs: number
  normalize: (raw: unknown) => MonitorItem[]
}

/**
 * One horizontal "shelf" per pillar — header band on top, then a left-to-right
 * scroll strip of pillar-specific cards. Each card mirrors its dedicated room's
 * visual identity (ArticleCard ↔ Coverage, NewspaperCard ↔ Cuttings, etc.).
 */
export function MonitorStripe({
  pillar,
  endpoint,
  token,
  paused,
  staggerOffsetMs,
  normalize,
}: MonitorStripeProps): React.ReactElement {
  const { items, totalToday, loading, error, lastUpdated } = useLivePillarFeed({
    endpoint,
    token,
    paused,
    staggerOffsetMs,
    normalize,
  })

  const updatedLabel = lastUpdated
    ? `updated ${lastUpdated.toLocaleTimeString('en-IN', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
        timeZone: 'Asia/Kolkata',
      })} IST`
    : ''

  return (
    <section style={{ padding: '36px 0', borderTop: '1px solid var(--rig-rule)' }}>
      <header
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: '16px',
          marginBottom: '18px',
          flexWrap: 'wrap',
        }}
      >
        <span className="rig-kicker rig-kicker-gold" style={{ flexShrink: 0 }}>
          <LiveDot paused={paused} />
          {PILLAR_KICKER[pillar]}
        </span>
        <span style={{ flex: 1, height: '1px', background: 'var(--rig-rule-hair)' }} />
        <span
          className="rig-byline"
          style={{ fontSize: '10px', color: 'var(--rig-ink-3)' }}
        >
          {totalToday > 0 ? `${totalToday} today` : '—'}
          {updatedLabel ? <span className="sep">·</span> : null}
          {updatedLabel}
        </span>
      </header>

      {error ? (
        <EmptyNote tone="error">Feed error — {error}</EmptyNote>
      ) : loading && items.length === 0 ? (
        <EmptyNote>Tuning the wire…</EmptyNote>
      ) : items.length === 0 ? (
        <EmptyNote>Quiet on this channel.</EmptyNote>
      ) : (
        <Shelf items={items} />
      )}
    </section>
  )
}

/* ── Horizontal-scroll shelf ───────────────────────────────────────────── */

function Shelf({ items }: { items: MonitorItem[] }): React.ReactElement {
  return (
    <div
      role="list"
      style={{
        display: 'flex',
        gap: '16px',
        overflowX: 'auto',
        overflowY: 'hidden',
        padding: '4px 4px 16px',
        // Native scroll-snap: each card aligns to the start when the user
        // flicks. Plays nicely with trackpad horizontal scroll on macOS and
        // shift-wheel on desktops.
        scrollSnapType: 'x mandatory',
        // Padding-inline so the first card has breathing room from the left
        // gutter and the last from the right.
        scrollPaddingLeft: '4px',
        scrollPaddingRight: '4px',
      }}
    >
      {items.map((item) => (
        <div
          key={`${item.pillar}-${item.id}`}
          role="listitem"
          className="anim-fade-up"
          style={{
            scrollSnapAlign: 'start',
            flex: '0 0 auto',
          }}
        >
          <Dispatch item={item} />
        </div>
      ))}
    </div>
  )
}

/**
 * Render the right card for the item's pillar. Discriminated union means
 * TypeScript narrows the item type inside each branch so the card receives
 * the exact shape it expects — no casts.
 */
function Dispatch({ item }: { item: MonitorItem }): React.ReactElement | null {
  switch (item.pillar) {
    case 'articles':
      return <ArticleCard item={item} />
    case 'newspaper':
      return <NewspaperCard item={item} />
    case 'social':
      return <SocialCard item={item} />
    case 'clips':
      return <ClipCard item={item} />
    case 'documents':
      return <DocumentCard item={item} />
    default:
      return null
  }
}

/* ── Bits ─────────────────────────────────────────────────────────────── */

function LiveDot({ paused }: { paused: boolean }): React.ReactElement {
  return (
    <span
      aria-hidden="true"
      style={{
        display: 'inline-block',
        width: '6px',
        height: '6px',
        borderRadius: '50%',
        background: paused ? 'var(--rig-ink-3)' : 'var(--rig-oxblood)',
        marginRight: '4px',
        animation: paused ? 'none' : 'pulse-gold 2.2s ease-out infinite',
      }}
    />
  )
}

function EmptyNote({
  tone = 'muted',
  children,
}: {
  tone?: 'muted' | 'error'
  children: React.ReactNode
}): React.ReactElement {
  return (
    <p
      className="rig-prose"
      style={{
        fontStyle: 'italic',
        color: tone === 'error' ? 'var(--rig-oxblood)' : 'var(--rig-ink-3)',
        fontSize: '14px',
      }}
    >
      {children}
    </p>
  )
}
