'use client'

/**
 * Brief Wizard — step-through redesigned daily intelligence brief.
 *
 * Renders ONE step at a time across 10 sections:
 *   1. At a Glance        (prose: SITUATION STATUS)
 *   2. The Day's Movers   (prose: KEY DEVELOPMENTS)
 *   3. Primary Sources    (evidence-driven: govt_docs[])
 *   4. The Print Press    (evidence-driven: newspaper_clippings[])
 *   5. Public Pulse       (evidence-driven: social_posts[])
 *   6. On The Wires       (evidence-driven: video_clips[])
 *   7. Entities Today     (prose: ENTITIES TODAY)
 *   8. Signals to Watch   (prose: SIGNALS TO WATCH)
 *   9. Financial Pulse    (prose: FINANCIAL PULSE)
 *  10. Source Coverage    (prose: SOURCE COVERAGE)
 *
 * Layout: sticky pulse header (always visible), left side-rail navigator,
 * main content area renders the active step, sticky bottom nav with
 * prev/next + step indicator. Keyboard: ←/→ steps; Esc returns to step 1.
 */

import { useEffect, useState } from 'react'
import type {
  ParsedBrief,
  GovtDocItem,
  SocialPostItem,
  NewspaperClipItem,
  VideoClipItem,
  SourceCounts,
} from '../lib/parseBrief'

/* ── Pillar palette ─────────────────────────────────────────────────────
   Each pillar's colour comes from CSS custom properties defined in
   `globals.css` for both the parchment and night themes. That is what
   makes the wizard usable in dark mode — hardcoded hex (the previous
   approach) made every label, border, and accent invisible against the
   night-paper background.

   `accent44` is a translucent variant of the accent — used for soft
   borders. We construct it via `color-mix(in srgb, …)` because
   appending an alpha-hex (`+ '44'`) to a `var(--…)` string does not
   work the way appending it to a literal hex would. */

type PillarKind = 'article' | 'govt' | 'paper' | 'social' | 'video'

interface PillarTokens {
  fg: string
  bg: string
  accent: string
  accentSoft: string
}

const PILLAR_COLORS: Record<PillarKind, PillarTokens> = {
  article: {
    fg:         'var(--rig-pillar-article-fg)',
    bg:         'var(--rig-pillar-article-bg)',
    accent:     'var(--rig-pillar-article-accent)',
    accentSoft: 'color-mix(in srgb, var(--rig-pillar-article-accent) 27%, transparent)',
  },
  govt: {
    fg:         'var(--rig-pillar-govt-fg)',
    bg:         'var(--rig-pillar-govt-bg)',
    accent:     'var(--rig-pillar-govt-accent)',
    accentSoft: 'color-mix(in srgb, var(--rig-pillar-govt-accent) 27%, transparent)',
  },
  paper: {
    fg:         'var(--rig-pillar-paper-fg)',
    bg:         'var(--rig-pillar-paper-bg)',
    accent:     'var(--rig-pillar-paper-accent)',
    accentSoft: 'color-mix(in srgb, var(--rig-pillar-paper-accent) 27%, transparent)',
  },
  social: {
    fg:         'var(--rig-pillar-social-fg)',
    bg:         'var(--rig-pillar-social-bg)',
    accent:     'var(--rig-pillar-social-accent)',
    accentSoft: 'color-mix(in srgb, var(--rig-pillar-social-accent) 27%, transparent)',
  },
  video: {
    fg:         'var(--rig-pillar-video-fg)',
    bg:         'var(--rig-pillar-video-bg)',
    accent:     'var(--rig-pillar-video-accent)',
    accentSoft: 'color-mix(in srgb, var(--rig-pillar-video-accent) 27%, transparent)',
  },
}

/* ── Step catalogue ───────────────────────────────────────────────────── */

interface StepDef {
  id: string
  num: string
  title: string
  subtitle: string
  pillar: PillarKind | 'mixed'
}

