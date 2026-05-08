/**
 * ContradictionsDrawer — slide-in right panel listing active
 * contradictions in plain prose. No tables, no graphs — each
 * row is a stacked text block.
 */

'use client'

import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface ContradictionSide {
  article_id: string
  title: string
  claim: string
  source_name: string
}

interface Contradiction {
  id: string
  summary: string
  confidence: number
  entity_name: string | null
  detected_at: string | null
  side_a: ContradictionSide
  side_b: ContradictionSide
}

interface Props {
  open: boolean
  onClose: () => void
  onArticleClick: (id: string) => void
}

export function ContradictionsDrawer({ open, onClose, onArticleClick }: Props) {
  const [items, setItems] = useState<Contradiction[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    void (async () => {
      try {
        const supabase = createClient()
        const { data: { session } } = await supabase.auth.getSession()
        const token = session?.access_token
        if (!token) return
        const res = await fetch(`${API_BASE}/api/coverage/contradictions?limit=50`, {
          headers: { Authorization: `Bearer ${token}` },
          cache: 'no-store',
        })
        if (!res.ok) return
        const json = await res.json() as { contradictions: Contradiction[] }
        if (!cancelled) setItems(json.contradictions || [])
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0, 0, 0, 0.6)',
        backdropFilter: 'blur(4px)',
        zIndex: 900,
        display: 'flex',
        justifyContent: 'flex-end',
        animation: 'onyx-fade-up 0.3s ease both',
      }}
    >
      <aside
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 'min(560px, 100vw)',
          height: '100vh',
          background: 'var(--onyx-bg)',
          borderLeft: '1px solid var(--onyx-red-hair)',
          padding: '32px 40px',
          overflowY: 'auto',
        }}
      >
        <header style={{ marginBottom: '32px' }}>
          <button
            type="button"
            onClick={onClose}
            className="onyx-mono"
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--onyx-dim)',
              fontSize: '11px',
              letterSpacing: '0.32em',
              textTransform: 'uppercase',
              cursor: 'pointer',
              padding: 0,
              marginBottom: '12px',
            }}
          >
            ← Close
          </button>
          <h2
            style={{
              fontFamily: 'var(--onyx-display)',
              fontWeight: 500,
              fontSize: '24px',
              color: 'var(--onyx-bone)',
              margin: 0,
            }}
          >
            Contradictions
          </h2>
        </header>

        {loading && (
          <div
            className="onyx-mono"
            style={{ fontSize: '11px', color: 'var(--onyx-dim)', letterSpacing: '0.32em' }}
          >
            Loading…
          </div>
        )}

        {!loading && items.length === 0 && (
          <div
            className="onyx-italic"
            style={{
              fontStyle: 'italic',
              fontSize: '15px',
              color: 'var(--onyx-bone-2)',
            }}
          >
            No active contradictions today.
          </div>
        )}

        {items.map((c) => (
          <article
            key={c.id}
            style={{
              padding: '24px 0',
              borderBottom: '1px solid var(--onyx-rule-dim)',
            }}
          >
            {c.entity_name && (
              <div
                className="onyx-mono"
                style={{
                  fontSize: '10px',
                  letterSpacing: '0.42em',
                  textTransform: 'uppercase',
                  color: 'var(--onyx-red)',
                  marginBottom: '12px',
                }}
              >
                {c.entity_name}
              </div>
            )}

            <Side label="Source A" side={c.side_a} onArticleClick={onArticleClick} />
            <Side label="Source B" side={c.side_b} onArticleClick={onArticleClick} />

            <div style={{ marginTop: '20px' }}>
              <div
                className="onyx-mono"
                style={{
                  fontSize: '9px',
                  letterSpacing: '0.32em',
                  textTransform: 'uppercase',
                  color: 'var(--onyx-dim)',
                  marginBottom: '8px',
                }}
              >
                Analysis
              </div>
              <p
                style={{
                  fontFamily: 'var(--onyx-italic)',
                  fontStyle: 'italic',
                  fontSize: '15px',
                  lineHeight: 1.6,
                  color: 'var(--onyx-bone)',
                  margin: 0,
                }}
              >
                {c.summary}
              </p>
            </div>
          </article>
        ))}
      </aside>
    </div>
  )
}

function Side({
  label,
  side,
  onArticleClick,
}: {
  label: string
  side: ContradictionSide
  onArticleClick: (id: string) => void
}) {
  return (
    <div style={{ marginBottom: '16px' }}>
      <div
        className="onyx-mono"
        style={{
          fontSize: '9px',
          letterSpacing: '0.32em',
          textTransform: 'uppercase',
          color: 'var(--onyx-dim)',
          marginBottom: '6px',
        }}
      >
        {label} · {side.source_name}
      </div>
      <button
        type="button"
        onClick={() => onArticleClick(side.article_id)}
        style={{
          background: 'transparent',
          border: 'none',
          color: 'var(--onyx-bone-2)',
          fontFamily: 'var(--onyx-italic)',
          fontStyle: 'italic',
          fontSize: '15px',
          lineHeight: 1.5,
          textAlign: 'left',
          padding: 0,
          cursor: 'pointer',
        }}
      >
        "{side.claim}"
      </button>
    </div>
  )
}
