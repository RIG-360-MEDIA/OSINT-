'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import Navigation from '@/components/Navigation'
import { Dateline } from '@/components/Dateline'

/* ── Types ────────────────────────────────────────────────────────────────── */

type PageState = 'loading_check' | 'no_brief' | 'generating' | 'showing_brief' | 'error' | 'too_early'

interface BriefMeta { briefDate: string; articlesUsed: number; generatedAt: string }
interface ParsedBrief { date: string; generatedFor: string; sections: Record<string, string>; meta: BriefMeta }
interface HistoryItem { date: string; articles_used: number; generated_at: string }

/* ── Constants ────────────────────────────────────────────────────────────── */

const SECTION_NAMES = [
  'SITUATION STATUS', 'KEY DEVELOPMENTS', 'ENTITIES TODAY',
  'SIGNALS TO WATCH', 'FINANCIAL PULSE', 'SOURCE COVERAGE',
] as const
type SectionName = typeof SECTION_NAMES[number]

const LOADING_PHASES = ['Reading the wires…', 'Marking the developments…', 'Filing the brief…']

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

/* ── Brief parser ─────────────────────────────────────────────────────────── */

function parseBrief(content: string, meta: BriefMeta): ParsedBrief {
  const dateMatch = content.match(/^## (.+)$/m)
  const metaMatch = content.match(/\*Generated for: (.+?)\*/)
  const sections: Record<string, string> = {}
  for (const part of content.split(/\n---\n/)) {
    const m = part.trim().match(/^## ([A-Z ]+)\n\n([\s\S]*)/)
    if (m) {
      const name = m[1].trim()
      if (SECTION_NAMES.includes(name as SectionName)) sections[name] = m[2].trim()
    }
  }
  return { date: dateMatch?.[1] ?? '', generatedFor: metaMatch?.[1] ?? '', sections, meta }
}

/* ── Newsroom section wrapper ─────────────────────────────────────────────── */

function Movement({
  numeral,
  title,
  delay = 0,
  children,
}: {
  numeral: string
  title: string
  delay?: number
  children: React.ReactNode
}) {
  return (
    <section className="anim-fade-up" style={{ animationDelay: `${delay}ms`, padding: '40px 0' }}>
      <div className="rig-section-head">
        <span className="numeral">{numeral}.</span>
        <span className="rig-kicker">{title}</span>
      </div>
      {children}
    </section>
  )
}

/* ── SITUATION STATUS (the standfirst) ────────────────────────────────────── */

function SituationSection({ text }: { text: string }) {
  return (
    <blockquote className="rig-pullquote">
      {text}
    </blockquote>
  )
}

/* ── KEY DEVELOPMENTS — numbered broadsheet entries ───────────────────────── */

function DevelopmentsSection({ text }: { text: string }) {
  const items = text.split(/(?=[①②③④⑤⑥⑦⑧⑨⑩])/).filter(Boolean)

  if (!items.length) {
    return <p className="rig-prose">{text}</p>
  }

  const arabic = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X']

  return (
    <div>
      {items.map((item, i) => {
        const m = item.match(/^([①②③④⑤⑥⑦⑧⑨⑩])([\s\S]*)$/)
        if (!m) return null
        const [, , rest] = m
        const lines = rest.trim().split('\n')
        const headline = lines[0].trim()
        const prose = lines.slice(1).join('\n').trim()

        return (
          <article
            key={i}
            style={{
              display: 'grid',
              gridTemplateColumns: '52px 1fr',
              gap: '22px',
              padding: '22px 0',
              borderBottom: i < items.length - 1 ? '1px solid var(--rig-rule-hair)' : 'none',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--font-serif)',
                fontStyle: 'italic',
                fontSize: '32px',
                lineHeight: 1,
                color: 'var(--rig-copper)',
                paddingTop: '2px',
              }}
            >
              {arabic[i] ?? i + 1}.
            </span>
            <div style={{ minWidth: 0 }}>
              {headline && (
                <h3
                  className="rig-headline"
                  style={{ fontSize: '22px', marginBottom: prose ? '10px' : 0 }}
                >
                  {headline}
                </h3>
              )}
              {prose && <p className="rig-prose">{prose}</p>}
            </div>
          </article>
        )
      })}
    </div>
  )
}

/* ── ENTITIES TODAY — typographic grid, no cards ──────────────────────────── */

function EntitiesSection({ text }: { text: string }) {
  const blocks = text.split(/\n\n+/).filter(Boolean)

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
        gap: '0',
      }}
    >
      {blocks.map((block, i) => {
        const lines = block.trim().split('\n')
        const name = lines[0].trim()
        const prose = lines.slice(1).join('\n').trim()

        return (
          <div
            key={i}
            style={{
              padding: '18px 24px 18px 0',
              borderTop: '1px solid var(--rig-rule-hair)',
              borderRight: '1px solid var(--rig-rule-hair)',
            }}
          >
            <p
              className="rig-kicker rig-kicker-gold"
              style={{ fontSize: '9px', marginBottom: '6px' }}
            >
              {name}
            </p>
            {prose && (
              <p
                className="rig-prose"
                style={{ fontSize: '14px' }}
              >
                {prose}
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}

/* ── SIGNALS TO WATCH ─────────────────────────────────────────────────────── */

function SignalsSection({ text }: { text: string }) {
  const items = text.split(/(?=⚑)/).filter(Boolean)
  if (!items.length) return <p className="rig-prose">{text}</p>

  return (
    <div>
      {items.map((item, i) => {
        const lines = item.replace(/^⚑\s*/, '').trim().split('\n')
        const headline = lines[0].trim()
        const prose = lines.slice(1).join('\n').trim()

        return (
          <div
            key={i}
            style={{
              padding: '18px 0 18px 20px',
              borderLeft: '2px solid var(--rig-oxblood)',
              borderBottom: i < items.length - 1 ? '1px solid var(--rig-rule-hair)' : 'none',
            }}
          >
            <p
              className="rig-kicker"
              style={{
                color: 'var(--rig-oxblood)',
                fontSize: '9px',
                marginBottom: '8px',
              }}
            >
              Signal · {String(i + 1).padStart(2, '0')}
            </p>
            <h4
              className="rig-headline"
              style={{ fontSize: '18px', marginBottom: prose ? '6px' : 0 }}
            >
              {headline}
            </h4>
            {prose && <p className="rig-prose" style={{ fontSize: '14px' }}>{prose}</p>}
          </div>
        )
      })}
    </div>
  )
}

/* ── FINANCIAL PULSE ──────────────────────────────────────────────────────── */

function FinancialSection({ text }: { text: string }) {
  const isNoData = text.toLowerCase().includes('no significant financial')
  return (
    <p
      className="rig-serif-body"
      style={{
        fontStyle: isNoData ? 'italic' : 'normal',
        color: isNoData ? 'var(--rig-ink-3)' : 'var(--rig-ink-2)',
      }}
    >
      {text}
    </p>
  )
}

/* ── SOURCE COVERAGE ──────────────────────────────────────────────────────── */

function SourcesSection({ text }: { text: string }) {
  const lines = text.split('\n').filter((l) => l.trim())

  return (
    <div>
      {lines.map((line, i) => {
        const dashIdx = line.indexOf(' — ')
        if (dashIdx === -1) {
          return (
            <p
              key={i}
              className="rig-prose"
              style={{
                fontFamily: 'var(--font-serif)',
                fontStyle: 'italic',
                padding: '10px 0',
                color: 'var(--rig-ink-3)',
              }}
            >
              {line}
            </p>
          )
        }
        const name = line.slice(0, dashIdx)
        const desc = line.slice(dashIdx + 3)

        return (
          <div
            key={i}
            style={{
              display: 'grid',
              gridTemplateColumns: '180px 1fr',
              gap: '24px',
              padding: '12px 0',
              borderBottom: i < lines.length - 1 ? '1px solid var(--rig-rule-hair)' : 'none',
            }}
          >
            <span
              className="rig-byline"
              style={{ color: 'var(--rig-gold)', fontSize: '11px' }}
            >
              {name}
            </span>
            <span className="rig-prose" style={{ fontSize: '14px' }}>
              {desc}
            </span>
          </div>
        )
      })}
    </div>
  )
}

/* ── Brief content ────────────────────────────────────────────────────────── */

function BriefContent({
  brief,
  onRegenerate,
}: {
  brief: ParsedBrief
  onRegenerate: () => void
}) {
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
      {/* ── Lead banner ─────────────────────────────────────────────── */}
      <div className="anim-fade-up" style={{ padding: '48px 0 36px' }}>
        <div className="rig-kicker rig-kicker-gold" style={{ marginBottom: '24px' }}>
          <span style={{ width: '28px', height: '1px', background: 'var(--rig-gold)', opacity: 0.7 }} />
          The Lead · Filed {formatTime(brief.meta.generatedAt)} IST
        </div>
        <h1
          className="rig-headline"
          style={{ fontSize: 'clamp(40px, 5vw, 64px)', maxWidth: '980px' }}
        >
          {brief.date}
        </h1>
        <p
          className="rig-byline"
          style={{ marginTop: '22px' }}
        >
          <span>{brief.meta.articlesUsed.toLocaleString()} articles analysed</span>
          <span className="sep">·</span>
          <span>Model · llama-3.3-70b</span>
          <span className="sep">·</span>
          <span>Generated {formatTime(brief.meta.generatedAt)} IST</span>
        </p>
      </div>

      <hr className="rig-rule-strong" />

      {/* ── Movements ───────────────────────────────────────────────── */}
      {brief.sections['SITUATION STATUS'] && (
        <Movement numeral="I" title="Situation Status" delay={80}>
          <SituationSection text={brief.sections['SITUATION STATUS']} />
        </Movement>
      )}

      {brief.sections['KEY DEVELOPMENTS'] && (
        <Movement numeral="II" title="Key Developments" delay={160}>
          <DevelopmentsSection text={brief.sections['KEY DEVELOPMENTS']} />
        </Movement>
      )}

      {brief.sections['SIGNALS TO WATCH'] && (
        <Movement numeral="III" title="Signals to Watch" delay={240}>
          <SignalsSection text={brief.sections['SIGNALS TO WATCH']} />
        </Movement>
      )}

      {brief.sections['ENTITIES TODAY'] && (
        <Movement numeral="IV" title="Entities Today" delay={320}>
          <EntitiesSection text={brief.sections['ENTITIES TODAY']} />
        </Movement>
      )}

      {brief.sections['FINANCIAL PULSE'] && (
        <Movement numeral="V" title="Financial Pulse" delay={400}>
          <FinancialSection text={brief.sections['FINANCIAL PULSE']} />
        </Movement>
      )}

      {brief.sections['SOURCE COVERAGE'] && (
        <Movement numeral="VI" title="Source Coverage" delay={400}>
          <SourcesSection text={brief.sections['SOURCE COVERAGE']} />
        </Movement>
      )}

      {/* ── Colophon / footer ───────────────────────────────────────── */}
      <div
        style={{
          marginTop: '60px',
          padding: '28px 0',
          borderTop: '1px solid var(--rig-rule)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '18px',
        }}
      >
        <span className="rig-byline">
          End of filing — {brief.meta.articlesUsed.toLocaleString()} articles analysed
        </span>
        {confirmVisible ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '18px' }}>
            <span className="rig-prose" style={{ fontSize: '14px', fontStyle: 'italic' }}>
              Replace today&apos;s filing?
            </span>
            <button
              onClick={() => {
                setConfirmVisible(false)
                onRegenerate()
              }}
              className="rig-btn-ghost"
              style={{ color: 'var(--rig-oxblood)', borderColor: 'color-mix(in srgb, var(--rig-oxblood) 50%, transparent)' }}
            >
              Yes, replace
            </button>
            <button onClick={() => setConfirmVisible(false)} className="rig-btn-ghost">
              Cancel
            </button>
          </div>
        ) : (
          <button onClick={() => setConfirmVisible(true)} className="rig-btn-ghost">
            ↻ Regenerate brief
          </button>
        )}
      </div>
    </div>
  )
}

/* ── Loading state ────────────────────────────────────────────────────────── */

function LoadingState() {
  const [phaseIdx, setPhaseIdx] = useState(0)
  const [progress, setProgress] = useState(5)

  useEffect(() => {
    const t1 = setInterval(
      () => setPhaseIdx((i) => Math.min(i + 1, LOADING_PHASES.length - 1)),
      8000,
    )
    const t2 = setInterval(() => setProgress((p) => Math.min(p + 1.2, 88)), 200)
    return () => {
      clearInterval(t1)
      clearInterval(t2)
    }
  }, [])

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '140px 0',
        gap: '28px',
      }}
    >
      <div className="rig-kicker rig-kicker-gold">The Desk · Filing in progress</div>
      <p
        className="rig-headline"
        style={{ fontSize: '28px', fontStyle: 'italic', textAlign: 'center' }}
      >
        {LOADING_PHASES[phaseIdx]}
      </p>
      <div
        style={{
          width: '320px',
          height: '1px',
          background: 'var(--rig-rule)',
          position: 'relative',
        }}
      >
        <div
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            height: '1px',
            background: 'var(--rig-gold)',
            width: `${progress}%`,
            transition: 'width 200ms linear',
          }}
        />
      </div>
      <p className="rig-byline">
        {progress < 40 ? 'Reading wires' : progress < 75 ? 'Weighing sources' : 'Setting type'}
        <span className="sep">·</span>
        {Math.round(progress)}%
      </p>
    </div>
  )
}

