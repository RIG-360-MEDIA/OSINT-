/**
 * RightRail — sticky vertical column that surfaces secondary intel:
 *   - Watchlist (pinned entities + new mention counts)
 *   - Recent Quotes (italic pull-quotes)
 *   - Today, last year (time travel retrospective)
 *   - Coverage gaps (under-covered entities)
 *   - Contradictions (count + open drawer)
 *
 * All textual. Polls each section once on mount; lightweight.
 */

'use client'

import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function authedFetch(path: string): Promise<Response | null> {
  const supabase = createClient()
  const { data: { session } } = await supabase.auth.getSession()
  const token = session?.access_token
  if (!token) return null
  return fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  })
}

interface RightRailProps {
  onContradictionsClick: () => void
  onArticleClick: (id: string) => void
}

export function RightRail({ onContradictionsClick, onArticleClick }: RightRailProps) {
  return (
    <aside
      style={{
        position: 'sticky',
        top: 'calc(var(--topbar-h) + 32px)',
        display: 'flex',
        flexDirection: 'column',
        gap: '32px',
        maxHeight: 'calc(100vh - var(--topbar-h) - 64px)',
        overflowY: 'auto',
        paddingRight: '8px',
      }}
    >
      <ContradictionsPill onClick={onContradictionsClick} />
      <WatchlistPanel />
      <QuotesPanel onArticleClick={onArticleClick} />
      <TimeTravelPanel onArticleClick={onArticleClick} />
      <CoverageGapsPanel />
    </aside>
  )
}


/* ── Contradictions pill ───────────────────────────────────────── */

function ContradictionsPill({ onClick }: { onClick: () => void }) {
  const [count, setCount] = useState<number>(0)
  useEffect(() => {
    let cancelled = false
    void (async () => {
      const res = await authedFetch('/api/coverage/contradictions?limit=1')
      if (!res || !res.ok) return
      const json = await res.json() as { contradictions: unknown[] }
      // Crude "active count" — backend caps to 1 here; for an accurate count
      // call again with limit=50 if you want a precise badge later.
      if (!cancelled) {
        // Use header? backend does not expose total. Re-fetch with limit=50:
        const r2 = await authedFetch('/api/coverage/contradictions?limit=50')
        if (r2 && r2.ok) {
          const j2 = await r2.json() as { contradictions: unknown[] }
          setCount(j2.contradictions?.length ?? 0)
        } else {
          setCount(json.contradictions?.length ?? 0)
        }
      }
    })()
    return () => { cancelled = true }
  }, [])

  if (count === 0) return null

  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        background: 'transparent',
        border: '1px solid var(--onyx-red)',
        color: 'var(--onyx-red)',
        fontFamily: 'var(--onyx-mono)',
        fontSize: '10px',
        letterSpacing: '0.32em',
        textTransform: 'uppercase',
        padding: '12px 14px',
        textAlign: 'left',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
      }}
    >
      <span style={{ flex: 1 }}>Contradictions ({count})</span>
      <span>→</span>
    </button>
  )
}


/* ── Watchlist panel ──────────────────────────────────────────── */

interface WatchPin {
  entity_id: string
  name: string
  new_mentions: number
}

