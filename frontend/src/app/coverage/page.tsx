'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import Navigation from '@/components/Navigation'
import { Dateline } from '@/components/Dateline'
import { domainColor, formatTimeAgo } from '@/lib/domainColor'

/* ── Types ────────────────────────────────────────────────────────────────── */

interface Article {
  article_id: string
  title: string
  url: string
  thumbnail_url: string | null
  author_name?: string | null
  topic_category: string | null
  geo_primary: string | null
  published_at?: string | null
  collected_at: string | null
  source_name: string
  source_domain: string
  has_full_text?: boolean
  score_final: number
  relevance_tier: number
  relevance_explanation: string | null
  matched_entity_names: string[]
  geo_multiplier?: number
  sentiment_for_user: 'FOR_USER' | 'AGAINST_USER' | 'NEUTRAL'
}

interface Totals { total: number; tier1: number; tier2: number; tier3: number }
interface FeedResponse {
  articles: Article[]
  pagination: { has_more: boolean; next_cursor: string | null; returned: number }
  totals: Totals
}
interface SearchResponse { query: string; count: number; articles: Article[] }

type TierFilter      = 'all' | '1' | '1,2'
type SortOption      = 'relevance' | 'recency'

/* ── Constants ────────────────────────────────────────────────────────────── */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const TOPICS = [
  'POLITICS', 'ECONOMICS', 'BUSINESS', 'TECHNOLOGY',
  'HEALTH', 'SCIENCE', 'ENVIRONMENT', 'SECURITY',
  'LEGAL', 'SOCIAL', 'INFRASTRUCTURE', 'AGRICULTURE',
  'EDUCATION', 'SPORTS', 'INTERNATIONAL',
]

const TIER_LABEL: Record<number, string> = { 1: 'I', 2: 'II', 3: 'III' }
const TIER_NAME: Record<number, string>  = { 1: 'Lead', 2: 'Notable', 3: 'Background' }

// Sentiment → left border on clipping
const SENTIMENT_BORDER: Record<string, string> = {
  FOR_USER:     'var(--rig-gold)',
  AGAINST_USER: 'var(--rig-oxblood)',
  NEUTRAL:      'transparent',
}

/* ── Clipping card ────────────────────────────────────────────────────────── */