const STEPS: ReadonlyArray<StepDef> = [
  { id: 'glance',    num: '01', title: 'At a Glance',        subtitle: 'The 30-second read',        pillar: 'mixed' },
  { id: 'movers',    num: '02', title: 'The Day’s Movers',   subtitle: 'Multi-source developments', pillar: 'mixed' },
  { id: 'sources',   num: '03', title: 'Primary Sources',    subtitle: 'What the State said',       pillar: 'govt' },
  { id: 'press',     num: '04', title: 'The Print Press',    subtitle: 'Vernacular coverage',       pillar: 'paper' },
  { id: 'pulse',     num: '05', title: 'Public Pulse',       subtitle: 'Social signals',            pillar: 'social' },
  { id: 'wires',     num: '06', title: 'On The Wires',       subtitle: 'Video evidence',            pillar: 'video' },
  { id: 'entities',  num: '07', title: 'Entities Today',     subtitle: 'Per-person dossiers',       pillar: 'mixed' },
  { id: 'signals',   num: '08', title: 'Signals to Watch',   subtitle: 'Forward-looking',           pillar: 'social' },
  { id: 'finance',   num: '09', title: 'Financial Pulse',    subtitle: 'State finances & policy',   pillar: 'govt' },
  { id: 'coverage',  num: '10', title: 'Source Coverage',    subtitle: 'Pillar pulse and gaps',     pillar: 'mixed' },
] as const

/* ── Top-level component ──────────────────────────────────────────────── */

interface BriefWizardProps {
  brief: ParsedBrief
  onRegenerate?: () => void
}

export function BriefWizard({ brief, onRegenerate }: BriefWizardProps) {
  const [stepIndex, setStepIndex] = useState(0)
  const [railOpen, setRailOpen] = useState(false)

  /* keyboard nav: ←/→ steps, Esc → step 1 */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLElement) {
        const tag = e.target.tagName
        if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target.isContentEditable) return
      }
      if (e.key === 'ArrowRight') {
        setStepIndex((s) => Math.min(s + 1, STEPS.length - 1))
      } else if (e.key === 'ArrowLeft') {
        setStepIndex((s) => Math.max(s - 1, 0))
      } else if (e.key === 'Escape') {
        setStepIndex(0)
        setRailOpen(false)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  /* sync URL hash to active step (deep-linkable) */
  useEffect(() => {
    const id = STEPS[stepIndex]?.id
    if (id && typeof window !== 'undefined') {
      window.history.replaceState(null, '', `#${id}`)
    }
  }, [stepIndex])

  /* on mount, read hash if present */
  useEffect(() => {
    if (typeof window === 'undefined') return
    const hash = window.location.hash.replace('#', '')
    const idx = STEPS.findIndex((s) => s.id === hash)
    if (idx >= 0) setStepIndex(idx)
  }, [])

  const step = STEPS[stepIndex]

  return (
    <div className="brief-wizard" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <PulseHeader
        brief={brief}
        stepIndex={stepIndex}
        totalSteps={STEPS.length}
        onToggleRail={() => setRailOpen((o) => !o)}
        onRegenerate={onRegenerate}
      />

      <div style={{ flex: 1, display: 'flex', position: 'relative' }}>
        <SideRail
          steps={STEPS}
          activeIndex={stepIndex}
          onSelect={setStepIndex}
          mobileOpen={railOpen}
          onClose={() => setRailOpen(false)}
        />

        <main
          aria-live="polite"
          style={{
            flex: 1,
            padding: '32px clamp(20px, 5vw, 64px) 120px',
            maxWidth: '880px',
            margin: '0 auto',
            width: '100%',
          }}
        >
          <StepHeader step={step} />
          <StepBody step={step} brief={brief} />
        </main>
      </div>

      <BottomNav
        stepIndex={stepIndex}
        totalSteps={STEPS.length}
        steps={STEPS}
        onPrev={() => setStepIndex((s) => Math.max(s - 1, 0))}
        onNext={() => setStepIndex((s) => Math.min(s + 1, STEPS.length - 1))}
      />
    </div>
  )
}

