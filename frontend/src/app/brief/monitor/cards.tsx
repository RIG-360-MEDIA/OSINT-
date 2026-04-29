'use client'

/**
 * Pillar-specific cards for the Monitoring shelves.
 *
 * Each card mirrors the visual identity of its dedicated pillar room:
 *   - ArticleCard   ↔ Coverage Room's `Clipping` (thumbnail + headline)
 *   - NewspaperCard ↔ Cuttings room (vernacular headline + edition meta)
 *   - SocialCard    ↔ Signal Room's `PostRow` (platform + serif text)
 *   - ClipCard      ↔ Clip Room's `StoryCard` (16:9 thumbnail + transcript)
 *   - DocumentCard  ↔ Document Room's `DocumentRow` (geo kicker + title)
 *
 * All five accept a fixed shelf width via `width` so they line up cleanly
 * inside `MonitorStripe`'s horizontal scroller.
 *
 * Click behaviour: each card deep-links to its pillar room with a query
 * param the room already knows how to auto-open (e.g. Coverage handles
 * `?article=<id>`). That preserves the user's "click for summary"
 * expectation without duplicating the dialog code in this file.
 */

import { useState } from 'react'
import type {
  ArticleMonitorItem,
  ClipMonitorItem,
  DocumentMonitorItem,
  NewspaperMonitorItem,
  SocialMonitorItem,
} from './types'
import { timeAgo } from './normalizers'

const SHELF_CARD_WIDTH = 320
const SHELF_CARD_HEIGHT = 360

const TIER_LABEL: Record<number, string> = { 1: 'I', 2: 'II', 3: 'III' }

const PLATFORM_LABEL: Record<string, string> = {
  reddit: 'Reddit',
  telegram: 'Telegram',
  twitter: 'Twitter/X',
}

const URGENCY_TONE: Record<string, string> = {
  high: 'var(--rig-oxblood)',
  medium: 'var(--rig-gold)',
  low: 'var(--rig-ink-3)',
}

interface CardShellProps {
  href?: string | null
  onClick?: () => void
  children: React.ReactNode
  /** Pillar accent colour applied as the left border. */
  accent?: string
}

function CardShell({ href, onClick, children, accent }: CardShellProps): React.ReactElement {
  const inner = (
    <article
      className="card-lift"
      onClick={onClick}
      style={{
        width: `${SHELF_CARD_WIDTH}px`,
        height: `${SHELF_CARD_HEIGHT}px`,
        flex: '0 0 auto',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--rig-paper-2)',
        border: '1px solid var(--rig-rule)',
        borderLeft: accent ? `3px solid ${accent}` : '1px solid var(--rig-rule)',
        cursor: href || onClick ? 'pointer' : 'default',
        overflow: 'hidden',
        transition: 'transform 0.18s ease, border-color 0.18s ease',
      }}
    >
      {children}
    </article>
  )
  if (href) {
    return (
      <a
        href={href}
        style={{ textDecoration: 'none', color: 'inherit', display: 'block' }}
        target={href.startsWith('http') ? '_blank' : undefined}
        rel={href.startsWith('http') ? 'noopener noreferrer' : undefined}
      >
        {inner}
      </a>
    )
  }
  return inner
}

/* ── ArticleCard ───────────────────────────────────────────────────────── */

interface ArticleCardProps {
  item: ArticleMonitorItem
}

export function ArticleCard({ item }: ArticleCardProps): React.ReactElement {
  const [imgBroken, setImgBroken] = useState(false)
  const hasImage = !!item.thumbnail_url && !imgBroken
  const tierLabel = item.relevance_tier ? TIER_LABEL[item.relevance_tier] ?? 'III' : null
  const ago = timeAgo(item.timestamp)

  return (
    <CardShell href={`/coverage?article=${item.id}`} accent="var(--rig-ink, #1a1a1a)">
      {/* Thumbnail */}
      <div
        style={{
          height: '160px',
          position: 'relative',
          flexShrink: 0,
          overflow: 'hidden',
          background: 'var(--rig-paper)',
        }}
      >
        {hasImage ? (
          <img
            src={item.thumbnail_url as string}
            alt=""
            onError={() => setImgBroken(true)}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              display: 'block',
              filter: 'saturate(0.92) contrast(1.04)',
            }}
          />
        ) : (
          <div
            style={{
              width: '100%',
              height: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'var(--rig-paper-2)',
              filter: 'saturate(0.5) brightness(0.95)',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--font-serif)',
                fontStyle: 'italic',
                fontSize: '40px',
                color: 'var(--rig-ink-3)',
              }}
            >
              {(item.source_name ?? '??').slice(0, 2).toUpperCase()}
            </span>
          </div>
        )}
        {tierLabel && (
          <span
            className="rig-kicker"
            style={{
              position: 'absolute',
              top: '10px',
              right: '10px',
              background: 'rgba(0, 0, 0, 0.78)',
              color: 'var(--rig-paper)',
              padding: '3px 8px',
              fontSize: '9px',
              letterSpacing: '0.15em',
            }}
          >
            T · {tierLabel}
          </span>
        )}
      </div>

      {/* Body */}
      <div
        style={{
          padding: '14px 16px 16px',
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
          minHeight: 0,
        }}
      >
        <div className="rig-byline" style={{ fontSize: '9px' }}>
          <span>{item.source_name ?? '—'}</span>
          {ago && (
            <>
              <span className="sep">·</span>
              <span>{ago}</span>
            </>
          )}
        </div>
        <h3
          className="rig-headline"
          style={{
            fontSize: '17px',
            lineHeight: 1.22,
            margin: 0,
            display: '-webkit-box',
            WebkitLineClamp: 4,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {item.title || '(untitled)'}
        </h3>
      </div>
    </CardShell>
  )
}

