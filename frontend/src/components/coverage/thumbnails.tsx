/**
 * Procedural SVG thumbnails for the five Coverage panels.
 *
 * Style rules (all share these so the set reads as one family):
 *   - Pure black background, bone (#F2EEE3) and dim (#5E5E5E) tones only
 *   - One subtle accent (cyan #00C2FF or red #FF2D2D) per panel
 *   - Halftone dot pattern overlay on every thumbnail
 *   - Heavy use of single-pixel hairlines and geometric primitives
 *   - No raster images, no external assets
 *   - Scales cleanly from 200px to 800px wide
 *
 * Each thumbnail evokes its section without literal stock-icon imagery.
 */

import type { ReactNode } from 'react'

type ThumbProps = {
  /** Optional override for outer wrapper class */
  className?: string
}

/* ── Shared building blocks ────────────────────────────────────────────── */

const BG = '#000000'
const BONE = '#F2EEE3'
const DIM = '#5E5E5E'
const DIM_2 = '#2A2A2A'
const CYAN = '#00C2FF'
const RED = '#FF2D2D'

/** Halftone dot pattern — applied as a subtle overlay on every thumb. */
function HalftoneDefs({ id }: { id: string }) {
  return (
    <defs>
      <pattern
        id={`halftone-${id}`}
        x="0"
        y="0"
        width="6"
        height="6"
        patternUnits="userSpaceOnUse"
      >
        <circle cx="3" cy="3" r="0.6" fill={BONE} fillOpacity="0.18" />
      </pattern>
      <linearGradient id={`fade-${id}`} x1="0" x2="0" y1="0" y2="1">
        <stop offset="0%" stopColor={BG} stopOpacity="0" />
        <stop offset="100%" stopColor={BG} stopOpacity="0.85" />
      </linearGradient>
      {/* Subtle inner glow for the accent strip on hover (uses CSS vars when in DOM) */}
    </defs>
  )
}

function ThumbFrame({ id, children, className }: { id: string; children: ReactNode; className?: string }) {
  return (
    <svg
      viewBox="0 0 400 240"
      preserveAspectRatio="xMidYMid slice"
      className={className}
      style={{ display: 'block', width: '100%', height: '100%' }}
      aria-hidden="true"
    >
      <HalftoneDefs id={id} />
      <rect width="400" height="240" fill={BG} />
      {children}
      {/* Halftone overlay on top of everything */}
      <rect width="400" height="240" fill={`url(#halftone-${id})`} />
      {/* Bottom vignette */}
      <rect width="400" height="240" fill={`url(#fade-${id})`} />
    </svg>
  )
}

/* ── 1. Articles — vertical newsprint columns ─────────────────────────── */

export function ArticlesThumb({ className }: ThumbProps) {
  // Generate the column-text bars deterministically so layout is stable
  const columns = [40, 110, 180, 250, 320]
  return (
    <ThumbFrame id="articles" className={className}>
      {/* Single dramatic side-light wash */}
      <rect x="0" y="0" width="200" height="240" fill={BONE} fillOpacity="0.04" />
      {columns.map((x, ci) => (
        <g key={ci}>
          {/* Column rule */}
          <line x1={x - 8} y1="30" x2={x - 8} y2="210" stroke={DIM_2} strokeWidth="0.5" />
          {/* Column heading slab */}
          <rect x={x} y="34" width="50" height="6" fill={BONE} fillOpacity={0.85 - ci * 0.12} />
          <rect x={x} y="44" width="38" height="3" fill={DIM} fillOpacity="0.6" />
          {/* Body lines */}
          {Array.from({ length: 14 }).map((_, li) => {
            const w = 38 + ((ci + li) % 5) * 4
            const skip = (ci + li) % 7 === 6 // occasional gap
            if (skip) return null
            return (
              <rect
                key={li}
                x={x}
                y={56 + li * 11}
                width={w}
                height="1.5"
                fill={BONE}
                fillOpacity={0.32 - li * 0.012}
              />
            )
          })}
        </g>
      ))}
      {/* Subtle red kicker dot top-left */}
      <circle cx="22" cy="24" r="2" fill={RED} />
      <line x1="28" y1="24" x2="60" y2="24" stroke={RED} strokeOpacity="0.4" strokeWidth="0.5" />
    </ThumbFrame>
  )
}

/* ── 2. Newspaper — folded broadsheet with masthead ───────────────────── */

