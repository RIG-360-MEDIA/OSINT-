/**
 * AskBar — sticky filter-aware RAG input + streamed answer panel.
 *
 * On submit:
 *   - Aborts any in-flight request.
 *   - POSTs to /api/coverage/ask with question + current filter state.
 *   - Consumes SSE stream: `meta` frame seeds source list,
 *     `token` frames append to answer prose,
 *     `done` frame closes,
 *     `error` frame surfaces a message.
 *
 * Displays answer in italic Instrument Serif. Inline [N] citations
 * become click targets that open the referenced article in the
 * existing slide-over reader (handled by parent via `onCiteClick`).
 *
 * Prompt chips below the input fire pre-baked questions.
 */

'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { createClient } from '@/lib/supabase/client'
import { consumeSSE } from '@/lib/sse'
import type { ArticleFilters } from '@/lib/articleFilters'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface AskSource {
  article_id: string
  title: string
  source_name: string
  source_domain: string
  published_at: string | null
}

interface AskBarProps {
  filters: ArticleFilters
  onCiteClick: (articleId: string) => void
  /** Optional — if set, replays a prior session on mount. */
  initialSessionId?: string | null
}

const PROMPT_CHIPS: ReadonlyArray<{ label: string; question: string }> = [
  { label: 'Summarize', question: 'Summarize the most important developments in the current view.' },
  { label: 'Diverging', question: 'Where do sources disagree in the current view?' },
  { label: 'Trending', question: 'What entity or topic is trending most strongly right now?' },
  { label: 'Compare', question: 'Pick two contrasting stories from the current view and compare how they frame the same issue.' },
]