/* ── Sticky pulse header ──────────────────────────────────────────────── */

interface PulseHeaderProps {
  brief: ParsedBrief
  stepIndex: number
  totalSteps: number
  onToggleRail: () => void
  onRegenerate?: () => void
}

function PulseHeader({ brief, stepIndex, totalSteps, onToggleRail, onRegenerate }: PulseHeaderProps) {
  const counts = brief.sourceCounts
  return (
    <header
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 30,
        background: 'var(--rig-paper-2)',
        color: 'var(--rig-ink)',
        borderBottom: '1px solid var(--rig-rule)',
        padding: '14px clamp(20px, 5vw, 64px)',
        backdropFilter: 'blur(6px)',
      }}
      role="banner"
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <button
            type="button"
            onClick={onToggleRail}
            aria-label="Toggle section list"
            style={{ ...iconButton, display: 'inline-flex' }}
          >
            ☰
          </button>
          <div>
            <div style={{ fontFamily: 'var(--font-serif, "Source Serif 4", Georgia, serif)', fontSize: 22, fontWeight: 600, letterSpacing: '-0.01em', lineHeight: 1.1, color: 'var(--rig-ink)' }}>
              The Brief
            </div>
            <div style={{ fontSize: 12, color: 'var(--rig-ink-3)', marginTop: 2, fontFamily: 'var(--font-sans, system-ui, sans-serif)' }}>
              {brief.date || 'Today'} · {brief.meta.briefDate}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {counts && <PillarChips counts={counts} />}
          <span style={stepCountChip} aria-live="polite">
            Step {stepIndex + 1} / {totalSteps}
          </span>
          {onRegenerate && (
            <button type="button" onClick={onRegenerate} style={textButton} aria-label="Regenerate brief">
              ↻ Refresh
            </button>
          )}
        </div>
      </div>
    </header>
  )
}

function PillarChips({ counts }: { counts: SourceCounts }) {
  const items: { label: string; value: number; pillar: PillarKind }[] = [
    { label: 'articles', value: counts.articles, pillar: 'article' },
    { label: 'govt orders', value: counts.govt_docs, pillar: 'govt' },
    { label: 'papers', value: counts.newspaper_clippings, pillar: 'paper' },
    { label: 'social', value: counts.social_posts, pillar: 'social' },
    { label: 'video', value: counts.video_clips, pillar: 'video' },
  ]
  return (
    <div role="group" aria-label="Pillar source counts" style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
      {items.map((it) => (
        <span
          key={it.label}
          style={{
            ...pillChip,
            background: PILLAR_COLORS[it.pillar].bg,
            color: PILLAR_COLORS[it.pillar].fg,
            borderColor: PILLAR_COLORS[it.pillar].accentSoft,
          }}
          aria-label={`${it.value} ${it.label}`}
        >
          <strong style={{ fontWeight: 700 }}>{it.value}</strong> {it.label}
        </span>
      ))}
    </div>
  )
}

/* ── Side rail ─────────────────────────────────────────────────────────── */

interface SideRailProps {
  steps: ReadonlyArray<StepDef>
  activeIndex: number
  onSelect: (idx: number) => void
  mobileOpen: boolean
  onClose: () => void
}

