'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'

// ── Types ─────────────────────────────────────────────────────────────────────

type PageState = 'loading_check' | 'no_brief' | 'generating' | 'showing_brief' | 'error'

interface BriefMeta {
  briefDate: string
  articlesUsed: number
  generatedAt: string
}

interface ParsedBrief {
  date: string
  generatedFor: string
  sections: Record<string, string>
  meta: BriefMeta
}

interface HistoryItem {
  date: string
  articles_used: number
  generated_at: string
}

// ── Constants ─────────────────────────────────────────────────────────────────

const SECTION_NAMES = [
  'SITUATION STATUS',
  'KEY DEVELOPMENTS',
  'ENTITIES TODAY',
  'SIGNALS TO WATCH',
  'FINANCIAL PULSE',
  'SOURCE COVERAGE',
] as const

type SectionName = typeof SECTION_NAMES[number]

const LOADING_PHASES = [
  'Reading articles...',
  'Identifying developments...',
  'Writing your brief...',
]

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ── Brief markdown parser ──────────────────────────────────────────────────────

function parseBrief(content: string, meta: BriefMeta): ParsedBrief {
  const dateMatch = content.match(/^## (.+)$/m)
  const metaMatch = content.match(/\*Generated for: (.+?)\*/)

  const sections: Record<string, string> = {}
  const parts = content.split(/\n---\n/)

  for (const part of parts) {
    const m = part.match(/^## ([A-Z ]+)\n\n([\s\S]*)/)
    if (m) {
      const name = m[1].trim()
      if (SECTION_NAMES.includes(name as SectionName)) {
        sections[name] = m[2].trim()
      }
    }
  }

  return {
    date: dateMatch?.[1] ?? '',
    generatedFor: metaMatch?.[1] ?? '',
    sections,
    meta,
  }
}

// ── Section block wrapper ─────────────────────────────────────────────────────

function SectionBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: '40px' }}>
      <div style={{ marginBottom: '16px' }}>
        <p style={{
          fontFamily: "'DM Sans', system-ui, sans-serif",
          fontSize: '11px',
          letterSpacing: '0.15em',
          textTransform: 'uppercase',
          color: '#9C928A',
          marginBottom: '8px',
        }}>
          {title}
        </p>
        <div style={{ height: '1px', backgroundColor: '#DDD8D0' }} />
      </div>
      {children}
    </div>
  )
}

// ── SITUATION STATUS ──────────────────────────────────────────────────────────

function SituationSection({ text }: { text: string }) {
  return (
    <p style={{
      fontFamily: "'Playfair Display', Georgia, serif",
      fontSize: '18px',
      fontStyle: 'italic',
      lineHeight: '1.7',
      color: '#1A1614',
      paddingLeft: '24px',
      borderLeft: '3px solid #8B1A1A',
      margin: '0',
    }}>
      {text}
    </p>
  )
}

// ── KEY DEVELOPMENTS ──────────────────────────────────────────────────────────