export function NewspaperThumb({ className }: ThumbProps) {
  return (
    <ThumbFrame id="newspaper" className={className}>
      {/* Paper plane tilted slightly — single dramatic raking light */}
      <g transform="rotate(-3 200 120)">
        <rect x="60" y="36" width="280" height="180" fill="#0E0E0E" />
        {/* Side-light wash */}
        <rect x="60" y="36" width="120" height="180" fill={BONE} fillOpacity="0.06" />
        {/* Masthead */}
        <rect x="74" y="50" width="252" height="22" fill={BONE} fillOpacity="0.78" />
        <rect x="74" y="76" width="120" height="2" fill={RED} fillOpacity="0.7" />
        {/* Lead headline */}
        <rect x="74" y="88" width="180" height="9" fill={BONE} fillOpacity="0.55" />
        <rect x="74" y="100" width="160" height="9" fill={BONE} fillOpacity="0.42" />
        {/* Body columns (3 narrow) */}
        {[74, 162, 250].map((cx, ci) => (
          <g key={ci}>
            {Array.from({ length: 11 }).map((_, li) => (
              <rect
                key={li}
                x={cx}
                y={120 + li * 8}
                width={56 + ((ci + li) % 3) * 4}
                height="1.2"
                fill={BONE}
                fillOpacity={0.22 - li * 0.014}
              />
            ))}
          </g>
        ))}
        {/* Fold crease */}
        <line x1="200" y1="36" x2="200" y2="216" stroke={BG} strokeWidth="2" />
        <line x1="200" y1="36" x2="200" y2="216" stroke={BONE} strokeWidth="0.5" strokeOpacity="0.2" />
      </g>
    </ThumbFrame>
  )
}

/* ── 3. TV — CRT screen with broadcast static ─────────────────────────── */

export function TvThumb({ className }: ThumbProps) {
  // Pre-compute static dot positions deterministically
  const statics = Array.from({ length: 90 }).map((_, i) => ({
    x: ((i * 37) % 280) + 60,
    y: ((i * 53) % 130) + 52,
    o: ((i * 13) % 7) / 10 + 0.1,
  }))
  return (
    <ThumbFrame id="tv" className={className}>
      {/* Screen frame (rounded slightly via clip-path on inner) */}
      <rect x="48" y="40" width="304" height="160" fill="#0A0A0A" stroke={DIM_2} strokeWidth="1" />
      {/* Inner screen with subtle gradient suggesting CRT bulge */}
      <defs>
        <radialGradient id="tv-glow" cx="50%" cy="50%" r="60%">
          <stop offset="0%" stopColor={BONE} stopOpacity="0.10" />
          <stop offset="100%" stopColor={BG} stopOpacity="1" />
        </radialGradient>
      </defs>
      <rect x="60" y="50" width="280" height="140" fill="url(#tv-glow)" />
      {/* Scanlines */}
      {Array.from({ length: 35 }).map((_, i) => (
        <line
          key={i}
          x1="60"
          y1={50 + i * 4}
          x2="340"
          y2={50 + i * 4}
          stroke={BONE}
          strokeOpacity="0.06"
          strokeWidth="1"
        />
      ))}
      {/* Static noise dots */}
      {statics.map((s, i) => (
        <circle key={i} cx={s.x} cy={s.y} r="0.8" fill={BONE} fillOpacity={s.o} />
      ))}
      {/* REC indicator */}
      <circle cx="68" cy="58" r="2.5" fill={RED} />
      <text
        x="76"
        y="61"
        fill={RED}
        fontFamily="JetBrains Mono, monospace"
        fontSize="7"
        letterSpacing="0.2em"
      >
        LIVE
      </text>
      {/* Channel tag bottom-right */}
      <text
        x="332"
        y="184"
        fill={BONE}
        fillOpacity="0.55"
        fontFamily="JetBrains Mono, monospace"
        fontSize="7"
        letterSpacing="0.2em"
        textAnchor="end"
      >
        CH 03
      </text>
      {/* Bezel base */}
      <rect x="170" y="200" width="60" height="6" fill="#0A0A0A" stroke={DIM_2} strokeWidth="0.5" />
    </ThumbFrame>
  )
}

/* ── 4. Social — network constellation of nodes & edges ───────────────── */