function SideRail({ steps, activeIndex, onSelect, mobileOpen, onClose }: SideRailProps) {
  return (
    <>
      {/* mobile overlay */}
      {mobileOpen && (
        <div
          onClick={onClose}
          aria-hidden="true"
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 25 }}
        />
      )}
      <nav
        aria-label="Brief sections"
        className="brief-side-rail"
        style={{
          position: 'sticky',
          top: 70,
          alignSelf: 'flex-start',
          width: 250,
          maxHeight: 'calc(100vh - 80px)',
          overflowY: 'auto',
          padding: '24px 12px 24px 4px',
          borderRight: '1px solid var(--rig-rule-hair, rgba(0,0,0,0.08))',
          flexShrink: 0,
        }}
      >
        <ol style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
          {steps.map((step, i) => {
            const active = i === activeIndex
            const accent =
              step.pillar === 'mixed'
                ? 'var(--rig-gold)'
                : PILLAR_COLORS[step.pillar].accent
            return (
              <li key={step.id}>
                <button
                  type="button"
                  onClick={() => { onSelect(i); onClose() }}
                  aria-current={active ? 'step' : undefined}
                  style={{
                    width: '100%',
                    textAlign: 'left',
                    background: 'transparent',
                    border: 'none',
                    borderLeft: `2px solid ${active ? 'var(--rig-gold)' : 'transparent'}`,
                    padding: '10px 14px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'baseline',
                    gap: 12,
                    fontFamily: 'var(--font-serif)',
                    color: active ? 'var(--rig-ink)' : 'var(--rig-ink-3)',
                    fontSize: 15,
                    transition: 'color 0.15s ease, border-color 0.15s ease',
                    borderRadius: 0,
                  }}
                  onFocus={(e) => { e.currentTarget.style.outline = `1px solid var(--rig-gold)` }}
                  onBlur={(e) => { e.currentTarget.style.outline = 'none' }}
                >
                  <span
                    className="rig-byline"
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontWeight: 600,
                      color: active ? 'var(--rig-gold)' : 'var(--rig-ink-4)',
                      minWidth: 22,
                      letterSpacing: '0.18em',
                    }}
                  >
                    {step.num}
                  </span>
                  <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                    <span style={{
                      fontStyle: active ? 'italic' : 'normal',
                      fontWeight: active ? 500 : 400,
                    }}>
                      {step.title}
                    </span>
                    <span
                      className="rig-byline"
                      style={{
                        fontSize: 10,
                        color: 'var(--rig-ink-4)',
                        marginTop: 2,
                        letterSpacing: '0.16em',
                      }}
                    >
                      {step.subtitle}
                    </span>
                  </span>
                </button>
              </li>
            )
          })}
        </ol>
      </nav>
    </>
  )
}

/* ── Active-step header ───────────────────────────────────────────────── */

function StepHeader({ step }: { step: StepDef }) {
  const accent =
    step.pillar === 'mixed'
      ? 'var(--rig-ink)'
      : PILLAR_COLORS[step.pillar].accent
  return (
    <div className="anim-fade-up" style={{ marginBottom: 28 }}>
      <div
        className="rig-byline"
        style={{
          color: 'var(--rig-gold)',
          letterSpacing: '0.32em',
          fontWeight: 600,
        }}
      >
        STEP {step.num}
      </div>
      <h1
        style={{
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontSize: 'clamp(28px, 4vw, 44px)',
          fontWeight: 500,
          letterSpacing: '-0.014em',
          color: 'var(--rig-ink)',
          margin: '6px 0',
          lineHeight: 1.04,
        }}
      >
        {step.title}
      </h1>
      <p
        style={{
          color: 'var(--rig-ink-3)',
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontSize: 17,
          margin: 0,
        }}
      >
        {step.subtitle}
      </p>
      <hr className="rig-rule-hair" style={{ marginTop: 18 }} />
    </div>
  )
}

/* ── Step body — dispatches by step.id ───────────────────────────────── */

function StepBody({ step, brief }: { step: StepDef; brief: ParsedBrief }) {
  switch (step.id) {
    case 'glance':    return <ProseStep text={brief.sections['SITUATION STATUS']}    inline />
    case 'movers':    return <ProseStep text={brief.sections['KEY DEVELOPMENTS']} />
    case 'sources':   return <PrimarySourcesStep docs={brief.evidence?.govt_docs ?? []} />
    case 'press':     return <PrintPressStep clips={brief.evidence?.newspaper_clippings ?? []} />
    case 'pulse':     return <PublicPulseStep posts={brief.evidence?.social_posts ?? []} />
    case 'wires':     return <OnTheWiresStep clips={brief.evidence?.video_clips ?? []} />
    case 'entities':  return <ProseStep text={brief.sections['ENTITIES TODAY']} />
    case 'signals':   return <ProseStep text={brief.sections['SIGNALS TO WATCH']} />
    case 'finance':   return <ProseStep text={brief.sections['FINANCIAL PULSE']} />
    case 'coverage':  return <ProseStep text={brief.sections['SOURCE COVERAGE']} />
    default:          return <p>Unknown step.</p>
  }
}