function WatchlistPanel() {
  const [pins, setPins] = useState<WatchPin[]>([])

  useEffect(() => {
    void (async () => {
      const res = await authedFetch('/api/coverage/watchlist')
      if (!res || !res.ok) return
      const json = await res.json() as { pins: WatchPin[] }
      setPins(json.pins || [])
    })()
  }, [])

  return (
    <Section title="Watchlist">
      {pins.length === 0 && <Empty>No pins yet.</Empty>}
      {pins.length > 0 && (
        <ul style={listReset()}>
          {pins.map((p) => (
            <li key={p.entity_id} style={rowStyle()}>
              <span
                style={{
                  fontFamily: 'var(--onyx-display)',
                  fontSize: '14px',
                  color: 'var(--onyx-bone)',
                }}
              >
                {p.name}
              </span>
              {p.new_mentions > 0 && (
                <span
                  className="onyx-mono"
                  style={{
                    fontSize: '10px',
                    color: 'var(--onyx-cyan)',
                    letterSpacing: '0.18em',
                  }}
                >
                  {p.new_mentions} new
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}


/* ── Recent quotes ────────────────────────────────────────────── */

interface Quote {
  id: string
  speaker_name: string
  // Translated/transliterated speaker name (English). Set by extractor
  // post-migration-049 OR by the backfill translator. Renderer prefers
  // it so a Telugu-script speaker name appears as English.
  speaker_name_en?: string | null
  quote_text: string
  // English translation of the quote text. Same fallback rule.
  quote_text_en?: string | null
  article_id: string
  source_name: string
}

function QuotesPanel({ onArticleClick }: { onArticleClick: (id: string) => void }) {
  const [quotes, setQuotes] = useState<Quote[]>([])

  useEffect(() => {
    void (async () => {
      const res = await authedFetch('/api/coverage/quotes?days=7&limit=4')
      if (!res || !res.ok) return
      const json = await res.json() as { quotes: Quote[] }
      setQuotes(json.quotes || [])
    })()
  }, [])

  return (
    <Section title="Recent quotes">
      {quotes.length === 0 && <Empty>No quotes captured yet.</Empty>}
      {quotes.map((q) => (
        <button
          key={q.id}
          type="button"
          onClick={() => onArticleClick(q.article_id)}
          style={{
            display: 'block',
            background: 'transparent',
            border: 'none',
            padding: '10px 0',
            textAlign: 'left',
            cursor: 'pointer',
            width: '100%',
            borderBottom: '1px solid var(--onyx-rule-dim)',
          }}
        >
          {(() => {
            // If the source-language text differs from the English
            // translation, show ORIGINAL first (italic, full opacity) then
            // English underneath (slightly smaller, dimmer). When the
            // article is already English, quote_text_en will match
            // quote_text — show only one line.
            //
            // Normalisation matters: Groq sometimes returns text with
            // surrounding quotation marks/apostrophes in one variant
            // and stripped in the other (e.g. "'stealing elections'"
            // vs "stealing elections"). Compare lowercased+stripped of
            // punctuation+whitespace before deciding to render twice.
            const original = q.quote_text
            const english = q.quote_text_en
            const norm = (s: string) =>
              s
                .toLowerCase()
                .replace(/[\s\p{P}]+/gu, '')
                .trim()
            const showBoth =
              !!english &&
              english.trim().length > 0 &&
              norm(english) !== norm(original)
            const truncate = (s: string) =>
              s.length > 180 ? `${s.slice(0, 180)}…` : s
            return (
              <>
                <div
                  style={{
                    fontFamily: 'var(--onyx-italic)',
                    fontStyle: 'italic',
                    fontSize: '14px',
                    lineHeight: 1.5,
                    color: 'var(--onyx-bone-2)',
                    marginBottom: showBoth ? '6px' : '8px',
                  }}
                >
                  {`"${truncate(original)}"`}
                </div>
                {showBoth && (
                  <div
                    style={{
                      fontSize: '12px',
                      lineHeight: 1.5,
                      color: 'var(--onyx-dim)',
                      marginBottom: '8px',
                    }}
                  >
                    {`"${truncate(english as string)}"`}
                  </div>
                )}
              </>
            )
          })()}
          <div
            className="onyx-mono"
            style={{
              fontSize: '9px',
              letterSpacing: '0.32em',
              textTransform: 'uppercase',
              color: 'var(--onyx-dim)',
            }}
          >
            {(() => {
              const sp = q.speaker_name
              const spEn = q.speaker_name_en
              const norm = (s: string) =>
                s
                  .toLowerCase()
                  .replace(/[\s\p{P}]+/gu, '')
                  .trim()
              const showBothSpeaker =
                !!spEn &&
                spEn.trim().length > 0 &&
                norm(spEn) !== norm(sp)
              return showBothSpeaker
                ? `${sp} (${spEn}) · ${q.source_name}`
                : `${sp} · ${q.source_name}`
            })()}
          </div>
        </button>
      ))}
    </Section>
  )
}


/* ── Time travel ──────────────────────────────────────────────── */

interface HistoricalArticle {
  article_id: string
  title: string
  source_name: string
  published_at: string | null
}

function TimeTravelPanel({ onArticleClick }: { onArticleClick: (id: string) => void }) {
  const [items, setItems] = useState<HistoricalArticle[]>([])

  useEffect(() => {
    void (async () => {
      const res = await authedFetch('/api/coverage/timetravel?offset_years=1')
      if (!res || !res.ok) return
      const json = await res.json() as { articles: HistoricalArticle[] }
      setItems(json.articles || [])
    })()
  }, [])

  if (items.length === 0) return null

  return (
    <Section title="Today, last year">
      {items.map((a) => (
        <button
          key={a.article_id}
          type="button"
          onClick={() => onArticleClick(a.article_id)}
          style={{
            display: 'block',
            background: 'transparent',
            border: 'none',
            padding: '8px 0',
            textAlign: 'left',
            cursor: 'pointer',
            width: '100%',
          }}
        >
          <div
            style={{
              fontFamily: 'var(--onyx-italic)',
              fontStyle: 'italic',
              fontSize: '13px',
              lineHeight: 1.5,
              color: 'var(--onyx-bone-2)',
              marginBottom: '4px',
            }}
          >
            {a.title}
          </div>
          <div
            className="onyx-mono"
            style={{
              fontSize: '9px',
              letterSpacing: '0.28em',
              textTransform: 'uppercase',
              color: 'var(--onyx-dim)',
            }}
          >
            {a.source_name}
          </div>
        </button>
      ))}
    </Section>
  )
}


/* ── Coverage gaps ────────────────────────────────────────────── */

interface Gap {
  entity_id: string
  name: string
  ratio: number
  summary: string
}

function CoverageGapsPanel() {
  const [gaps, setGaps] = useState<Gap[]>([])

  useEffect(() => {
    void (async () => {
      const res = await authedFetch('/api/coverage/coverage-gaps')
      if (!res || !res.ok) return
      const json = await res.json() as { gaps: Gap[] }
      setGaps(json.gaps?.slice(0, 4) || [])
    })()
  }, [])

  if (gaps.length === 0) return null

  return (
    <Section title="Under-covered today">
      {gaps.map((g) => (
        <div key={g.entity_id} style={{ padding: '10px 0', borderBottom: '1px solid var(--onyx-rule-dim)' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'baseline',
              marginBottom: '4px',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--onyx-display)',
                fontSize: '13px',
                fontWeight: 500,
                color: 'var(--onyx-bone)',
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
              }}
            >
              {g.name}
            </span>
            <span
              className="onyx-mono"
              style={{
                fontSize: '9px',
                letterSpacing: '0.18em',
                color: 'var(--onyx-cyan)',
              }}
            >
              {g.ratio.toFixed(1)}× social
            </span>
          </div>
          {g.summary && (
            <div
              style={{
                fontFamily: 'var(--onyx-body)',
                fontStyle: 'normal',
                fontSize: '12.5px',
                lineHeight: 1.55,
                color: 'var(--onyx-bone-2)',
              }}
            >
              {g.summary}
            </div>
          )}
        </div>
      ))}
    </Section>
  )
}


/* ── Shared layout helpers ────────────────────────────────────── */

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <section>
    <header style={{ marginBottom: '12px' }}>
      <div
        className="onyx-mono"
        style={{
          fontSize: '10px',
          letterSpacing: '0.42em',
          textTransform: 'uppercase',
          color: 'var(--onyx-dim)',
        }}
      >
        {title}
      </div>
      <hr className="onyx-hairline-dim" style={{ marginTop: '8px' }} />
    </header>
    {children}
  </section>
)

const Empty = ({ children }: { children: React.ReactNode }) => (
  <div
    className="onyx-italic"
    style={{
      fontStyle: 'italic',
      fontSize: '13px',
      color: 'var(--onyx-dim)',
      padding: '8px 0',
    }}
  >
    {children}
  </div>
)

const listReset = (): React.CSSProperties => ({
  listStyle: 'none',
  padding: 0,
  margin: 0,
  display: 'flex',
  flexDirection: 'column',
})

const rowStyle = (): React.CSSProperties => ({
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'baseline',
  padding: '8px 0',
  borderBottom: '1px solid var(--onyx-rule-dim)',
})