export function AskBar({ filters, onCiteClick, initialSessionId = null }: AskBarProps) {
  const [question, setQuestion] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [answer, setAnswer] = useState('')
  const [sources, setSources] = useState<AskSource[]>([])
  const [error, setError] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(initialSessionId)
  const abortRef = useRef<AbortController | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Abort any in-flight stream when filters change.
  useEffect(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
      setStreaming(false)
    }
  }, [filters])

  const submit = useCallback(async (q: string) => {
    if (!q.trim() || streaming) return
    setError(null)
    setAnswer('')
    setSources([])

    const supabase = createClient()
    const { data: { session } } = await supabase.auth.getSession()
    const token = session?.access_token
    if (!token) {
      setError('Sign in required.')
      return
    }

    const ctrl = new AbortController()
    abortRef.current = ctrl
    setStreaming(true)

    try {
      await consumeSSE({
        url: `${API_BASE}/api/coverage/ask`,
        body: { question: q, filters, session_id: sessionId },
        headers: { Authorization: `Bearer ${token}` },
        signal: ctrl.signal,
        onEvent: (evt) => {
          if (evt.event === 'meta') {
            try {
              const meta = JSON.parse(evt.data) as {
                session_id: string
                sources: AskSource[]
              }
              setSessionId(meta.session_id)
              setSources(meta.sources)
            } catch {
              /* ignore malformed */
            }
          } else if (evt.event === 'token') {
            try {
              const parsed = JSON.parse(evt.data) as unknown
              if (
                parsed &&
                typeof parsed === 'object' &&
                't' in parsed &&
                typeof (parsed as { t: unknown }).t === 'string'
              ) {
                const t = (parsed as { t: string }).t
                setAnswer((prev) => prev + t)
              } else if (typeof parsed === 'string') {
                // Defensive: server sometimes used to send raw string literals.
                setAnswer((prev) => prev + parsed)
              }
              // else: unknown shape — silently drop so we never render "undefined".
            } catch {
              // Non-JSON payload — safe to append as-is unless it looks like literal undefined.
              const raw = evt.data
              if (raw && raw !== 'undefined') {
                setAnswer((prev) => prev + raw)
              }
            }
          } else if (evt.event === 'error') {
            let message = 'Could not generate an answer.'
            try {
              const parsed = JSON.parse(evt.data) as { message?: unknown }
              if (parsed && typeof parsed.message === 'string' && parsed.message.trim()) {
                message = parsed.message
              }
            } catch {
              /* keep default */
            }
            setError(message)
          } else if (evt.event === 'done') {
            // no-op; finally block will reset streaming flag
          }
        },
      })
    } catch (err: unknown) {
      if (err instanceof Error && err.name !== 'AbortError') {
        setError(err.message)
      }
    } finally {
      setStreaming(false)
      abortRef.current = null
    }
  }, [filters, sessionId, streaming])

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault()
    void submit(question)
  }, [question, submit])

  return (
    <section
      style={{
        position: 'relative',
        zIndex: 5,
        padding: '32px 0 24px',
        borderBottom: '1px solid var(--onyx-rule-hair)',
      }}
    >
      <form
        onSubmit={handleSubmit}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '16px',
          paddingBottom: '16px',
        }}
      >
        <input
          ref={inputRef}
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask anything about the current view…"
          disabled={streaming}
          style={{
            flex: 1,
            background: 'transparent',
            border: 'none',
            borderBottom: '1px solid var(--onyx-rule-dim)',
            color: 'var(--onyx-bone)',
            fontFamily: 'var(--onyx-italic)',
            fontStyle: 'italic',
            fontSize: '24px',
            padding: '12px 0',
            outline: 'none',
            transition: 'border-color 0.3s ease',
          }}
          onFocus={(e) => {
            (e.currentTarget.style.borderBottomColor = 'var(--onyx-cyan)')
          }}
          onBlur={(e) => {
            (e.currentTarget.style.borderBottomColor = 'var(--onyx-rule-dim)')
          }}
        />
        <button
          type="submit"
          disabled={streaming || !question.trim()}
          style={{
            background: 'transparent',
            border: '1px solid var(--onyx-rule-hair)',
            color: streaming ? 'var(--onyx-dim)' : 'var(--onyx-bone)',
            fontFamily: 'var(--onyx-mono)',
            fontSize: '11px',
            letterSpacing: '0.32em',
            textTransform: 'uppercase',
            padding: '12px 24px',
            cursor: streaming ? 'not-allowed' : 'pointer',
            transition: 'all 0.3s ease',
          }}
        >
          {streaming ? '…' : 'Ask →'}
        </button>
      </form>

      {/* Prompt chips */}
      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
        {PROMPT_CHIPS.map((chip) => (
          <button
            key={chip.label}
            type="button"
            disabled={streaming}
            onClick={() => {
              setQuestion(chip.question)
              void submit(chip.question)
            }}
            style={{
              background: 'transparent',
              border: '1px solid var(--onyx-rule-hair)',
              color: 'var(--onyx-dim)',
              fontFamily: 'var(--onyx-mono)',
              fontSize: '10px',
              letterSpacing: '0.28em',
              textTransform: 'uppercase',
              padding: '6px 12px',
              cursor: streaming ? 'not-allowed' : 'pointer',
              transition: 'border-color 0.3s, color 0.3s',
            }}
            onMouseEnter={(e) => {
              if (!streaming) {
                (e.currentTarget.style.borderColor = 'var(--onyx-cyan)')
                ;(e.currentTarget.style.color = 'var(--onyx-bone-2)')
              }
            }}
            onMouseLeave={(e) => {
              (e.currentTarget.style.borderColor = 'var(--onyx-rule-hair)')
              ;(e.currentTarget.style.color = 'var(--onyx-dim)')
            }}
          >
            {chip.label}
          </button>
        ))}
      </div>

      {/* Answer panel */}
      {(answer || streaming || error) && (
        <AnswerPanel
          answer={answer}
          sources={sources}
          streaming={streaming}
          error={error}
          onCiteClick={onCiteClick}
        />
      )}
    </section>
  )
}


interface AnswerPanelProps {
  answer: string
  sources: AskSource[]
  streaming: boolean
  error: string | null
  onCiteClick: (articleId: string) => void
}

/**
 * Renders streamed prose with inline [N] citation pills. Each pill is a
 * click target that opens the referenced article via the parent reader.
 */
