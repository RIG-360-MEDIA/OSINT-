'use client'

import { type CSSProperties, useMemo } from 'react'

export interface PaperSummary {
  newspaper_id: string
  name: string
  language: string
  edition_date: string | null
  clip_count: number
  pdf_available: boolean
}

const LANG_LABEL: Record<string, string> = {
  en: 'ENGLISH',
  hi: 'हिन्दी',
  te: 'తెలుగు',
  bn: 'বাংলা',
  gu: 'ગુજરાતી',
  mr: 'मराठी',
  kn: 'ಕನ್ನಡ',
  ml: 'മലയാളം',
  ta: 'தமிழ்',
  pa: 'ਪੰਜਾਬੀ',
}

interface FilterPillProps {
  label: string
  active: boolean
  onClick: () => void
}

function FilterPill({ label, active, onClick }: FilterPillProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      style={{
        padding: '6px 14px',
        fontFamily: 'var(--font-sans-condensed)',
        fontSize: '11px',
        letterSpacing: '0.14em',
        textTransform: 'uppercase',
        background: active ? 'var(--rig-ink)' : 'transparent',
        color: active ? 'var(--rig-paper)' : 'var(--rig-ink)',
        border: `1px solid ${active ? 'var(--rig-ink)' : 'color-mix(in srgb, var(--rig-ink) 25%, transparent)'}`,
        cursor: 'pointer',
        borderRadius: '2px',
        transition: 'background 120ms ease, color 120ms ease',
      }}
    >
      {label}
    </button>
  )
}

interface MastheadCardProps {
  paper: PaperSummary
  onClick: () => void
}

function MastheadCard({ paper, onClick }: MastheadCardProps) {
  const editionLabel = paper.edition_date
    ? new Date(paper.edition_date).toLocaleDateString('en-IN', {
        day: '2-digit', month: 'short', year: 'numeric',
      }).toUpperCase()
    : ''

  // Gold-foil text styling: warm gradient + embossed shadow.
  const nameplateStyle: CSSProperties = {
    fontFamily: 'var(--font-serif)',
    fontWeight: 700,
    fontStyle: 'italic',
    fontSize: paper.name.length > 18 ? '24px' : paper.name.length > 12 ? '30px' : '36px',
    letterSpacing: '0.01em',
    backgroundImage:
      'linear-gradient(180deg, #1a1a1a 0%, #2d2d2d 38%, #6b6b6b 50%, #2d2d2d 62%, #0d0d0d 100%)',
    WebkitBackgroundClip: 'text',
    backgroundClip: 'text',
    color: 'transparent',
    textShadow:
      '0 1px 0 rgba(255,255,255,0.55), 0 -1px 0 rgba(0,0,0,0.35)',
    lineHeight: 1.05,
    textAlign: 'center',
  }

  return (
    <button
      type="button"
      onClick={onClick}
      data-testid="masthead-card"
      data-paper-name={paper.name}
      style={{
        position: 'relative',
        background: 'var(--rig-paper)',
        border: '1px solid color-mix(in srgb, var(--rig-ink) 18%, transparent)',
        borderRadius: '4px',
        padding: '28px 22px 18px',
        textAlign: 'left',
        cursor: 'pointer',
        boxShadow:
          '0 1px 0 rgba(255,255,255,0.6) inset, 0 2px 6px rgba(0,0,0,0.06)',
        transition: 'transform 160ms ease, box-shadow 160ms ease',
        display: 'flex',
        flexDirection: 'column',
        gap: '14px',
        minHeight: '180px',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.transform = 'translateY(-3px)'
        e.currentTarget.style.boxShadow =
          '0 1px 0 rgba(255,255,255,0.6) inset, 0 8px 18px rgba(0,0,0,0.12)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.transform = 'translateY(0)'
        e.currentTarget.style.boxShadow =
          '0 1px 0 rgba(255,255,255,0.6) inset, 0 2px 6px rgba(0,0,0,0.06)'
      }}
    >
      <div
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '14px 6px',
          background:
            'radial-gradient(circle at 50% 30%, rgba(255,255,255,0.7), transparent 75%)',
          borderTop: '1px solid color-mix(in srgb, var(--rig-ink) 12%, transparent)',
          borderBottom: '1px solid color-mix(in srgb, var(--rig-ink) 12%, transparent)',
        }}
      >
        <span style={nameplateStyle}>{paper.name}</span>
      </div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          fontFamily: 'var(--font-sans-condensed)',
          fontSize: '10px',
          letterSpacing: '0.18em',
          color: 'var(--rig-ink-soft)',
          textTransform: 'uppercase',
        }}
      >
        <span>{editionLabel}</span>
        <span>{LANG_LABEL[paper.language] ?? paper.language.toUpperCase()}</span>
      </div>
      <div
        style={{
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          color: paper.clip_count > 0 ? 'var(--rig-ink)' : 'var(--rig-ink-soft)',
          fontSize: '13px',
        }}
      >
        {paper.clip_count > 0
          ? `${paper.clip_count} ${paper.clip_count === 1 ? 'cutting' : 'cuttings'}`
          : 'Full edition only'}
      </div>
    </button>
  )
}

