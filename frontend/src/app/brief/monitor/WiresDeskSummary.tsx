'use client'

import { useEffect, useMemo, useState } from 'react'
import type { Pillar } from './types'
import { PILLAR_LABEL } from './types'
import type { ScoredStory } from './WiresMomentCard'

/**
 * Live Desk Summary — sectioned, user-oriented panel.
 *
 * Sections (top to bottom):
 *   1. WHAT'S DOMINANT — first 1-2 sentences from today's brief
 *      SITUATION STATUS (LLM-generated synthesis, already cached).
 *   2. TOP RIGHT NOW    — single most-critical story, with a verb-led
 *                         summary line.
 *   3. ON THE WIRES     — concrete pillar count tally.
 *   4. WORTH WATCHING   — a runner-up story (WATCH-grade).
 *   5. QUIET ON         — pillars with zero items today (absence is a
 *                         signal too).
 *
 * Each section has a sans-caps kicker label so the user knows what
 * they're reading. No symbol soup (∑ ◐ ⚑) — proper labels.
 */

interface WiresDeskSummaryProps {
  apiBase: string
  token: string | null
  paused: boolean
  topStories: ScoredStory[]
  pillarCounts: Record<Pillar, number>
}

const ANCHOR_POLL_MS = 5 * 60_000

export function WiresDeskSummary({
  apiBase,
  token,
  paused,
  topStories,
  pillarCounts,
}: WiresDeskSummaryProps): React.ReactElement {
  const [anchor, setAnchor] = useState<string | null>(null)
  const [anchorMissing, setAnchorMissing] = useState(false)

  useEffect(() => {
    if (!token) return
    let cancelled = false

    const tick = async (): Promise<void> => {
      if (paused) return
      try {
        const res = await fetch(`${apiBase}/api/brief/today`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (cancelled) return
        if (res.status === 404) {
          setAnchorMissing(true)
          return
        }
        if (!res.ok) return
        const json = (await res.json()) as { content?: string }
        const m = (json.content ?? '').match(
          /##\s+SITUATION STATUS\s*\n+([\s\S]*?)(?:\n---\n|$)/,
        )
        if (cancelled) return
        const prose = m ? m[1].trim() : null
        // Strip citation symbols ① ② ③ … and (Doc:…) etc. for the
        // summary panel — they confuse the eye out of the brief context.
        const stripped = prose ? stripCitations(prose) : null
        const compact = stripped ? takeSentences(stripped, 2) : null
        setAnchor(compact)
        setAnchorMissing(false)
      } catch {
        /* network error — keep prior anchor */
      }
    }

    void tick()
    const id = setInterval(() => void tick(), ANCHOR_POLL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [apiBase, token, paused])

  const sections = useMemo(
    () => buildSections(topStories, pillarCounts),
    [topStories, pillarCounts],
  )

  return (
    <aside
      className="anim-fade-up"
      style={{
        background: 'var(--rig-paper-2)',
        border: '1px solid var(--rig-rule)',
        padding: '22px 24px 24px',
        minHeight: '320px',
        display: 'flex',
        flexDirection: 'column',
        gap: '18px',
        position: 'relative',
      }}
    >
      <header
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: '10px',
        }}
      >
        <span
          className="rig-kicker rig-kicker-gold"
          style={{ fontSize: '10px' }}
        >
          Desk summary · live
        </span>
        <span style={{ flex: 1, height: '1px', background: 'var(--rig-rule-hair)' }} />
        <LiveDot />
      </header>

      {/* SECTION 1 — What's dominant (anchor from brief) */}
      <Section label="What's dominant today">
        {anchor ? (
          <p style={proseStyle}>{anchor}</p>
        ) : anchorMissing ? (
          <p style={mutedProseStyle}>
            Today&apos;s brief hasn&apos;t been generated yet. The dominant-story
            line will appear once it&apos;s filed.
          </p>
        ) : (
          <p style={mutedProseStyle}>Reading the wires…</p>
        )}
      </Section>

      {/* SECTION 2 — Top right now (most critical) */}
      {sections.topCritical && (
        <Section label="Top right now" tone="critical">
          <p style={proseStyle}>
            <strong style={{ color: 'var(--rig-oxblood)' }}>
              {sections.topCritical.headline}
            </strong>
            {sections.topCritical.context && <> — {sections.topCritical.context}</>}
          </p>
        </Section>
      )}

      {/* SECTION 3 — On the wires (counts) */}
      {sections.tally.length > 0 && (
        <Section label="On the wires now">
          <p style={proseStyle}>
            {sections.tally.map((t, i) => (
              <span key={t.pillar}>
                <strong style={{ color: 'var(--rig-oxblood)' }}>{t.count}</strong>{' '}
                {t.label.toLowerCase()}
                {i < sections.tally.length - 1
                  ? i === sections.tally.length - 2
                    ? ' and '
                    : ', '
                  : ''}
              </span>
            ))}
            <span>.</span>
          </p>
        </Section>
      )}

      {/* SECTION 4 — Worth watching (next-tier story) */}
      {sections.worthWatching && (
        <Section label="Worth watching" tone="watch">
          <p style={proseStyle}>{sections.worthWatching.headline}</p>
        </Section>
      )}

      {/* SECTION 5 — Quiet on (absences) */}
      {sections.quietOn.length > 0 && (
        <Section label="Quiet on">
          <p style={mutedProseStyle}>
            <em>{sections.quietOn.join(', ')}</em> — nothing came in today on
            {sections.quietOn.length === 1 ? ' this pillar.' : ' these pillars.'}
          </p>
        </Section>
      )}
    </aside>
  )
}

/* ── Section wrapper with kicker label ─────────────────────────────────── */

interface SectionProps {
  label: string
  tone?: 'critical' | 'watch' | 'neutral'
  children: React.ReactNode
}

function Section({ label, tone = 'neutral', children }: SectionProps): React.ReactElement {
  const accent =
    tone === 'critical' ? 'var(--rig-oxblood, #7a1f1f)'
      : tone === 'watch' ? 'var(--rig-gold, #a87f2c)'
        : 'var(--rig-ink-3, #6b6660)'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      <span
        className="rig-kicker"
        style={{
          fontSize: '9px',
          color: accent,
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
        }}
      >
        {label}
      </span>
      {children}
    </div>
  )
}