/* ── Prose step (SITUATION / DEVELOPMENTS / ENTITIES / SIGNALS / FINANCIAL / SOURCES) */

function ProseStep({ text, inline }: { text?: string; inline?: boolean }) {
  if (!text) {
    return <EmptyNote message="The brief did not contain this section. Re-generate to fill it in." />
  }
  return (
    <article
      className="anim-fade-up"
      style={{
        fontFamily: 'var(--font-serif, "Source Serif 4", Georgia, serif)',
        fontSize: inline ? 20 : 18,
        lineHeight: 1.65,
        color: 'var(--rig-ink)',
        whiteSpace: 'pre-wrap',
      }}
    >
      {text}
    </article>
  )
}

/* ── Step 03: Primary Sources (govt docs) ─────────────────────────────── */

function PrimarySourcesStep({ docs }: { docs: GovtDocItem[] }) {
  if (docs.length === 0) {
    return <EmptyNote message="No new government orders, circulars, or notifications today. Absence is itself a signal." />
  }
  return (
    <ul className="anim-fade-up" style={listReset}>
      {docs.map((d, i) => {
        const intel = (d.intel_json ?? {}) as Record<string, unknown>
        const what = typeof intel.what_it_does === 'string' ? intel.what_it_does : ''
        const date = (d.published_at ?? d.collected_at ?? '').slice(0, 10)
        return (
          <li key={d.doc_id ?? i} style={{ ...evidenceCard, borderLeftColor: PILLAR_COLORS.govt.accent }}>
            <header style={evidenceHeader}>
              <span style={{ ...pillChip, background: PILLAR_COLORS.govt.bg, color: PILLAR_COLORS.govt.fg }}>
                Govt Document
              </span>
              <span style={evidenceMeta}>
                {d.source_name ?? '(unknown department)'} · {date || '—'}
                {d.page_number ? ` · p.${d.page_number}` : ''}
              </span>
            </header>
            <h3 style={evidenceTitle}>{d.title || '(untitled order)'}</h3>
            {what && <p style={evidenceWhat}>What it does — {what}</p>}
            {d.snippet && <p style={evidenceSnippet}>{d.snippet}</p>}
          </li>
        )
      })}
    </ul>
  )
}

/* ── Step 04: The Print Press (newspaper clippings) ───────────────────── */

function PrintPressStep({ clips }: { clips: NewspaperClipItem[] }) {
  if (clips.length === 0) {
    return <EmptyNote message="No vernacular newspaper clippings retrieved today. The print desk hasn't filed yet, or none of today's editions match your monitored entities." />
  }
  return (
    <div
      className="anim-fade-up"
      style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 18 }}
    >
      {clips.map((n, i) => (
        <article key={n.clip_id ?? i} style={{ ...evidenceCard, borderLeftColor: PILLAR_COLORS.paper.accent, padding: 18 }}>
          <header style={evidenceHeader}>
            <span style={{ ...pillChip, background: PILLAR_COLORS.paper.bg, color: PILLAR_COLORS.paper.fg }}>
              Newspaper
            </span>
            <span style={evidenceMeta}>
              {n.newspaper ?? '—'} ({n.language ?? '?'}) · {(n.edition_date ?? '').slice(0, 10)}
              {n.page_number ? ` · p.${n.page_number}` : ''}
            </span>
          </header>
          <h3 style={{ ...evidenceTitle, fontSize: 18 }} lang={langTag(n.language)}>
            {n.headline ?? '(headline unavailable)'}
          </h3>
          {n.text_snippet && <p style={evidenceSnippet} lang={langTag(n.language)}>{n.text_snippet}</p>}
          {(n.topic_category || n.geo_primary) && (
            <div style={{ display: 'flex', gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
              {n.topic_category && <span style={tagChip}>{n.topic_category}</span>}
              {n.geo_primary && <span style={tagChip}>{n.geo_primary}</span>}
            </div>
          )}
        </article>
      ))}
    </div>
  )
}

