/**
 * TopFiveStories — onyx editorial stack of today's top 5.
 *
 * Each story renders:
 *   - serif headline (editorial)
 *   - italic chain-of-thought "why this matters" paragraph
 *   - mono row: source name · time ago · DISSENT chip if applicable
 *   - action triplet: Read · Compare · Add to card
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

export function TopFiveStories({ onRead, onAddToCard, onCompareToggle, selectedForCompare }: Props) {
  const [stories, setStories] = useState<TopStory[] | null>(null)

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
    <section style={{ padding: '48px 0', borderTop: '1px solid var(--onyx-rule-hair)' }}>
      <header style={{ marginBottom: '32px' }}>
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
        <hr className="onyx-hairline-dim" style={{ marginTop: '12px' }} />
      </header>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '40px' }}>
        {stories.map((story, i) => {
          const isSelected = selectedForCompare?.has(story.article_id) ?? false
          return (
            <article
              key={story.article_id}
              style={{
                display: 'grid',
                gridTemplateColumns: '40px 1fr',
                gap: '24px',
                padding: '24px 0',
                borderBottom: '1px solid var(--onyx-rule-dim)',
              }}
            >
              <div
                className="onyx-mono"
                style={{
                  fontSize: '14px',
                  color: 'var(--onyx-dim)',
                  letterSpacing: '0.18em',
                  paddingTop: '8px',
                }}
              >
                №{String(i + 1).padStart(2, '0')}
              </div>

              <div>
                <h3
                  style={{
                    fontFamily: 'var(--onyx-display)',
                    fontStyle: 'normal',
                    fontSize: '28px',
                    lineHeight: 1.2,
                    fontWeight: 500,
                    letterSpacing: '-0.012em',
                    color: 'var(--onyx-bone)',
                    margin: 0,
                    cursor: 'pointer',
                  }}
                  onClick={() => onRead(story.article_id)}
                >
                  {story.title}
                </h3>

                {story.why_matters && (
                  <p
                    style={{
                      marginTop: '16px',
                      fontFamily: 'var(--onyx-body)',
                      fontStyle: 'normal',
                      fontSize: '16px',
                      lineHeight: 1.65,
                      color: 'var(--onyx-bone-2)',
                      maxWidth: '70ch',
                    }}
                  >
                    {story.why_matters}
                  </p>
                )}

                <div
                  className="onyx-mono"
                  style={{
                    marginTop: '16px',
                    fontSize: '10px',
                    letterSpacing: '0.24em',
                    textTransform: 'uppercase',
                    color: 'var(--onyx-dim)',
                    display: 'flex',
                    gap: '14px',
                    flexWrap: 'wrap',
                    alignItems: 'center',
                  }}
                >
                  <span>{story.source_name}</span>
                  <span style={{ opacity: 0.4 }}>·</span>
                  <span>{formatTimeAgo(story.published_at)}</span>
                  <span style={{ flex: 1 }} />
                  <button
                    type="button"
                    onClick={() => onRead(story.article_id)}
                    className="onyx-mono"
                    style={actionButtonStyle()}
                  >
                    Read →
                  </button>
                  {onCompareToggle && (
                    <button
                      type="button"
                      onClick={() => onCompareToggle(story.article_id)}
                      className="onyx-mono"
                      style={actionButtonStyle(isSelected)}
                    >
                      {isSelected ? '✓ Compare' : 'Compare'}
                    </button>
                  )}
                  {onAddToCard && (
                    <button
                      type="button"
                      onClick={() => onAddToCard(story.article_id)}
                      className="onyx-mono"
                      style={actionButtonStyle()}
                    >
                      + Card
                    </button>
                  )}
                </div>
              </div>
            </article>
          )
        })}
      </div>
    </section>
  )
}

function actionButtonStyle(active: boolean = false): React.CSSProperties {
  return {
    background: 'transparent',
    border: 'none',
    color: active ? 'var(--onyx-cyan)' : 'var(--onyx-dim)',
    fontSize: '10px',
    letterSpacing: '0.32em',
    textTransform: 'uppercase',
    padding: '6px 0',
    cursor: 'pointer',
    transition: 'color 0.3s',
  }
}
