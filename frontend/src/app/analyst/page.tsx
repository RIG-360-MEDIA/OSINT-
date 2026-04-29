'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import Navigation from '@/components/Navigation'
import { Dateline } from '@/components/Dateline'
import DossierPanel from '@/components/dossier/DossierPanel'

const DOSSIER_ENABLED = process.env.NEXT_PUBLIC_DOSSIER_ENABLED === 'true'

// ── Types ──────────────────────────────────────────────────────────────────────

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

interface Section { header: string; body: string }

interface PastTurn {
  id: string
  question: string
  answer: string
  evidence_count: number
  confidence: string
  retrieval_ms: number
  created_at: string
}

interface Session {
  session_id: string
  first_question: string | null
  turn_count: number
  last_activity: string | null
  created_at: string
  turns?: PastTurn[]
}

function formatTimeAgo(iso: string | null | undefined): string {
  if (!iso) return 'unknown'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

const API_BASE  = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const VALID_MODES = ['SITUATION', 'OPPOSITION', 'RISK', 'POLICY', 'PATTERN', 'BRIEF']

const MODE_LABEL: Record<string, string> = {
  SITUATION:  'The situation',
  OPPOSITION: 'The opposition',
  RISK:       'The risk',
  POLICY:     'The policy',
  PATTERN:    'The pattern',
  BRIEF:      'The brief',
}

const LOADING_TEXTS = [
  'Pulling the corpus from the stacks…',
  'Gathering dispatches of record…',
  'Composing the context…',
  'Reading between the lines…',
  'Filing the assessment…',
]

const CIRCLED: Record<number, string> = { 1:'①',2:'②',3:'③',4:'④',5:'⑤',6:'⑥',7:'⑦',8:'⑧',9:'⑨',10:'⑩' }

const CONF_TONE: Record<string, 'gold' | 'copper' | 'alert'> = {
  HIGH:   'gold',
  MEDIUM: 'copper',
  LOW:    'alert',
}

const CONF_LABEL: Record<string, string> = {
  HIGH:   'On the record',
  MEDIUM: 'On balance',
  LOW:    'Off the record',
}

// ── Helpers ────────────────────────────────────────────────────────────────────

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
  return sections.filter(s => s.header || s.body.trim())
}

function renderWithCitations(
  text: string,
  articles: EvidenceArticle[],
  onCite: (a: EvidenceArticle) => void,
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
            display:            'inline',
            background:         'none',
            border:             'none',
            padding:            '0 3px',
            fontFamily:         "'Cormorant Garamond', serif",
            fontStyle:          'italic',
            fontSize:           '18px',
            color:              'var(--rig-gold)',
            cursor:             'pointer',
            verticalAlign:      'baseline',
          }}
        >{part}</button>
      )
    }
    return <span key={i}>{part}</span>
  })
}

// ── Evidence card ──────────────────────────────────────────────────────────────

function EvidenceCard({ article, index, router }: { article: EvidenceArticle; index: number; router: ReturnType<typeof useRouter> }) {
  return (
    <div style={{
      display:         'flex',
      alignItems:      'flex-start',
      gap:             '14px',
      padding:         '12px 16px',
      backgroundColor: 'var(--rig-paper-2)',
      border:          '1px solid var(--rig-rule-hair)',
      borderLeft:      '2px solid var(--rig-gold)',
    }}>
      <div style={{
        fontFamily: "'Cormorant Garamond', serif",
        fontStyle:  'italic',
        fontSize:   '22px',
        color:      'var(--rig-gold)',
        lineHeight: 1,
        flexShrink: 0,
        width:      '28px',
        textAlign:  'center',
      }}>
        {index + 1}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontFamily: "'Cormorant Garamond', serif",
          fontSize:   '17px',
          color:      'var(--rig-ink)',
          lineHeight: 1.35,
          marginBottom: '4px',
        }}>
          {article.title}
        </div>
        <div style={{
          fontFamily:    "'DM Mono', monospace",
          fontSize:      '10px',
          color:         'var(--rig-ink-3)',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
        }}>
          {article.source_name}
          {article.topic_category && ` · ${article.topic_category}`}
          {article.geo_primary && ` · ${article.geo_primary}`}
        </div>
      </div>
      <button
        onClick={() => router.push(`/coverage?article=${article.article_id}`)}
        title="Open in the Coverage Room"
        style={{
          background:  'none',
          border:      'none',
          cursor:      'pointer',
          padding:     '4px 8px',
          fontFamily:  "'Cormorant Garamond', serif",
          fontStyle:   'italic',
          fontSize:    '16px',
          color:       'var(--rig-gold)',
          flexShrink:  0,
        }}
      >→</button>
    </div>
  )
}