/* ── Step 05: Public Pulse (social posts) ─────────────────────────────── */

function PublicPulseStep({ posts }: { posts: SocialPostItem[] }) {
  if (posts.length === 0) {
    return <EmptyNote message="No relevant social signals retrieved today. Either the social collectors are between cycles, or your monitored topics aren't trending right now." />
  }
  // Group by platform
  const byPlatform = posts.reduce<Record<string, SocialPostItem[]>>((acc, p) => {
    const key = (p.platform ?? 'other').toLowerCase()
    if (!acc[key]) acc[key] = []
    acc[key].push(p)
    return acc
  }, {})

  return (
    <div className="anim-fade-up" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 18 }}>
      {Object.entries(byPlatform).map(([plat, items]) => {
        const avgSent = avgSentiment(items)
        return (
          <article key={plat} style={{ ...evidenceCard, borderLeftColor: PILLAR_COLORS.social.accent }}>
            <header style={evidenceHeader}>
              <span style={{ ...pillChip, background: PILLAR_COLORS.social.bg, color: PILLAR_COLORS.social.fg }}>
                {plat.toUpperCase()}
              </span>
              <span style={evidenceMeta} aria-label={`${items.length} posts, sentiment ${describeSentiment(avgSent)}`}>
                {items.length} posts · {describeSentiment(avgSent)} {sentimentArrow(avgSent)}
              </span>
            </header>
            <ul style={listReset}>
              {items.slice(0, 3).map((p, i) => (
                <li key={p.post_id ?? i} style={{ marginTop: 12, paddingTop: 12, borderTop: i === 0 ? 'none' : '1px dotted var(--rig-rule)' }}>
                  <div style={{ ...evidenceMeta, marginBottom: 4 }}>
                    @{p.author ?? 'unknown'} · {(p.posted_at ?? '').slice(0, 10)}
                    {typeof p.sentiment === 'number' && (
                      <> · <span aria-label={`Sentiment ${p.sentiment.toFixed(2)}`}>
                        {p.sentiment >= 0 ? '+' : ''}{p.sentiment.toFixed(2)}
                      </span></>
                    )}
                  </div>
                  <p style={{ ...evidenceSnippet, marginTop: 0 }}>{p.text_snippet}</p>
                  {p.url && (
                    <a href={p.url} target="_blank" rel="noopener noreferrer" style={evidenceLink}>
                      Open post →
                    </a>
                  )}
                </li>
              ))}
            </ul>
          </article>
        )
      })}
    </div>
  )
}

/* ── Step 06: On The Wires (video clips) ──────────────────────────────── */

function OnTheWiresStep({ clips }: { clips: VideoClipItem[] }) {
  if (clips.length === 0) {
    return <EmptyNote message="No relevant video clips today. YouTube collectors haven't matched any monitored entities in the last cycle." />
  }
  return (
    <ul className="anim-fade-up" style={listReset}>
      {clips.map((c, i) => {
        const startSec = c.start_seconds ?? 0
        const mins = Math.floor(startSec / 60)
        const secs = startSec % 60
        const ts = `${mins}:${String(secs).padStart(2, '0')}`
        return (
          <li key={c.video_id ?? i} style={{ ...evidenceCard, borderLeftColor: PILLAR_COLORS.video.accent }}>
            <header style={evidenceHeader}>
              <span style={{ ...pillChip, background: PILLAR_COLORS.video.bg, color: PILLAR_COLORS.video.fg }}>
                Video
              </span>
              <span style={evidenceMeta}>
                {c.channel ?? '—'} · @ {ts}
                {c.matched_entity ? ` · entity: ${c.matched_entity}` : ''}
              </span>
            </header>
            <h3 style={evidenceTitle}>{c.title ?? '(untitled clip)'}</h3>
            {c.text_snippet && (
              <blockquote style={{ ...evidenceSnippet, borderLeft: `3px solid ${PILLAR_COLORS.video.accentSoft}`, paddingLeft: 10, fontStyle: 'italic', marginLeft: 0 }}>
                “{c.text_snippet}”
              </blockquote>
            )}
            {c.embed_url && (
              <a href={c.embed_url + (c.embed_url.includes('?') ? '&' : '?') + `start=${Math.max(0, startSec - 1)}`} target="_blank" rel="noopener noreferrer" style={evidenceLink}>
                Watch from {ts} →
              </a>
            )}
          </li>
        )
      })}
    </ul>
  )
}