/* ── Empty state (as a typed memo) ────────────────────────────────────────── */

function EmptyState({ onGenerate }: { onGenerate: () => void }) {
  return (
    <section
      className="anim-fade-up"
      style={{
        width: '100%',
        padding: '28px 0 80px',
        position: 'relative',
        borderTop: '1px solid var(--rig-rule-hair)',
        marginTop: '16px',
      }}
    >
      {/* Kicker row — full-width editorial rule */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr auto 1fr',
          alignItems: 'center',
          gap: '24px',
          marginBottom: '36px',
        }}
      >
        <span style={{ height: '1px', background: 'var(--rig-rule-hair)' }} />
        <div
          className="rig-kicker rig-kicker-gold"
          style={{ justifyContent: 'center', whiteSpace: 'nowrap' }}
        >
          <span style={{ width: '32px', height: '1px', background: 'var(--rig-gold)', opacity: 0.7 }} />
          Desk Memo
          <span style={{ width: '32px', height: '1px', background: 'var(--rig-gold)', opacity: 0.7 }} />
        </div>
        <span style={{ height: '1px', background: 'var(--rig-rule-hair)' }} />
      </div>

      {/* Headline — oversized, page-spanning */}
      <h2
        className="rig-headline"
        style={{
          fontSize: 'clamp(48px, 6vw, 88px)',
          lineHeight: 1.05,
          letterSpacing: '-0.01em',
          textAlign: 'center',
          margin: '0 auto 32px',
          maxWidth: '1200px',
          padding: '0 24px',
        }}
      >
        No filing yet for today.
        <br />
        <em style={{ color: 'var(--rig-gold)', fontWeight: 500 }}>The wires are warm.</em>
      </h2>

      {/* Lede + CTA split row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr)',
          maxWidth: '960px',
          margin: '0 auto',
          padding: '0 32px',
          textAlign: 'center',
        }}
      >
        <p
          className="rig-lede"
          style={{
            fontSize: 'clamp(17px, 1.3vw, 20px)',
            lineHeight: 1.6,
            margin: '0 auto 36px',
            maxWidth: '640px',
          }}
        >
          Generate the morning brief — threads, signals, entities and opposition
          reads, ordered by consequence.
        </p>

        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '40px' }}>
          <button onClick={onGenerate} className="rig-btn-primary">
            File today&apos;s brief
            <span className="arrow">→</span>
          </button>
        </div>

        {/* Meta strip — three-column editorial footer */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr auto 1fr',
            alignItems: 'center',
            gap: '20px',
            maxWidth: '560px',
            margin: '24px auto 0',
          }}
        >
          <p
            className="rig-byline"
            style={{ margin: 0, textAlign: 'right' }}
          >
            Takes ≈ 20 seconds
          </p>
          <span
            aria-hidden="true"
            style={{
              width: '4px',
              height: '4px',
              borderRadius: '50%',
              background: 'var(--rig-gold)',
              opacity: 0.6,
            }}
          />
          <p
            className="rig-byline"
            style={{ margin: 0, textAlign: 'left' }}
          >
            All sources in your feed
          </p>
        </div>
      </div>
    </section>
  )
}

