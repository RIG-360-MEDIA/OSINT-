/**
 * CustomCardsRow — horizontally-scrolling row of compact tracker tiles.
 *
 * Each tile (240×280) is a glance summary: label + state-line + meta.
 * Click → opens CardDetailView mini-page (parent owns expandedCardId state).
 *
 * No 4-section content rendered inline — all of that is revealed in the
 * detail view alongside the spawned sub-cards.
 */

'use client'

import { useCallback, useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface CardSummary {
  sections: {
    state?: string
    whats_new?: string[]
    why_matters?: string
    watch_for?: string[]
  } | null
  citations: string[]
  generated_at: string | null
  sample_size: number
}

interface UserCard {
  id: string
  label: string
  definition_hash: string
  user_intent: string | null
  last_refreshed_at: string | null
  summary: CardSummary | null
}

interface Props {
  onOpenCreate: () => void
  onCardClick: (cardId: string) => void
  refreshTick?: number
}

const formatTimeAgo = (iso: string | null): string => {
  if (!iso) return 'NEVER'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return 'NEVER'
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (seconds < 60) return `${seconds}S AGO`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}M AGO`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}H AGO`
  return `${Math.floor(seconds / 86400)}D AGO`
}

export function CustomCardsRow({ onOpenCreate, onCardClick, refreshTick }: Props) {
  const [cards, setCards] = useState<UserCard[] | null>(null)
  const [hoveredId, setHoveredId] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const supabase = createClient()
      const { data: { session } } = await supabase.auth.getSession()
      const token = session?.access_token
      if (!token) return
      const res = await fetch(`${API_BASE}/api/coverage/cards`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: 'no-store',
      })
      if (!res.ok) return
      const json = await res.json() as { cards: UserCard[] }
      setCards(Array.isArray(json.cards) ? json.cards : [])
    } catch {
      setCards([])
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load, refreshTick])

  // Repeat-poll while any card is awaiting first refresh — surfaces the
  // "Refreshing…" state moving to populated without manual reload.
  useEffect(() => {
    if (!cards) return
    const anyPending = cards.some((c) => !c.summary)
    if (!anyPending) return
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [cards, load])

  if (cards === null) return null

  return (
    <section>
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          marginBottom: '20px',
        }}
      >
        <span
          className="onyx-mono"
          style={{
            fontSize: '10px',
            letterSpacing: '0.42em',
            textTransform: 'uppercase',
            color: 'var(--onyx-dim)',
          }}
        >
          Your trackers
        </span>
        <span
          className="onyx-mono"
          style={{
            fontSize: '9px',
            letterSpacing: '0.32em',
            textTransform: 'uppercase',
            color: 'var(--onyx-dim)',
            opacity: 0.6,
          }}
        >
          Click a tile to expand
        </span>
      </div>

      <div
        style={{
          display: 'flex',
          gap: '16px',
          overflowX: 'auto',
          paddingBottom: '4px',
          scrollSnapType: 'x mandatory',
        }}
      >
        {cards.map((card, i) => {
          const isHovered = hoveredId === card.id
          const state = card.summary?.sections?.state || (
            card.summary === null ? 'Refreshing…' : 'No summary yet'
          )
          const sources = card.summary?.sample_size || 0
          return (
            <button
              key={card.id}
              type="button"
              data-card-id={card.id}
              onMouseEnter={() => setHoveredId(card.id)}
              onMouseLeave={() => setHoveredId(null)}
              onClick={() => onCardClick(card.id)}
              style={{
                flex: '0 0 240px',
                minHeight: '280px',
                display: 'flex',
                flexDirection: 'column',
                position: 'relative',
                padding: '20px 18px 16px',
                background:
                  'linear-gradient(180deg, rgba(15, 15, 17, 0.95) 0%, rgba(8, 8, 10, 0.95) 100%)',
                border: isHovered
                  ? '1px solid rgba(255, 45, 45, 0.5)'
                  : '1px solid rgba(255, 255, 255, 0.06)',
                cursor: 'pointer',
                textAlign: 'left',
                color: 'inherit',
                font: 'inherit',
                outline: 'none',
                transition:
                  'transform 0.32s cubic-bezier(0.2, 0.7, 0.3, 1), border-color 0.32s, box-shadow 0.32s',
                transform: isHovered ? 'translateY(-3px)' : 'translateY(0)',
                boxShadow: isHovered
                  ? '0 12px 36px rgba(255, 45, 45, 0.10)'
                  : 'none',
                animation: `onyx-fade-up 0.5s cubic-bezier(0.2, 0.7, 0.3, 1) ${i * 50}ms both`,
                scrollSnapAlign: 'start',
              }}
            >
              {/* HUD-corner brackets — top-right + bottom-left */}
              <span
                aria-hidden
                style={{
                  position: 'absolute',
                  top: '8px', right: '8px',
                  width: '12px', height: '12px',
                  borderTop: `1px solid ${isHovered ? 'var(--onyx-red)' : 'rgba(255,255,255,0.18)'}`,
                  borderRight: `1px solid ${isHovered ? 'var(--onyx-red)' : 'rgba(255,255,255,0.18)'}`,
                  transition: 'border-color 0.32s',
                  pointerEvents: 'none',
                }}
              />
              <span
                aria-hidden
                style={{
                  position: 'absolute',
                  bottom: '8px', left: '8px',
                  width: '12px', height: '12px',
                  borderBottom: `1px solid ${isHovered ? 'var(--onyx-red)' : 'rgba(255,255,255,0.18)'}`,
                  borderLeft: `1px solid ${isHovered ? 'var(--onyx-red)' : 'rgba(255,255,255,0.18)'}`,
                  transition: 'border-color 0.32s',
                  pointerEvents: 'none',
                }}
              />

              {/* Live-tracking dot */}
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '8px',
                  marginBottom: '14px',
                }}
              >
                <span
                  aria-hidden
                  style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    background: 'var(--onyx-red)',
                    boxShadow: '0 0 8px var(--onyx-red)',
                    animation: 'onyx-pulse-cyan 1.6s ease-in-out infinite',
                  }}
                />
                <span
                  className="onyx-mono"
                  style={{
                    fontSize: '8px',
                    letterSpacing: '0.36em',
                    textTransform: 'uppercase',
                    color: 'var(--onyx-dim)',
                  }}
                >
                  Tracking
                </span>
              </span>

              {/* Label */}
              <h4
                style={{
                  margin: 0,
                  fontFamily: 'var(--onyx-display)',
                  fontSize: '18px',
                  fontWeight: 500,
                  lineHeight: 1.22,
                  letterSpacing: '-0.005em',
                  color: 'var(--onyx-bone)',
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                  marginBottom: '14px',
                }}
              >
                {card.label}
              </h4>

              {/* State line */}
              <p
                style={{
                  margin: 0,
                  fontFamily: 'var(--onyx-italic)',
                  fontStyle: 'italic',
                  fontSize: '13px',
                  lineHeight: 1.5,
                  color: 'var(--onyx-bone-2)',
                  opacity: 0.85,
                  display: '-webkit-box',
                  WebkitLineClamp: 4,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                  flex: 1,
                }}
              >
                {state}
              </p>

              {/* Footer */}
              <div
                style={{
                  marginTop: '14px',
                  paddingTop: '12px',
                  borderTop: '1px solid rgba(255, 45, 45, 0.20)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <span
                  className="onyx-mono"
                  style={{
                    fontSize: '8.5px',
                    letterSpacing: '0.32em',
                    textTransform: 'uppercase',
                    color: 'var(--onyx-dim)',
                  }}
                >
                  {formatTimeAgo(card.last_refreshed_at)}
                </span>
                <span
                  className="onyx-mono"
                  style={{
                    fontSize: '8.5px',
                    letterSpacing: '0.32em',
                    textTransform: 'uppercase',
                    color: isHovered ? 'var(--onyx-red)' : 'var(--onyx-dim)',
                    transition: 'color 0.32s',
                  }}
                >
                  {sources} · OPEN →
                </span>
              </div>
            </button>
          )
        })}

        {/* + Track tile — same shape as cards, dashed border */}
        <button
          type="button"
          onClick={onOpenCreate}
          onMouseEnter={() => setHoveredId('__track__')}
          onMouseLeave={() => setHoveredId(null)}
          style={{
            flex: '0 0 240px',
            minHeight: '280px',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '12px',
            background: 'transparent',
            border: hoveredId === '__track__'
              ? '1px dashed rgba(255, 45, 45, 0.7)'
              : '1px dashed rgba(255, 45, 45, 0.30)',
            cursor: 'pointer',
            color: 'inherit',
            font: 'inherit',
            outline: 'none',
            transition:
              'transform 0.32s cubic-bezier(0.2, 0.7, 0.3, 1), border-color 0.32s, background 0.32s',
            transform: hoveredId === '__track__' ? 'translateY(-3px)' : 'translateY(0)',
            background: hoveredId === '__track__' ? 'rgba(255, 45, 45, 0.04)' : 'transparent',
            scrollSnapAlign: 'start',
          }}
        >
          <span
            aria-hidden
            style={{
              fontFamily: 'var(--onyx-display)',
              fontSize: '36px',
              fontWeight: 300,
              color: 'var(--onyx-red)',
              lineHeight: 1,
            }}
          >
            +
          </span>
          <span
            className="onyx-mono"
            style={{
              fontSize: '10px',
              letterSpacing: '0.42em',
              textTransform: 'uppercase',
              color: 'var(--onyx-dim)',
            }}
          >
            Track
          </span>
        </button>
      </div>
    </section>
  )
}
