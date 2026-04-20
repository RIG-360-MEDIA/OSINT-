'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import Navigation from '@/components/Navigation'

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
const LOADING_TEXTS = [
  'Searching intelligence corpus…',
  'Retrieving relevant articles…',
  'Building context window…',
  'Running analysis…',
  'Structuring assessment…',
]
const CIRCLED: Record<number, string> = { 1:'①',2:'②',3:'③',4:'④',5:'⑤',6:'⑥',7:'⑦',8:'⑧',9:'⑨',10:'⑩' }

const CONF_CONFIG: Record<string, { bg: string; text: string; border: string; dot: string }> = {
  HIGH:   { bg: '#ECFDF5', text: '#059669', border: '#D1FAE5', dot: '#10B981' },
  MEDIUM: { bg: '#FFFBEB', text: '#D97706', border: '#FEF3C7', dot: '#F59E0B' },
  LOW:    { bg: '#FFF1F2', text: '#E11D48', border: '#FFE4E6', dot: '#F43F5E' },
}

const MODE_CONFIG: Record<string, { color: string; bg: string }> = {
  SITUATION:  { color: '#2563EB', bg: '#EFF6FF' },
  OPPOSITION: { color: '#E11D48', bg: '#FFF1F2' },
  RISK:       { color: '#D97706', bg: '#FFFBEB' },
  POLICY:     { color: '#7C3AED', bg: '#EDE9FE' },
  PATTERN:    { color: '#059669', bg: '#ECFDF5' },
  BRIEF:      { color: '#18181B', bg: '#F1F5F9' },
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
            padding:            '0 2px',
            fontFamily:         "'DM Mono', monospace",
            fontSize:           '13px',
            color:              '#3B82F6',
            cursor:             'pointer',
            textDecoration:     'underline',
            textDecorationStyle:'dotted',
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
      gap:             '10px',
      padding:         '10px 14px',
      borderRadius:    '8px',
      backgroundColor: '#EFF6FF',
      border:          '1px solid #DBEAFE',
      borderLeft:      '3px solid #3B82F6',
    }}>
      <div style={{
        width: '22px', height: '22px', borderRadius: '50%',
        backgroundColor: '#DBEAFE', border: '1px solid #BFDBFE',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0,
        fontFamily: "'DM Mono', monospace", fontSize: '11px', color: '#3B82F6', fontWeight: 700,
      }}>
        {index + 1}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontFamily: "'DM Sans', system-ui", fontSize: '13px', fontWeight: 500, color: '#18181B', lineHeight: 1.4, marginBottom: '3px' }}>
          {article.title}
        </div>
        <div style={{ fontFamily: "'DM Sans', system-ui", fontSize: '11px', color: '#64748B' }}>
          {article.source_name}
          {article.topic_category && ` · ${article.topic_category}`}
          {article.geo_primary && ` · ${article.geo_primary}`}
        </div>
      </div>
      <button
        onClick={() => router.push(`/coverage?article=${article.article_id}`)}
        title="Open in Coverage Room"
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          padding: '3px 6px', borderRadius: '4px',
          fontFamily: "'DM Sans', system-ui", fontSize: '13px', color: '#3B82F6',
          transition: 'background 0.12s',
          flexShrink: 0,
        }}
        onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = 'rgba(59,130,246,0.1)' }}
        onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = 'none' }}
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
  const modeConf  = MODE_CONFIG[mode] ?? { color: '#64748B', bg: '#F1F5F9' }
  const confConf  = CONF_CONFIG[confidence] ?? { bg: '#F1F5F9', text: '#64748B', border: '#E2E8F0', dot: '#94A3B8' }

  return (
    <div className="anim-fade-up" style={{
      backgroundColor: '#FFFFFF',
      borderRadius:    '12px',
      border:          '1px solid #E2E8F0',
      boxShadow:       '0 4px 12px rgba(15,23,42,0.07)',
      overflow:        'hidden',
      marginBottom:    '24px',
    }}>
      {/* Header bar */}
      <div style={{
        padding:         '12px 20px',
        borderBottom:    '1px solid #F1F5F9',
        display:         'flex',
        alignItems:      'center',
        gap:             '10px',
        flexWrap:        'wrap',
        backgroundColor: '#FAFAFA',
      }}>
        {/* Mode badge */}
        <span style={{
          padding:         '3px 10px',
          borderRadius:    '9999px',
          backgroundColor: modeConf.bg,
          fontFamily:      "'DM Mono', monospace",
          fontSize:        '10px',
          fontWeight:      700,
          color:           modeConf.color,
          letterSpacing:   '0.08em',
        }}>{mode}</span>

        {/* Confidence */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '5px',
          padding: '3px 10px', borderRadius: '9999px',
          backgroundColor: confConf.bg, border: `1px solid ${confConf.border}`,
        }}>
          <div style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: confConf.dot }} />
          <span style={{ fontFamily: "'DM Mono', monospace", fontSize: '10px', fontWeight: 700, color: confConf.text, letterSpacing: '0.06em' }}>
            {confidence}{confidence_pct !== undefined ? ` ${confidence_pct}%` : ''}
          </span>
        </div>

        {/* Stats */}
        <span style={{ marginLeft: 'auto', fontFamily: "'DM Mono', monospace", fontSize: '11px', color: '#94A3B8' }}>
          {article_count} sources · {retrieval_ms}ms
        </span>
      </div>

      {/* Body */}
      <div style={{ padding: '24px 28px' }}>
        {sections.slice(0, visibleCount).map((section, i) => (
          <div key={i} className="anim-fade-up" style={{ marginBottom: '20px', animationDelay: `${i * 80}ms` }}>
            {section.header && (
              <div style={{
                fontFamily:    "'DM Mono', monospace",
                fontSize:      '10px',
                fontWeight:    700,
                textTransform: 'uppercase',
                letterSpacing: '0.14em',
                color:         '#94A3B8',
                marginBottom:  '8px',
                display:       'flex',
                alignItems:    'center',
                gap:           '8px',
              }}>
                <div style={{ flex: 1, height: '1px', backgroundColor: '#F1F5F9' }} />
                {section.header}
                <div style={{ flex: 1, height: '1px', backgroundColor: '#F1F5F9' }} />
              </div>
            )}
            <div style={{
              fontFamily:  "'DM Sans', system-ui",
              fontSize:    '15px',
              lineHeight:  1.8,
              color:       '#27272A',
              whiteSpace:  'pre-wrap',
            }}>
              {renderWithCitations(section.body, articles, setCitedArticle)}
            </div>
          </div>
        ))}

        {/* Cited article popover */}
        {citedArticle && (
          <div style={{
            marginBottom:    '16px',
            padding:         '12px 16px',
            borderRadius:    '8px',
            backgroundColor: '#EFF6FF',
            border:          '1px solid #DBEAFE',
            borderLeft:      '3px solid #3B82F6',
            display:         'flex',
            alignItems:      'center',
            gap:             '12px',
          }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontFamily: "'DM Sans', system-ui", fontSize: '13px', fontWeight: 600, color: '#18181B' }}>{citedArticle.title}</div>
              <div style={{ fontFamily: "'DM Sans', system-ui", fontSize: '11px', color: '#64748B', marginTop: '2px' }}>{citedArticle.source_name}</div>
            </div>
            <button
              onClick={() => router.push(`/coverage?article=${citedArticle.article_id}`)}
              style={{
                padding: '5px 12px', borderRadius: '6px',
                border: '1px solid #DBEAFE', background: '#FFFFFF',
                fontFamily: "'DM Sans', system-ui", fontSize: '12px', fontWeight: 500, color: '#3B82F6',
                cursor: 'pointer', flexShrink: 0,
              }}
            >Open →</button>
            <button onClick={() => setCitedArticle(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94A3B8', fontSize: '16px', flexShrink: 0 }}>×</button>
          </div>
        )}

        {/* Evidence panel */}
        {visibleCount >= sections.length && articles.length > 0 && (
          <div style={{ marginTop: '20px' }}>
            <button
              onClick={() => setShowEvidence(v => !v)}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                fontFamily: "'DM Sans', system-ui", fontSize: '13px', fontWeight: 500,
                color: '#3B82F6', display: 'flex', alignItems: 'center', gap: '6px',
                padding: 0,
              }}
            >
              <span>{showEvidence ? '▴' : '▾'}</span>
              {showEvidence ? 'Hide' : `Show ${articles.length} sources`}
            </button>
            {showEvidence && (
              <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {articles.map((a, i) => <EvidenceCard key={a.article_id} article={a} index={i} router={router} />)}
              </div>
            )}
          </div>
        )}

        {/* Follow-ups */}
        {visibleCount >= sections.length && followups.length > 0 && (
          <div style={{ marginTop: '20px', paddingTop: '20px', borderTop: '1px solid #F1F5F9' }}>
            <div style={{ fontFamily: "'DM Sans', system-ui", fontSize: '11px', fontWeight: 600, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '10px' }}>
              Suggested follow-ups
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {followups.map((q, i) => (
                <button
                  key={i}
                  onClick={() => onFollowup(q)}
                  style={{
                    background:   '#F8FAFC',
                    border:       '1px solid #E2E8F0',
                    borderRadius: '8px',
                    padding:      '10px 14px',
                    fontFamily:   "'DM Sans', system-ui",
                    fontSize:     '13px',
                    color:        '#334155',
                    cursor:       'pointer',
                    textAlign:    'left',
                    transition:   'all 0.15s',
                  }}
                  onMouseEnter={e => { const el = e.currentTarget; el.style.background = '#F1F5F9'; el.style.borderColor = '#CBD5E1' }}
                  onMouseLeave={e => { const el = e.currentTarget; el.style.background = '#F8FAFC'; el.style.borderColor = '#E2E8F0' }}
                >
                  ↳ {q}
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
      padding:         '28px 28px',
      backgroundColor: '#FFFFFF',
      borderRadius:    '12px',
      border:          '1px solid #E2E8F0',
      boxShadow:       '0 4px 12px rgba(15,23,42,0.06)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
        <div style={{ width: '18px', height: '18px', borderRadius: '50%', border: '2px solid #E2E8F0', borderTopColor: '#3B82F6', animation: 'spin 0.8s linear infinite', flexShrink: 0 }} />
        <span style={{ fontFamily: "'DM Sans', system-ui", fontSize: '14px', color: '#475569' }}>
          {LOADING_TEXTS[textIdx]}
        </span>
      </div>
      <div style={{ height: '4px', backgroundColor: '#F1F5F9', borderRadius: '4px', overflow: 'hidden' }}>
        <div style={{
          height: '100%', width: `${progress}%`,
          background: 'linear-gradient(90deg, #3B82F6, #60A5FA)',
          borderRadius: '4px',
          transition: 'width 150ms linear',
          boxShadow: '0 0 8px rgba(59,130,246,0.5)',
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
  const [trailOpen, setTrailOpen]           = useState(true)
  const [allSessions, setAllSessions]       = useState<Session[]>([])
  const [loadingSessions, setLoadingSessions] = useState(false)
  const [viewingSession, setViewingSession] = useState<Session | null>(null)

  const inputRef = useRef<HTMLTextAreaElement>(null)
  // Ref to latest handleSubmit — used by the URL-param auto-submit effect
  // to avoid stale closure issues with setTimeout.
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

  // Keep ref pointing to latest handleSubmit every render
  handleSubmitRef.current = handleSubmit

  // Pre-load question + session from URL params (from Story Threads → Investigate)
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
  }, []) // intentionally runs once on mount

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
    <div style={{ minHeight: '100vh', backgroundColor: '#F1F5F9' }}>
      <Navigation />

      <main style={{ paddingTop: '56px', display: 'flex', height: 'calc(100vh - 56px)' }}>

        {/* ── Investigation trail (left panel) ─────────────── */}
        <aside style={{
          width:           trailOpen ? '260px' : '48px',
          flexShrink:      0,
          backgroundColor: '#18181B',
          borderRight:     '1px solid rgba(255,255,255,0.07)',
          display:         'flex',
          flexDirection:   'column',
          height:          '100%',
          transition:      'width 0.25s cubic-bezier(0.16,1,0.3,1)',
          overflow:        'hidden',
        }}>
          {/* Trail header */}
          <div style={{
            padding:         trailOpen ? '16px 14px 12px' : '16px 10px 12px',
            borderBottom:    '1px solid rgba(255,255,255,0.07)',
            display:         'flex',
            alignItems:      'center',
            justifyContent:  'space-between',
            flexShrink:      0,
          }}>
            {trailOpen && (
              <span style={{ fontFamily: "'DM Mono', monospace", fontSize: '10px', color: '#64748B', letterSpacing: '0.12em', textTransform: 'uppercase' }}>
                Trail
              </span>
            )}
            <div style={{ display: 'flex', gap: '6px', marginLeft: trailOpen ? 0 : 'auto' }}>
              {trailOpen && (
                <button
                  onClick={handleNewInvestigation}
                  style={{
                    padding: '3px 8px', borderRadius: '5px',
                    border: '1px solid rgba(255,255,255,0.12)', background: 'none',
                    fontFamily: "'DM Sans', system-ui", fontSize: '10px', color: 'rgba(255,255,255,0.4)',
                    cursor: 'pointer', transition: 'all 0.15s',
                  }}
                  onMouseEnter={e => { const el = e.currentTarget; el.style.color = 'rgba(255,255,255,0.75)'; el.style.borderColor = 'rgba(255,255,255,0.25)' }}
                  onMouseLeave={e => { const el = e.currentTarget; el.style.color = 'rgba(255,255,255,0.4)'; el.style.borderColor = 'rgba(255,255,255,0.12)' }}
                >New</button>
              )}
              <button
                onClick={() => setTrailOpen(v => !v)}
                title={trailOpen ? 'Collapse' : 'Expand'}
                style={{
                  width: '26px', height: '26px', borderRadius: '6px',
                  border: '1px solid rgba(255,255,255,0.1)', background: 'none',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  cursor: 'pointer', color: 'rgba(255,255,255,0.35)',
                  fontSize: '11px', transition: 'all 0.15s',
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.color = 'rgba(255,255,255,0.7)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = 'rgba(255,255,255,0.35)' }}
              >
                {trailOpen ? '‹' : '›'}
              </button>
            </div>
          </div>

          {/* Trail items */}
          {trailOpen && (
            <div style={{ flex: 1, overflowY: 'auto', padding: '10px 12px' }}>
              {trail.length === 0 && !viewingSession && (
                <p style={{ fontFamily: "'DM Sans', system-ui", fontSize: '12px', color: '#334155', fontStyle: 'italic', marginTop: '8px' }}>
                  No questions yet
                </p>
              )}
              {trail.map((turn, i) => {
                const cc = CONF_CONFIG[turn.confidence]
                return (
                  <div key={turn.id} style={{ marginBottom: '12px', padding: '8px 10px', borderRadius: '7px', backgroundColor: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <div style={{ display: 'flex', gap: '7px', alignItems: 'flex-start' }}>
                      <span style={{ fontFamily: "'DM Mono', monospace", fontSize: '10px', color: '#F59E0B', flexShrink: 0, marginTop: '1px' }}>
                        {String(i + 1).padStart(2, '0')}
                      </span>
                      <span style={{ fontFamily: "'DM Sans', system-ui", fontSize: '12px', color: '#CBD5E1', lineHeight: 1.4 }}>
                        {turn.question}
                      </span>
                    </div>
                    <div style={{ marginTop: '5px', display: 'flex', alignItems: 'center', gap: '6px', paddingLeft: '19px' }}>
                      <div style={{ width: '5px', height: '5px', borderRadius: '50%', backgroundColor: cc?.dot ?? '#64748B', flexShrink: 0 }} />
                      <span style={{ fontFamily: "'DM Mono', monospace", fontSize: '9px', color: '#475569' }}>
                        {turn.evidence_count} src · {turn.confidence}
                        {turn.confidence_pct !== undefined ? ` ${turn.confidence_pct}%` : ''}
                      </span>
                    </div>
                  </div>
                )
              })}

              {/* Previous Investigations */}
              <div style={{ marginTop: '20px', paddingTop: '14px', borderTop: '1px solid rgba(255,255,255,0.07)' }}>
                <div style={{
                  fontFamily: "'DM Mono', monospace",
                  fontSize: '9px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.12em',
                  color: '#475569',
                  marginBottom: '8px',
                }}>
                  Previous Investigations
                </div>

                {loadingSessions && (
                  <div style={{ fontSize: '11px', color: '#475569', fontFamily: "'DM Sans', system-ui" }}>Loading…</div>
                )}

                {allSessions
                  .filter(s => s.session_id !== sessionId)
                  .slice(0, 10)
                  .map(session => (
                    <div
                      key={session.session_id}
                      onClick={() => void loadPastSession(session)}
                      style={{
                        padding: '7px 0',
                        borderBottom: '1px solid rgba(255,255,255,0.05)',
                        cursor: 'pointer',
                      }}
                      onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.opacity = '0.75' }}
                      onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.opacity = '1' }}
                    >
                      <div style={{
                        fontFamily: "'DM Sans', system-ui",
                        fontSize: '11px',
                        color: '#94A3B8',
                        lineHeight: 1.4,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        maxWidth: '210px',
                      }}>
                        {session.first_question?.slice(0, 55) ?? 'Untitled investigation'}
                      </div>
                      <div style={{
                        fontFamily: "'DM Mono', monospace",
                        fontSize: '9px',
                        color: '#334155',
                        marginTop: '2px',
                      }}>
                        {session.turn_count} q · {formatTimeAgo(session.last_activity)}
                      </div>
                    </div>
                  ))
                }

                {!loadingSessions && allSessions.filter(s => s.session_id !== sessionId).length === 0 && (
                  <div style={{ fontSize: '11px', color: '#334155', fontFamily: "'DM Sans', system-ui", fontStyle: 'italic' }}>
                    No previous investigations
                  </div>
                )}
              </div>
            </div>
          )}
        </aside>

        {/* ── Workspace (right area) ────────────────────────── */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
          {/* Page header */}
          <div style={{
            padding:         '16px 28px 14px',
            borderBottom:    '1px solid #E2E8F0',
            backgroundColor: '#FFFFFF',
            flexShrink:      0,
          }}>
            <div style={{ fontFamily: "'DM Mono', monospace", fontSize: '10px', color: '#94A3B8', letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: '3px' }}>
              Intelligence Analyst
            </div>
            <h1 style={{ fontFamily: "'DM Sans', system-ui", fontSize: '20px', fontWeight: 700, color: '#18181B', letterSpacing: '-0.02em' }}>
              Ask an intelligence question
            </h1>
          </div>

          {/* Scrollable workspace */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '24px 28px 0' }}>

            {/* Viewing past session banner */}
            {viewingSession && (
              <div style={{
                backgroundColor: '#EEF3FA',
                border: '1px solid #1B3A6B',
                borderRadius: '4px',
                padding: '10px 16px',
                marginBottom: '16px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}>
                <span style={{ fontFamily: "'DM Sans', system-ui", fontSize: '13px', color: '#1B3A6B' }}>
                  Viewing past investigation · {formatTimeAgo(viewingSession.last_activity)}
                </span>
                <button
                  onClick={handleNewInvestigation}
                  style={{
                    background: 'none', border: 'none',
                    fontFamily: "'DM Sans', system-ui", fontSize: '12px',
                    color: '#8B1A1A', cursor: 'pointer',
                  }}
                >
                  Return to current →
                </button>
              </div>
            )}

            {/* Suggestions */}
            {!response && !loading && suggestions.length > 0 && (
              <div className="anim-fade-up" style={{ marginBottom: '28px' }}>
                <div style={{ fontFamily: "'DM Sans', system-ui", fontSize: '11px', fontWeight: 600, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '10px' }}>
                  Suggested Investigations
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '7px' }}>
                  {suggestions.map((s, i) => (
                    <button
                      key={i}
                      onClick={() => handleFollowup(s)}
                      className="anim-fade-up"
                      style={{
                        background:   '#FFFFFF',
                        border:       '1px solid #E2E8F0',
                        borderRadius: '8px',
                        padding:      '12px 16px',
                        fontFamily:   "'DM Sans', system-ui",
                        fontSize:     '14px',
                        color:        '#334155',
                        cursor:       'pointer',
                        textAlign:    'left',
                        transition:   'all 0.15s',
                        animationDelay: `${i * 60}ms`,
                      }}
                      onMouseEnter={e => { const el = e.currentTarget; el.style.borderColor = '#CBD5E1'; el.style.background = '#F8FAFC' }}
                      onMouseLeave={e => { const el = e.currentTarget; el.style.borderColor = '#E2E8F0'; el.style.background = '#FFFFFF' }}
                    >
                      <span style={{ color: '#94A3B8', marginRight: '8px' }}>✦</span>{s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Loading */}
            {loading && <LoadingState />}

            {/* Error */}
            {errorMsg && !loading && (
              <div style={{
                padding:      '14px 18px',
                borderRadius: '8px',
                backgroundColor: '#FFF1F2',
                border:       '1px solid #FFE4E6',
                borderLeft:   '3px solid #F43F5E',
                fontFamily:   "'DM Sans', system-ui",
                fontSize:     '14px',
                color:        '#E11D48',
                marginBottom: '16px',
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

            {/* Spacer so content doesn't hide behind input bar */}
            <div style={{ height: '200px' }} />
          </div>

          {/* ── Input bar ──────────────────────────────────── */}
          <div style={{
            flexShrink:      0,
            backgroundColor: '#FFFFFF',
            borderTop:       '1px solid #E2E8F0',
            padding:         '14px 28px 20px',
          }}>
            {/* Mode selector */}
            <div style={{ display: 'flex', gap: '5px', marginBottom: '10px', flexWrap: 'wrap' }}>
              {VALID_MODES.map(m => {
                const active = selectedMode === m
                const mc = MODE_CONFIG[m] ?? { color: '#64748B', bg: '#F1F5F9' }
                return (
                  <button
                    key={m}
                    onClick={() => setSelectedMode(active ? '' : m)}
                    style={{
                      padding:         '4px 10px',
                      borderRadius:    '9999px',
                      border:          `1px solid ${active ? mc.color + '50' : '#E2E8F0'}`,
                      backgroundColor: active ? mc.bg : 'transparent',
                      fontFamily:      "'DM Mono', monospace",
                      fontSize:        '10px',
                      fontWeight:      700,
                      letterSpacing:   '0.08em',
                      color:           active ? mc.color : '#94A3B8',
                      cursor:          'pointer',
                      transition:      'all 0.15s',
                    }}
                  >{m}</button>
                )
              })}
              {selectedMode && (
                <span style={{ fontFamily: "'DM Sans', system-ui", fontSize: '11px', color: '#94A3B8', alignSelf: 'center', marginLeft: '4px' }}>
                  · mode locked
                </span>
              )}
            </div>

            <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-end' }}>
              <textarea
                ref={inputRef}
                value={question}
                onChange={e => setQuestion(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void handleSubmit() } }}
                placeholder="Ask an intelligence question… (Enter to submit, Shift+Enter for newline)"
                rows={2}
                style={{
                  flex:         1,
                  padding:      '11px 14px',
                  border:       '1.5px solid #E2E8F0',
                  borderRadius: '10px',
                  backgroundColor: '#F8FAFC',
                  fontFamily:   "'DM Sans', system-ui",
                  fontSize:     '14px',
                  color:        '#18181B',
                  resize:       'none',
                  outline:      'none',
                  lineHeight:   1.55,
                  transition:   'border-color 0.15s, box-shadow 0.15s',
                }}
                onFocus={e => { e.target.style.borderColor = '#3B82F6'; e.target.style.boxShadow = '0 0 0 3px rgba(59,130,246,0.12)' }}
                onBlur={e => { e.target.style.borderColor = '#E2E8F0'; e.target.style.boxShadow = 'none' }}
              />
              <button
                onClick={() => void handleSubmit()}
                disabled={loading || !question.trim()}
                style={{
                  padding:         '0 22px',
                  height:          '54px',
                  backgroundColor: loading || !question.trim() ? '#E2E8F0' : '#18181B',
                  color:           loading || !question.trim() ? '#94A3B8' : '#F8FAFC',
                  border:          'none',
                  borderRadius:    '10px',
                  fontFamily:      "'DM Sans', system-ui",
                  fontSize:        '14px',
                  fontWeight:      600,
                  cursor:          loading || !question.trim() ? 'not-allowed' : 'pointer',
                  flexShrink:      0,
                  transition:      'all 0.15s',
                  display:         'flex',
                  alignItems:      'center',
                  gap:             '6px',
                }}
                onMouseEnter={e => {
                  const el = e.currentTarget
                  if (!loading && question.trim()) el.style.backgroundColor = '#27272A'
                }}
                onMouseLeave={e => {
                  const el = e.currentTarget
                  if (!loading && question.trim()) el.style.backgroundColor = '#18181B'
                  else el.style.backgroundColor = '#E2E8F0'
                }}
              >
                {loading ? (
                  <div style={{ width: '16px', height: '16px', borderRadius: '50%', border: '2px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', animation: 'spin 0.8s linear infinite' }} />
                ) : 'Analyse →'}
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
