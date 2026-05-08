/**
 * TopFiveStories — onyx horizontal card rail of today's top 5.
 *
 * Visual language: each story is its own self-contained card, sized
 * for fast scanning. The rail scrolls horizontally on smaller screens
 * and lays out as a 5-column flex row on wide screens.
 *
 * Card anatomy:
 *   - Thumbnail strip (16:9) with gradient fallback when image missing.
 *     Number chip (№01) overlaid in top-left corner.
 *   - Headline — display_title (English) preferred, original fallback.
 *   - "Why this matters" — 4-line clamp with ellipsis.
 *   - Footer — source · time-ago, plus an arrow Read affordance.
 *
 * Interaction: hover lifts the card, brightens the cyan border, fades
 * a subtle glow under it. Click anywhere on the card opens the reader.
 *
 * Server-rendered via /api/coverage/top-stories. Falls back gracefully
 * when the cache is empty (no rationale string).
 */

'use client'

import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface TopStory {
  article_id: string
  title: string
  display_title?: string | null
  lead: string
  source_name: string
  source_domain: string
  published_at: string | null
  why_matters: string | null
  thumbnail_url?: string | null
}

interface Props {
  onRead: (articleId: string) => void
  onAddToCard?: (articleId: string) => void
  onCompareToggle?: (articleId: string) => void
  selectedForCompare?: ReadonlySet<string>
}