/* ── Bottom navigator ─────────────────────────────────────────────────── */

interface BottomNavProps {
  stepIndex: number
  totalSteps: number
  steps: ReadonlyArray<StepDef>
  onPrev: () => void
  onNext: () => void
}

function BottomNav({ stepIndex, totalSteps, steps, onPrev, onNext }: BottomNavProps) {
  const prevStep = stepIndex > 0 ? steps[stepIndex - 1] : null
  const nextStep = stepIndex < totalSteps - 1 ? steps[stepIndex + 1] : null
  return (
    <nav
      aria-label="Step navigation"
      style={{
        position: 'sticky',
        bottom: 0,
        zIndex: 20,
        background: 'var(--rig-paper-2)',
        color: 'var(--rig-ink)',
        borderTop: '1px solid var(--rig-rule)',
        padding: '12px clamp(20px, 5vw, 64px)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: 12,
        backdropFilter: 'blur(6px)',
      }}
    >
      <button
        type="button"
        onClick={onPrev}
        disabled={!prevStep}
        style={{ ...navButton, opacity: prevStep ? 1 : 0.3, cursor: prevStep ? 'pointer' : 'not-allowed' }}
        aria-label={prevStep ? `Previous: ${prevStep.title}` : 'No previous step'}
      >
        ◀ {prevStep ? prevStep.title : 'Start'}
      </button>

      <div style={{ flex: 1, textAlign: 'center', fontFamily: 'var(--font-sans, system-ui, sans-serif)', fontSize: 13, color: 'var(--rig-ink-3)' }}>
        Step {stepIndex + 1} of {totalSteps}
      </div>

      <button
        type="button"
        onClick={onNext}
        disabled={!nextStep}
        style={{ ...navButton, opacity: nextStep ? 1 : 0.3, cursor: nextStep ? 'pointer' : 'not-allowed' }}
        aria-label={nextStep ? `Next: ${nextStep.title}` : 'End of brief'}
      >
        {nextStep ? nextStep.title : 'Done'} →
      </button>
    </nav>
  )
}

/* ── Tiny helpers ─────────────────────────────────────────────────────── */

function EmptyNote({ message }: { message: string }) {
  return (
    <p
      className="anim-fade-up"
      style={{
        fontFamily: 'var(--font-serif, "Source Serif 4", Georgia, serif)',
        fontSize: 17,
        color: 'var(--rig-ink-3)',
        fontStyle: 'italic',
        padding: '24px 20px',
        background: 'var(--rig-overlay-2)',
        borderLeft: '3px solid var(--rig-rule-strong)',
      }}
    >
      {message}
    </p>
  )
}

function avgSentiment(items: SocialPostItem[]): number | null {
  const scored = items.map((p) => p.sentiment).filter((v): v is number => typeof v === 'number')
  if (scored.length === 0) return null
  return scored.reduce((a, b) => a + b, 0) / scored.length
}

function describeSentiment(avg: number | null): string {
  if (avg === null) return 'sentiment n/a'
  if (avg > 0.15) return 'positive'
  if (avg < -0.15) return 'negative'
  return 'mixed'
}

function sentimentArrow(avg: number | null): string {
  if (avg === null) return '—'
  if (avg > 0.15) return '▲'
  if (avg < -0.15) return '▼'
  return '—'
}