export function SocialThumb({ className }: ThumbProps) {
  // Nodes: deterministic constellation
  const nodes = [
    { x: 90, y: 60, r: 4 },
    { x: 200, y: 50, r: 6 },
    { x: 310, y: 90, r: 5 },
    { x: 140, y: 120, r: 7 },
    { x: 260, y: 150, r: 4 },
    { x: 80, y: 180, r: 5 },
    { x: 200, y: 200, r: 6 },
    { x: 340, y: 180, r: 4 },
    { x: 60, y: 100, r: 3 },
    { x: 180, y: 80, r: 3 },
    { x: 280, y: 50, r: 3 },
    { x: 120, y: 170, r: 3 },
    { x: 320, y: 130, r: 3 },
  ]
  // Edges between selected pairs
  const edges: Array<[number, number]> = [
    [0, 1], [1, 2], [1, 3], [3, 4], [3, 5], [5, 6],
    [4, 6], [4, 7], [2, 7], [0, 8], [9, 1], [10, 2],
    [11, 5], [12, 4], [3, 9], [6, 11],
  ]
  return (
    <ThumbFrame id="social" className={className}>
      {/* Edges */}
      {edges.map(([a, b], i) => {
        const A = nodes[a], B = nodes[b]
        if (!A || !B) return null
        return (
          <line
            key={i}
            x1={A.x}
            y1={A.y}
            x2={B.x}
            y2={B.y}
            stroke={BONE}
            strokeOpacity={0.18}
            strokeWidth="0.6"
          />
        )
      })}
      {/* Nodes — outer ring + inner dot */}
      {nodes.map((n, i) => (
        <g key={i}>
          <circle cx={n.x} cy={n.y} r={n.r} fill="none" stroke={BONE} strokeOpacity="0.5" strokeWidth="0.8" />
          <circle cx={n.x} cy={n.y} r={n.r * 0.35} fill={BONE} fillOpacity="0.85" />
        </g>
      ))}
      {/* One hot node — cyan accent */}
      <g>
        <circle cx="200" cy="50" r="10" fill="none" stroke={CYAN} strokeOpacity="0.4" strokeWidth="0.6" />
        <circle cx="200" cy="50" r="14" fill="none" stroke={CYAN} strokeOpacity="0.18" strokeWidth="0.4" />
      </g>
      {/* Counter top-right */}
      <text
        x="380"
        y="28"
        fill={BONE}
        fillOpacity="0.55"
        fontFamily="JetBrains Mono, monospace"
        fontSize="7"
        letterSpacing="0.2em"
        textAnchor="end"
      >
        13 NODES
      </text>
    </ThumbFrame>
  )
}

/* ── 5. Govt Docs — sealed envelope with redactions ───────────────────── */

export function GovtThumb({ className }: ThumbProps) {
  return (
    <ThumbFrame id="govt" className={className}>
      {/* Document body — slightly tilted */}
      <g transform="rotate(2 200 120)">
        {/* Side-light wash */}
        <rect x="80" y="40" width="240" height="170" fill={BONE} fillOpacity="0.05" />
        <rect x="80" y="40" width="240" height="170" fill="none" stroke={BONE} strokeOpacity="0.22" strokeWidth="1" />
        {/* Letterhead block */}
        <rect x="92" y="54" width="160" height="6" fill={BONE} fillOpacity="0.6" />
        <rect x="92" y="64" width="100" height="3" fill={BONE} fillOpacity="0.32" />
        {/* Hairline divider */}
        <line x1="92" y1="76" x2="308" y2="76" stroke={BONE} strokeOpacity="0.32" strokeWidth="0.6" />
        {/* Doc number / classification stripe */}
        <text
          x="92"
          y="90"
          fill={BONE}
          fillOpacity="0.5"
          fontFamily="JetBrains Mono, monospace"
          fontSize="6"
          letterSpacing="0.2em"
        >
          DOC #2841 / 2026
        </text>
        {/* Body paragraphs with redaction bars */}
        {Array.from({ length: 9 }).map((_, li) => {
          const isRedacted = li === 2 || li === 5 || li === 7
          const w = 200 + ((li * 7) % 16)
          if (isRedacted) {
            return (
              <g key={li}>
                <rect x="92" y={102 + li * 11} width={36} height="5" fill={BONE} fillOpacity="0.22" />
                <rect x="132" y={102 + li * 11} width={68} height="5" fill={BONE} fillOpacity="0.85" />
                <rect x="204" y={102 + li * 11} width={w - 116} height="5" fill={BONE} fillOpacity="0.22" />
              </g>
            )
          }
          return (
            <rect
              key={li}
              x="92"
              y={102 + li * 11}
              width={w}
              height="1.5"
              fill={BONE}
              fillOpacity={0.28 - li * 0.012}
            />
          )
        })}
        {/* Red wax seal / classified stamp */}
        <g transform="translate(280 188) rotate(-12)">
          <rect x="-32" y="-10" width="64" height="20" fill="none" stroke={RED} strokeWidth="1.2" />
          <text
            x="0"
            y="3"
            fill={RED}
            fontFamily="JetBrains Mono, monospace"
            fontSize="7"
            letterSpacing="0.3em"
            textAnchor="middle"
            fontWeight="600"
          >
            CLASSIFIED
          </text>
        </g>
      </g>
    </ThumbFrame>
  )
}

/* ── Lookup ────────────────────────────────────────────────────────────── */

export type CoverageSlug = 'articles' | 'newspaper' | 'tv' | 'social' | 'govt'

export function CoverageThumb({ slug, className }: { slug: CoverageSlug; className?: string }) {
  switch (slug) {
    case 'articles':  return <ArticlesThumb className={className} />
    case 'newspaper': return <NewspaperThumb className={className} />
    case 'tv':        return <TvThumb className={className} />
    case 'social':    return <SocialThumb className={className} />
    case 'govt':      return <GovtThumb className={className} />
  }
}