// ── Answer document ────────────────────────────────────────────────────────────

function AnswerDocument({
  sections, visibleCount, articles, mode, confidence, confidence_pct,
  retrieval_ms, article_count, followups, onFollowup, router,
}: {
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
}) {
  const [showEvidence, setShowEvidence]     = useState(false)
  const [citedArticle, setCitedArticle]     = useState<EvidenceArticle | null>(null)
  const confTone  = CONF_TONE[confidence] ?? 'copper'
  const modeLabel = MODE_LABEL[mode] ?? mode.toLowerCase()

  return (
    <div className="anim-fade-up" style={{
      backgroundColor: 'var(--rig-paper)',
      border:          '1px solid var(--rig-rule)',
      borderTop:       '3px solid var(--rig-ink)',
      marginBottom:    '32px',
    }}>
      {/* Masthead */}
      <div style={{
        padding:         '16px 28px 14px',
        borderBottom:    '1px solid var(--rig-rule-hair)',
        display:         'flex',
        alignItems:      'flex-end',
        justifyContent:  'space-between',
        gap:             '16px',
        flexWrap:        'wrap',
      }}>
        <div>
          <div style={{
            fontFamily:    "'DM Mono', monospace",
            fontSize:      '10px',
            textTransform: 'uppercase',
            letterSpacing: '0.14em',
            color:         'var(--rig-ink-3)',
            marginBottom:  '4px',
          }}>
            The assessment · {mode.toLowerCase()}
          </div>
          <div style={{
            fontFamily: "'Cormorant Garamond', serif",
            fontStyle:  'italic',
            fontSize:   '24px',
            color:      'var(--rig-ink)',
            lineHeight: 1.1,
          }}>
            {modeLabel}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <span className="rig-chip" data-tone={confTone}>
            {CONF_LABEL[confidence] ?? confidence}
            {confidence_pct !== undefined ? ` · ${confidence_pct}%` : ''}
          </span>
          <span style={{
            fontFamily:    "'DM Mono', monospace",
            fontSize:      '10px',
            textTransform: 'uppercase',
            letterSpacing: '0.1em',
            color:         'var(--rig-ink-3)',
          }}>
            {article_count} dispatches · {retrieval_ms}ms
          </span>
        </div>
      </div>

      {/* Body */}
      <div style={{ padding: '28px 32px' }}>
        {sections.slice(0, visibleCount).map((section, i) => (
          <div key={i} className="anim-fade-up" style={{ marginBottom: '26px', animationDelay: `${i * 80}ms` }}>
            {section.header && (
              <div style={{
                display:       'flex',
                alignItems:    'center',
                gap:           '12px',
                marginBottom:  '12px',
              }}>
                <span style={{
                  fontFamily:    "'DM Mono', monospace",
                  fontSize:      '10px',
                  fontWeight:    700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.14em',
                  color:         'var(--rig-gold)',
                  flexShrink:    0,
                }}>
                  § {String(i + 1).padStart(2, '0')}
                </span>
                <span style={{
                  fontFamily: "'Cormorant Garamond', serif",
                  fontStyle:  'italic',
                  fontSize:   '20px',
                  color:      'var(--rig-ink)',
                }}>
                  {section.header}
                </span>
                <div style={{ flex: 1, height: '1px', backgroundColor: 'var(--rig-rule-hair)' }} />
              </div>
            )}
            <div style={{
              fontFamily:  "'Cormorant Garamond', serif",
              fontSize:    '18px',
              lineHeight:  1.65,
              color:       'var(--rig-ink-2)',
              whiteSpace:  'pre-wrap',
            }}>
              {renderWithCitations(section.body, articles, setCitedArticle)}
            </div>
          </div>
        ))}

        {/* Cited article popover */}
        {citedArticle && (
          <div style={{
            marginBottom:    '20px',
            padding:         '14px 18px',
            backgroundColor: 'var(--rig-paper-2)',
            border:          '1px solid var(--rig-rule-hair)',
            borderLeft:      '2px solid var(--rig-gold)',
            display:         'flex',
            alignItems:      'center',
            gap:             '14px',
          }}>
            <div style={{ flex: 1 }}>
              <div style={{
                fontFamily: "'Cormorant Garamond', serif",
                fontSize:   '18px',
                color:      'var(--rig-ink)',
                lineHeight: 1.3,
              }}>{citedArticle.title}</div>
              <div style={{
                fontFamily:    "'DM Mono', monospace",
                fontSize:      '10px',
                color:         'var(--rig-ink-3)',
                marginTop:     '4px',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
              }}>{citedArticle.source_name}</div>
            </div>
            <button
              onClick={() => router.push(`/coverage?article=${citedArticle.article_id}`)}
              className="rig-btn-ghost"
              style={{ flexShrink: 0 }}
            >Open →</button>
            <button
              onClick={() => setCitedArticle(null)}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--rig-ink-3)', fontSize: '18px', flexShrink: 0,
              }}
            >×</button>
          </div>
        )}

        {/* Evidence panel */}
        {visibleCount >= sections.length && articles.length > 0 && (
          <div style={{ marginTop: '24px' }}>
            <button
              onClick={() => setShowEvidence(v => !v)}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                fontFamily: "'DM Mono', monospace", fontSize: '11px',
                textTransform: 'uppercase', letterSpacing: '0.1em',
                color: 'var(--rig-gold)', display: 'flex', alignItems: 'center', gap: '8px',
                padding: 0,
              }}
            >
              <span>{showEvidence ? '▴' : '▾'}</span>
              {showEvidence ? 'Close the references' : `Consult the ${articles.length} references`}
            </button>
            {showEvidence && (
              <div style={{ marginTop: '14px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {articles.map((a, i) => <EvidenceCard key={a.article_id} article={a} index={i} router={router} />)}
              </div>
            )}
          </div>
        )}

        {/* Follow-ups */}
        {visibleCount >= sections.length && followups.length > 0 && (
          <div style={{ marginTop: '28px', paddingTop: '24px', borderTop: '1px solid var(--rig-rule-hair)' }}>
            <div style={{
              fontFamily:    "'DM Mono', monospace",
              fontSize:      '10px',
              fontWeight:    700,
              color:         'var(--rig-ink-3)',
              textTransform: 'uppercase',
              letterSpacing: '0.14em',
              marginBottom:  '14px',
            }}>
              Lines of further inquiry
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {followups.map((q, i) => (
                <button
                  key={i}
                  onClick={() => onFollowup(q)}
                  style={{
                    background:   'var(--rig-paper-2)',
                    border:       '1px solid var(--rig-rule-hair)',
                    padding:      '12px 16px',
                    fontFamily:   "'Cormorant Garamond', serif",
                    fontSize:     '17px',
                    fontStyle:    'italic',
                    color:        'var(--rig-ink-2)',
                    cursor:       'pointer',
                    textAlign:    'left',
                    transition:   'all 0.15s',
                  }}
                  onMouseEnter={e => { const el = e.currentTarget; el.style.borderColor = 'var(--rig-gold)'; el.style.color = 'var(--rig-ink)' }}
                  onMouseLeave={e => { const el = e.currentTarget; el.style.borderColor = 'var(--rig-rule-hair)'; el.style.color = 'var(--rig-ink-2)' }}
                >
                  <span style={{ color: 'var(--rig-gold)', marginRight: '8px' }}>↳</span>{q}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Loading state ──────────────────────────────────────────────────────────────

function LoadingState() {
  const [textIdx, setTextIdx]   = useState(0)
  const [progress, setProgress] = useState(3)

  useEffect(() => {
    const t1 = setInterval(() => setTextIdx(i => (i + 1) % LOADING_TEXTS.length), 1800)
    const t2 = setInterval(() => setProgress(p => Math.min(p + 1.5, 88)), 150)
    return () => { clearInterval(t1); clearInterval(t2) }
  }, [])

  return (
    <div style={{
      padding:         '28px 32px',
      backgroundColor: 'var(--rig-paper)',
      border:          '1px solid var(--rig-rule)',
      borderTop:       '3px solid var(--rig-gold)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '16px' }}>
        <div style={{
          width: '18px', height: '18px', borderRadius: '50%',
          border: '2px solid var(--rig-rule-hair)', borderTopColor: 'var(--rig-gold)',
          animation: 'spin 0.8s linear infinite', flexShrink: 0,
        }} />
        <span style={{
          fontFamily: "'Cormorant Garamond', serif",
          fontStyle:  'italic',
          fontSize:   '18px',
          color:      'var(--rig-ink-2)',
        }}>
          {LOADING_TEXTS[textIdx]}
        </span>
      </div>
      <div style={{ height: '2px', backgroundColor: 'var(--rig-rule-hair)', overflow: 'hidden' }}>
        <div style={{
          height: '100%', width: `${progress}%`,
          backgroundColor: 'var(--rig-gold)',
          transition: 'width 150ms linear',
        }} />
      </div>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function AnalystPage() {
  const router = useRouter()

  const getToken = useCallback(async (): Promise<string | null> => {
    const supabase = createClient()
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) { router.push('/login'); return null }
    return session.access_token
  }, [router])

  const [sessionId, setSessionId]           = useState('')
  const [question, setQuestion]             = useState('')
  const [loading, setLoading]               = useState(false)
  const [errorMsg, setErrorMsg]             = useState('')
  const [response, setResponse]             = useState<QueryResponse | null>(null)
  const [sections, setSections]             = useState<Section[]>([])
  const [visibleCount, setVisibleCount]     = useState(0)
  const [trail, setTrail]                   = useState<Turn[]>([])
  const [suggestions, setSuggestions]       = useState<string[]>([])
  const [selectedMode, setSelectedMode]     = useState('')
  const [dossierOpen, setDossierOpen]       = useState(false)
  const [trailOpen, setTrailOpen]           = useState(true)
  const [allSessions, setAllSessions]       = useState<Session[]>([])
  const [loadingSessions, setLoadingSessions] = useState(false)
  const [viewingSession, setViewingSession] = useState<Session | null>(null)

  const inputRef = useRef<HTMLTextAreaElement>(null)
  const handleSubmitRef = useRef<((q?: string) => Promise<void>) | null>(null)

  const fetchAllSessions = async (token: string) => {
    setLoadingSessions(true)
    try {
      const res = await fetch(`${API_BASE}/api/analyst/sessions`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setAllSessions(data.sessions ?? [])
      }
    } catch { /* silent */ } finally {
      setLoadingSessions(false)
    }
  }

  const loadPastSession = async (session: Session) => {
    const token = await getToken()
    if (!token) return
    try {
      const res = await fetch(
        `${API_BASE}/api/analyst/sessions/${session.session_id}`,
        { headers: { Authorization: `Bearer ${token}` } },
      )
      if (res.ok) {
        const data = await res.json()
        const pastTurns: Turn[] = (data.turns as PastTurn[]).map(t => ({
          id: t.id,
          question: t.question,
          answer: t.answer,
          evidence_count: t.evidence_count,
          confidence: t.confidence ?? 'MEDIUM',
          confidence_pct: undefined,
          created_at: t.created_at,
        }))
        setTrail(pastTurns)
        setViewingSession({ ...session, turns: data.turns })
        setSessionId(session.session_id)
        setResponse(null)
        setSections([])
        setVisibleCount(0)
      }
    } catch (e) {
      console.error('Failed to load past session:', e)
    }
  }

  useEffect(() => {
    const boot = async () => {
      const token = await getToken()
      if (!token) return
      try {
        const [sessRes, ctxRes] = await Promise.all([
          fetch(`${API_BASE}/api/analyst/session`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API_BASE}/api/analyst/context`, { headers: { Authorization: `Bearer ${token}` } }),
        ])
        if (sessRes.ok) { const s = await sessRes.json(); setSessionId(s.session_id); if (s.turns?.length) setTrail(s.turns) }
        if (ctxRes.ok)  { const c = await ctxRes.json(); setSuggestions(c.suggestions ?? []) }
      } catch { /* ignore */ }
      await fetchAllSessions(token)
    }
    void boot()
    // eslint-disable-next-line
  }, [])

  useEffect(() => {
    if (!sections.length) return
    setVisibleCount(0)
    sections.forEach((_, i) => setTimeout(() => setVisibleCount(i + 1), i * 400))
  }, [sections])

  const handleSubmit = async (overrideQ?: string) => {
    const q = (overrideQ ?? question).trim()
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
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, mode: selectedMode, session_id: sessionId }),
      })
      if (!res.ok) { const err = await res.json().catch(() => ({})); setErrorMsg(err.detail ?? `Request failed (${res.status})`); return }
      const data: QueryResponse = await res.json()
      setResponse(data)
      setSessionId(data.session_id)
      setSections(parseSections(data.answer))
      setTrail(prev => [...prev, {
        id: Date.now().toString(), question: q, answer: data.answer,
        evidence_count: data.article_count, confidence: data.confidence,
        confidence_pct: data.confidence_pct, created_at: new Date().toISOString(),
      }])
      setQuestion('')
      const refreshToken = await getToken()
      if (refreshToken) void fetchAllSessions(refreshToken)
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : 'Network error')
    } finally { setLoading(false) }
  }

  handleSubmitRef.current = handleSubmit

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const questionParam = params.get('question')
    const sessionParam  = params.get('session')
    if (!questionParam) return
    const decoded = decodeURIComponent(questionParam)
    setQuestion(decoded)
    if (sessionParam) setSessionId(sessionParam)
    const timer = setTimeout(() => {
      handleSubmitRef.current?.(decoded)
    }, 700)
    return () => clearTimeout(timer)
  }, [])

  const handleNewInvestigation = async () => {
    const token = await getToken()
    if (!token) return
    if (viewingSession) {
      setViewingSession(null)
      try {
        const res = await fetch(`${API_BASE}/api/analyst/session`, { headers: { Authorization: `Bearer ${token}` } })
        if (res.ok) { const s = await res.json(); setSessionId(s.session_id); setTrail(s.turns ?? []) }
      } catch { /* ignore */ }
      setResponse(null); setSections([]); setVisibleCount(0); setQuestion(''); setErrorMsg('')
      return
    }
    try {
      const res = await fetch(`${API_BASE}/api/analyst/session/new`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
      if (res.ok) { const s = await res.json(); setSessionId(s.session_id) }
    } catch { /* ignore */ }
    setTrail([]); setResponse(null); setSections([]); setVisibleCount(0); setQuestion(''); setErrorMsg('')
  }

  const handleFollowup = (q: string) => { setQuestion(q); inputRef.current?.focus() }

  return (
    <div style={{
      height:          '100vh',
      display:         'flex',
      flexDirection:   'column',
      backgroundColor: 'var(--rig-paper-2)',
      overflow:        'hidden',
    }}>
      <Navigation />
      <div style={{ height: '56px', flexShrink: 0 }} aria-hidden />

      <main style={{
        flex:     1,
        display:  'flex',
        minHeight: 0,
      }}>

        {/* ── Trail (left panel) ─────────────── */}
        <aside style={{
          width:           trailOpen ? '300px' : '52px',
          flexShrink:      0,
          backgroundColor: 'var(--rig-ink)',
          color:           'var(--rig-paper)',
          borderRight:     '1px solid var(--rig-rule)',
          display:         'flex',
          flexDirection:   'column',
          height:          '100%',
          transition:      'width 0.25s cubic-bezier(0.16,1,0.3,1)',
          overflow:        'hidden',
        }}>
          {/* Trail header */}
          <div style={{
            padding:         trailOpen ? '20px 18px 16px' : '20px 12px 16px',
            borderBottom:    '1px solid rgba(255,255,255,0.08)',
            flexShrink:      0,
          }}>
            {trailOpen ? (
              <>
                <div style={{
                  display:        'flex',
                  alignItems:     'center',
                  justifyContent: 'space-between',
                  marginBottom:   '10px',
                }}>
                  <span style={{
                    fontFamily:    "'DM Mono', monospace",
                    fontSize:      '9px',
                    color:         'rgba(212,175,55,0.85)',
                    letterSpacing: '0.2em',
                    textTransform: 'uppercase',
                  }}>
                    The Trail
                  </span>
                  <button
                    onClick={() => setTrailOpen(false)}
                    title="Collapse"
                    style={{
                      width: '24px', height: '24px',
                      border: '1px solid rgba(255,255,255,0.15)',
                      background: 'none',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      cursor: 'pointer', color: 'rgba(255,255,255,0.55)',
                      fontSize: '12px',
                    }}
                  >‹</button>
                </div>
                <div style={{
                  fontFamily: "'Cormorant Garamond', serif",
                  fontStyle:  'italic',
                  fontSize:   '22px',
                  color:      'var(--rig-paper)',
                  lineHeight: 1.1,
                  marginBottom: '12px',
                }}>
                  Lines of inquiry
                </div>
                <button
                  onClick={handleNewInvestigation}
                  style={{
                    display:        'inline-flex',
                    alignItems:     'center',
                    gap:            '6px',
                    padding:        '5px 12px',
                    border:         '1px solid rgba(212,175,55,0.35)',
                    background:     'none',
                    fontFamily:     "'DM Mono', monospace",
                    fontSize:       '10px',
                    textTransform:  'uppercase',
                    letterSpacing:  '0.14em',
                    color:          'var(--rig-gold)',
                    cursor:         'pointer',
                    transition:     'all 0.15s',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'rgba(212,175,55,0.08)' }}
                  onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent' }}
                >
                  + Open a new file
                </button>
              </>
            ) : (
              <button
                onClick={() => setTrailOpen(true)}
                title="Expand"
                style={{
                  width: '28px', height: '28px',
                  border: '1px solid rgba(255,255,255,0.15)',
                  background: 'none',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  cursor: 'pointer', color: 'rgba(255,255,255,0.55)',
                  fontSize: '13px',
                  margin: '0 auto',
                }}
              >›</button>
            )}
          </div>

          {/* Trail items */}
          {trailOpen && (
            <div style={{ flex: 1, overflowY: 'auto', padding: '14px 14px' }}>
              {trail.length === 0 && !viewingSession && (
                <p style={{
                  fontFamily: "'Cormorant Garamond', serif",
                  fontStyle: 'italic',
                  fontSize: '15px',
                  color: 'rgba(255,255,255,0.4)',
                  marginTop: '8px',
                  lineHeight: 1.4,
                }}>
                  The file is empty. Put your question to the room.
                </p>
              )}
              {trail.map((turn, i) => (
                <div key={turn.id} style={{
                  marginBottom: '14px',
                  padding: '10px 12px',
                  backgroundColor: 'rgba(255,255,255,0.03)',
                  borderLeft: '2px solid rgba(212,175,55,0.5)',
                }}>
                  <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
                    <span style={{
                      fontFamily: "'Cormorant Garamond', serif",
                      fontStyle: 'italic',
                      fontSize: '18px',
                      color: 'var(--rig-gold)',
                      flexShrink: 0,
                      lineHeight: 1,
                      marginTop: '2px',
                    }}>
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <span style={{
                      fontFamily: "'Cormorant Garamond', serif",
                      fontSize: '15px',
                      color: 'rgba(255,255,255,0.88)',
                      lineHeight: 1.35,
                    }}>
                      {turn.question}
                    </span>
                  </div>
                  <div style={{
                    marginTop: '6px',
                    paddingLeft: '26px',
                    fontFamily: "'DM Mono', monospace",
                    fontSize: '9px',
                    color: 'rgba(255,255,255,0.4)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                  }}>
                    {turn.evidence_count} src · {turn.confidence}
                    {turn.confidence_pct !== undefined ? ` ${turn.confidence_pct}%` : ''}
                  </div>
                </div>
              ))}

              {/* Previous Investigations */}
              <div style={{ marginTop: '24px', paddingTop: '16px', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                <div style={{
                  fontFamily: "'DM Mono', monospace",
                  fontSize: '9px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.14em',
                  color: 'rgba(212,175,55,0.7)',
                  marginBottom: '10px',
                }}>
                  From the archive
                </div>

                {loadingSessions && (
                  <div style={{
                    fontFamily: "'Cormorant Garamond', serif",
                    fontStyle: 'italic',
                    fontSize: '14px',
                    color: 'rgba(255,255,255,0.4)',
                  }}>Pulling the files…</div>
                )}

                {allSessions
                  .filter(s => s.session_id !== sessionId)
                  .slice(0, 10)
                  .map(session => (
                    <div
                      key={session.session_id}
                      onClick={() => void loadPastSession(session)}
                      style={{
                        padding: '9px 0',
                        borderBottom: '1px solid rgba(255,255,255,0.06)',
                        cursor: 'pointer',
                        transition: 'opacity 0.15s',
                      }}
                      onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.opacity = '0.7' }}
                      onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.opacity = '1' }}
                    >
                      <div style={{
                        fontFamily: "'Cormorant Garamond', serif",
                        fontSize: '14px',
                        color: 'rgba(255,255,255,0.75)',
                        lineHeight: 1.35,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        maxWidth: '230px',
                      }}>
                        {session.first_question?.slice(0, 55) ?? 'Untitled investigation'}
                      </div>
                      <div style={{
                        fontFamily: "'DM Mono', monospace",
                        fontSize: '9px',
                        color: 'rgba(255,255,255,0.35)',
                        textTransform: 'uppercase',
                        letterSpacing: '0.08em',
                        marginTop: '3px',
                      }}>
                        {session.turn_count} q · {formatTimeAgo(session.last_activity)}
                      </div>
                    </div>
                  ))
                }

                {!loadingSessions && allSessions.filter(s => s.session_id !== sessionId).length === 0 && (
                  <div style={{
                    fontFamily: "'Cormorant Garamond', serif",
                    fontStyle: 'italic',
                    fontSize: '14px',
                    color: 'rgba(255,255,255,0.35)',
                  }}>
                    No files on record
                  </div>
                )}
              </div>
            </div>
          )}
        </aside>

        {/* ── Workspace (right area) ────────────────────────── */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
          {/* Page masthead */}
          <div style={{
            padding:         '18px 40px 16px',
            borderBottom:    '2px solid var(--rig-ink)',
            backgroundColor: 'var(--rig-paper)',
            flexShrink:      0,
            display:         'flex',
            alignItems:      'center',
            justifyContent:  'space-between',
            gap:             '24px',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px', minWidth: 0, flex: 1 }}>
              <span style={{
                fontFamily:    "'DM Mono', monospace",
                fontSize:      '10px',
                color:         'var(--rig-gold)',
                letterSpacing: '0.2em',
                textTransform: 'uppercase',
                whiteSpace:    'nowrap',
                flexShrink:    0,
              }}>
                Edition VII
              </span>
              <span style={{ width: '24px', height: '1px', backgroundColor: 'var(--rig-gold)', flexShrink: 0 }} />
              <h1 style={{
                fontFamily:    "'Cormorant Garamond', serif",
                fontSize:      '26px',
                fontWeight:    400,
                color:         'var(--rig-ink)',
                letterSpacing: '-0.01em',
                lineHeight:    1.2,
                overflow:      'hidden',
                textOverflow:  'ellipsis',
                whiteSpace:    'nowrap',
                margin:        0,
              }}>
                Chat System
                <span style={{
                  fontStyle:  'italic',
                  color:      'var(--rig-ink-3)',
                  fontSize:   '20px',
                  marginLeft: '12px',
                }}>
                  put the question to the corpus
                </span>
              </h1>
            </div>
            <div style={{
              fontFamily:    "'DM Mono', monospace",
              fontSize:      '10px',
              color:         'var(--rig-ink-3)',
              letterSpacing: '0.14em',
              textTransform: 'uppercase',
              flexShrink:    0,
              whiteSpace:    'nowrap',
            }}>
              {trail.length} {trail.length === 1 ? 'file' : 'files'} on desk
            </div>
          </div>

          {/* Scrollable workspace */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '28px 36px 0' }}>

            {/* Viewing past session banner */}
            {viewingSession && (
              <div style={{
                backgroundColor: 'var(--rig-paper)',
                border: '1px solid var(--rig-rule)',
                borderLeft: '3px solid var(--rig-copper)',
                padding: '12px 18px',
                marginBottom: '20px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}>
                <div>
                  <div style={{
                    fontFamily: "'DM Mono', monospace",
                    fontSize: '10px',
                    textTransform: 'uppercase',
                    letterSpacing: '0.12em',
                    color: 'var(--rig-ink-3)',
                  }}>
                    From the archive
                  </div>
                  <div style={{
                    fontFamily: "'Cormorant Garamond', serif",
                    fontStyle: 'italic',
                    fontSize: '17px',
                    color: 'var(--rig-ink)',
                    marginTop: '2px',
                  }}>
                    Filed {formatTimeAgo(viewingSession.last_activity)}
                  </div>
                </div>
                <button
                  onClick={handleNewInvestigation}
                  style={{
                    background: 'none', border: 'none',
                    fontFamily: "'Cormorant Garamond', serif",
                    fontStyle: 'italic',
                    fontSize: '15px',
                    color: 'var(--rig-copper)',
                    cursor: 'pointer',
                  }}
                >
                  Return to the desk →
                </button>
              </div>
            )}

            {/* Suggestions */}
            {!response && !loading && suggestions.length > 0 && (
              <div className="anim-fade-up" style={{ marginBottom: '32px' }}>
                <div style={{
                  fontFamily:    "'DM Mono', monospace",
                  fontSize:      '10px',
                  fontWeight:    700,
                  color:         'var(--rig-gold)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.14em',
                  marginBottom:  '12px',
                }}>
                  The desk suggests
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {suggestions.map((s, i) => (
                    <button
                      key={i}
                      onClick={() => handleFollowup(s)}
                      className="anim-fade-up"
                      style={{
                        background:     'var(--rig-paper)',
                        border:         '1px solid var(--rig-rule-hair)',
                        padding:        '14px 18px',
                        fontFamily:     "'Cormorant Garamond', serif",
                        fontSize:       '18px',
                        fontStyle:      'italic',
                        color:          'var(--rig-ink-2)',
                        cursor:         'pointer',
                        textAlign:      'left',
                        transition:     'all 0.15s',
                        animationDelay: `${i * 60}ms`,
                        lineHeight:     1.35,
                      }}
                      onMouseEnter={e => { const el = e.currentTarget; el.style.borderColor = 'var(--rig-gold)'; el.style.color = 'var(--rig-ink)' }}
                      onMouseLeave={e => { const el = e.currentTarget; el.style.borderColor = 'var(--rig-rule-hair)'; el.style.color = 'var(--rig-ink-2)' }}
                    >
                      <span style={{ color: 'var(--rig-gold)', marginRight: '10px' }}>✦</span>{s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Dossier panel — flag-gated, self-contained */}
            {DOSSIER_ENABLED && dossierOpen && (
              <DossierPanel onClose={() => setDossierOpen(false)} />
            )}

            {/* Loading */}
            {loading && <LoadingState />}

            {/* Error */}
            {errorMsg && !loading && (
              <div style={{
                padding:      '14px 20px',
                backgroundColor: 'var(--rig-paper)',
                border:       '1px solid var(--rig-rule)',
                borderLeft:   '3px solid var(--rig-oxblood)',
                fontFamily:   "'Cormorant Garamond', serif",
                fontSize:     '17px',
                fontStyle:    'italic',
                color:        'var(--rig-oxblood)',
                marginBottom: '20px',
              }}>{errorMsg}</div>
            )}

            {/* Answer */}
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

            <div style={{ height: '200px' }} />
          </div>

          {/* ── Input bar ──────────────────────────────────── */}
          <div style={{
            flexShrink:      0,
            backgroundColor: 'var(--rig-paper)',
            borderTop:       '1px solid var(--rig-rule)',
            padding:         '16px 36px 22px',
          }}>
            {/* Mode selector */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px', flexWrap: 'wrap' }}>
              <span style={{
                fontFamily:    "'DM Mono', monospace",
                fontSize:      '10px',
                textTransform: 'uppercase',
                letterSpacing: '0.12em',
                color:         'var(--rig-ink-3)',
              }}>
                Mode of enquiry ·
              </span>
              {VALID_MODES.map(m => {
                const active = selectedMode === m
                return (
                  <button
                    key={m}
                    onClick={() => setSelectedMode(active ? '' : m)}
                    style={{
                      padding:         '4px 12px',
                      border:          `1px solid ${active ? 'var(--rig-gold)' : 'var(--rig-rule)'}`,
                      backgroundColor: active ? 'color-mix(in srgb, var(--rig-gold) 10%, transparent)' : 'transparent',
                      fontFamily:      "'DM Mono', monospace",
                      fontSize:        '10px',
                      fontWeight:      700,
                      letterSpacing:   '0.1em',
                      color:           active ? 'var(--rig-gold)' : 'var(--rig-ink-3)',
                      cursor:          'pointer',
                      transition:      'all 0.15s',
                    }}
                  >{m}</button>
                )
              })}
              {selectedMode && (
                <span style={{
                  fontFamily: "'Cormorant Garamond', serif",
                  fontStyle: 'italic',
                  fontSize: '14px',
                  color: 'var(--rig-ink-3)',
                }}>
                  locked
                </span>
              )}
              {DOSSIER_ENABLED && (
                <button
                  onClick={() => setDossierOpen(v => !v)}
                  style={{
                    marginLeft:      'auto',
                    background:      'transparent',
                    padding:         '4px 12px',
                    border:          `1px solid ${dossierOpen ? 'var(--rig-gold)' : 'var(--rig-rule)'}`,
                    fontFamily:      "'DM Mono', monospace",
                    fontSize:        '10px',
                    fontWeight:      700,
                    letterSpacing:   '0.1em',
                    color:           dossierOpen ? 'var(--rig-gold)' : 'var(--rig-ink-3)',
                    cursor:          'pointer',
                    textTransform:   'uppercase',
                  }}
                >
                  {dossierOpen ? 'Close dossier' : 'Dossier'}
                </button>
              )}
            </div>

            <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-end' }}>
              <textarea
                ref={inputRef}
                value={question}
                onChange={e => setQuestion(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void handleSubmit() } }}
                placeholder="Put a question to the desk…   ·   Enter files · Shift+Enter drops a line"
                rows={1}
                className="rig-input"
                style={{
                  flex:         1,
                  fontFamily:   "'Cormorant Garamond', serif",
                  fontSize:     '16px',
                  resize:       'none',
                  lineHeight:   1.45,
                  minHeight:    '40px',
                  padding:      '9px 14px',
                }}
              />
              <button
                onClick={() => void handleSubmit()}
                disabled={loading || !question.trim()}
                className="rig-btn-primary"
                style={{
                  padding:         '0 18px',
                  height:          '40px',
                  cursor:          loading || !question.trim() ? 'not-allowed' : 'pointer',
                  opacity:         loading || !question.trim() ? 0.5 : 1,
                  flexShrink:      0,
                  display:         'flex',
                  alignItems:      'center',
                  gap:             '8px',
                  fontFamily:      "'Cormorant Garamond', serif",
                  fontStyle:       'italic',
                  fontSize:        '15px',
                  whiteSpace:      'nowrap',
                }}
              >
                {loading ? (
                  <div style={{ width: '14px', height: '14px', borderRadius: '50%', border: '2px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', animation: 'spin 0.8s linear infinite' }} />
                ) : 'File →'}
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