/* ── NewspaperCard ─────────────────────────────────────────────────────── */

interface NewspaperCardProps {
  item: NewspaperMonitorItem
}

export function NewspaperCard({ item }: NewspaperCardProps): React.ReactElement {
  const [imgBroken, setImgBroken] = useState(false)
  const hasImage = !!item.clipping_image_url && !imgBroken
  const editionStr = item.edition_date ? new Date(item.edition_date).toLocaleDateString('en-IN', {
    day: 'numeric', month: 'short',
  }) : '—'
  const showTranslation =
    item.headline_translated &&
    item.headline_translated !== item.headline

  return (
    <CardShell href="/cuttings" accent="var(--rig-copper, #7a5a2e)">
      {/* Image strip OR newspaper-name banner if no image */}
      <div
        style={{
          height: '120px',
          position: 'relative',
          flexShrink: 0,
          overflow: 'hidden',
          background: 'var(--rig-paper-3)',
          borderBottom: '1px solid var(--rig-rule)',
        }}
      >
        {hasImage ? (
          <img
            src={item.clipping_image_url as string}
            alt=""
            onError={() => setImgBroken(true)}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              display: 'block',
              filter: 'sepia(0.15) contrast(1.05)',
            }}
          />
        ) : (
          <div
            style={{
              width: '100%',
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '12px',
              textAlign: 'center',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--font-serif)',
                fontStyle: 'italic',
                fontSize: '22px',
                color: 'var(--rig-copper, #7a5a2e)',
                lineHeight: 1.1,
              }}
            >
              {item.newspaper_name ?? 'Newspaper'}
            </span>
            <span
              className="rig-kicker"
              style={{ fontSize: '9px', marginTop: '6px', color: 'var(--rig-ink-3)' }}
            >
              {item.newspaper_language ?? ''} · {editionStr}
              {item.page_number ? ` · p.${item.page_number}` : ''}
            </span>
          </div>
        )}
      </div>

      <div style={{ padding: '14px 16px', flex: 1, display: 'flex', flexDirection: 'column', gap: '6px', minHeight: 0 }}>
        <div className="rig-byline" style={{ fontSize: '9px' }}>
          <span>{item.newspaper_name ?? '—'}</span>
          <span className="sep">·</span>
          <span>{editionStr}</span>
          {item.page_number ? (
            <>
              <span className="sep">·</span>
              <span>p.{item.page_number}</span>
            </>
          ) : null}
        </div>
        <h3
          className="rig-headline"
          lang={item.newspaper_language ?? undefined}
          style={{
            fontSize: '16px',
            lineHeight: 1.25,
            margin: 0,
            display: '-webkit-box',
            WebkitLineClamp: 3,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {item.headline || '(untitled)'}
        </h3>
        {showTranslation && (
          <p
            className="rig-prose"
            style={{
              fontSize: '12px',
              fontStyle: 'italic',
              color: 'var(--rig-ink-3)',
              margin: 0,
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
          >
            {item.headline_translated}
          </p>
        )}
      </div>
    </CardShell>
  )
}

/* ── SocialCard ────────────────────────────────────────────────────────── */

interface SocialCardProps {
  item: SocialMonitorItem
}

export function SocialCard({ item }: SocialCardProps): React.ReactElement {
  const ago = timeAgo(item.timestamp)
  const platformLabel = PLATFORM_LABEL[item.platform.toLowerCase()] ?? item.platform
  const showTranslated =
    item.post_text_translated &&
    item.post_language &&
    item.post_language !== 'en'
  const text = showTranslated ? item.post_text_translated! : item.post_text
  const sentiment = item.sentiment_score
  const sentimentArrow =
    sentiment === null
      ? null
      : sentiment > 0.15
        ? '▲'
        : sentiment < -0.15
          ? '▼'
          : '—'
  const sentimentColor =
    sentiment === null
      ? 'var(--rig-ink-3)'
      : sentiment > 0.15
        ? 'var(--rig-gold)'
        : sentiment < -0.15
          ? 'var(--rig-oxblood)'
          : 'var(--rig-ink-3)'

  return (
    <CardShell href={item.post_url ?? '/signals'} accent="var(--rig-slate, #1f5a7a)">
      {/* Platform / author meta band */}
      <div
        style={{
          padding: '12px 16px 8px',
          background: 'rgba(31, 90, 122, 0.06)',
          borderBottom: '1px solid var(--rig-rule-hair)',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            gap: '8px',
            fontFamily: 'var(--font-mono)',
            fontSize: '10px',
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            color: 'var(--rig-ink-3)',
          }}
        >
          <span style={{ color: 'var(--rig-slate, #1f5a7a)', fontWeight: 600 }}>
            {platformLabel}
          </span>
          <span aria-hidden="true">·</span>
          <span
            style={{
              maxWidth: '140px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {item.monitor_name ?? item.author ?? '—'}
          </span>
          <span aria-hidden="true" style={{ marginLeft: 'auto' }} />
          {sentimentArrow && (
            <span style={{ color: sentimentColor }} aria-label="sentiment">
              {sentimentArrow}
            </span>
          )}
        </div>
      </div>

      {/* Post text */}
      <div
        style={{
          flex: 1,
          padding: '14px 16px',
          minHeight: 0,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
        }}
      >
        <p
          lang={item.post_language ?? undefined}
          style={{
            fontFamily: 'var(--font-serif)',
            fontSize: '14.5px',
            lineHeight: 1.5,
            margin: 0,
            color: 'var(--rig-ink)',
            display: '-webkit-box',
            WebkitLineClamp: 8,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {text}
        </p>
      </div>

      {/* Footer meta */}
      <div
        style={{
          padding: '8px 16px 12px',
          borderTop: '1px solid var(--rig-rule-hair)',
          display: 'flex',
          gap: '12px',
          fontFamily: 'var(--font-mono)',
          fontSize: '9.5px',
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          color: 'var(--rig-ink-3)',
        }}
      >
        <span>{ago || 'just now'}</span>
        {typeof item.upvotes === 'number' && item.upvotes > 0 && (
          <>
            <span aria-hidden="true">·</span>
            <span>↑ {item.upvotes}</span>
          </>
        )}
        {typeof item.comment_count === 'number' && item.comment_count > 0 && (
          <>
            <span aria-hidden="true">·</span>
            <span>💬 {item.comment_count}</span>
          </>
        )}
      </div>
    </CardShell>
  )
}

/* ── ClipCard ──────────────────────────────────────────────────────────── */

interface ClipCardProps {
  item: ClipMonitorItem
}

export function ClipCard({ item }: ClipCardProps): React.ReactElement {
  const [imgBroken, setImgBroken] = useState(false)
  const hasImage = !!item.thumbnail_url && !imgBroken
  const startSec = item.clip_start_seconds ?? 0
  const minutes = Math.floor(startSec / 60)
  const seconds = startSec % 60
  const timestamp = `${minutes}:${String(seconds).padStart(2, '0')}`
  const ago = timeAgo(item.timestamp)
  const transcript = item.transcript_translated ?? item.transcript_segment ?? null

  return (
    <CardShell href={`/clips`} accent="var(--rig-violet, #5a2e7a)">
      {/* 16:9 thumbnail */}
      <div
        style={{
          width: '100%',
          aspectRatio: '16/9',
          background: '#000',
          position: 'relative',
          flexShrink: 0,
          overflow: 'hidden',
        }}
      >
        {hasImage ? (
          <img
            src={item.thumbnail_url as string}
            alt={item.video_title}
            onError={() => setImgBroken(true)}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              display: 'block',
              filter: 'grayscale(0.1) contrast(1.04)',
            }}
          />
        ) : (
          <div
            style={{
              width: '100%',
              height: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: '#111',
              color: '#888',
              fontSize: '28px',
            }}
          >
            ▶
          </div>
        )}
        {/* Play overlay + timestamp */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'rgba(0,0,0,0.10)',
          }}
        >
          <span
            style={{
              width: '48px',
              height: '48px',
              borderRadius: '50%',
              background: 'rgba(0,0,0,0.7)',
              color: '#fff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '20px',
              paddingLeft: '4px',
            }}
            aria-hidden="true"
          >
            ▶
          </span>
        </div>
        <span
          style={{
            position: 'absolute',
            bottom: '8px',
            right: '8px',
            background: 'rgba(0,0,0,0.78)',
            color: '#fff',
            padding: '2px 7px',
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            letterSpacing: '0.05em',
          }}
        >
          {timestamp}
        </span>
      </div>

      <div style={{ padding: '14px 16px', flex: 1, display: 'flex', flexDirection: 'column', gap: '8px', minHeight: 0 }}>
        <div className="rig-byline" style={{ fontSize: '9px' }}>
          <span>{item.channel_name ?? '—'}</span>
          {item.matched_entity && (
            <>
              <span className="sep">·</span>
              <span>{item.matched_entity}</span>
            </>
          )}
          {ago && (
            <>
              <span className="sep">·</span>
              <span>{ago}</span>
            </>
          )}
        </div>
        <h3
          className="rig-headline"
          style={{
            fontSize: '15px',
            lineHeight: 1.25,
            margin: 0,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {item.video_title || '(untitled clip)'}
        </h3>
        {transcript && (
          <p
            style={{
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              fontSize: '12.5px',
              lineHeight: 1.4,
              color: 'var(--rig-ink-2, #2c2722)',
              margin: 0,
              borderLeft: '2px solid var(--rig-violet, #5a2e7a)',
              paddingLeft: '8px',
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
          >
            {`"${transcript}"`}
          </p>
        )}
      </div>
    </CardShell>
  )
}

/* ── DocumentCard ──────────────────────────────────────────────────────── */

interface DocumentCardProps {
  item: DocumentMonitorItem
}

export function DocumentCard({ item }: DocumentCardProps): React.ReactElement {
  const ago = timeAgo(item.timestamp)
  const urgencyColor = item.urgency
    ? URGENCY_TONE[item.urgency.toLowerCase()] ?? 'var(--rig-ink-3)'
    : null

  return (
    <CardShell href="/documents" accent="var(--rig-oxblood, #7a1f1f)">
      {/* Top kicker band — geo · type */}
      <div
        style={{
          padding: '14px 16px 10px',
          borderBottom: '1px solid var(--rig-rule-hair)',
          background: 'rgba(122, 31, 31, 0.04)',
        }}
      >
        <div
          className="rig-kicker"
          style={{
            display: 'flex',
            alignItems: 'baseline',
            gap: '8px',
            fontSize: '9px',
            color: 'var(--rig-oxblood, #7a1f1f)',
            flexWrap: 'wrap',
          }}
        >
          <span>{item.source_geography ?? '—'}</span>
          {item.document_type && (
            <>
              <span aria-hidden="true">·</span>
              <span>{item.document_type.replace(/_/g, ' ')}</span>
            </>
          )}
          {urgencyColor && item.urgency && (
            <>
              <span aria-hidden="true">·</span>
              <span style={{ color: urgencyColor, fontWeight: 600 }}>
                {item.urgency.toUpperCase()}
              </span>
            </>
          )}
        </div>
      </div>

      <div
        style={{
          flex: 1,
          padding: '14px 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
          minHeight: 0,
        }}
      >
        <h3
          className="rig-headline"
          style={{
            fontSize: '17px',
            lineHeight: 1.25,
            margin: 0,
            display: '-webkit-box',
            WebkitLineClamp: 3,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {item.title || '(untitled document)'}
        </h3>
        {item.intel_snippet && (
          <p
            className="rig-prose"
            style={{
              fontSize: '13px',
              fontStyle: 'italic',
              color: 'var(--rig-ink-2, #2c2722)',
              margin: 0,
              display: '-webkit-box',
              WebkitLineClamp: 4,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
          >
            {item.intel_snippet}
          </p>
        )}
      </div>

      <div
        style={{
          padding: '8px 16px 12px',
          borderTop: '1px solid var(--rig-rule-hair)',
          display: 'flex',
          gap: '10px',
          fontFamily: 'var(--font-mono)',
          fontSize: '9.5px',
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          color: 'var(--rig-ink-3)',
        }}
      >
        {item.source_name && <span>{item.source_name}</span>}
        {item.source_name && ago ? <span aria-hidden="true">·</span> : null}
        {ago && <span>{ago}</span>}
      </div>
    </CardShell>
  )
}