const formatTimeAgo = (iso: string | null): string => {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

// Hash source-domain to a stable hue so each outlet's gradient placeholder
// is consistent across cards. No external dep.
const hueForDomain = (domain: string): number => {
  let h = 0
  for (let i = 0; i < domain.length; i++) {
    h = (h * 31 + domain.charCodeAt(i)) | 0
  }
  return ((h % 360) + 360) % 360
}

export function TopFiveStories({
  onRead,
  onAddToCard,
  onCompareToggle,
  selectedForCompare,
}: Props) {
  const [stories, setStories] = useState<TopStory[] | null>(null)
  const [hoveredId, setHoveredId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const supabase = createClient()
        const { data: { session } } = await supabase.auth.getSession()
        const token = session?.access_token
        if (!token) return
        const res = await fetch(`${API_BASE}/api/coverage/top-stories?days=1`, {
          headers: { Authorization: `Bearer ${token}` },
          cache: 'no-store',
        })
        if (!res.ok) return
        const json = await res.json()
        if (!cancelled) setStories(Array.isArray(json.stories) ? json.stories : [])
      } catch {
        if (!cancelled) setStories([])
      }
    }
    void load()
    return () => { cancelled = true }
  }, [])

  if (stories === null) {
    return (
      <div
        className="onyx-mono"
        style={{
          padding: '40px 0',
          fontSize: '11px',
          letterSpacing: '0.32em',
          textTransform: 'uppercase',
          color: 'var(--onyx-dim)',
        }}
      >
        Loading top stories…
      </div>
    )
  }

  if (stories.length === 0) {
    return null
  }

  return (
    <section
      style={{
        padding: '48px 0',
        borderTop: '1px solid var(--onyx-rule-hair)',
      }}
    >
      <header
        style={{
          marginBottom: '24px',
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          gap: '24px',
          flexWrap: 'wrap',
        }}
      >
        <div>
          <div
            className="onyx-mono"
            style={{
              fontSize: '10px',
              letterSpacing: '0.42em',
              textTransform: 'uppercase',
              color: 'var(--onyx-dim)',
            }}
          >
            Top 5 stories today
          </div>
        </div>
        <div
          className="onyx-mono"
          style={{
            fontSize: '9px',
            letterSpacing: '0.32em',
            textTransform: 'uppercase',
            color: 'var(--onyx-dim)',
            opacity: 0.6,
          }}
        >
          Curated · refreshed every 6h
        </div>
      </header>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
          gap: '20px',
          alignItems: 'stretch',
        }}
      >
        {stories.map((story, i) => {
          const isSelected = selectedForCompare?.has(story.article_id) ?? false
          const isHovered = hoveredId === story.article_id
          const hue = hueForDomain(story.source_domain || story.source_name)

          return (
            <article
              key={story.article_id}
              onMouseEnter={() => setHoveredId(story.article_id)}
              onMouseLeave={() => setHoveredId(null)}
              onClick={() => onRead(story.article_id)}
              style={{
                position: 'relative',
                display: 'flex',
                flexDirection: 'column',
                background:
                  'linear-gradient(180deg, rgba(15, 15, 17, 0.95) 0%, rgba(8, 8, 10, 0.95) 100%)',
                border: isHovered
                  ? '1px solid rgba(0, 194, 255, 0.45)'
                  : isSelected
                  ? '1px solid rgba(0, 194, 255, 0.8)'
                  : '1px solid rgba(255, 255, 255, 0.06)',
                borderRadius: '4px',
                cursor: 'pointer',
                overflow: 'hidden',
                transition:
                  'transform 0.32s cubic-bezier(0.2, 0.7, 0.3, 1), border-color 0.32s, box-shadow 0.32s',
                transform: isHovered ? 'translateY(-4px)' : 'translateY(0)',
                boxShadow: isHovered
                  ? '0 12px 40px rgba(0, 194, 255, 0.12), 0 0 0 1px rgba(0, 194, 255, 0.08) inset'
                  : isSelected
                  ? '0 0 0 1px rgba(0, 194, 255, 0.4) inset'
                  : 'none',
                animation: `onyx-fade-up 0.5s cubic-bezier(0.2, 0.7, 0.3, 1) ${
                  i * 80
                }ms both`,
              }}
            >
              {/* Thumbnail / gradient header */}
              <div
                style={{
                  position: 'relative',
                  width: '100%',
                  aspectRatio: '16 / 9',
                  background: story.thumbnail_url
                    ? `url("${story.thumbnail_url}") center/cover no-repeat`
                    : `linear-gradient(135deg, hsla(${hue}, 60%, 28%, 0.55) 0%, hsla(${
                        (hue + 60) % 360
                      }, 65%, 12%, 0.85) 100%)`,
                  borderBottom: '1px solid rgba(255, 255, 255, 0.04)',
                }}
              >
                {/* Subtle dither noise overlay (CSS-only, astrodither-inspired) */}
                <div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    backgroundImage:
                      'radial-gradient(rgba(255,255,255,0.04) 1px, transparent 1px)',
                    backgroundSize: '3px 3px',
                    pointerEvents: 'none',
                    opacity: 0.7,
                  }}
                />
                {/* Vignette so headline area stays legible */}
                <div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    background:
                      'linear-gradient(180deg, transparent 40%, rgba(0,0,0,0.7) 100%)',
                    pointerEvents: 'none',
                  }}
                />
                {/* Number chip — top-left */}
                <div
                  className="onyx-mono"
                  style={{
                    position: 'absolute',
                    top: '12px',
                    left: '12px',
                    padding: '4px 9px',
                    fontSize: '9px',
                    letterSpacing: '0.32em',
                    textTransform: 'uppercase',
                    color: isHovered ? 'var(--onyx-cyan)' : 'var(--onyx-bone-2)',
                    background: 'rgba(0, 0, 0, 0.55)',
                    border: '1px solid rgba(255, 255, 255, 0.12)',
                    backdropFilter: 'blur(6px)',
                    WebkitBackdropFilter: 'blur(6px)',
                    transition: 'color 0.32s',
                  }}
                >
                  №{String(i + 1).padStart(2, '0')}
                </div>
                {/* Source pill — top-right */}
                <div
                  className="onyx-mono"
                  style={{
                    position: 'absolute',
                    top: '12px',
                    right: '12px',
                    padding: '4px 9px',
                    fontSize: '8px',
                    letterSpacing: '0.28em',
                    textTransform: 'uppercase',
                    color: 'var(--onyx-bone-2)',
                    background: 'rgba(0, 0, 0, 0.55)',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                    backdropFilter: 'blur(6px)',
                    WebkitBackdropFilter: 'blur(6px)',
                    maxWidth: '60%',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {story.source_name}
                </div>
                {/* Hover glow band along the top edge */}
                <div
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    right: 0,
                    height: '2px',
                    background:
                      'linear-gradient(90deg, transparent 0%, var(--onyx-cyan) 50%, transparent 100%)',
                    opacity: isHovered ? 0.85 : 0,
                    transition: 'opacity 0.32s',
                  }}
                />
              </div>

              {/* Body */}
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px',
                  padding: '18px 18px 16px',
                  flex: 1,
                }}
              >
                <h3
                  style={{
                    fontFamily: 'var(--onyx-display)',
                    fontSize: '17px',
                    lineHeight: 1.28,
                    fontWeight: 500,
                    letterSpacing: '-0.005em',
                    color: 'var(--onyx-bone)',
                    margin: 0,
                    display: '-webkit-box',
                    WebkitLineClamp: 3,
                    WebkitBoxOrient: 'vertical',
                    overflow: 'hidden',
                  }}
                >
                  {story.display_title || story.title}
                </h3>

                {story.why_matters && (
                  <p
                    style={{
                      margin: 0,
                      fontFamily: 'var(--onyx-body)',
                      fontSize: '12.5px',
                      lineHeight: 1.55,
                      color: 'var(--onyx-bone-2)',
                      opacity: 0.78,
                      display: '-webkit-box',
                      WebkitLineClamp: 4,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                    }}
                  >
                    {story.why_matters}
                  </p>
                )}

                <div style={{ flex: 1 }} />

                <div
                  className="onyx-mono"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '8px',
                    paddingTop: '12px',
                    borderTop: '1px solid rgba(255, 255, 255, 0.04)',
                    fontSize: '9px',
                    letterSpacing: '0.28em',
                    textTransform: 'uppercase',
                    color: 'var(--onyx-dim)',
                  }}
                >
                  <span>{formatTimeAgo(story.published_at)}</span>
                  <span
                    style={{
                      color: isHovered ? 'var(--onyx-cyan)' : 'var(--onyx-dim)',
                      transition: 'color 0.32s',
                    }}
                  >
                    Read →
                  </span>
                </div>

                {/* Secondary actions row — only visible if any onCompareToggle/onAddToCard provided */}
                {(onCompareToggle || onAddToCard) && (
                  <div
                    style={{
                      display: 'flex',
                      gap: '6px',
                      marginTop: '4px',
                    }}
                  >
                    {onCompareToggle && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          onCompareToggle(story.article_id)
                        }}
                        className="onyx-mono"
                        style={chipButtonStyle(isSelected)}
                      >
                        {isSelected ? '✓ COMPARE' : 'COMPARE'}
                      </button>
                    )}
                    {onAddToCard && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          onAddToCard(story.article_id)
                        }}
                        className="onyx-mono"
                        style={chipButtonStyle()}
                      >
                        + CARD
                      </button>
                    )}
                  </div>
                )}
              </div>
            </article>
          )
        })}
      </div>
    </section>
  )
}

function chipButtonStyle(active: boolean = false): React.CSSProperties {
  return {
    flex: 1,
    background: active ? 'rgba(0, 194, 255, 0.08)' : 'transparent',
    border: active
      ? '1px solid rgba(0, 194, 255, 0.4)'
      : '1px solid rgba(255, 255, 255, 0.06)',
    color: active ? 'var(--onyx-cyan)' : 'var(--onyx-dim)',
    fontSize: '9px',
    letterSpacing: '0.28em',
    textTransform: 'uppercase',
    padding: '6px 8px',
    cursor: 'pointer',
    transition: 'color 0.3s, border-color 0.3s, background 0.3s',
    borderRadius: '2px',
  }
}