function DevelopmentsSection({ text }: { text: string }) {
  const circled = /[①②③④⑤⑥⑦⑧⑨⑩]/
  const items = text.split(/(?=[①②③④⑤⑥⑦⑧⑨⑩])/).filter(Boolean)

  if (items.length === 0) {
    return (
      <p style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: '15px', color: '#1A1614', lineHeight: '1.6' }}>
        {text}
      </p>
    )
  }

  return (
    <div>
      {items.map((item, i) => {
        const numMatch = item.match(/^([①②③④⑤⑥⑦⑧⑨⑩])([\s\S]*)$/)
        if (!numMatch) return null
        const [, num, rest] = numMatch
        const lines = rest.trim().split('\n')
        const headline = lines[0].trim()
        const prose = lines.slice(1).join('\n').trim()

        return (
          <div
            key={i}
            style={{
              paddingTop: '16px',
              paddingBottom: '16px',
              borderBottom: i < items.length - 1 ? '1px dashed #DDD8D0' : 'none',
            }}
          >
            <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
              <span style={{
                fontFamily: "'DM Mono', ui-monospace, monospace",
                fontSize: '16px',
                color: '#8B1A1A',
                flexShrink: 0,
                lineHeight: '1.5',
              }}>
                {num}
              </span>
              <div>
                {headline && (
                  <p style={{
                    fontFamily: "'DM Sans', system-ui, sans-serif",
                    fontSize: '15px',
                    fontWeight: 600,
                    color: '#1A1614',
                    marginBottom: prose ? '6px' : '0',
                    lineHeight: '1.5',
                  }}>
                    {headline}
                  </p>
                )}
                {prose && (
                  <p style={{
                    fontFamily: "'DM Sans', system-ui, sans-serif",
                    fontSize: '15px',
                    color: '#1A1614',
                    lineHeight: '1.6',
                    margin: '0',
                  }}>
                    {prose}
                  </p>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── ENTITIES TODAY ────────────────────────────────────────────────────────────

function EntitiesSection({ text }: { text: string }) {
  const blocks = text.split(/\n\n+/).filter(Boolean)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {blocks.map((block, i) => {
        const lines = block.trim().split('\n')
        const name = lines[0].trim()
        const prose = lines.slice(1).join('\n').trim()

        if (!prose) {
          return (
            <p key={i} style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: '15px', color: '#1A1614', lineHeight: '1.6' }}>
              {name}
            </p>
          )
        }

        return (
          <div key={i}>
            <p style={{
              fontFamily: "'DM Sans', system-ui, sans-serif",
              fontSize: '13px',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              color: '#5C5249',
              marginBottom: '6px',
            }}>
              {name}
            </p>
            <p style={{
              fontFamily: "'DM Sans', system-ui, sans-serif",
              fontSize: '15px',
              color: '#1A1614',
              lineHeight: '1.6',
              margin: '0',
            }}>
              {prose}
            </p>
          </div>
        )
      })}
    </div>
  )
}

// ── SIGNALS TO WATCH ──────────────────────────────────────────────────────────

function SignalsSection({ text }: { text: string }) {
  const items = text.split(/(?=⚑)/).filter(Boolean)

  if (items.length === 0) {
    return (
      <p style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: '15px', color: '#1A1614', lineHeight: '1.6' }}>
        {text}
      </p>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {items.map((item, i) => {
        const lines = item.replace(/^⚑\s*/, '').trim().split('\n')
        const headline = lines[0].trim()
        const prose = lines.slice(1).join('\n').trim()

        return (
          <div
            key={i}
            style={{
              backgroundColor: '#FDF0EF',
              borderLeft: '3px solid #8B1A1A',
              borderRadius: '2px',
              padding: '14px 16px',
            }}
          >
            <p style={{
              fontFamily: "'DM Sans', system-ui, sans-serif",
              fontSize: '14px',
              fontWeight: 600,
              color: '#1A1614',
              marginBottom: prose ? '6px' : '0',
            }}>
              ⚑ {headline}
            </p>
            {prose && (
              <p style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '14px',
                color: '#5C5249',
                lineHeight: '1.6',
                margin: '0',
              }}>
                {prose}
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── FINANCIAL PULSE ───────────────────────────────────────────────────────────

function FinancialSection({ text }: { text: string }) {
  const isNoData = text.toLowerCase().includes('no significant financial')
  return (
    <p style={{
      fontFamily: "'DM Sans', system-ui, sans-serif",
      fontSize: '15px',
      color: isNoData ? '#9C928A' : '#1A1614',
      fontStyle: isNoData ? 'italic' : 'normal',
      lineHeight: '1.7',
      margin: '0',
    }}>
      {text}
    </p>
  )
}

// ── SOURCE COVERAGE ───────────────────────────────────────────────────────────

function SourcesSection({ text }: { text: string }) {
  const lines = text.split('\n').filter(l => l.trim())

  return (
    <div>
      {lines.map((line, i) => {
        const dashIdx = line.indexOf(' — ')
        if (dashIdx === -1) {
          return (
            <p key={i} style={{
              fontFamily: "'DM Sans', system-ui, sans-serif",
              fontSize: '14px',
              color: '#5C5249',
              lineHeight: '1.6',
              marginTop: i > 0 ? '10px' : '0',
              fontStyle: 'italic',
            }}>
              {line}
            </p>
          )
        }
        const name = line.slice(0, dashIdx)
        const desc = line.slice(dashIdx + 3)
        return (
          <p key={i} style={{
            fontFamily: "'DM Sans', system-ui, sans-serif",
            fontSize: '14px',
            color: '#5C5249',
            lineHeight: '1.5',
            marginTop: i > 0 ? '6px' : '0',
          }}>
            <span style={{ fontWeight: 600, color: '#1A1614' }}>{name}</span>
            {' — '}{desc}
          </p>
        )
      })}
    </div>
  )
}

// ── Brief content renderer ────────────────────────────────────────────────────

function BriefContent({ brief, onRegenerate }: { brief: ParsedBrief; onRegenerate: () => void }) {
  const [confirmVisible, setConfirmVisible] = useState(false)

  const formatTime = (iso: string) => {
    try {
      return new Date(iso).toLocaleTimeString('en-IN', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
        timeZone: 'Asia/Kolkata',
      })
    } catch {
      return ''
    }
  }

  return (
    <div>
      {/* Page header */}
      <div style={{ marginBottom: '32px' }}>
        <p style={{
          fontFamily: "'DM Sans', system-ui, sans-serif",
          fontSize: '11px',
          letterSpacing: '0.15em',
          textTransform: 'uppercase',
          color: '#9C928A',
          marginBottom: '8px',
        }}>
          Daily Intelligence Brief
        </p>
        <h1 style={{
          fontFamily: "'Playfair Display', Georgia, serif",
          fontSize: '32px',
          fontWeight: 700,
          color: '#1A1614',
          lineHeight: '1.2',
          marginBottom: '8px',
        }}>
          {brief.date}
        </h1>
        <p style={{
          fontFamily: "'DM Mono', ui-monospace, monospace",
          fontSize: '12px',
          color: '#9C928A',
        }}>
          {brief.meta.articlesUsed} articles · llama-3.3-70b-versatile · Generated {formatTime(brief.meta.generatedAt)}
        </p>
        <div style={{ height: '1px', backgroundColor: '#DDD8D0', marginTop: '16px' }} />
      </div>

      {/* Six sections */}
      {brief.sections['SITUATION STATUS'] && (
        <SectionBlock title="Situation Status">
          <SituationSection text={brief.sections['SITUATION STATUS']} />
        </SectionBlock>
      )}

      {brief.sections['KEY DEVELOPMENTS'] && (
        <SectionBlock title="Key Developments">
          <DevelopmentsSection text={brief.sections['KEY DEVELOPMENTS']} />
        </SectionBlock>
      )}

      {brief.sections['ENTITIES TODAY'] && (
        <SectionBlock title="Entities Today">
          <EntitiesSection text={brief.sections['ENTITIES TODAY']} />
        </SectionBlock>
      )}

      {brief.sections['SIGNALS TO WATCH'] && (
        <SectionBlock title="Signals to Watch">
          <SignalsSection text={brief.sections['SIGNALS TO WATCH']} />
        </SectionBlock>
      )}

      {brief.sections['FINANCIAL PULSE'] && (
        <SectionBlock title="Financial Pulse">
          <FinancialSection text={brief.sections['FINANCIAL PULSE']} />
        </SectionBlock>
      )}

      {brief.sections['SOURCE COVERAGE'] && (
        <SectionBlock title="Source Coverage">
          <SourcesSection text={brief.sections['SOURCE COVERAGE']} />
        </SectionBlock>
      )}

      {/* Footer */}
      <div style={{
        borderTop: '1px solid #DDD8D0',
        paddingTop: '16px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginTop: '8px',
      }}>
        <p style={{
          fontFamily: "'DM Sans', system-ui, sans-serif",
          fontSize: '13px',
          color: '#9C928A',
        }}>
          {brief.meta.articlesUsed} articles analysed
        </p>

        {confirmVisible ? (
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <p style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: '13px', color: '#5C5249' }}>
              Regenerate today&apos;s brief?
            </p>
            <button
              onClick={() => { setConfirmVisible(false); onRegenerate() }}
              style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: '13px', color: '#8B1A1A', cursor: 'pointer', background: 'none', border: 'none', padding: 0 }}
            >
              Yes, replace
            </button>
            <button
              onClick={() => setConfirmVisible(false)}
              style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: '13px', color: '#9C928A', cursor: 'pointer', background: 'none', border: 'none', padding: 0 }}
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            onClick={() => setConfirmVisible(true)}
            style={{
              fontFamily: "'DM Sans', system-ui, sans-serif",
              fontSize: '13px',
              color: '#9C928A',
              cursor: 'pointer',
              background: 'none',
              border: 'none',
              padding: 0,
            }}
          >
            Regenerate ↻
          </button>
        )}
      </div>
    </div>
  )
}

// ── Loading state ─────────────────────────────────────────────────────────────

function LoadingState() {
  const [phaseIdx, setPhaseIdx] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => {
      setPhaseIdx(i => Math.min(i + 1, LOADING_PHASES.length - 1))
    }, 8000)
    return () => clearInterval(timer)
  }, [])

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '80px 0',
      gap: '12px',
    }}>
      <style>{`
        @keyframes rig-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
      <p style={{
        fontFamily: "'DM Sans', system-ui, sans-serif",
        fontSize: '15px',
        color: '#5C5249',
        animation: 'rig-pulse 2s ease-in-out infinite',
      }}>
        {LOADING_PHASES[phaseIdx]}
      </p>
      <p style={{
        fontFamily: "'DM Mono', ui-monospace, monospace",
        fontSize: '12px',
        color: '#9C928A',
      }}>
        Analysing 30 articles
      </p>
    </div>
  )
}

// ── Left sidebar ──────────────────────────────────────────────────────────────

function LeftSidebar({
  history,
  onSelectDate,
  selectedDate,
}: {
  history: HistoryItem[]
  onSelectDate: (date: string) => void
  selectedDate: string | null
}) {
  const formatDate = (iso: string) => {
    try {
      return new Date(iso + 'T00:00:00').toLocaleDateString('en-IN', {
        day: 'numeric',
        month: 'short',
      })
    } catch {
      return iso
    }
  }

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      width: '200px',
      height: '100vh',
      backgroundColor: '#EFEBE4',
      borderRight: '1px solid #DDD8D0',
      display: 'flex',
      flexDirection: 'column',
      zIndex: 10,
      overflowY: 'auto',
    }}>
      {/* Wordmark */}
      <div style={{ padding: '24px 20px', borderBottom: '1px solid #DDD8D0', flexShrink: 0 }}>
        <p style={{
          fontFamily: "'Playfair Display', Georgia, serif",
          fontSize: '14px',
          color: '#8B1A1A',
          lineHeight: '1.4',
          letterSpacing: '0.02em',
        }}>
          RIG<br />SURVEILLANCE
        </p>
      </div>

      {/* Nav */}
      <nav style={{ padding: '12px 0', flexShrink: 0 }}>
        <div style={{ padding: '10px 20px', borderLeft: '2px solid #8B1A1A' }}>
          <p style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: '14px', color: '#8B1A1A' }}>
            Daily Brief
          </p>
        </div>

        <div style={{ padding: '10px 20px', borderLeft: '2px solid transparent' }}>
          <p style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: '14px', color: '#9C928A' }}>
            Coverage Room
          </p>
          <p style={{ fontFamily: "'DM Mono', ui-monospace, monospace", fontSize: '10px', color: '#9C928A', marginTop: '2px' }}>
            coming soon
          </p>
        </div>

        <div style={{ padding: '10px 20px', borderLeft: '2px solid transparent' }}>
          <p style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: '14px', color: '#9C928A' }}>
            Analyst
          </p>
          <p style={{ fontFamily: "'DM Mono', ui-monospace, monospace", fontSize: '10px', color: '#9C928A', marginTop: '2px' }}>
            coming soon
          </p>
        </div>
      </nav>

      {/* Previous briefs */}
      {history.length > 0 && (
        <div style={{ marginTop: 'auto', borderTop: '1px solid #DDD8D0', padding: '16px 0' }}>
          <p style={{
            fontFamily: "'DM Sans', system-ui, sans-serif",
            fontSize: '11px',
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            color: '#9C928A',
            padding: '0 20px',
            marginBottom: '8px',
          }}>
            Previous Briefs
          </p>
          {history.map(item => (
            <button
              key={item.date}
              onClick={() => onSelectDate(item.date)}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                padding: '8px 20px',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                borderLeft: selectedDate === item.date ? '2px solid #8B1A1A' : '2px solid transparent',
              }}
            >
              <p style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '13px',
                color: selectedDate === item.date ? '#8B1A1A' : '#5C5249',
              }}>
                {formatDate(item.date)}
              </p>
              <p style={{ fontFamily: "'DM Mono', ui-monospace, monospace", fontSize: '10px', color: '#9C928A' }}>
                {item.articles_used} articles
              </p>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function BriefPage() {
  const router = useRouter()
  const [pageState, setPageState] = useState<PageState>('loading_check')
  const [brief, setBrief] = useState<ParsedBrief | null>(null)
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [errorMsg, setErrorMsg] = useState('')
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const tokenRef = useRef<string | null>(null)

  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getSession().then(async ({ data }) => {
      if (!data.session) {
        router.push('/login')
        return
      }
      tokenRef.current = data.session.access_token
      await loadTodayBrief(data.session.access_token)
      await loadHistory(data.session.access_token)
    })
  }, [router])

  const loadTodayBrief = async (token: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/brief/today`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setBrief(parseBrief(data.content, {
          briefDate: data.brief_date,
          articlesUsed: data.articles_used,
          generatedAt: data.generated_at,
        }))
        setSelectedDate(data.brief_date)
        setPageState('showing_brief')
      } else if (res.status === 404) {
        setPageState('no_brief')
      } else {
        setErrorMsg('Failed to check for today\'s brief')
        setPageState('error')
      }
    } catch {
      setErrorMsg('Network error. Is the server running?')
      setPageState('error')
    }
  }

  const loadHistory = async (token: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/brief/history/list`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setHistory(data.briefs ?? [])
      }
    } catch { /* non-critical */ }
  }

  const handleGenerate = async () => {
    if (!tokenRef.current) return
    setPageState('generating')
    setErrorMsg('')

    try {
      const res = await fetch(`${API_BASE}/api/brief/generate`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${tokenRef.current}`,
          'Content-Type': 'application/json',
        },
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Generation failed' }))
        setErrorMsg((err as { detail?: string }).detail ?? 'Brief generation failed')
        setPageState('error')
        return
      }

      const data = await res.json()
      setBrief(parseBrief(data.content, {
        briefDate: data.brief_date,
        articlesUsed: data.articles_used,
        generatedAt: new Date().toISOString(),
      }))
      setSelectedDate(data.brief_date)
      setPageState('showing_brief')
      if (tokenRef.current) await loadHistory(tokenRef.current)
    } catch {
      setErrorMsg('Network error during generation')
      setPageState('error')
    }
  }

  const handleSelectDate = async (dateStr: string) => {
    if (!tokenRef.current) return
    setSelectedDate(dateStr)

    const today = new Date().toISOString().split('T')[0]
    if (dateStr === today && brief?.meta.briefDate === today) return

    try {
      const res = await fetch(`${API_BASE}/api/brief/${dateStr}`, {
        headers: { Authorization: `Bearer ${tokenRef.current}` },
      })
      if (res.ok) {
        const data = await res.json()
        setBrief(parseBrief(data.content, {
          briefDate: data.brief_date,
          articlesUsed: data.articles_used,
          generatedAt: data.generated_at,
        }))
        setPageState('showing_brief')
      }
    } catch { /* stay on current */ }
  }

  const renderMain = () => {
    switch (pageState) {
      case 'loading_check':
        return (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '80px 0' }}>
            <p style={{ fontFamily: "'DM Mono', ui-monospace, monospace", fontSize: '12px', color: '#9C928A' }}>
              Loading...
            </p>
          </div>
        )

      case 'no_brief':
        return (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '80px 0',
            gap: '12px',
          }}>
            <button
              onClick={handleGenerate}
              style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '15px',
                color: '#8B1A1A',
                cursor: 'pointer',
                background: 'none',
                border: 'none',
                padding: 0,
              }}
            >
              Generate Today&apos;s Brief
            </button>
            <p style={{
              fontFamily: "'DM Mono', ui-monospace, monospace",
              fontSize: '12px',
              color: '#9C928A',
            }}>
              Takes approximately 20 seconds
            </p>
          </div>
        )

      case 'generating':
        return <LoadingState />

      case 'showing_brief':
        return brief ? <BriefContent brief={brief} onRegenerate={handleGenerate} /> : null

      case 'error':
        return (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            padding: '80px 0',
            gap: '16px',
          }}>
            <p style={{
              fontFamily: "'DM Sans', system-ui, sans-serif",
              fontSize: '15px',
              color: '#8B1A1A',
              textAlign: 'center',
            }}>
              Brief generation failed: {errorMsg}
            </p>
            <button
              onClick={() => setPageState('no_brief')}
              style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '13px',
                color: '#5C5249',
                cursor: 'pointer',
                background: 'none',
                border: 'none',
                padding: 0,
                textDecoration: 'underline',
              }}
            >
              Try again
            </button>
          </div>
        )
    }
  }

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#F7F4EF' }}>
      <LeftSidebar
        history={history}
        onSelectDate={handleSelectDate}
        selectedDate={selectedDate}
      />
      <main style={{
        marginLeft: '200px',
        padding: '48px 48px 80px',
      }}>
        <div style={{ maxWidth: '720px' }}>
          {renderMain()}
        </div>
      </main>
    </div>
  )
}