function Clipping({ article, onClick }: { article: Article; onClick: () => void }) {
  const brandColor = domainColor(article.source_domain || article.source_name)
  const timeAgo    = formatTimeAgo(article.collected_at)
  const [imgBroken, setImgBroken] = useState(false)
  const hasImage   = !!article.thumbnail_url && !imgBroken
  const sentBorder = SENTIMENT_BORDER[article.sentiment_for_user] ?? 'transparent'
  const tierLabel  = TIER_LABEL[article.relevance_tier] ?? 'III'

  return (
    <article
      onClick={onClick}
      className="card-lift"
      style={{
        background: 'var(--rig-paper-2)',
        border: '1px solid var(--rig-rule)',
        borderLeft: sentBorder !== 'transparent'
          ? `2px solid ${sentBorder}`
          : '1px solid var(--rig-rule)',
        cursor: 'pointer',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        transition: 'border-color 0.2s',
      }}
    >
      {/* Thumbnail / Fallback */}
      <div style={{ height: '140px', position: 'relative', flexShrink: 0, overflow: 'hidden' }}>
        {hasImage ? (
          <img
            src={article.thumbnail_url as string}
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
          <div style={{
            width: '100%', height: '100%',
            backgroundColor: brandColor,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            filter: 'saturate(0.5) brightness(0.9)',
          }}>
            <span style={{
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              fontSize: '44px',
              color: 'var(--rig-paper)',
            }}>
              {article.source_name.slice(0, 2).toUpperCase()}
            </span>
          </div>
        )}
        {/* Tier numeral overlay */}
        <span
          className="rig-kicker"
          style={{
            position: 'absolute',
            top: '10px',
            right: '12px',
            background: 'var(--rig-paper)',
            padding: '3px 9px',
            border: '1px solid var(--rig-rule)',
            fontSize: '9px',
            letterSpacing: '0.28em',
            color: 'var(--rig-ink)',
          }}
        >
          T · {tierLabel}
        </span>
      </div>

      {/* Body */}
      <div style={{ padding: '16px 18px 18px', flex: 1, display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {/* Byline */}
        <div className="rig-byline" style={{ fontSize: '9px' }}>
          <span>{article.source_name}</span>
          {timeAgo && (<><span className="sep">·</span><span>{timeAgo}</span></>)}
        </div>

        {/* Title */}
        <h3
          className="rig-headline"
          style={{
            fontSize: '18px',
            lineHeight: 1.18,
            display: '-webkit-box',
            WebkitLineClamp: 3,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {article.title}
        </h3>

        {/* Relevance */}
        <p
          className="rig-prose"
          style={{
            fontSize: '13px',
            color: 'var(--rig-ink-3)',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            fontStyle: 'italic',
            fontFamily: 'var(--font-serif)',
            lineHeight: 1.45,
          }}
        >
          {article.relevance_explanation || 'Relevant to your monitored geography and topics.'}
        </p>

        {/* Footer */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginTop: 'auto',
            paddingTop: '10px',
            borderTop: '1px solid var(--rig-rule-hair)',
          }}
        >
          <div className="rig-byline" style={{ fontSize: '9px', gap: '8px' }}>
            {article.topic_category && <span>{article.topic_category}</span>}
            {article.topic_category && article.geo_primary && <span className="sep">·</span>}
            {article.geo_primary && <span>{article.geo_primary}</span>}
          </div>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '11px',
              color: 'var(--rig-gold)',
              letterSpacing: '0.06em',
            }}
          >
            {article.score_final.toFixed(2)}
          </span>
        </div>
      </div>
    </article>
  )
}

/* ── Tier separator ───────────────────────────────────────────────────────── */

function TierSeparator({ numeral, name }: { numeral: string; name: string }) {
  return (
    <div style={{
      gridColumn: '1 / -1',
      display: 'flex',
      alignItems: 'center',
      gap: '16px',
      padding: '22px 0 8px',
    }}>
      <span
        style={{
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontSize: '24px',
          color: 'var(--rig-copper)',
          lineHeight: 1,
        }}
      >
        {numeral}.
      </span>
      <span
        className="rig-kicker"
        style={{ fontSize: '10px' }}
      >
        Tier {numeral} — {name}
      </span>
      <div style={{ flex: 1, height: '1px', background: 'var(--rig-rule)' }} />
    </div>
  )
}

/* ── Article dialog (slide-in panel) ──────────────────────────────────────── */

function ArticleDialog({
  article, summary, summaryLoading, summaryError,
  onClose, onGenerateSummary,
}: {
  article: Article
  summary: string | null
  summaryLoading: boolean
  summaryError: string | null
  onClose: () => void
  onGenerateSummary: () => void
}) {
  const brandColor = domainColor(article.source_domain || article.source_name)
  const [imgBroken, setImgBroken] = useState(false)
  const hasImage   = !!article.thumbnail_url && !imgBroken
  const tierLabel  = TIER_LABEL[article.relevance_tier] ?? 'III'
  const panelRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const html = document.documentElement
    const body = document.body
    const scrollY = window.scrollY
    const scrollbarWidth = window.innerWidth - html.clientWidth

    const prev = {
      htmlOverflow: html.style.overflow,
      bodyOverflow: body.style.overflow,
      bodyPosition: body.style.position,
      bodyTop: body.style.top,
      bodyWidth: body.style.width,
      bodyPaddingRight: body.style.paddingRight,
    }

    html.style.overflow = 'hidden'
    body.style.overflow = 'hidden'
    body.style.position = 'fixed'
    body.style.top = `-${scrollY}px`
    body.style.width = '100%'
    if (scrollbarWidth > 0) {
      body.style.paddingRight = `${scrollbarWidth}px`
    }

    const blockOutside = (e: Event) => {
      const panel = panelRef.current
      if (!panel) { e.preventDefault(); return }
      const target = e.target as Node | null
      if (!target || !panel.contains(target)) {
        e.preventDefault()
      }
    }
    window.addEventListener('wheel', blockOutside, { passive: false })
    window.addEventListener('touchmove', blockOutside, { passive: false })

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)

    return () => {
      html.style.overflow = prev.htmlOverflow
      body.style.overflow = prev.bodyOverflow
      body.style.position = prev.bodyPosition
      body.style.top = prev.bodyTop
      body.style.width = prev.bodyWidth
      body.style.paddingRight = prev.bodyPaddingRight
      window.removeEventListener('wheel', blockOutside)
      window.removeEventListener('touchmove', blockOutside)
      window.removeEventListener('keydown', onKey)
      window.scrollTo(0, scrollY)
    }
  }, [onClose])

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'color-mix(in srgb, var(--rig-ink) 50%, transparent)',
        backdropFilter: 'blur(6px)',
        zIndex: 300,
        overscrollBehavior: 'contain',
      }}
    >
      <div
        ref={panelRef}
        onClick={(e) => e.stopPropagation()}
        className="anim-slide-right"
        style={{
          position: 'fixed',
          top: 'var(--topbar-h, 0px)',
          right: 0,
          bottom: 0,
          width: '560px',
          maxWidth: '100vw',
          background: 'var(--rig-paper)',
          borderLeft: '1px solid var(--rig-rule)',
          overflowY: 'auto',
          overscrollBehavior: 'contain',
          WebkitOverflowScrolling: 'touch',
        }}
      >
        <button
          onClick={onClose}
          aria-label="Close"
          style={{
            position: 'absolute',
            top: '16px',
            right: '16px',
            width: '32px',
            height: '32px',
            background: 'var(--rig-paper-2)',
            border: '1px solid var(--rig-rule)',
            color: 'var(--rig-ink-2)',
            cursor: 'pointer',
            fontSize: '18px',
            zIndex: 1,
            fontFamily: 'var(--font-serif)',
            lineHeight: 1,
          }}
          onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--rig-gold)' }}
          onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--rig-rule)' }}
        >
          ×
        </button>

        {/* Hero */}
        {hasImage ? (
          <img
            src={article.thumbnail_url as string}
            alt=""
            onError={() => setImgBroken(true)}
            style={{
              width: '100%',
              height: '220px',
              objectFit: 'cover',
              display: 'block',
              filter: 'saturate(0.9) contrast(1.04)',
            }}
          />
        ) : (
          <div style={{
            width: '100%',
            height: '220px',
            backgroundColor: brandColor,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            filter: 'saturate(0.45) brightness(0.88)',
          }}>
            <span style={{ fontFamily: 'var(--font-serif)', fontStyle: 'italic', fontSize: '72px', color: 'var(--rig-paper)' }}>
              {article.source_name.slice(0, 2).toUpperCase()}
            </span>
          </div>
        )}

        <div style={{ padding: '32px 36px 56px' }}>
          {/* Kicker */}
          <div className="rig-kicker rig-kicker-gold" style={{ marginBottom: '18px' }}>
            <span style={{ width: '28px', height: '1px', background: 'var(--rig-gold)', opacity: 0.7 }} />
            Tier {tierLabel} · {TIER_NAME[article.relevance_tier] ?? 'Background'}
          </div>

          {/* Title */}
          <h2
            className="rig-headline"
            style={{ fontSize: '32px', lineHeight: 1.1, marginBottom: '18px' }}
          >
            {article.title}
          </h2>

          {/* Byline */}
          <div className="rig-byline" style={{ marginBottom: '28px' }}>
            <span>{article.source_name}</span>
            {article.collected_at && (<><span className="sep">·</span><span>{formatTimeAgo(article.collected_at)}</span></>)}
            {article.author_name && (<><span className="sep">·</span><span>{article.author_name}</span></>)}
          </div>

          {/* Why this matters */}
          <div
            style={{
              padding: '18px 20px',
              borderLeft: '2px solid var(--rig-gold)',
              background: 'var(--rig-overlay)',
              marginBottom: '28px',
            }}
          >
            <div className="rig-kicker rig-kicker-gold" style={{ fontSize: '9px', marginBottom: '8px' }}>
              Why this matters
            </div>
            <p
              className="rig-serif-body"
              style={{ fontSize: '17px', color: 'var(--rig-ink)' }}
            >
              {article.relevance_explanation || 'Relevant to your monitored geography and topics.'}
            </p>
          </div>

          {/* Summary */}
          {!summary && !summaryLoading && !summaryError && (
            <button onClick={onGenerateSummary} className="rig-btn-ghost" style={{ marginBottom: '24px' }}>
              ✦ Generate summary
            </button>
          )}
          {summaryLoading && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
              <div style={{
                width: '14px', height: '14px', borderRadius: '50%',
                border: '1.5px solid var(--rig-rule)',
                borderTopColor: 'var(--rig-gold)',
                animation: 'spin 0.8s linear infinite',
              }} />
              <span className="rig-byline">Filing summary…</span>
            </div>
          )}
          {summaryError && !summaryLoading && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
              <span className="rig-byline" style={{ color: 'var(--rig-oxblood)' }}>{summaryError}</span>
              <button onClick={onGenerateSummary} className="rig-btn-ghost">
                Retry
              </button>
            </div>
          )}
          {summary && (
            <div style={{
              padding: '18px 20px',
              border: '1px solid var(--rig-rule)',
              background: 'var(--rig-paper-2)',
              marginBottom: '28px',
            }}>
              <div className="rig-kicker" style={{ fontSize: '9px', marginBottom: '10px' }}>
                Summary
              </div>
              <p className="rig-serif-body" style={{ fontSize: '16px' }}>{summary}</p>
            </div>
          )}

          {/* Matched entities */}
          {article.matched_entity_names.length > 0 && (
            <div style={{ marginBottom: '28px' }}>
              <div className="rig-kicker" style={{ fontSize: '9px', marginBottom: '12px' }}>
                Matched entities
              </div>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {article.matched_entity_names.map((e) => (
                  <span
                    key={e}
                    style={{
                      padding: '4px 12px',
                      border: '1px solid var(--rig-rule)',
                      fontFamily: 'var(--font-mono)',
                      fontSize: '10px',
                      letterSpacing: '0.16em',
                      textTransform: 'uppercase',
                      color: 'var(--rig-ink-2)',
                    }}
                  >
                    {e}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Meta row */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '16px',
              flexWrap: 'wrap',
              padding: '16px 0',
              borderTop: '1px solid var(--rig-rule-hair)',
              borderBottom: '1px solid var(--rig-rule-hair)',
              marginBottom: '24px',
            }}
          >
            <span className="rig-byline">
              {article.topic_category && <span>{article.topic_category}</span>}
              {article.topic_category && article.geo_primary && <span className="sep">·</span>}
              {article.geo_primary && <span>{article.geo_primary}</span>}
            </span>
            <span
              style={{
                marginLeft: 'auto',
                fontFamily: 'var(--font-mono)',
                fontSize: '12px',
                color: 'var(--rig-gold)',
                letterSpacing: '0.1em',
              }}
            >
              Score {article.score_final.toFixed(2)}
            </span>
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '16px' }}>
            <span className="rig-byline" style={{ color: 'var(--rig-ink-4)', cursor: 'default' }}>
              ♦ Save to collection
            </span>
            <a
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              className="rig-btn-primary"
              style={{ padding: '12px 20px', fontSize: '10px', gap: '12px', textDecoration: 'none' }}
            >
              Read original
              <span className="arrow">→</span>
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ── Filter bar ───────────────────────────────────────────────────────────── */

function FilterBar(props: {
  selectedTopics: string[]
  onToggleTopic: (t: string) => void
  selectedTier: TierFilter
  onTierChange: (t: TierFilter) => void
  selectedDays: number
  onDaysChange: (d: number) => void
  sortBy: SortOption
  onSortChange: (s: SortOption) => void
  onClearFilters: () => void
}) {
  const [topicsOpen, setTopicsOpen] = useState(false)
  const activeFilters =
    props.selectedTopics.length > 0 ||
    props.selectedTier !== 'all' ||
    props.selectedDays !== 0

  return (
    <div
      style={{
        position: 'sticky',
        top: 'var(--topbar-h)',
        zIndex: 100,
        background: 'var(--rig-paper-2)',
        borderBottom: '1px solid var(--rig-rule)',
        padding: '12px 40px',
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        flexWrap: 'wrap',
      }}
    >
      {/* Topics */}
      <div style={{ position: 'relative' }}>
        <FilterPill active={props.selectedTopics.length > 0} onClick={() => setTopicsOpen((v) => !v)}>
          Topics
          {props.selectedTopics.length > 0 && (
            <span style={{
              marginLeft: '4px',
              fontFamily: 'var(--font-mono)',
              color: 'var(--rig-gold)',
            }}>{props.selectedTopics.length}</span>
          )}
          <span aria-hidden="true" style={{ marginLeft: '4px', fontSize: '8px', opacity: 0.6 }}>
            {topicsOpen ? '▲' : '▼'}
          </span>
        </FilterPill>

        {topicsOpen && (
          <div
            style={{
              position: 'absolute',
              top: 'calc(100% + 10px)',
              left: 0,
              background: 'var(--rig-paper)',
              border: '1px solid var(--rig-rule)',
              padding: '12px',
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: '4px',
              minWidth: '360px',
              zIndex: 200,
            }}
          >
            {TOPICS.map((t) => {
              const active = props.selectedTopics.includes(t)
              return (
                <button
                  key={t}
                  onClick={() => props.onToggleTopic(t)}
                  style={{
                    padding: '6px 10px',
                    background: active ? 'var(--rig-overlay)' : 'transparent',
                    border: 'none',
                    color: active ? 'var(--rig-gold)' : 'var(--rig-ink-3)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '10px',
                    letterSpacing: '0.18em',
                    textTransform: 'uppercase',
                    cursor: 'pointer',
                    textAlign: 'left',
                    transition: 'color 0.15s',
                  }}
                >
                  {t}
                </button>
              )
            })}
          </div>
        )}
      </div>

      <FilterDivider />

      {([
        ['all', 'All tiers'],
        ['1', 'Tier I'],
        ['1,2', 'T I+II'],
      ] as const).map(([v, lbl]) => (
        <FilterPill key={v} active={props.selectedTier === v} onClick={() => props.onTierChange(v)}>
          {lbl}
        </FilterPill>
      ))}

      <FilterDivider />

      {([[0, 'All time'], [7, 'This week'], [1, 'Today']] as const).map(([v, lbl]) => (
        <FilterPill key={v} active={props.selectedDays === v} onClick={() => props.onDaysChange(v)}>
          {lbl}
        </FilterPill>
      ))}

      <FilterDivider />

      {([
        ['relevance', 'By weight'],
        ['recency', 'By wire'],
      ] as const).map(([v, lbl]) => (
        <FilterPill key={v} active={props.sortBy === v} onClick={() => props.onSortChange(v)}>
          {lbl}
        </FilterPill>
      ))}

      {activeFilters && (
        <>
          <FilterDivider />
          <button
            onClick={props.onClearFilters}
            style={{
              padding: '5px 12px',
              background: 'transparent',
              border: '1px solid color-mix(in srgb, var(--rig-oxblood) 50%, transparent)',
              color: 'var(--rig-oxblood)',
              fontFamily: 'var(--font-mono)',
              fontSize: '10px',
              letterSpacing: '0.2em',
              textTransform: 'uppercase',
              cursor: 'pointer',
            }}
          >
            × Clear
          </button>
        </>
      )}
    </div>
  )
}

function FilterPill({ active, onClick, children }: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '5px 12px',
        border: `1px solid ${active ? 'var(--rig-gold)' : 'var(--rig-rule)'}`,
        background: active ? 'var(--rig-overlay)' : 'transparent',
        color: active ? 'var(--rig-gold)' : 'var(--rig-ink-3)',
        fontFamily: 'var(--font-mono)',
        fontSize: '10px',
        letterSpacing: '0.2em',
        textTransform: 'uppercase',
        cursor: 'pointer',
        transition: 'color 0.15s, border-color 0.15s, background 0.15s',
        whiteSpace: 'nowrap',
      }}
    >
      {children}
    </button>
  )
}