function langTag(lang?: string): string | undefined {
  if (!lang) return undefined
  const map: Record<string, string> = {
    telugu: 'te',
    urdu: 'ur',
    hindi: 'hi',
    marathi: 'mr',
    tamil: 'ta',
    bengali: 'bn',
    odia: 'or',
    kannada: 'kn',
    malayalam: 'ml',
    gujarati: 'gu',
    punjabi: 'pa',
    english: 'en',
  }
  return map[lang.toLowerCase()] ?? lang.slice(0, 2).toLowerCase()
}

/* ── Style tokens (kept inline so the component is self-contained) ───── */

const pillChip: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
  padding: '4px 10px',
  borderRadius: 999,
  fontSize: 12,
  border: '1px solid var(--rig-rule)',
  fontFamily: 'var(--font-sans, system-ui, sans-serif)',
  fontWeight: 500,
  whiteSpace: 'nowrap',
}

const stepCountChip: React.CSSProperties = {
  ...pillChip,
  background: 'var(--rig-ink)',
  color: 'var(--rig-paper)',
  border: 'none',
  fontWeight: 600,
}

const tagChip: React.CSSProperties = {
  ...pillChip,
  background: 'var(--rig-overlay-2)',
  color: 'var(--rig-ink-3)',
  fontSize: 11,
}

const iconButton: React.CSSProperties = {
  border: 'none',
  background: 'transparent',
  fontSize: 22,
  cursor: 'pointer',
  width: 36,
  height: 36,
  borderRadius: 4,
  color: 'var(--rig-ink)',
}

const textButton: React.CSSProperties = {
  border: '1px solid var(--rig-rule)',
  background: 'transparent',
  padding: '6px 14px',
  borderRadius: 999,
  cursor: 'pointer',
  fontSize: 13,
  fontFamily: 'var(--font-sans, system-ui, sans-serif)',
  color: 'var(--rig-ink)',
}

const navButton: React.CSSProperties = {
  ...textButton,
  fontFamily: 'var(--font-serif, "Source Serif 4", Georgia, serif)',
  fontSize: 15,
  border: 'none',
  padding: '8px 16px',
  background: 'transparent',
  color: 'var(--rig-ink)',
}

const evidenceCard: React.CSSProperties = {
  listStyle: 'none',
  background: 'var(--rig-card)',
  border: '1px solid var(--rig-card-border)',
  borderLeft: '3px solid var(--rig-ink)',
  padding: '20px 24px',
  marginBottom: 16,
  borderRadius: 4,
  color: 'var(--rig-ink)',
}

const evidenceHeader: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  flexWrap: 'wrap',
  marginBottom: 8,
}

const evidenceMeta: React.CSSProperties = {
  fontSize: 12,
  color: 'var(--rig-ink-3)',
  fontFamily: 'var(--font-sans, system-ui, sans-serif)',
}

const evidenceTitle: React.CSSProperties = {
  fontFamily: 'var(--font-serif, "Source Serif 4", Georgia, serif)',
  fontSize: 20,
  fontWeight: 600,
  margin: '4px 0 8px',
  letterSpacing: '-0.01em',
  color: 'var(--rig-ink)',
}

const evidenceWhat: React.CSSProperties = {
  fontFamily: 'var(--font-serif, "Source Serif 4", Georgia, serif)',
  fontSize: 15,
  fontStyle: 'italic',
  color: 'var(--rig-ink-2)',
  margin: '6px 0',
}

const evidenceSnippet: React.CSSProperties = {
  fontFamily: 'var(--font-serif, "Source Serif 4", Georgia, serif)',
  fontSize: 16,
  lineHeight: 1.55,
  color: 'var(--rig-ink)',
  margin: '8px 0 0',
}

const evidenceLink: React.CSSProperties = {
  display: 'inline-block',
  marginTop: 10,
  fontFamily: 'var(--font-sans, system-ui, sans-serif)',
  fontSize: 13,
  color: 'var(--rig-link)',
  textDecoration: 'underline',
}

const listReset: React.CSSProperties = { listStyle: 'none', padding: 0, margin: 0 }
