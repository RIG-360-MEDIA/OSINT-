'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import Navigation from '@/components/Navigation'

// ── Types ─────────────────────────────────────────────────────────────────────

interface EvidenceArticle {
  article_id: string
  title: string
  source_name: string
  source_domain: string
  published_at: string | null
  collected_at: string | null
  topic_category: string | null
  geo_primary: string | null
  score_final: number
  distance?: number
}

interface Turn {
  id: string
  question: string
  answer: string
  evidence_count: number
  confidence: string
  confidence_pct?: number
  created_at: string
}

interface QueryResponse {
  mode: string
  auto_detected: boolean
  answer: string
  articles: EvidenceArticle[]
  confidence: string
  confidence_pct?: number
  followups: string[]
  session_id: string
  retrieval_ms: number
  retrieval_method: string
  article_count: number
}

interface Section {
  header: string
  body: string
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const VALID_MODES = ['SITUATION', 'OPPOSITION', 'RISK', 'POLICY', 'PATTERN', 'BRIEF']

const LOADING_TEXTS = [
  'Searching intelligence corpus…',
  'Retrieving relevant articles…',
  'Building context window…',
  'Running analysis…',
  'Structuring assessment…',
]

const CIRCLED: Record<number, string> = {
  1: '①', 2: '②', 3: '③', 4: '④', 5: '⑤',
  6: '⑥', 7: '⑦', 8: '⑧', 9: '⑨', 10: '⑩',
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function parseSections(text: string): Section[] {
  const lines = text.split('\n')
  const sections: Section[] = []
  let current: Section | null = null

  for (const line of lines) {
    const trimmed = line.trim()
    const isHeader = /^#{1,3}\s+/.test(trimmed) || /^[A-Z][A-Z\s\-:]{4,}$/.test(trimmed)
    if (isHeader) {
      if (current) sections.push(current)
      current = { header: trimmed.replace(/^#+\s+/, ''), body: '' }
    } else {
      if (!current) current = { header: '', body: '' }
      current.body += (current.body ? '\n' : '') + line
    }
  }
  if (current) sections.push(current)
  return sections.filter((s) => s.header || s.body.trim())
}

function renderTextWithCitations(
  text: string,
  articles: EvidenceArticle[],
  onCite: (article: EvidenceArticle) => void
): React.ReactNode[] {
  const parts = text.split(/(①|②|③|④|⑤|⑥|⑦|⑧|⑨|⑩)/g)
  return parts.map((part, i) => {
    const idx = Object.values(CIRCLED).indexOf(part)
    if (idx !== -1 && articles[idx]) {
      const article = articles[idx]
      return (
        <button
          key={i}
          onClick={() => onCite(article)}
          title={article.title}
          style={{
            display: 'inline',
            background: 'none',
            border: 'none',
            padding: '0 2px',
            fontFamily: "'DM Mono', ui-monospace, monospace",
            fontSize: '13px',
            color: '#1B3A6B',
            cursor: 'pointer',
            textDecoration: 'underline',
            textDecorationStyle: 'dotted',
          }}
        >
          {part}
        </button>
      )
    }
    return <span key={i}>{part}</span>
  })
}

// ── Evidence card ─────────────────────────────────────────────────────────────

interface EvidenceCardProps {
  article: EvidenceArticle
  index: number
  router: ReturnType<typeof useRouter>
}

function EvidenceCard({ article, index, router }: EvidenceCardProps) {
  return (
    <div
      style={{
        borderLeft: '3px solid #1B3A6B',
        padding: '10px 14px',
        backgroundColor: '#EEF3FA',
        borderRadius: '0 2px 2px 0',
        display: 'flex',
        alignItems: 'flex-start',
        gap: '10px',
      }}
    >
      <span
        style={{
          fontFamily: "'DM Mono', ui-monospace, monospace",
          fontSize: '13px',
          color: '#1B3A6B',
          flexShrink: 0,
          marginTop: '1px',
        }}
      >
        {CIRCLED[index + 1] ?? `[${index + 1}]`}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontFamily: "'DM Sans', system-ui, sans-serif",
            fontSize: '13px',
            fontWeight: 500,
            color: '#1A1614',
            lineHeight: 1.4,
            marginBottom: '4px',
          }}
        >
          {article.title}
        </div>
        <div
          style={{
            fontFamily: "'DM Sans', system-ui, sans-serif",
            fontSize: '11px',
            color: '#9C928A',
          }}
        >
          {article.source_name}
          {article.topic_category && ` · ${article.topic_category}`}
          {article.geo_primary && ` · ${article.geo_primary}`}
        </div>
      </div>
      <button
        onClick={() => router.push(`/coverage?article=${article.article_id}`)}
        title="Open in Coverage Room"
        style={{
          background: 'none',
          border: 'none',
          padding: '2px 4px',
          fontFamily: "'DM Sans', system-ui, sans-serif",
          fontSize: '13px',
          color: '#1B3A6B',
          cursor: 'pointer',
          flexShrink: 0,
        }}
      >
        →
      </button>
    </div>
  )
}

// ── Answer document ───────────────────────────────────────────────────────────

interface AnswerDocProps {
  sections: Section[]
  visibleCount: number
  articles: EvidenceArticle[]
  mode: string
  confidence: string
  confidence_pct?: number
  retrieval_ms: number
  article_count: number
  followups: string[]
  onFollowup: (q: string) => void
  router: ReturnType<typeof useRouter>
}

function AnswerDocument({
  sections,
  visibleCount,
  articles,
  mode,
  confidence,
  confidence_pct,
  retrieval_ms,
  article_count,
  followups,
  onFollowup,
  router,
}: AnswerDocProps) {
  const [showEvidence, setShowEvidence] = useState(false)
  const [citedArticle, setCitedArticle] = useState<EvidenceArticle | null>(null)

  const CONF_COLOR: Record<string, string> = {
    HIGH: '#2D6B3A', MEDIUM: '#8B6A1A', LOW: '#8B1A1A',
  }

  return (
    <div
      style={{
        backgroundColor: '#F7F4EF',
        border: '1px solid #DDD8D0',
        borderRadius: '2px',
        overflow: 'hidden',
      }}
    >
      {/* Header bar */}
      <div
        style={{
          borderBottom: '1px solid #DDD8D0',
          padding: '12px 24px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          flexWrap: 'wrap',
        }}
      >
        <span
          style={{
            fontFamily: "'DM Mono', ui-monospace, monospace",
            fontSize: '10px',
            letterSpacing: '0.12em',
            color: '#F7F4EF',
            backgroundColor: '#1B3A6B',
            padding: '2px 8px',
            borderRadius: '2px',
          }}
        >
          {mode}
        </span>
        <span
          style={{
            fontFamily: "'DM Mono', ui-monospace, monospace",
            fontSize: '10px',
            letterSpacing: '0.1em',
            color: CONF_COLOR[confidence] ?? '#9C928A',
            border: `1px solid ${CONF_COLOR[confidence] ?? '#9C928A'}`,
            padding: '2px 6px',
            borderRadius: '2px',
          }}
        >
          {confidence} CONFIDENCE{confidence_pct !== undefined ? ` (${confidence_pct}%)` : ''}
        </span>
        <span
          style={{
            fontFamily: "'DM Mono', ui-monospace, monospace",
            fontSize: '11px',
            color: '#9C928A',
            marginLeft: 'auto',
          }}
        >
          {article_count} sources · {retrieval_ms}ms
        </span>
      </div>

      {/* Body */}
      <div style={{ padding: '24px 32px' }}>
        {sections.slice(0, visibleCount).map((section, i) => (
          <div
            key={i}
            style={{
              marginBottom: '20px',
              opacity: 1,
              transition: 'opacity 300ms ease',
            }}
          >
            {section.header && (
              <div
                style={{
                  fontFamily: "'DM Mono', ui-monospace, monospace",
                  fontSize: '10px',
                  letterSpacing: '0.15em',
                  textTransform: 'uppercase',
                  color: '#9C928A',
                  marginBottom: '8px',
                }}
              >
                {section.header}
              </div>
            )}
            <div
              style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '15px',
                lineHeight: 1.75,
                color: '#1A1614',
                whiteSpace: 'pre-wrap',
              }}
            >
              {renderTextWithCitations(section.body, articles, setCitedArticle)}
            </div>
          </div>
        ))}

        {/* Cited article popover */}
        {citedArticle && (
          <div
            style={{
              marginBottom: '16px',
              padding: '12px 16px',
              backgroundColor: '#EEF3FA',
              borderLeft: '3px solid #1B3A6B',
              borderRadius: '0 2px 2px 0',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
            }}
          >
            <div style={{ flex: 1 }}>
              <div
                style={{
                  fontFamily: "'DM Sans', system-ui, sans-serif",
                  fontSize: '13px',
                  fontWeight: 500,
                  color: '#1A1614',
                }}
              >
                {citedArticle.title}
              </div>
              <div
                style={{
                  fontFamily: "'DM Sans', system-ui, sans-serif",
                  fontSize: '11px',
                  color: '#9C928A',
                  marginTop: '2px',
                }}
              >
                {citedArticle.source_name}
              </div>
            </div>
            <button
              onClick={() =>
                router.push(`/coverage?article=${citedArticle.article_id}`)
              }
              style={{
                background: 'none',
                border: '1px solid #1B3A6B',
                padding: '4px 10px',
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '12px',
                color: '#1B3A6B',
                cursor: 'pointer',
                borderRadius: '2px',
                flexShrink: 0,
              }}
            >
              Open →
            </button>
            <button
              onClick={() => setCitedArticle(null)}
              style={{
                background: 'none',
                border: 'none',
                padding: '0 4px',
                fontSize: '16px',
                color: '#9C928A',
                cursor: 'pointer',
                lineHeight: 1,
                flexShrink: 0,
              }}
            >
              ×
            </button>
          </div>
        )}

        {/* Evidence panel toggle */}
        {visibleCount >= sections.length && articles.length > 0 && (
          <div style={{ marginTop: '24px' }}>
            <button
              onClick={() => setShowEvidence((v) => !v)}
              style={{
                background: 'none',
                border: 'none',
                padding: 0,
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '12px',
                color: '#1B3A6B',
                cursor: 'pointer',
                letterSpacing: '0.06em',
              }}
            >
              {showEvidence ? '▴ Hide sources' : `▾ Show ${articles.length} sources`}
            </button>
            {showEvidence && (
              <div
                style={{
                  marginTop: '12px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                }}
              >
                {articles.map((a, i) => (
                  <EvidenceCard key={a.article_id} article={a} index={i} router={router} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Follow-up suggestions */}
        {visibleCount >= sections.length && followups.length > 0 && (
          <div style={{ marginTop: '24px', paddingTop: '20px', borderTop: '1px dashed #DDD8D0' }}>
            <div
              style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '10px',
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
                color: '#9C928A',
                marginBottom: '10px',
              }}
            >
              Suggested follow-ups
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {followups.map((q, i) => (
                <button
                  key={i}
                  onClick={() => onFollowup(q)}
                  style={{
                    background: 'none',
                    border: '1px solid #DDD8D0',
                    borderRadius: '2px',
                    padding: '8px 12px',
                    fontFamily: "'DM Sans', system-ui, sans-serif",
                    fontSize: '13px',
                    color: '#1A1614',
                    cursor: 'pointer',
                    textAlign: 'left',
                  }}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Loading state ─────────────────────────────────────────────────────────────

function LoadingState() {
  const [textIdx, setTextIdx] = useState(0)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const textInterval = setInterval(() => {
      setTextIdx((i) => (i + 1) % LOADING_TEXTS.length)
    }, 1800)
    const progInterval = setInterval(() => {
      setProgress((p) => Math.min(p + 2, 90))
    }, 150)
    return () => {
      clearInterval(textInterval)
      clearInterval(progInterval)
    }
  }, [])

  return (
    <div
      style={{
        padding: '32px',
        backgroundColor: '#F7F4EF',
        border: '1px solid #DDD8D0',
        borderRadius: '2px',
      }}
    >
      <div
        style={{
          fontFamily: "'DM Sans', system-ui, sans-serif",
          fontSize: '14px',
          color: '#5C5249',
          marginBottom: '16px',
        }}
      >
        {LOADING_TEXTS[textIdx]}
      </div>
      <div
        style={{
          height: '3px',
          backgroundColor: '#E8E3DA',
          borderRadius: '2px',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            height: '100%',
            width: `${progress}%`,
            backgroundColor: '#1B3A6B',
            borderRadius: '2px',
            transition: 'width 150ms linear',
          }}
        />
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AnalystPage() {
  const router = useRouter()

  const getToken = useCallback(async (): Promise<string | null> => {
    const supabase = createClient()
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) {
      router.push('/login')
      return null
    }
    return session.access_token
  }, [router])

  const [sessionId, setSessionId] = useState('')
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')

  const [response, setResponse] = useState<QueryResponse | null>(null)
  const [sections, setSections] = useState<Section[]>([])
  const [visibleCount, setVisibleCount] = useState(0)

  const [trail, setTrail] = useState<Turn[]>([])
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [selectedMode, setSelectedMode] = useState('')

  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Boot: get session + context suggestions
  useEffect(() => {
    const boot = async () => {
      const token = await getToken()
      if (!token) return
      try {
        const [sessRes, ctxRes] = await Promise.all([
          fetch(`${API_BASE}/api/analyst/session`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`${API_BASE}/api/analyst/context`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
        ])
        if (sessRes.ok) {
          const s = await sessRes.json()
          setSessionId(s.session_id)
          if (s.turns?.length) setTrail(s.turns)
        }
        if (ctxRes.ok) {
          const c = await ctxRes.json()
          setSuggestions(c.suggestions ?? [])
        }
      } catch {
        // ignore boot errors
      }
    }
    void boot()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Progressive section reveal
  useEffect(() => {
    if (!sections.length) return
    setVisibleCount(0)
    sections.forEach((_, i) => {
      setTimeout(() => setVisibleCount(i + 1), i * 400)
    })
  }, [sections])

  const handleSubmit = async () => {
    const q = question.trim()
    if (!q || loading) return
    const token = await getToken()
    if (!token) return

    setLoading(true)
    setErrorMsg('')
    setResponse(null)
    setSections([])
    setVisibleCount(0)

    try {
      const res = await fetch(`${API_BASE}/api/analyst/query`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question: q,
          mode: selectedMode,
          session_id: sessionId,
        }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        setErrorMsg(err.detail ?? `Request failed (${res.status})`)
        return
      }

      const data: QueryResponse = await res.json()
      setResponse(data)
      setSessionId(data.session_id)
      setSections(parseSections(data.answer))

      setTrail((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          question: q,
          answer: data.answer,
          evidence_count: data.article_count,
          confidence: data.confidence,
          confidence_pct: data.confidence_pct,
          created_at: new Date().toISOString(),
        },
      ])
      setQuestion('')
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : 'Network error')
    } finally {
      setLoading(false)
    }
  }

  const handleNewInvestigation = async () => {
    const token = await getToken()
    if (!token) return
    try {
      const res = await fetch(`${API_BASE}/api/analyst/session/new`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const s = await res.json()
        setSessionId(s.session_id)
      }
    } catch {
      // ignore
    }
    setTrail([])
    setResponse(null)
    setSections([])
    setVisibleCount(0)
    setQuestion('')
    setErrorMsg('')
  }

  const handleFollowup = (q: string) => {
    setQuestion(q)
    inputRef.current?.focus()
  }

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#F7F4EF' }}>
      <Navigation />

      <main style={{ marginLeft: '200px', display: 'flex', height: '100vh' }}>
        {/* Left: investigation trail */}
        <aside
          style={{
            width: '260px',
            flexShrink: 0,
            borderRight: '1px solid #DDD8D0',
            backgroundColor: '#F0EDE8',
            display: 'flex',
            flexDirection: 'column',
            height: '100vh',
            position: 'sticky',
            top: 0,
          }}
        >
          <div
            style={{
              padding: '20px 16px 12px',
              borderBottom: '1px solid #DDD8D0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <div
              style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '10px',
                letterSpacing: '0.15em',
                textTransform: 'uppercase',
                color: '#9C928A',
              }}
            >
              Investigation Trail
            </div>
            <button
              onClick={handleNewInvestigation}
              style={{
                background: 'none',
                border: '1px solid #DDD8D0',
                borderRadius: '2px',
                padding: '3px 8px',
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '10px',
                color: '#5C5249',
                cursor: 'pointer',
              }}
            >
              New
            </button>
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
            {trail.length === 0 && (
              <div
                style={{
                  fontFamily: "'DM Sans', system-ui, sans-serif",
                  fontSize: '12px',
                  color: '#9C928A',
                  fontStyle: 'italic',
                  marginTop: '8px',
                }}
              >
                No questions yet
              </div>
            )}
            {trail.map((turn, i) => (
              <div key={turn.id} style={{ marginBottom: '14px' }}>
                <div
                  style={{
                    display: 'flex',
                    gap: '8px',
                    alignItems: 'flex-start',
                  }}
                >
                  <span
                    style={{
                      fontFamily: "'DM Mono', ui-monospace, monospace",
                      fontSize: '10px',
                      color: '#9C928A',
                      flexShrink: 0,
                      marginTop: '1px',
                    }}
                  >
                    {i + 1}.
                  </span>
                  <span
                    style={{
                      fontFamily: "'DM Sans', system-ui, sans-serif",
                      fontSize: '12px',
                      color: '#1A1614',
                      lineHeight: 1.4,
                    }}
                  >
                    {turn.question}
                  </span>
                </div>
                <div
                  style={{
                    marginLeft: '20px',
                    marginTop: '3px',
                    fontFamily: "'DM Mono', ui-monospace, monospace",
                    fontSize: '10px',
                    color: '#9C928A',
                  }}
                >
                  {turn.evidence_count} src · {turn.confidence}{turn.confidence_pct !== undefined ? ` (${turn.confidence_pct}%)` : ''}
                </div>
              </div>
            ))}
          </div>
        </aside>

        {/* Right: workspace */}
        <div
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            height: '100vh',
            overflow: 'hidden',
          }}
        >
          {/* Header */}
          <div
            style={{
              padding: '20px 32px 16px',
              borderBottom: '1px solid #DDD8D0',
              flexShrink: 0,
            }}
          >
            <div
              style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '11px',
                letterSpacing: '0.15em',
                textTransform: 'uppercase',
                color: '#9C928A',
              }}
            >
              Intelligence Analyst
            </div>
            <div
              style={{
                fontFamily: "'Playfair Display', Georgia, serif",
                fontSize: '22px',
                fontWeight: 700,
                color: '#1A1614',
                marginTop: '2px',
              }}
            >
              Ask an intelligence question
            </div>
          </div>

          {/* Scrollable content */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '24px 32px 120px' }}>
            {/* Suggestions */}
            {!response && !loading && suggestions.length > 0 && (
              <div style={{ marginBottom: '28px' }}>
                <div
                  style={{
                    fontFamily: "'DM Sans', system-ui, sans-serif",
                    fontSize: '10px',
                    letterSpacing: '0.12em',
                    textTransform: 'uppercase',
                    color: '#9C928A',
                    marginBottom: '10px',
                  }}
                >
                  Suggested investigations
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {suggestions.map((s, i) => (
                    <button
                      key={i}
                      onClick={() => handleFollowup(s)}
                      style={{
                        background: 'none',
                        border: '1px solid #DDD8D0',
                        borderRadius: '2px',
                        padding: '10px 14px',
                        fontFamily: "'DM Sans', system-ui, sans-serif",
                        fontSize: '13px',
                        color: '#1A1614',
                        cursor: 'pointer',
                        textAlign: 'left',
                      }}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Loading */}
            {loading && <LoadingState />}

            {/* Error */}
            {errorMsg && !loading && (
              <div
                style={{
                  padding: '16px',
                  backgroundColor: '#FDF0EF',
                  borderLeft: '3px solid #8B1A1A',
                  borderRadius: '0 2px 2px 0',
                  fontFamily: "'DM Sans', system-ui, sans-serif",
                  fontSize: '13px',
                  color: '#8B1A1A',
                }}
              >
                {errorMsg}
              </div>
            )}

            {/* Answer document */}
            {response && !loading && (
              <AnswerDocument
                sections={sections}
                visibleCount={visibleCount}
                articles={response.articles}
                mode={response.mode}
                confidence={response.confidence}
                confidence_pct={response.confidence_pct}
                retrieval_ms={response.retrieval_ms}
                article_count={response.article_count}
                followups={response.followups}
                onFollowup={handleFollowup}
                router={router}
              />
            )}
          </div>

          {/* Input bar — sticky at bottom */}
          <div
            style={{
              position: 'sticky',
              bottom: 0,
              backgroundColor: '#F7F4EF',
              borderTop: '1px solid #DDD8D0',
              padding: '16px 32px',
              flexShrink: 0,
            }}
          >
            {/* Mode selector */}
            <div style={{ display: 'flex', gap: '6px', marginBottom: '10px', flexWrap: 'wrap' }}>
              {VALID_MODES.map((m) => {
                const active = selectedMode === m
                return (
                  <button
                    key={m}
                    onClick={() => setSelectedMode(active ? '' : m)}
                    style={{
                      padding: '3px 8px',
                      border: `1px solid ${active ? '#1B3A6B' : '#DDD8D0'}`,
                      backgroundColor: active ? '#EEF3FA' : 'transparent',
                      fontFamily: "'DM Mono', ui-monospace, monospace",
                      fontSize: '10px',
                      letterSpacing: '0.08em',
                      color: active ? '#1B3A6B' : '#9C928A',
                      borderRadius: '2px',
                      cursor: 'pointer',
                    }}
                  >
                    {m}
                  </button>
                )
              })}
              {selectedMode && (
                <span
                  style={{
                    fontFamily: "'DM Sans', system-ui, sans-serif",
                    fontSize: '11px',
                    color: '#9C928A',
                    alignSelf: 'center',
                    marginLeft: '4px',
                  }}
                >
                  mode locked
                </span>
              )}
            </div>

            <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-end' }}>
              <textarea
                ref={inputRef}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    void handleSubmit()
                  }
                }}
                placeholder="Ask an intelligence question… (Enter to submit, Shift+Enter for newline)"
                rows={2}
                style={{
                  flex: 1,
                  padding: '10px 12px',
                  border: '1px solid #DDD8D0',
                  borderRadius: '2px',
                  backgroundColor: '#FFFFFF',
                  fontFamily: "'DM Sans', system-ui, sans-serif",
                  fontSize: '14px',
                  color: '#1A1614',
                  resize: 'none',
                  outline: 'none',
                  lineHeight: 1.5,
                }}
              />
              <button
                onClick={() => void handleSubmit()}
                disabled={loading || !question.trim()}
                style={{
                  padding: '10px 20px',
                  backgroundColor: loading || !question.trim() ? '#DDD8D0' : '#1B3A6B',
                  color: '#F7F4EF',
                  border: 'none',
                  borderRadius: '2px',
                  fontFamily: "'DM Sans', system-ui, sans-serif",
                  fontSize: '13px',
                  cursor: loading || !question.trim() ? 'default' : 'pointer',
                  flexShrink: 0,
                  alignSelf: 'stretch',
                }}
              >
                {loading ? '…' : 'Analyse'}
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