/* ── History strip ────────────────────────────────────────────────────────── */

function HistoryStrip({
  history,
  onSelectDate,
  selectedDate,
}: {
  history: HistoryItem[]
  onSelectDate: (date: string) => void
  selectedDate: string | null
}) {
  if (!history.length) return null

  const formatDate = (iso: string) => {
    try {
      return new Date(iso + 'T00:00:00')
        .toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
        .toUpperCase()
    } catch {
      return iso
    }
  }

  return (
    <div style={{ padding: '32px 0 22px', borderBottom: '1px solid var(--rig-rule-hair)' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '14px',
          marginBottom: '14px',
        }}
      >
        <span style={{ width: '20px', height: '1px', background: 'var(--rig-rule)' }} />
        <p className="rig-byline" style={{ margin: 0 }}>
          Previous filings
        </p>
        <span style={{ flex: 1, height: '1px', background: 'var(--rig-rule-hair)' }} />
      </div>
      <div style={{ display: 'flex', gap: '22px', flexWrap: 'wrap', alignItems: 'baseline' }}>
        {history.map((item) => {
          const isSelected = selectedDate === item.date
          return (
            <button
              key={item.date}
              onClick={() => onSelectDate(item.date)}
              style={{
                background: 'none',
                border: 'none',
                padding: 0,
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'baseline',
                gap: '8px',
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                letterSpacing: '0.22em',
                textTransform: 'uppercase',
                color: isSelected ? 'var(--rig-gold)' : 'var(--rig-ink-3)',
                borderBottom: isSelected ? '1px solid var(--rig-gold)' : '1px solid transparent',
                paddingBottom: '4px',
                transition: 'color 0.2s, border-color 0.2s',
              }}
              onMouseEnter={(e) => {
                if (!isSelected) e.currentTarget.style.color = 'var(--rig-ink)'
              }}
              onMouseLeave={(e) => {
                if (!isSelected) e.currentTarget.style.color = 'var(--rig-ink-3)'
              }}
            >
              {formatDate(item.date)}
              <span style={{ fontSize: '9px', opacity: 0.6 }}>{item.articles_used}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

/* ── Main page ────────────────────────────────────────────────────────────── */

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
        setBrief(
          parseBrief(data.content, {
            briefDate: data.brief_date,
            articlesUsed: data.articles_used,
            generatedAt: data.generated_at,
          }),
        )
        setSelectedDate(data.brief_date)
        setPageState('showing_brief')
      } else if (res.status === 404) {
        setPageState('no_brief')
      } else {
        const err = await res
          .json()
          .catch(() => ({ detail: "Failed to check for today's brief" }))
        setErrorMsg(
          `[${res.status}] ${(err as { detail?: string }).detail ?? "Failed to check for today's brief"}`,
        )
        setPageState('error')
      }
    } catch (e) {
      setErrorMsg(
        `Network error: ${e instanceof Error ? e.message : 'Is the server running?'}`,
      )
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
    } catch {
      /* non-critical */
    }
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
      if (res.status === 425) {
        const err = await res
          .json()
          .catch(() => ({ detail: 'Feed is still being prepared' }))
        setErrorMsg(
          (err as { detail?: string }).detail ?? 'Feed is still being prepared',
        )
        setPageState('too_early')
        setTimeout(() => setPageState('no_brief'), 60000)
        return
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Generation failed' }))
        setErrorMsg(
          (err as { detail?: string }).detail ?? 'Brief generation failed',
        )
        setPageState('error')
        return
      }
      const data = await res.json()
      setBrief(
        parseBrief(data.content, {
          briefDate: data.brief_date,
          articlesUsed: data.articles_used,
          generatedAt: new Date().toISOString(),
        }),
      )
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
        setBrief(
          parseBrief(data.content, {
            briefDate: data.brief_date,
            articlesUsed: data.articles_used,
            generatedAt: data.generated_at,
          }),
        )
        setPageState('showing_brief')
      }
    } catch {
      /* stay on current */
    }
  }

  const renderMain = () => {
    switch (pageState) {
      case 'loading_check':
        return (
          <div
            style={{
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
              height: '360px',
            }}
          >
            <div
              style={{
                width: '22px',
                height: '22px',
                borderRadius: '50%',
                border: '1.5px solid var(--rig-rule)',
                borderTopColor: 'var(--rig-gold)',
                animation: 'spin 0.9s linear infinite',
              }}
            />
          </div>
        )

      case 'no_brief':
        return <EmptyState onGenerate={handleGenerate} />

      case 'generating':
        return <LoadingState />

      case 'too_early':
        return (
          <div style={{ padding: '120px 0', textAlign: 'left', maxWidth: '620px' }}>
            <div className="rig-kicker rig-kicker-gold" style={{ marginBottom: '22px' }}>
              Desk Memo · Stand by
            </div>
            <h3
              className="rig-headline"
              style={{ fontSize: '36px', marginBottom: '18px' }}
            >
              Feed still <em>warming.</em>
            </h3>
            <p className="rig-lede" style={{ marginBottom: '16px' }}>{errorMsg}</p>
            <p className="rig-byline">Retrying automatically</p>
          </div>
        )

      case 'showing_brief':
        return brief ? <BriefContent brief={brief} onRegenerate={handleGenerate} /> : null

      case 'error':
        return (
          <div style={{ padding: '120px 0', maxWidth: '620px' }}>
            <div
              className="rig-kicker"
              style={{ color: 'var(--rig-oxblood)', marginBottom: '18px' }}
            >
              Desk Memo · Error
            </div>
            <h3 className="rig-headline" style={{ fontSize: '30px', marginBottom: '14px' }}>
              Filing could not complete.
            </h3>
            <p
              className="rig-prose"
              style={{
                fontStyle: 'italic',
                color: 'var(--rig-oxblood)',
                marginBottom: '24px',
              }}
            >
              {errorMsg}
            </p>
            <button onClick={() => setPageState('no_brief')} className="rig-btn-ghost">
              Try again
            </button>
          </div>
        )
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--rig-paper)', position: 'relative', zIndex: 0 }}>
      <Navigation />
      <main style={{ paddingTop: 'var(--topbar-h)' }}>
        <Dateline
          issueNumber={history.length + (brief ? 1 : 0)}
          filedAt={brief ? '06:00 IST' : undefined}
          sources={brief?.meta.articlesUsed}
        />
        <div
          style={{
            maxWidth: '980px',
            margin: '0 auto',
            padding: '20px 40px 120px',
            position: 'relative',
            zIndex: 2,
          }}
        >
          <HistoryStrip
            history={history}
            onSelectDate={handleSelectDate}
            selectedDate={selectedDate}
          />
          {renderMain()}
        </div>
      </main>
    </div>
  )
}
