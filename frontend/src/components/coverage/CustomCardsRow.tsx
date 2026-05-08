/**
 * CustomCardsRow — horizontally-scrolling row of user tracker cards.
 *
 * Each card shows the 4-section LLM-generated summary:
 *   - State (1 line)
 *   - What's New (bullets)
 *   - Why This Matters To You (chain-of-thought paragraph)
 *   - Watch For (bullets)
 *
 * Plus a "+ Track" affordance that opens the create modal.
 *
 * All text. No graphs.
 */

'use client'

import { useCallback, useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface CardSummary {
  sections: {
    state: string
    whats_new: string[]
    why_matters: string
    watch_for: string[]
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
  refreshTick?: number  // bump to force reload after create
}

const formatTimeAgo = (iso: string | null): string => {
  if (!iso) return 'never'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return 'never'
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

export function CustomCardsRow({ onOpenCreate, refreshTick = 0 }: Props) {
  const [cards, setCards] = useState<UserCard[]>([])
  const [loading, setLoading] = useState(true)

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
      setCards(json.cards || [])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load, refreshTick])

  const onDelete = useCallback(async (id: string) => {
    const supabase = createClient()
    const { data: { session } } = await supabase.auth.getSession()
    const token = session?.access_token
    if (!token) return
    await fetch(`${API_BASE}/api/coverage/cards/${id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    })
    void load()
  }, [load])

  return (
    <section style={{ padding: '40px 0 16px' }}>
      <header
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          marginBottom: '24px',
        }}
      >
        <div
          className="onyx-mono"
          style={{
            fontSize: '10px',
            letterSpacing: '0.42em',
            textTransform: 'uppercase',
            color: 'var(--onyx-dim)',
          }}
        >
          Your cards ({cards.length})
        </div>
        <button
          type="button"
          onClick={onOpenCreate}
          className="onyx-mono"
          style={{
            background: 'transparent',
            border: '1px dashed var(--onyx-rule-dim)',
            color: 'var(--onyx-bone-2)',
            fontSize: '10px',
            letterSpacing: '0.32em',
            textTransform: 'uppercase',
            padding: '8px 18px',
            cursor: 'pointer',
            transition: 'border-color 0.3s, color 0.3s',
          }}
          onMouseEnter={(e) => {
            (e.currentTarget.style.borderColor = 'var(--onyx-cyan)')
            ;(e.currentTarget.style.color = 'var(--onyx-bone)')
          }}
          onMouseLeave={(e) => {
            (e.currentTarget.style.borderColor = 'var(--onyx-rule-dim)')
            ;(e.currentTarget.style.color = 'var(--onyx-bone-2)')
          }}
        >
          + Track
        </button>
      </header>

      {loading && (
        <div
          className="onyx-mono"
          style={{
            fontSize: '11px',
            letterSpacing: '0.32em',
            color: 'var(--onyx-dim)',
            padding: '24px 0',
          }}
        >
          Loading…
        </div>
      )}

      {!loading && cards.length === 0 && (
        <div
          className="onyx-italic"
          style={{
            fontStyle: 'italic',
            fontSize: '15px',
            color: 'var(--onyx-bone-2)',
            padding: '8px 0 24px',
            maxWidth: '60ch',
          }}
        >
          No tracker cards yet. Create one to get a daily LLM-written
          summary about a person, topic, or theme you want to follow.
        </div>
      )}

      {!loading && cards.length > 0 && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
            gap: '20px',
          }}
        >
          {cards.map((card) => (
            <CardTile key={card.id} card={card} onDelete={() => onDelete(card.id)} />
          ))}
        </div>
      )}
    </section>
  )
}


function CardTile({ card, onDelete }: { card: UserCard; onDelete: () => void }) {
  const s = card.summary?.sections
  const isReady = !!s
  return (
    <article
      style={{
        position: 'relative',
        padding: '20px 22px 18px',
        border: '1px solid var(--onyx-red-hair)',
        background: 'var(--onyx-panel)',
        display: 'flex',
        flexDirection: 'column',
        gap: '14px',
        minHeight: '320px',
        animation: 'onyx-fade-up 0.4s ease both',
      }}
    >
      <header
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
        }}
      >
        <h3
          style={{
            fontFamily: 'var(--onyx-display)',
            fontWeight: 500,
            fontSize: '18px',
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: 'var(--onyx-bone)',
            margin: 0,
          }}
        >
          {card.label}
        </h3>
        <button
          type="button"
          onClick={onDelete}
          className="onyx-mono"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--onyx-dim)',
            fontSize: '9px',
            letterSpacing: '0.24em',
            textTransform: 'uppercase',
            cursor: 'pointer',
            padding: 0,
            transition: 'color 0.3s',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--onyx-red)')}
          onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--onyx-dim)')}
          aria-label="Remove card"
        >
          ×
        </button>
      </header>

      {!isReady && (
        <div
          className="onyx-italic"
          style={{
            fontStyle: 'italic',
            fontSize: '14px',
            color: 'var(--onyx-dim)',
          }}
        >
          Refreshing… first summary lands within a few minutes.
        </div>
      )}

      {isReady && s && (
        <>
          <div>
            <Label>State</Label>
            <Italic>{s.state || '—'}</Italic>
          </div>

          {s.whats_new && s.whats_new.length > 0 && (
            <div>
              <Label>What's new</Label>
              <Bullets items={s.whats_new} />
            </div>
          )}

          {s.why_matters && (
            <div>
              <Label>Why this matters to you</Label>
              <Italic small={false}>{s.why_matters}</Italic>
            </div>
          )}

          {s.watch_for && s.watch_for.length > 0 && (
            <div>
              <Label>Watch for</Label>
              <Bullets items={s.watch_for} />
            </div>
          )}
        </>
      )}

      <footer
        className="onyx-mono"
        style={{
          marginTop: 'auto',
          paddingTop: '12px',
          borderTop: '1px solid var(--onyx-rule-dim)',
          fontSize: '9px',
          letterSpacing: '0.24em',
          textTransform: 'uppercase',
          color: 'var(--onyx-dim)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <span>Updated {formatTimeAgo(card.last_refreshed_at)}</span>
        <span>{card.summary?.sample_size ?? 0} articles</span>
      </footer>
    </article>
  )
}

const Label = ({ children }: { children: React.ReactNode }) => (
  <div
    className="onyx-mono"
    style={{
      fontSize: '9px',
      letterSpacing: '0.32em',
      textTransform: 'uppercase',
      color: 'var(--onyx-dim)',
      marginBottom: '4px',
    }}
  >
    {children}
  </div>
)

const Italic = ({ children, small = true }: { children: React.ReactNode; small?: boolean }) => (
  <p
    style={{
      fontFamily: 'var(--onyx-italic)',
      fontStyle: 'italic',
      fontSize: small ? '14px' : '14px',
      lineHeight: 1.55,
      color: 'var(--onyx-bone-2)',
      margin: 0,
    }}
  >
    {children}
  </p>
)

const Bullets = ({ items }: { items: string[] }) => (
  <ul
    style={{
      listStyle: 'none',
      padding: 0,
      margin: 0,
      display: 'flex',
      flexDirection: 'column',
      gap: '4px',
    }}
  >
    {items.map((item, i) => (
      <li
        key={i}
        style={{
          fontFamily: 'var(--onyx-italic)',
          fontStyle: 'normal',
          fontSize: '13.5px',
          lineHeight: 1.5,
          color: 'var(--onyx-bone-2)',
          paddingLeft: '14px',
          position: 'relative',
        }}
      >
        <span
          style={{
            position: 'absolute',
            left: 0,
            color: 'var(--onyx-red)',
            opacity: 0.7,
          }}
        >
          ·
        </span>
        {item}
      </li>
    ))}
  </ul>
)
