/**
 * CardDetailView — centre-screen mini-page revealing the spawned
 * sub-cards behind a custom tracker card.
 *
 * Composition:
 *   • Header strip (60px): parent label + close chip + last-refreshed
 *   • Body grid (auto-fit, 360×280): 3-5 sub-card panels — each shows
 *     angle, reasoning paragraph, status chips, 1-3 source-article rows.
 *
 * Animation: FLIP from the source tile's bounding rect into the centre
 * mini-page (~75vw × 85vh). Page behind dims to 40%. Reverse FLIP on
 * close.
 *
 * No charts in v1 — typography, side-rule treatments, and chip language
 * carry the differentiation.
 */

'use client'

import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface SourceArticle {
  article_id: string
  title: string
  lead: string
  source_name: string
  source_domain: string
  thumbnail_url: string | null
  published_at: string | null
  geo_primary: string | null
  language_detected: string | null
}

interface CardSummarySections {
  state?: string
  whats_new?: string[]
  why_matters?: string
  watch_for?: string[]
}

interface CardSlice {
  id: string
  label: string
  sub_card_angle: string | null
  user_intent: string | null
  last_refreshed_at: string | null
  summary: {
    sections: CardSummarySections | null
    generated_at: string | null
    sample_size: number
  } | null
  articles: SourceArticle[]
}

interface FullPayload {
  parent: CardSlice
  sub_cards: CardSlice[]
  sub_cards_spawned: boolean
}

interface Props {
  cardId: string
  onClose: () => void
  onArticleClick: (articleId: string) => void
}