function AnswerPanel({ answer, sources, streaming, error, onCiteClick }: AnswerPanelProps) {
  return (
    <div
      style={{
        marginTop: '32px',
        padding: '24px 0',
        borderTop: '1px solid var(--onyx-rule-hair)',
        animation: 'onyx-fade-up 0.5s ease both',
      }}
    >
      {error && (
        <div
          className="onyx-mono"
          style={{
            fontSize: '11px',
            letterSpacing: '0.24em',
            textTransform: 'uppercase',
            color: 'var(--onyx-red)',
            marginBottom: '16px',
          }}
        >
          {error}
        </div>
      )}

      <div
        style={{
          fontFamily: 'var(--onyx-italic)',
          fontStyle: 'italic',
          fontSize: '20px',
          lineHeight: 1.65,
          color: 'var(--onyx-bone)',
          maxWidth: '78ch',
        }}
      >
        {renderAnswer(answer, sources, onCiteClick)}
        {streaming && (
          <span
            style={{
              display: 'inline-block',
              width: '8px',
              height: '20px',
              background: 'var(--onyx-cyan)',
              marginLeft: '6px',
              verticalAlign: 'text-bottom',
              animation: 'onyx-blink 0.85s steps(2) infinite',
            }}
          />
        )}
      </div>

      {sources.length > 0 && !streaming && (
        <div style={{ marginTop: '24px' }}>
          <div
            className="onyx-mono"
            style={{
              fontSize: '10px',
              letterSpacing: '0.32em',
              textTransform: 'uppercase',
              color: 'var(--onyx-dim)',
              marginBottom: '12px',
            }}
          >
            Sources ({sources.length})
          </div>
          <ol
            style={{
              listStyle: 'none',
              padding: 0,
              margin: 0,
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
            }}
          >
            {sources.map((s, i) => (
              <li key={s.article_id}>
                <button
                  type="button"
                  onClick={() => onCiteClick(s.article_id)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--onyx-bone-2)',
                    fontFamily: 'var(--onyx-display)',
                    fontSize: '14px',
                    textAlign: 'left',
                    padding: 0,
                    cursor: 'pointer',
                    display: 'flex',
                    gap: '12px',
                    alignItems: 'baseline',
                  }}
                >
                  <span
                    className="onyx-mono"
                    style={{
                      color: 'var(--onyx-cyan)',
                      fontSize: '11px',
                      letterSpacing: '0.18em',
                      flexShrink: 0,
                      width: '24px',
                    }}
                  >
                    [{i + 1}]
                  </span>
                  <span>
                    {s.title}{' '}
                    <span style={{ color: 'var(--onyx-dim)', fontSize: '11px' }}>
                      — {s.source_name}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  )
}


function renderAnswer(
  text: string,
  sources: AskSource[],
  onCiteClick: (articleId: string) => void,
): React.ReactNode[] {
  // Replace [N] tokens with click pills.
  const parts: React.ReactNode[] = []
  const regex = /\[(\d+)\]/g
  let lastIdx = 0
  let m: RegExpExecArray | null

  while ((m = regex.exec(text)) !== null) {
    const before = text.slice(lastIdx, m.index)
    if (before) parts.push(before)

    const n = parseInt(m[1], 10)
    const src = sources[n - 1]
    parts.push(
      <button
        key={`cite-${m.index}`}
        type="button"
        disabled={!src}
        onClick={() => src && onCiteClick(src.article_id)}
        title={src ? `${src.title} — ${src.source_name}` : undefined}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          height: '20px',
          padding: '0 6px',
          margin: '0 2px',
          background: 'transparent',
          border: '1px solid var(--onyx-cyan)',
          color: 'var(--onyx-cyan)',
          fontFamily: 'var(--onyx-mono)',
          fontStyle: 'normal',
          fontSize: '10px',
          letterSpacing: '0.12em',
          cursor: src ? 'pointer' : 'default',
          verticalAlign: 'middle',
          transition: 'background 0.2s',
        }}
        onMouseEnter={(e) => {
          if (src) (e.currentTarget.style.background = 'var(--onyx-cyan-soft)')
        }}
        onMouseLeave={(e) => {
          (e.currentTarget.style.background = 'transparent')
        }}
      >
        {n}
      </button>
    )
    lastIdx = m.index + m[0].length
  }

  const tail = text.slice(lastIdx)
  if (tail) parts.push(tail)
  return parts
}