const proseStyle: React.CSSProperties = {
  fontFamily: 'var(--font-serif)',
  fontSize: '14.5px',
  lineHeight: 1.55,
  color: 'var(--rig-ink)',
  margin: 0,
}

const mutedProseStyle: React.CSSProperties = {
  ...proseStyle,
  color: 'var(--rig-ink-3)',
  fontStyle: 'italic',
  fontSize: '13.5px',
}

/* ── Section builder ───────────────────────────────────────────────────── */

interface BuiltSections {
  topCritical: { headline: string; context: string | null } | null
  tally: { pillar: Pillar; label: string; count: number }[]
  worthWatching: { headline: string } | null
  quietOn: string[]
}

function buildSections(
  stories: ScoredStory[],
  counts: Record<Pillar, number>,
): BuiltSections {
  const critical = stories.find((s) => s.label === 'CRITICAL')
  const watch = stories.find((s) => s.label === 'WATCH' && s !== critical)

  const topCritical = critical
    ? {
        headline: truncate(critical.headline, 110),
        context:
          critical.pillarCohort.size >= 2
            ? `corroborated across ${critical.pillarCohort.size} pillars`
            : null,
      }
    : null

  const tally: BuiltSections['tally'] = (
    ['articles', 'newspaper', 'social', 'clips', 'documents'] as Pillar[]
  )
    .map((p) => ({ pillar: p, label: PILLAR_LABEL[p], count: counts[p] ?? 0 }))
    .filter((t) => t.count > 0)

  const worthWatching = watch ? { headline: truncate(watch.headline, 110) } : null

  const quietOn = (
    ['articles', 'newspaper', 'social', 'clips', 'documents'] as Pillar[]
  )
    .filter((p) => (counts[p] ?? 0) === 0)
    .map((p) => PILLAR_LABEL[p])

  return { topCritical, tally, worthWatching, quietOn }
}

/* ── Helpers ───────────────────────────────────────────────────────────── */

function takeSentences(prose: string, n: number): string {
  const parts = prose.split(/(?<=[.!?])\s+/).slice(0, n)
  return parts.join(' ').trim()
}

function stripCitations(prose: string): string {
  // Remove circled-numeral citations and (Doc:…) (Social:…) (Paper:…)
  // (Video:…) parentheticals so the desk summary reads cleanly without
  // looking like the brief's evidence-heavy version.
  return prose
    .replace(/[①-⑳]/g, '')
    .replace(/\((?:Doc|Social|Paper|Video):[^)]+\)/g, '')
    .replace(/\[Established:[^\]]+\]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s
  return `${s.slice(0, n - 1)}…`
}

function LiveDot(): React.ReactElement {
  return (
    <span
      aria-hidden="true"
      style={{
        display: 'inline-block',
        width: '6px',
        height: '6px',
        borderRadius: '50%',
        background: 'var(--rig-oxblood)',
        animation: 'pulse-gold 2.2s ease-out infinite',
      }}
    />
  )
}