function FilterDivider() {
  return (
    <div
      aria-hidden="true"
      style={{
        width: '1px',
        height: '16px',
        background: 'var(--rig-rule)',
        flexShrink: 0,
      }}
    />
  )
}

/* ── Skeleton ─────────────────────────────────────────────────────────────── */

function SkeletonClipping() {
  return (
    <div style={{ background: 'var(--rig-paper-2)', border: '1px solid var(--rig-rule)', overflow: 'hidden' }}>
      <div className="skeleton" style={{ height: '140px' }} />
      <div style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
        <div className="skeleton" style={{ height: '10px', width: '50%' }} />
        <div className="skeleton" style={{ height: '16px', width: '95%' }} />
        <div className="skeleton" style={{ height: '14px', width: '80%' }} />
        <div className="skeleton" style={{ height: '10px', width: '40%' }} />
      </div>
    </div>
  )
}

/* ── Stats badge ──────────────────────────────────────────────────────────── */

function StatBadge({ value, label, tone }: { value: string; label: string; tone?: 'gold' | 'copper' | 'default' }) {
  const color =
    tone === 'gold' ? 'var(--rig-gold)' :
    tone === 'copper' ? 'var(--rig-copper)' :
    'var(--rig-ink-2)'
  return (
    <div style={{ display: 'inline-flex', alignItems: 'baseline', gap: '6px' }}>
      <span style={{
        fontFamily: 'var(--font-serif)',
        fontSize: '22px',
        color,
        lineHeight: 1,
      }}>{value}</span>
      <span
        className="rig-byline"
        style={{ fontSize: '9px' }}
      >{label}</span>
    </div>
  )
}