const formatTimeAgo = (iso: string | null): string => {
  if (!iso) return 'never'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return 'never'
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

export function CardDetailView({ cardId, onClose, onArticleClick }: Props) {
  const [data, setData] = useState<FullPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // FLIP entry: capture source tile rect, animate FROM tile bounding box
  // to the modal's natural (flex-centered) position. Because the outer
  // wrapper centers the modal via flex, the modal's natural transform
  // is identity — we animate from the tile's offset back to identity.
  useLayoutEffect(() => {
    if (!containerRef.current) return
    const sourceTile = document.querySelector<HTMLElement>(
      `[data-card-id="${cardId}"]`
    )
    if (!sourceTile) return
    const sourceRect = sourceTile.getBoundingClientRect()
    const targetRect = containerRef.current.getBoundingClientRect()
    const dx = sourceRect.left - targetRect.left
    const dy = sourceRect.top - targetRect.top
    const sx = sourceRect.width / targetRect.width
    const sy = sourceRect.height / targetRect.height

    const el = containerRef.current
    el.style.transformOrigin = 'top left'
    el.style.transform = `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`
    el.style.opacity = '0.4'
    el.getBoundingClientRect() // force layout flush
    el.style.transition =
      'transform 0.42s cubic-bezier(0.2, 0.7, 0.3, 1), opacity 0.42s'
    el.style.transform = ''  // identity — flex centers structurally
    el.style.opacity = '1'
  }, [cardId])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const supabase = createClient()
        const { data: { session } } = await supabase.auth.getSession()
        const token = session?.access_token
        if (!token) {
          setError('Not authenticated.')
          return
        }
        const res = await fetch(
          `${API_BASE}/api/coverage/cards/${cardId}/full`,
          {
            headers: { Authorization: `Bearer ${token}` },
            cache: 'no-store',
          },
        )
        if (!res.ok) {
          setError(`Failed to load: HTTP ${res.status}`)
          return
        }
        const json = await res.json() as FullPayload
        if (cancelled) return
        setData(json)
      } catch (e) {
        if (!cancelled) setError('Unexpected error loading card.')
      }
    }
    void load()
    return () => { cancelled = true }
  }, [cardId])

  // Re-poll while sub-cards are still being spawned/refreshed.
  useEffect(() => {
    if (!data) return
    const noSubsYet = !data.sub_cards_spawned || data.sub_cards.length === 0
    const someEmpty = data.sub_cards.some((sc) => !sc.summary)
    if (!noSubsYet && !someEmpty) return
    const id = setInterval(async () => {
      try {
        const supabase = createClient()
        const { data: { session } } = await supabase.auth.getSession()
        const token = session?.access_token
        if (!token) return
        const res = await fetch(
          `${API_BASE}/api/coverage/cards/${cardId}/full`,
          { headers: { Authorization: `Bearer ${token}` }, cache: 'no-store' },
        )
        if (!res.ok) return
        const json = await res.json() as FullPayload
        setData(json)
      } catch {
        /* silent */
      }
    }, 8000)
    return () => clearInterval(id)
  }, [data, cardId])

  return (
    <>
      {/* Dimmed backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          background:
            'radial-gradient(circle at 50% 50%, rgba(255, 45, 45, 0.04) 0%, rgba(0, 0, 0, 0.78) 70%)',
          backdropFilter: 'blur(6px)',
          WebkitBackdropFilter: 'blur(6px)',
          zIndex: 940,
          animation: 'onyx-fade-in 0.32s ease both',
          cursor: 'pointer',
        }}
      />

      {/* Centring wrapper — flex puts the modal at viewport centre.
          The inner panel uses transform only for the FLIP entry/exit. */}
      <div
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 950,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          pointerEvents: 'none', // backdrop catches clicks; modal opts back in
          padding: '32px',
        }}
      >
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        style={{
          width: 'min(1200px, 92vw)',
          height: 'min(85vh, 880px)',
          background:
            'linear-gradient(180deg, rgba(10, 10, 12, 0.96) 0%, rgba(0, 0, 0, 0.98) 100%)',
          border: '1px solid rgba(255, 45, 45, 0.30)',
          boxShadow: '0 40px 120px rgba(0, 0, 0, 0.7), 0 0 0 1px rgba(255, 45, 45, 0.10) inset',
          borderRadius: '6px',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          pointerEvents: 'auto',
          position: 'relative',
        }}
      >
        {/* Top edge — pulsing red beam */}
        <span
          aria-hidden
          style={{
            position: 'absolute',
            top: 0, left: 0, right: 0,
            height: '2px',
            background: 'linear-gradient(90deg, transparent, var(--onyx-red), transparent)',
            animation: 'onyx-pulse-cyan 3s ease-in-out infinite',
            pointerEvents: 'none',
          }}
        />

        {/* Header strip */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '20px 28px',
            borderBottom: '1px solid rgba(255, 45, 45, 0.20)',
            flex: '0 0 auto',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px', minWidth: 0 }}>
            <span
              aria-hidden
              style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: 'var(--onyx-red)',
                boxShadow: '0 0 10px var(--onyx-red)',
                animation: 'onyx-pulse-cyan 1.6s ease-in-out infinite',
                flexShrink: 0,
              }}
            />
            <span
              className="onyx-mono"
              style={{
                fontSize: '9px',
                letterSpacing: '0.42em',
                textTransform: 'uppercase',
                color: 'var(--onyx-dim)',
              }}
            >
              Tracker / Detail
            </span>
            <span
              style={{
                fontFamily: 'var(--onyx-display)',
                fontSize: '20px',
                fontWeight: 500,
                letterSpacing: '-0.005em',
                color: 'var(--onyx-bone)',
                textTransform: 'uppercase',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {data?.parent.label || 'Loading…'}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexShrink: 0 }}>
            {data?.parent.last_refreshed_at && (
              <span
                className="onyx-mono"
                style={{
                  fontSize: '9px',
                  letterSpacing: '0.32em',
                  textTransform: 'uppercase',
                  color: 'var(--onyx-dim)',
                }}
              >
                Refreshed {formatTimeAgo(data.parent.last_refreshed_at)}
              </span>
            )}
            <button
              type="button"
              onClick={onClose}
              className="onyx-mono"
              style={{
                fontSize: '9px',
                letterSpacing: '0.32em',
                textTransform: 'uppercase',
                color: 'var(--onyx-bone-2)',
                background: 'transparent',
                border: '1px solid rgba(255, 45, 45, 0.30)',
                padding: '6px 12px',
                cursor: 'pointer',
                outline: 'none',
              }}
            >
              × Close
            </button>
          </div>
        </div>

        {/* Body */}
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '32px 36px',
          }}
        >
          {error && (
            <div
              className="onyx-mono"
              style={{ color: 'var(--onyx-dim)', textAlign: 'center', padding: '40px' }}
            >
              {error}
            </div>
          )}

          {!data && !error && (
            <div
              className="onyx-mono"
              style={{
                fontSize: '11px',
                letterSpacing: '0.32em',
                textTransform: 'uppercase',
                color: 'var(--onyx-dim)',
                textAlign: 'center',
                padding: '40px',
              }}
            >
              Loading…
            </div>
          )}

          {data && (
            <>
              {/* Parent state line — single sentence overview */}
              {data.parent.summary?.sections?.state && (
                <p
                  style={{
                    margin: '0 0 24px',
                    fontFamily: 'var(--onyx-italic)',
                    fontStyle: 'italic',
                    fontSize: '17px',
                    lineHeight: 1.55,
                    color: 'var(--onyx-bone-2)',
                    maxWidth: '70ch',
                  }}
                >
                  {data.parent.summary.sections.state}
                </p>
              )}

              {/* Sub-card grid */}
              {!data.sub_cards_spawned && (
                <div
                  className="onyx-mono"
                  style={{
                    fontSize: '10px',
                    letterSpacing: '0.32em',
                    textTransform: 'uppercase',
                    color: 'var(--onyx-dim)',
                    padding: '40px 0',
                    textAlign: 'center',
                  }}
                >
                  Spawning intelligence sub-cards… (~30 seconds)
                </div>
              )}

              {data.sub_cards.length > 0 && (
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
                    gap: '20px',
                  }}
                >
                  {data.sub_cards.map((sc, i) => (
                    <SubCardPanel
                      key={sc.id}
                      slice={sc}
                      onArticleClick={onArticleClick}
                      stagger={i}
                    />
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
      </div>
    </>
  )
}


function SubCardPanel({
  slice,
  onArticleClick,
  stagger,
}: {
  slice: CardSlice
  onArticleClick: (id: string) => void
  stagger: number
}) {
  const [hovered, setHovered] = useState(false)

  const sections = slice.summary?.sections
  const reasoning = sections?.why_matters || ''
  const whatsNew = sections?.whats_new || []
  const watchFor = sections?.watch_for || []
  const articleCount = slice.articles.length

  return (
    <article
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position: 'relative',
        padding: '20px 22px',
        background:
          'linear-gradient(180deg, rgba(15, 15, 17, 0.7) 0%, rgba(8, 8, 10, 0.7) 100%)',
        border: hovered
          ? '1px solid rgba(255, 45, 45, 0.45)'
          : '1px solid rgba(255, 255, 255, 0.06)',
        transition: 'border-color 0.32s, transform 0.32s cubic-bezier(0.2, 0.7, 0.3, 1)',
        transform: hovered ? 'translateY(-2px)' : 'translateY(0)',
        animation: `onyx-fade-up 0.5s cubic-bezier(0.2, 0.7, 0.3, 1) ${stagger * 60}ms both`,
      }}
    >
      {/* Side rule */}
      <span
        aria-hidden
        style={{
          position: 'absolute',
          left: 0,
          top: '20px',
          bottom: '20px',
          width: '2px',
          background: 'var(--onyx-red)',
          opacity: hovered ? 0.85 : 0.6,
          transition: 'opacity 0.32s',
        }}
      />

      {/* Angle label */}
      <h5
        style={{
          margin: '0 0 6px',
          paddingLeft: '12px',
          fontFamily: 'var(--onyx-display)',
          fontSize: '15px',
          fontWeight: 500,
          letterSpacing: '-0.005em',
          color: 'var(--onyx-bone)',
          textTransform: 'uppercase',
        }}
      >
        {slice.sub_card_angle || slice.label}
      </h5>

      {/* Status chips */}
      <div
        style={{
          display: 'flex',
          gap: '8px',
          paddingLeft: '12px',
          marginBottom: '14px',
        }}
      >
        <span
          className="onyx-mono"
          style={{
            fontSize: '8px',
            letterSpacing: '0.32em',
            textTransform: 'uppercase',
            color: 'var(--onyx-dim)',
          }}
        >
          {(slice.summary?.sample_size ?? articleCount)}
          {' '}
          {(slice.summary?.sample_size ?? articleCount) === 1 ? 'article' : 'articles'}
        </span>
        <span style={{ color: 'var(--onyx-dim)', opacity: 0.4 }}>·</span>
        <span
          className="onyx-mono"
          style={{
            fontSize: '8px',
            letterSpacing: '0.32em',
            textTransform: 'uppercase',
            color: 'var(--onyx-dim)',
          }}
        >
          {slice.last_refreshed_at
            ? `Refreshed ${formatTimeAgo(slice.last_refreshed_at)}`
            : 'Awaiting first refresh'}
        </span>
      </div>

      {/* Reasoning paragraph */}
      {reasoning ? (
        <p
          style={{
            margin: '0 0 14px',
            paddingLeft: '12px',
            fontFamily: 'var(--onyx-italic)',
            fontStyle: 'italic',
            fontSize: '13.5px',
            lineHeight: 1.6,
            color: 'var(--onyx-bone-2)',
            opacity: 0.9,
            display: '-webkit-box',
            WebkitLineClamp: 5,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {reasoning}
        </p>
      ) : (
        <p
          className="onyx-mono"
          style={{
            margin: '0 0 14px',
            paddingLeft: '12px',
            fontSize: '10px',
            letterSpacing: '0.32em',
            textTransform: 'uppercase',
            color: 'var(--onyx-dim)',
          }}
        >
          {slice.summary === null ? 'Awaiting refresh…' : 'No reasoning yet.'}
        </p>
      )}

      {/* What's new — bullet timeline (3 max) */}
      {whatsNew.length > 0 && (
        <ul
          style={{
            margin: '0 0 14px',
            paddingLeft: '12px',
            listStyle: 'none',
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
          }}
        >
          {whatsNew.slice(0, 3).map((item, i) => (
            <li
              key={i}
              style={{
                position: 'relative',
                paddingLeft: '14px',
                fontSize: '12px',
                lineHeight: 1.55,
                color: 'var(--onyx-bone-2)',
                opacity: 0.85,
              }}
            >
              <span
                aria-hidden
                style={{
                  position: 'absolute',
                  left: 0,
                  top: '8px',
                  width: '5px',
                  height: '5px',
                  background: 'var(--onyx-red)',
                  borderRadius: '50%',
                }}
              />
              {item}
            </li>
          ))}
        </ul>
      )}

      {/* Watch-for chips */}
      {watchFor.length > 0 && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '6px',
            paddingLeft: '12px',
            marginBottom: '14px',
          }}
        >
          {watchFor.slice(0, 3).map((w, i) => (
            <span
              key={i}
              className="onyx-mono"
              style={{
                fontSize: '8.5px',
                letterSpacing: '0.24em',
                textTransform: 'uppercase',
                color: 'var(--onyx-bone-2)',
                background: 'rgba(255, 45, 45, 0.06)',
                border: '1px solid rgba(255, 45, 45, 0.20)',
                padding: '4px 8px',
              }}
            >
              ▢ {w}
            </span>
          ))}
        </div>
      )}

      {/* Source articles — top 3 compact rows */}
      {slice.articles.length > 0 && (
        <div
          style={{
            paddingLeft: '12px',
            paddingTop: '12px',
            borderTop: '1px solid rgba(255, 255, 255, 0.06)',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
          }}
        >
          {slice.articles.slice(0, 3).map((a) => (
            <button
              key={a.article_id}
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                onArticleClick(a.article_id)
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                background: 'transparent',
                border: 'none',
                color: 'inherit',
                font: 'inherit',
                cursor: 'pointer',
                outline: 'none',
                padding: 0,
                textAlign: 'left',
              }}
            >
              <span
                style={{
                  flexShrink: 0,
                  width: '4px',
                  height: '24px',
                  background: 'var(--onyx-red)',
                  opacity: 0.5,
                }}
              />
              <span
                style={{
                  fontSize: '11px',
                  lineHeight: 1.4,
                  color: 'var(--onyx-bone-2)',
                  display: '-webkit-box',
                  WebkitLineClamp: 1,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                  flex: 1,
                  minWidth: 0,
                }}
              >
                {a.title}
              </span>
              <span
                className="onyx-mono"
                style={{
                  fontSize: '8px',
                  letterSpacing: '0.24em',
                  textTransform: 'uppercase',
                  color: 'var(--onyx-dim)',
                  flexShrink: 0,
                }}
              >
                {(a.source_name || '').slice(0, 16)}
              </span>
            </button>
          ))}
        </div>
      )}
    </article>
  )
}
