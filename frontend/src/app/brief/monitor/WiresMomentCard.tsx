'use client'

import { useEffect, useRef, useState } from 'react'
import type { Pillar } from './types'
import { PILLAR_LABEL } from './types'
import { timeAgo } from './normalizers'

/**
 * Auto-rotating "Story of the Moment" card.
 *
 * Shows ONE top story at a time, rotates every 8s, pauses on hover, ◀ ▶
 * keys + dot pagination to jump. Each card is rich: rank numeral,
 * criticality pill, pillar tag, headline, source · category · time, and
 * a click handoff to the relevant pillar room.
 *
 * Criticality is computed deterministically (no LLM) from pillar
 * diversity in the time window, recency, and tier.
 */

export interface WireStory {
  id: string
  pillar: Pillar
  headline: string
  source: string | null
  timestamp: string | null
  topic: string | null
  href: string
  /** Tier 1/2/3 if known (articles only). */
  tier: number | null
  /** Bonus signals — sentiment magnitude, volume spike. */
  sentiment: number | null
  /** Lead / snippet text — gives the card the extra body the headline
   * alone can't carry. 1-3 sentences when available. */
  snippet: string | null
  /** Optional matched entities to render as small chips below the body. */
  entities: string[]
}

export type CriticalityLabel = 'CRITICAL' | 'WATCH' | 'QUIET'

export interface ScoredStory extends WireStory {
  score: number
  label: CriticalityLabel
  /** Distinct pillars active in the same 6-hour window as this story. */
  pillarCohort: Set<Pillar>
}

const ROTATE_MS = 8_000

const PILLAR_ACCENT: Record<Pillar, string> = {
  articles: 'var(--rig-ink, #1a1a1a)',
  newspaper: 'var(--rig-copper, #7a5a2e)',
  social: 'var(--rig-slate, #1f5a7a)',
  clips: 'var(--rig-violet, #5a2e7a)',
  documents: 'var(--rig-oxblood, #7a1f1f)',
}

const PILLAR_TINT: Record<Pillar, string> = {
  articles: 'rgba(26, 26, 26, 0.04)',
  newspaper: 'rgba(122, 90, 46, 0.06)',
  social: 'rgba(31, 90, 122, 0.06)',
  clips: 'rgba(90, 46, 122, 0.06)',
  documents: 'rgba(122, 31, 31, 0.06)',
}

const CRITICALITY_TONE: Record<CriticalityLabel, { fg: string; bg: string; dot: string }> = {
  CRITICAL: { fg: 'var(--rig-oxblood, #7a1f1f)', bg: 'rgba(122, 31, 31, 0.10)', dot: 'var(--rig-oxblood, #7a1f1f)' },
  WATCH:    { fg: 'var(--rig-gold, #a87f2c)',    bg: 'rgba(168, 127, 44, 0.10)', dot: 'var(--rig-gold, #a87f2c)' },
  QUIET:    { fg: 'var(--rig-ink-3, #6b6660)',   bg: 'rgba(107, 102, 96, 0.08)', dot: 'var(--rig-ink-3, #6b6660)' },
}

interface WiresMomentCardProps {
  stories: ScoredStory[]
}