/* ── Main page ────────────────────────────────────────────────────────────── */

export default function CoveragePage() {
  const router = useRouter()
  const searchParams = useSearchParams()

  const getToken = useCallback(async (): Promise<string | null> => {
    const supabase = createClient()
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) { router.push('/login'); return null }
    return session.access_token
  }, [router])

  const [loading, setLoading]           = useState(true)
  const [loadingMore, setLoadingMore]   = useState(false)
  const [articles, setArticles]         = useState<Article[]>([])
  const [hasMore, setHasMore]           = useState(false)
  const [nextCursor, setNextCursor]     = useState<string>('')
  const [totals, setTotals]             = useState<Totals>({ total: 0, tier1: 0, tier2: 0, tier3: 0 })
  const [errorMsg, setErrorMsg]         = useState<string>('')

  const [selectedTopics, setSelectedTopics]       = useState<string[]>([])
  const [selectedTier, setSelectedTier]           = useState<TierFilter>('all')
  const [selectedDays, setSelectedDays]           = useState<number>(0)
  const [sortBy, setSortBy]                       = useState<SortOption>('relevance')

  const [searchQuery, setSearchQuery]     = useState('')
  const [searchResults, setSearchResults] = useState<Article[] | null>(null)
  const [isSearching, setIsSearching]     = useState(false)

  const [selectedArticle, setSelectedArticle]   = useState<Article | null>(null)
  const [summariesById, setSummariesById]       = useState<Record<string, string>>({})
  const [summaryLoading, setSummaryLoading]     = useState(false)
  const [summaryError, setSummaryError]         = useState<string | null>(null)

  const buildFeedUrl = useCallback((cursor: string = '') => {
    const params = new URLSearchParams()
    const tierParam = selectedTier === 'all' ? '1,2,3' : selectedTier
    params.set('tier', tierParam)
    if (selectedTopics.length > 0) params.set('topic', selectedTopics.join(','))
    if (selectedDays > 0) params.set('days', String(selectedDays))
    params.set('sort', sortBy)
    if (cursor) params.set('cursor', cursor)
    params.set('limit', '20')
    return `${API_BASE}/api/coverage/feed?${params.toString()}`
  }, [selectedTier, selectedTopics, selectedDays, sortBy])

  const inflightRef = useRef<AbortController | null>(null)
  const fetchFeed = useCallback(async (cursor: string = '', append = false) => {
    const token = await getToken()
    if (!token) return
    inflightRef.current?.abort()
    const ctrl = new AbortController()
    inflightRef.current = ctrl
    append ? setLoadingMore(true) : setLoading(true)
    setErrorMsg('')
    try {
      const res = await fetch(buildFeedUrl(cursor), { headers: { Authorization: `Bearer ${token}` }, signal: ctrl.signal })
      if (!res.ok) { setErrorMsg(`Feed request failed (${res.status})`); return }
      const data: FeedResponse = await res.json()
      setArticles((prev) => append ? [...prev, ...data.articles] : data.articles)
      setHasMore(data.pagination.has_more)
      setNextCursor(data.pagination.next_cursor ?? '')
      setTotals(data.totals)
    } catch (e) {
      if (ctrl.signal.aborted) return
      setErrorMsg(e instanceof Error ? e.message : 'Network error')
    } finally {
      if (inflightRef.current === ctrl) inflightRef.current = null
      if (!ctrl.signal.aborted) {
        setLoading(false)
        setLoadingMore(false)
      }
    }
  }, [buildFeedUrl, getToken])

  useEffect(() => { void fetchFeed('', false) }, []) // eslint-disable-line

  useEffect(() => {
    const articleParam = searchParams.get('article')
    if (!articleParam) return
    let cancelled = false
    const open = async () => {
      const token = await getToken()
      if (!token || cancelled) return
      try {
        const res = await fetch(`${API_BASE}/api/coverage/article/${articleParam}`, { headers: { Authorization: `Bearer ${token}` } })
        if (!res.ok || cancelled) return
        const article: Article = await res.json()
        if (!cancelled) handleOpenArticle(article)
      } catch { /* silent */ }
    }
    void open()
    return () => { cancelled = true }
    // eslint-disable-next-line
  }, [searchParams])

  const filtersKey = `${selectedTier}|${selectedTopics.join(',')}|${selectedDays}|${sortBy}`
  const didMountRef = useRef(false)
  useEffect(() => {
    if (!didMountRef.current) { didMountRef.current = true; return }
    void fetchFeed('', false)
    // eslint-disable-next-line
  }, [filtersKey])

  const handleSearchEnter = async () => {
    if (searchQuery.trim().length < 2) return
    const token = await getToken()
    if (!token) return
    setIsSearching(true)
    try {
      const params = new URLSearchParams({ q: searchQuery.trim(), tier: selectedTier === 'all' ? '1,2,3' : selectedTier })
      const res = await fetch(`${API_BASE}/api/coverage/search?${params}`, { headers: { Authorization: `Bearer ${token}` } })
      if (res.ok) { const data: SearchResponse = await res.json(); setSearchResults(data.articles) }
    } catch { /* ignore */ } finally { setIsSearching(false) }
  }

  const clearSearch     = () => { setSearchQuery(''); setSearchResults(null) }
  const handleToggleTopic = (t: string) => setSelectedTopics((prev) => prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t])
  const clearFilters    = () => { setSelectedTopics([]); setSelectedTier('all'); setSelectedDays(0); setSortBy('relevance') }
  const handleOpenArticle = (a: Article) => { setSelectedArticle(a); setSummaryError(null) }
  const handleCloseDialog = () => { setSelectedArticle(null); setSummaryError(null) }

  const handleGenerateSummary = async () => {
    if (!selectedArticle) return
    const id = selectedArticle.article_id
    if (summariesById[id]) return
    const token = await getToken()
    if (!token) return
    setSummaryLoading(true)
    setSummaryError(null)
    try {
      const res = await fetch(`${API_BASE}/api/coverage/summary/${id}`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
      if (!res.ok) { setSummaryError('Summary generation failed'); return }
      const data: { summary: string } = await res.json()
      setSummariesById((prev) => ({ ...prev, [id]: data.summary }))
    } catch { setSummaryError('Network error — check connection') }
    finally { setSummaryLoading(false) }
  }

  const serverSearchActive  = searchResults !== null
  const clientFilterActive  = !serverSearchActive && searchQuery.trim().length >= 2
  const visibleArticles     = serverSearchActive
    ? (searchResults as Article[])
    : clientFilterActive
      ? articles.filter((a) => a.title.toLowerCase().includes(searchQuery.trim().toLowerCase()))
      : articles

  const renderGrid = () => {
    const nodes: React.ReactNode[] = []
    let lastTier = 0
    visibleArticles.forEach((a) => {
      if (!serverSearchActive && !clientFilterActive && sortBy === 'relevance' && a.relevance_tier !== lastTier) {
        if (a.relevance_tier === 2) nodes.push(<TierSeparator key="sep-t2" numeral="II" name="Notable" />)
        else if (a.relevance_tier === 3) nodes.push(<TierSeparator key="sep-t3" numeral="III" name="Background" />)
        lastTier = a.relevance_tier
      }
      nodes.push(<Clipping key={a.article_id} article={a} onClick={() => handleOpenArticle(a)} />)
    })
    return nodes
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--rig-paper)', position: 'relative', zIndex: 0 }}>
      <Navigation />

      <main style={{ paddingTop: 'var(--topbar-h)', position: 'relative', zIndex: 2 }}>
        <Dateline
          issueNumber="Coverage"
          sources={totals.total > 0 ? totals.total : undefined}
        />

        {/* ── Section head ────────────────────────────────── */}
        <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '40px 40px 28px' }}>
          <div className="rig-kicker rig-kicker-gold" style={{ marginBottom: '18px' }}>
            <span style={{ width: '28px', height: '1px', background: 'var(--rig-gold)', opacity: 0.7 }} />
            The Coverage Room
          </div>
          <h1 className="rig-headline" style={{ fontSize: 'clamp(38px, 4.6vw, 56px)', marginBottom: '20px' }}>
            Who is saying what, and <em>who is silent.</em>
          </h1>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '32px', flexWrap: 'wrap' }}>
            <StatBadge value={totals.total.toLocaleString()} label="Articles in view" />
            <StatBadge value={String(totals.tier1)} label="Tier I" tone="gold" />
            <StatBadge value={String(totals.tier2)} label="Tier II" tone="copper" />
            <StatBadge value={String(totals.tier3)} label="Tier III" />
          </div>
        </div>

        <FilterBar
          selectedTopics={selectedTopics}
          onToggleTopic={handleToggleTopic}
          selectedTier={selectedTier}
          onTierChange={setSelectedTier}
          selectedDays={selectedDays}
          onDaysChange={setSelectedDays}
          sortBy={sortBy}
          onSortChange={setSortBy}
          onClearFilters={clearFilters}
        />

        {/* ── Search strip ────────────────────────────────── */}
        <div style={{
          maxWidth: '1280px',
          margin: '0 auto',
          padding: '20px 40px 4px',
          display: 'flex',
          alignItems: 'center',
          gap: '16px',
          flexWrap: 'wrap',
        }}>
          <div style={{ flex: 1, minWidth: '260px', position: 'relative' }}>
            <span style={{
              position: 'absolute',
              left: 0,
              top: '50%',
              transform: 'translateY(-50%)',
              color: 'var(--rig-ink-4)',
              fontFamily: 'var(--font-serif)',
              fontSize: '18px',
              pointerEvents: 'none',
            }}>⌕</span>
            <input
              value={searchQuery}
              onChange={(e) => { setSearchQuery(e.target.value); if (searchResults) setSearchResults(null) }}
              onKeyDown={(e) => { if (e.key === 'Enter') void handleSearchEnter() }}
              placeholder="Search the room… press enter for full search"
              className="rig-input"
              style={{ paddingLeft: '28px', paddingRight: searchQuery ? '28px' : '0' }}
            />
            {searchQuery && (
              <button
                onClick={clearSearch}
                aria-label="Clear search"
                style={{
                  position: 'absolute',
                  right: 0,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  color: 'var(--rig-ink-4)',
                  fontSize: '18px',
                  fontFamily: 'var(--font-serif)',
                  cursor: 'pointer',
                  lineHeight: 1,
                }}
              >×</button>
            )}
          </div>

          {isSearching && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{
                width: '14px', height: '14px', borderRadius: '50%',
                border: '1.5px solid var(--rig-rule)',
                borderTopColor: 'var(--rig-gold)',
                animation: 'spin 0.8s linear infinite',
              }} />
              <span className="rig-byline">Searching</span>
            </div>
          )}

          {serverSearchActive && (
            <span className="rig-byline">
              {(searchResults as Article[]).length} results — &ldquo;{searchQuery}&rdquo;
            </span>
          )}
          {clientFilterActive && (
            <span className="rig-byline">
              {visibleArticles.length} of {articles.length} · enter to search all
            </span>
          )}
        </div>

        {/* ── Grid ────────────────────────────────────────── */}
        <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '28px 40px 120px' }}>
          {loading && (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
              gap: '20px',
            }}>
              {Array.from({ length: 9 }).map((_, i) => <SkeletonClipping key={i} />)}
            </div>
          )}

          {errorMsg && !loading && (
            <div
              style={{
                padding: '24px',
                border: '1px solid color-mix(in srgb, var(--rig-oxblood) 50%, transparent)',
                background: 'var(--rig-overlay)',
              }}
            >
              <div className="rig-kicker" style={{ color: 'var(--rig-oxblood)', marginBottom: '8px' }}>Desk Memo · Error</div>
              <p className="rig-serif-body" style={{ fontStyle: 'italic', color: 'var(--rig-oxblood)' }}>
                {errorMsg}
              </p>
            </div>
          )}

          {!loading && !errorMsg && visibleArticles.length === 0 && (
            <div style={{ textAlign: 'left', padding: '80px 0', maxWidth: '620px' }}>
              <div className="rig-kicker" style={{ marginBottom: '18px' }}>Desk Memo</div>
              <h3 className="rig-headline" style={{ fontSize: '30px', marginBottom: '12px' }}>
                No clippings match <em>the filters you set.</em>
              </h3>
              <p className="rig-lede">
                Try loosening the tier, widening the window, or clearing topic filters.
              </p>
            </div>
          )}

          {!loading && visibleArticles.length > 0 && (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
              gap: '20px',
            }}>
              {renderGrid()}
            </div>
          )}

          {!loading && !serverSearchActive && !clientFilterActive && hasMore && (
            <div style={{ textAlign: 'center', marginTop: '48px' }}>
              <button
                onClick={() => { if (!loadingMore && nextCursor) void fetchFeed(nextCursor, true) }}
                disabled={loadingMore}
                className="rig-btn-ghost"
              >
                {loadingMore ? (
                  <>
                    <div style={{
                      width: '12px', height: '12px', borderRadius: '50%',
                      border: '1.5px solid var(--rig-rule)',
                      borderTopColor: 'var(--rig-gold)',
                      animation: 'spin 0.8s linear infinite',
                    }} />
                    Loading
                  </>
                ) : 'File more clippings'}
              </button>
            </div>
          )}

          {serverSearchActive && (
            <div style={{ marginTop: '40px', textAlign: 'center' }}>
              <span className="rig-byline">
                Want deeper analysis?{' '}
                <button
                  onClick={() => router.push('/analyst')}
                  className="rig-link"
                  style={{
                    background: 'none',
                    padding: 0,
                    fontFamily: 'inherit',
                    fontSize: 'inherit',
                    letterSpacing: 'inherit',
                    cursor: 'pointer',
                  }}
                >
                  Ask the Analyst →
                </button>
              </span>
            </div>
          )}
        </div>
      </main>

      {selectedArticle && (
        <ArticleDialog
          article={selectedArticle}
          summary={summariesById[selectedArticle.article_id] ?? null}
          summaryLoading={summaryLoading}
          summaryError={summaryError}
          onClose={handleCloseDialog}
          onGenerateSummary={handleGenerateSummary}
        />
      )}
    </div>
  )
}