interface NewsstandProps {
  papers: PaperSummary[]
  langFilter: string
  onLangFilterChange: (lang: string) => void
  onPaperClick: (paper: PaperSummary) => void
}

export function Newsstand({
  papers, langFilter, onLangFilterChange, onPaperClick,
}: NewsstandProps) {
  const availableLangs = useMemo(() => {
    const set = new Set<string>()
    papers.forEach(p => set.add(p.language))
    return Array.from(set).sort()
  }, [papers])

  const visiblePapers = useMemo(
    () =>
      langFilter === 'all'
        ? papers
        : papers.filter(p => p.language === langFilter),
    [papers, langFilter],
  )

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div
        role="group"
        aria-label="Filter by language"
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '8px',
          alignItems: 'center',
        }}
        data-testid="newsstand-filter-rail"
      >
        <span
          style={{
            fontFamily: 'var(--font-sans-condensed)',
            fontSize: '10px',
            letterSpacing: '0.2em',
            color: 'var(--rig-ink-soft)',
            textTransform: 'uppercase',
            marginRight: '6px',
          }}
        >
          Filter
        </span>
        <FilterPill
          label="ALL"
          active={langFilter === 'all'}
          onClick={() => onLangFilterChange('all')}
        />
        {availableLangs.map(l => (
          <FilterPill
            key={l}
            label={LANG_LABEL[l] ?? l.toUpperCase()}
            active={langFilter === l}
            onClick={() => onLangFilterChange(l)}
          />
        ))}
      </div>

      {visiblePapers.length === 0 ? (
        <DeskMemo
          kicker="DESK MEMO"
          headline="No editions on the desk today."
          body="The morning run starts at 07:30 IST. Fresh scans will appear here as the papers hit the desk."
        />
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
            gap: '20px',
          }}
          data-testid="newsstand-grid"
        >
          {visiblePapers.map(p => (
            <MastheadCard
              key={p.newspaper_id}
              paper={p}
              onClick={() => onPaperClick(p)}
            />
          ))}
        </div>
      )}
    </section>
  )
}

interface DeskMemoProps {
  kicker: string
  headline: string
  body: string
}

function DeskMemo({ kicker, headline, body }: DeskMemoProps) {
  return (
    <div
      style={{
        margin: '40px auto',
        maxWidth: '480px',
        padding: '28px 32px',
        background: 'var(--rig-paper-2)',
        border: '1px solid color-mix(in srgb, var(--rig-ink) 18%, transparent)',
        borderRadius: '4px',
        textAlign: 'center',
      }}
    >
      <div
        style={{
          fontFamily: 'var(--font-sans-condensed)',
          fontSize: '10px',
          letterSpacing: '0.22em',
          color: 'var(--rig-ink-soft)',
          textTransform: 'uppercase',
          marginBottom: '12px',
        }}
      >
        {kicker}
      </div>
      <div
        style={{
          fontFamily: 'var(--font-serif)',
          fontSize: '20px',
          fontStyle: 'italic',
          marginBottom: '8px',
        }}
      >
        {headline}
      </div>
      <div
        style={{
          fontFamily: 'var(--font-serif)',
          fontSize: '14px',
          color: 'var(--rig-ink-soft)',
          lineHeight: 1.5,
        }}
      >
        {body}
      </div>
    </div>
  )
}