export function WiresMomentCard({ stories }: WiresMomentCardProps): React.ReactElement {
  const [activeIdx, setActiveIdx] = useState(0)
  const [paused, setPaused] = useState(false)
  const containerRef = useRef<HTMLDivElement | null>(null)

  // Reset to first story whenever the upstream list changes (so we don't
  // get stuck on an index that's now out of range).
  useEffect(() => {
    setActiveIdx((i) => (i >= stories.length ? 0 : i))
  }, [stories.length])

  // Auto-rotate every ROTATE_MS ms, pause on hover.
  useEffect(() => {
    if (paused || stories.length <= 1) return
    const id = setInterval(() => {
      setActiveIdx((i) => (i + 1) % stories.length)
    }, ROTATE_MS)
    return () => clearInterval(id)
  }, [paused, stories.length])

  // Keyboard navigation when the card area has focus.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!containerRef.current?.contains(document.activeElement) && document.activeElement !== document.body) {
        return
      }
      if (e.key === 'ArrowRight') {
        setActiveIdx((i) => (i + 1) % Math.max(1, stories.length))
      } else if (e.key === 'ArrowLeft') {
        setActiveIdx((i) => (i - 1 + Math.max(1, stories.length)) % Math.max(1, stories.length))
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [stories.length])

  if (stories.length === 0) {
    return (
      <div
        style={{
          minHeight: '270px',
          padding: '32px 28px',
          border: '1px solid var(--rig-rule)',
          borderTop: '3px solid var(--rig-ink-3)',
          background: 'var(--rig-paper-2)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--rig-ink-3)',
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
        }}
      >
        Reading the wires…
      </div>
    )
  }

  const story = stories[activeIdx] ?? stories[0]
  const accent = PILLAR_ACCENT[story.pillar]
  const tint = PILLAR_TINT[story.pillar]
  const tone = CRITICALITY_TONE[story.label]
  const ago = timeAgo(story.timestamp)

  return (
    <div
      ref={containerRef}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      style={{ position: 'relative' }}
    >
      <a
        key={story.id}
        href={story.href}
        target={story.href.startsWith('http') ? '_blank' : undefined}
        rel={story.href.startsWith('http') ? 'noopener noreferrer' : undefined}
        style={{ textDecoration: 'none', color: 'inherit', display: 'block' }}
      >
        <article
          className="anim-fade-up card-lift"
          style={{
            background: tint,
            border: '1px solid var(--rig-rule)',
            borderTop: `3px solid ${accent}`,
            padding: '24px 30px 22px',
            minHeight: '320px',
            display: 'grid',
            gridTemplateColumns: 'auto 1fr auto',
            gridTemplateRows: 'auto auto 1fr auto',
            columnGap: '22px',
            rowGap: '12px',
            cursor: 'pointer',
          }}
        >
          {/* Top-left: rank numeral spans header + headline rows */}
          <span
            style={{
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              fontSize: 'clamp(40px, 4vw, 56px)',
              lineHeight: 1,
              color: accent,
              fontWeight: 400,
              gridColumn: '1 / 2',
              gridRow: '1 / 3',
            }}
            aria-hidden="true"
          >
            №{String(activeIdx + 1).padStart(2, '0')}
          </span>

          {/* Top-middle: pillar + topic kicker */}
          <div
            style={{
              gridColumn: '2 / 3',
              gridRow: '1 / 2',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              paddingTop: '6px',
            }}
          >
            <span
              className="rig-kicker"
              style={{ fontSize: '10px', color: accent, letterSpacing: '0.18em' }}
            >
              {PILLAR_LABEL[story.pillar]}
            </span>
            {story.topic && (
              <>
                <span style={{ color: 'var(--rig-ink-3)', fontSize: '10px' }}>·</span>
                <span
                  className="rig-kicker"
                  style={{ fontSize: '10px', color: 'var(--rig-ink-3)', letterSpacing: '0.14em' }}
                >
                  {story.topic}
                </span>
              </>
            )}
            {story.source && (
              <>
                <span style={{ color: 'var(--rig-ink-3)', fontSize: '10px' }}>·</span>
                <span
                  className="rig-byline"
                  style={{ fontSize: '10px', color: 'var(--rig-ink-3)' }}
                >
                  {story.source}
                </span>
              </>
            )}
          </div>

          {/* Top-right: criticality pill */}
          <span
            style={{
              gridColumn: '3 / 4',
              gridRow: '1 / 2',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '4px 10px 4px 8px',
              fontFamily: 'var(--font-mono)',
              fontSize: '10px',
              letterSpacing: '0.18em',
              fontWeight: 700,
              color: tone.fg,
              background: tone.bg,
              border: `1px solid ${tone.fg}33`,
              borderRadius: '999px',
              alignSelf: 'start',
              marginTop: '4px',
            }}
            aria-label={`Criticality ${story.label}`}
          >
            <span
              aria-hidden="true"
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                background: tone.dot,
                animation: story.label === 'CRITICAL' ? 'pulse-gold 2.2s ease-out infinite' : 'none',
              }}
            />
            {story.label}
          </span>

          {/* Headline — second row, spans middle + right.
           *
           * Translation rule: if the headline contains non-Latin script
           * (Telugu, Kannada, Hindi, Tamil, Bengali, Arabic, etc.) and an
           * English snippet/translation is available, we render BOTH at
           * the headline font size — original on top, English co-equal
           * below — so the reader is never asked to squint at a
           * translation that's smaller than the source. When the headline
           * is purely Latin we fall back to the original single-line
           * treatment. */}
          {(() => {
            const headline = story.headline || '(untitled)'
            const hasNonLatin = /[^ -ɏḀ-ỿ]/.test(headline)
            const englishSnippet = story.snippet?.trim()
            const headlineStyle = {
              gridColumn: '2 / 4' as const,
              fontSize: 'clamp(20px, 2vw, 26px)',
              lineHeight: 1.24,
              margin: 0,
              color: 'var(--rig-ink)',
              display: '-webkit-box',
              WebkitLineClamp: 3,
              WebkitBoxOrient: 'vertical' as const,
              overflow: 'hidden',
            }
            if (hasNonLatin && englishSnippet) {
              return (
                <div
                  style={{
                    gridColumn: '2 / 4',
                    gridRow: '2 / 3',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '6px',
                  }}
                >
                  <h2 className="rig-headline" style={{ ...headlineStyle, gridRow: undefined }}>
                    {headline}
                  </h2>
                  <p
                    className="rig-headline"
                    aria-label="English translation"
                    style={{
                      ...headlineStyle,
                      gridRow: undefined,
                      WebkitLineClamp: 3,
                      color: 'var(--rig-ink-2, #2c2722)',
                      fontStyle: 'italic',
                      opacity: 0.92,
                    }}
                  >
                    {englishSnippet}
                  </p>
                </div>
              )
            }
            if (hasNonLatin && !englishSnippet) {
              // Non-Latin headline, no translation available.
              // Surface a small placeholder so the user knows it's
              // pending rather than missing.
              return (
                <div
                  style={{
                    gridColumn: '2 / 4',
                    gridRow: '2 / 3',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '4px',
                  }}
                >
                  <h2 className="rig-headline" style={{ ...headlineStyle, gridRow: undefined }}>
                    {headline}
                  </h2>
                  <span
                    className="rig-byline"
                    style={{
                      fontSize: '11px',
                      fontStyle: 'italic',
                      color: 'var(--rig-ink-3, #6b6660)',
                      letterSpacing: '0.04em',
                    }}
                  >
                    Translation pending…
                  </span>
                </div>
              )
            }
            return (
              <h2 className="rig-headline" style={{ ...headlineStyle, gridRow: '2 / 3' }}>
                {headline}
              </h2>
            )
          })()}

          {/* Snippet / lead — third row, the new richness layer */}
          <div
            style={{
              gridColumn: '2 / 4',
              gridRow: '3 / 4',
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
              minWidth: 0,
            }}
          >
            {story.snippet && !/[^ -ɏḀ-ỿ]/.test(story.headline || '') && (
              <p
                className="rig-prose"
                style={{
                  fontSize: '14.5px',
                  lineHeight: 1.55,
                  margin: 0,
                  color: 'var(--rig-ink-2, #2c2722)',
                  fontFamily: 'var(--font-serif)',
                  display: '-webkit-box',
                  WebkitLineClamp: 4,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                }}
              >
                {story.snippet}
              </p>
            )}
            {story.entities.length > 0 && (
              <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                {story.entities.slice(0, 5).map((e) => (
                  <span
                    key={e}
                    style={{
                      padding: '2px 8px',
                      fontFamily: 'var(--font-mono)',
                      fontSize: '10px',
                      letterSpacing: '0.06em',
                      color: accent,
                      background: 'var(--rig-paper)',
                      border: `1px solid ${accent}33`,
                      borderRadius: '3px',
                    }}
                  >
                    {e}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Footer — corroboration ribbon + filed time */}
          <div
            style={{
              gridColumn: '2 / 4',
              gridRow: '4 / 5',
              display: 'flex',
              alignItems: 'center',
              gap: '14px',
              flexWrap: 'wrap',
              paddingTop: '10px',
              borderTop: '1px solid var(--rig-rule-hair)',
            }}
          >
            <CorroborationRibbon cohort={story.pillarCohort} active={story.pillar} />
            <span style={{ flex: 1 }} />
            {ago && (
              <span
                className="rig-byline"
                style={{ fontSize: '10px', color: 'var(--rig-ink-3)' }}
              >
                Filed {ago}
              </span>
            )}
          </div>
        </article>
      </a>

      {/* Dot pagination + prev/next, sits below the card */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '12px',
          marginTop: '14px',
        }}
      >
        <button
          type="button"
          onClick={() =>
            setActiveIdx((i) => (i - 1 + stories.length) % stories.length)
          }
          aria-label="Previous story"
          style={iconBtn}
        >
          ◀
        </button>
        {stories.map((s, i) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setActiveIdx(i)}
            aria-label={`Story ${i + 1}`}
            aria-current={i === activeIdx ? 'true' : undefined}
            style={{
              width: i === activeIdx ? '24px' : '8px',
              height: '8px',
              borderRadius: '4px',
              border: 'none',
              padding: 0,
              background: i === activeIdx ? accent : 'var(--rig-rule)',
              cursor: 'pointer',
              transition: 'width 0.25s ease, background 0.2s ease',
            }}
          />
        ))}
        <button
          type="button"
          onClick={() => setActiveIdx((i) => (i + 1) % stories.length)}
          aria-label="Next story"
          style={iconBtn}
        >
          ▶
        </button>
      </div>
    </div>
  )
}

function CorroborationRibbon({
  cohort,
  active,
}: {
  cohort: Set<Pillar>
  active: Pillar
}): React.ReactElement {
  const pillars: Pillar[] = ['articles', 'newspaper', 'social', 'clips', 'documents']
  return (
    <div
      style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}
      aria-label="Pillar corroboration"
      title={`Corroborated across: ${[...cohort].map((p) => PILLAR_LABEL[p]).join(', ')}`}
    >
      {pillars.map((p) => {
        const present = cohort.has(p)
        const isActive = p === active
        return (
          <span
            key={p}
            aria-hidden="true"
            style={{
              width: isActive ? '18px' : '12px',
              height: '4px',
              background: present ? PILLAR_ACCENT[p] : 'var(--rig-rule)',
              opacity: present ? 1 : 0.5,
              borderRadius: '2px',
            }}
          />
        )
      })}
      <span
        className="rig-byline"
        style={{ fontSize: '9px', marginLeft: '6px', color: 'var(--rig-ink-3)' }}
      >
        across {cohort.size} pillar{cohort.size === 1 ? '' : 's'}
      </span>
    </div>
  )
}

const iconBtn: React.CSSProperties = {
  border: '1px solid var(--rig-rule)',
  background: 'var(--rig-paper-2)',
  width: '28px',
  height: '28px',
  cursor: 'pointer',
  fontSize: '11px',
  color: 'var(--rig-ink-3)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: 0,
  borderRadius: '4px',
}

/* ── Criticality scorer (exported for use by parent) ──────────────────── */

export function scoreStory(item: WireStory, allItems: WireStory[]): ScoredStory {
  // Pillar cohort: distinct pillars within ±6h of this item's timestamp.
  const itemTs = item.timestamp ? Date.parse(item.timestamp) : Date.now()
  const window = 6 * 3600 * 1000
  const cohort = new Set<Pillar>([item.pillar])
  for (const other of allItems) {
    if (other === item) continue
    const ts = other.timestamp ? Date.parse(other.timestamp) : 0
    if (Math.abs(ts - itemTs) <= window) cohort.add(other.pillar)
  }

  const pillarFactor = Math.min(1, cohort.size / 4)
  const ageMs = Date.now() - itemTs
  const recencyFactor =
    ageMs < 60 * 60 * 1000 ? 1
      : ageMs < 6 * 60 * 60 * 1000 ? 0.7
        : ageMs < 24 * 60 * 60 * 1000 ? 0.4
          : 0.2

  const tierFactor =
    item.tier === 1 ? 1
      : item.tier === 2 ? 0.7
        : item.tier == null ? 0.6
          : 0.5

  const sentimentFactor = item.sentiment !== null ? Math.min(1, Math.abs(item.sentiment) * 2) : 0

  const score =
    pillarFactor * 0.35 +
    recencyFactor * 0.30 +
    tierFactor * 0.15 +
    sentimentFactor * 0.10 +
    0.10 // base — every retrieved item gets non-zero baseline

  const label: CriticalityLabel =
    score >= 0.75 ? 'CRITICAL' : score >= 0.45 ? 'WATCH' : 'QUIET'

  return { ...item, score, label, pillarCohort: cohort }
}
