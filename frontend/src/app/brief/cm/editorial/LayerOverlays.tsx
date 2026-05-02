'use client'

/**
 * Per-layer atmospheric overlays — each layer transforms the *mood* of
 * the map, not just stamps icons on it. Pure SVG (no images), uses
 * filters, patterns and animation defined in TelanganaMap's <defs>.
 *
 * Treatments:
 *
 *   News Hotspot — wax-red ink blooms (Gaussian-blurred radial fields)
 *                  spreading outward from the day's top-3 districts.
 *   Sentiment    — storm-cloud turbulence over negative districts;
 *                  italic-serif caption marking the dominant cell.
 *   ACLED        — paper-darkening wash + irregular bloodstain blots
 *                  (turbulence-displaced) at every event district,
 *                  pulsing on a slow heartbeat.
 *   Mandi        — flowing trade-route bezier caravans from producer
 *                  districts to the Hyderabad market hub. Commodity
 *                  letter-stamps anchor each origin.
 *   Welfare      — woven-thread fabric texture across districts; at-
 *                  risk districts show frayed sparse hatch + a small
 *                  "tear" mark.
 *   Power        — living grid: bezier power lines flow from Hyderabad
 *                  with animated dash-offset, transformer glyphs at
 *                  substations, ⚡ flicker at stressed feeders.
 *   Stability    — turbulent storm cells over stressed districts; calm
 *                  golden-hour wash over stable ones.
 */

import {
  ACLED_FEED,
  MANDI_FEED,
  NEWS_FEED,
  POWER_FEED,
  SENTIMENT_FEED,
  STABILITY_FEED,
  WELFARE_FEED,
} from './layer-feeds'
import { findCentroid } from './layers'
import { TELANGANA_DISTRICTS } from './telangana-geo'
import styles from './styles.module.css'

interface LayerOverlaysProps {
  activeLayerId: string
}

export function LayerOverlays({ activeLayerId }: LayerOverlaysProps) {
  switch (activeLayerId) {
    case 'news-hotspot':
      return <NewsHotspotOverlay />
    case 'sentiment':
      return <SentimentOverlay />
    case 'acled':
      return <AcledOverlay />
    case 'mandi':
      return <MandiOverlay />
    case 'welfare':
      return <WelfareOverlay />
    case 'power':
      return <PowerOverlay />
    case 'stability':
      return <StabilityOverlay />
    default:
      return null
  }
}

/* ------------------------------------------------------------------ */
/* News Hotspot — wax-red ink blooms                                   */
/* ------------------------------------------------------------------ */

function NewsHotspotOverlay() {
  const seen = new Set<string>()
  const top = NEWS_FEED.filter((n) => {
    const id = n.district.toLowerCase()
    if (seen.has(id) || id === 'statewide') return false
    seen.add(id)
    return true
  }).slice(0, 3)
  return (
    <g pointerEvents="none">
      {/* Soft ink blooms — the visual language. */}
      {top.map((n, i) => {
        const c = findCentroid(slug(n.district))
        if (!c) return null
        const radius = 64 - i * 10
        return (
          <g key={i}>
            <circle
              cx={c.cx}
              cy={c.cy}
              r={radius}
              fill="url(#bloomNews)"
              filter="url(#inkBleed)"
              className={styles.bloomBreathe}
            />
          </g>
        )
      })}
      {/* Hairline ink-threads from top story to other mentioned districts. */}
      {top[0] &&
        top.slice(1).map((n, i) => {
          const a = findCentroid(slug(top[0]!.district))
          const b = findCentroid(slug(n.district))
          if (!a || !b) return null
          const midX = (a.cx + b.cx) / 2
          const midY = Math.min(a.cy, b.cy) - 30
          return (
            <path
              key={`thread-${i}`}
              d={`M ${a.cx} ${a.cy} Q ${midX} ${midY} ${b.cx} ${b.cy}`}
              stroke="#9c2b1f"
              strokeWidth={0.7}
              strokeOpacity={0.35}
              strokeDasharray="2 3"
              fill="none"
            />
          )
        })}
      {/* Lead-story marker — italic serif caption. */}
      {top[0] && (() => {
        const c = findCentroid(slug(top[0]!.district))
        if (!c) return null
        return (
          <g key="lead">
            <text
              x={c.cx + 22}
              y={c.cy - 18}
              fontFamily="'Tiempos Headline','Playfair Display','Georgia',serif"
              fontSize={9}
              letterSpacing="0.18em"
              fill="#9c2b1f"
              fontWeight={700}
            >
              TODAY&apos;S LEAD
            </text>
            <text
              x={c.cx + 22}
              y={c.cy - 6}
              fontFamily="'Tiempos Text','Lora','Georgia',serif"
              fontStyle="italic"
              fontSize={10}
              fill="#3a2a1a"
            >
              {top[0]!.district}
            </text>
          </g>
        )
      })()}
    </g>
  )
}

/* ------------------------------------------------------------------ */
/* Sentiment — storm-cloud turbulence over negative districts          */
/* ------------------------------------------------------------------ */

function SentimentOverlay() {
  return (
    <g pointerEvents="none">
      {/* Cloud cells over the four most-negative districts. */}
      {SENTIMENT_FEED.topNegativeDistricts.map((d, i) => {
        const c = findCentroid(slug(d.name))
        if (!c) return null
        const intensity = Math.min(1, Math.abs(d.value))
        const radius = 28 + intensity * 22
        return (
          <g key={i}>
            <ellipse
              cx={c.cx}
              cy={c.cy}
              rx={radius}
              ry={radius * 0.62}
              fill="url(#stormCloud)"
              filter="url(#turbulent)"
              opacity={0.55 + intensity * 0.25}
            />
          </g>
        )
      })}
      {/* Anchor caption beside the most-negative district. */}
      {(() => {
        const lead = SENTIMENT_FEED.topNegativeDistricts[0]
        const c = findCentroid(slug(lead.name))
        if (!c) return null
        return (
          <g>
            <text
              x={c.cx + 36}
              y={c.cy - 24}
              fontFamily="'Tiempos Headline','Playfair Display','Georgia',serif"
              fontSize={9}
              letterSpacing="0.2em"
              fill="#5a160e"
              fontWeight={700}
            >
              STORM CELL
            </text>
            <text
              x={c.cx + 36}
              y={c.cy - 12}
              fontFamily="'Tiempos Text','Lora','Georgia',serif"
              fontStyle="italic"
              fontSize={10}
              fill="#3a2a1a"
            >
              {lead.name} · {lead.value.toFixed(2)}
            </text>
          </g>
        )
      })()}
    </g>
  )
}

/* ------------------------------------------------------------------ */
/* ACLED — irregular bloodstain blots, slow heartbeat                  */
/* ------------------------------------------------------------------ */

function AcledOverlay() {
  // Aggregate event count per district from the feed.
  const counts: Record<string, number> = {}
  for (const e of ACLED_FEED.events) {
    const id = slug(e.district)
    counts[id] = (counts[id] ?? 0) + 1
  }
  return (
    <g pointerEvents="none">
      {/* Paper-darkening wash — gives blots more weight. */}
      <rect x={0} y={0} width={1000} height={900} fill="#3a2a1a" opacity={0.16} />
      {Object.entries(counts).map(([id, n]) => {
        const c = findCentroid(id)
        if (!c) return null
        const r = 14 + n * 3.5
        return (
          <g key={id} className={styles.heartbeat}>
            {/* Outer halo (turbulence-distorted, looks like ink seeping). */}
            <circle
              cx={c.cx}
              cy={c.cy}
              r={r + 9}
              fill="#5a160e"
              fillOpacity={0.25}
              filter="url(#turbulentSoft)"
            />
            {/* Main blot. */}
            <circle
              cx={c.cx}
              cy={c.cy}
              r={r}
              fill="#9c2b1f"
              filter="url(#turbulent)"
            />
            {/* Solid center reads the count. */}
            <circle cx={c.cx} cy={c.cy} r={r * 0.55} fill="#5a160e" />
            <text
              x={c.cx}
              y={c.cy + 4}
              textAnchor="middle"
              fontFamily="'Tiempos Headline','Playfair Display','Georgia',serif"
              fontSize={r * 0.7}
              fontWeight={700}
              fill="#f5f0e6"
            >
              {n}
            </text>
          </g>
        )
      })}
    </g>
  )
}

/* ------------------------------------------------------------------ */
/* Mandi — trade-route caravans flowing toward Hyderabad               */
/* ------------------------------------------------------------------ */

function MandiOverlay() {
  const hub = findCentroid('hyderabad')
  if (!hub) return null
  return (
    <g pointerEvents="none">
      {/* Flowing trade routes from producer districts to the hub. */}
      {MANDI_FEED.topMovers.map((m, i) => {
        const c = findCentroid(slug(m.district))
        if (!c || m.district.toLowerCase() === 'hyderabad') return null
        const colour =
          m.trend === 'up' ? '#9c2b1f' : m.trend === 'down' ? '#1d3557' : '#7a6a55'
        // Curve the path — caravan-like sweep, not straight line.
        const dx = hub.cx - c.cx
        const dy = hub.cy - c.cy
        const cpx = c.cx + dx * 0.5 + dy * 0.3
        const cpy = c.cy + dy * 0.5 - dx * 0.3
        const d = `M ${c.cx} ${c.cy} Q ${cpx} ${cpy} ${hub.cx} ${hub.cy}`
        return (
          <g key={i}>
            <path
              d={d}
              stroke={colour}
              strokeWidth={1.6}
              strokeOpacity={0.3}
              fill="none"
            />
            <path
              d={d}
              stroke={colour}
              strokeWidth={1.6}
              strokeOpacity={0.95}
              fill="none"
              strokeDasharray="6 6"
              className={styles.tradeFlow}
            />
            {/* Origin commodity stamp. */}
            <rect
              x={c.cx - 11}
              y={c.cy - 11}
              width={22}
              height={14}
              fill="#faf8f3"
              stroke={colour}
              strokeWidth={1.2}
              rx={1}
            />
            <text
              x={c.cx}
              y={c.cy - 1}
              textAnchor="middle"
              fontFamily="'Tiempos Headline','Playfair Display','Georgia',serif"
              fontSize={9}
              fontWeight={700}
              fill={colour}
            >
              {commodityLetter(m.commodity)}
            </text>
            <text
              x={c.cx}
              y={c.cy + 8}
              textAnchor="middle"
              fontFamily="'Söhne Mono','IBM Plex Mono','Menlo',monospace"
              fontSize={7}
              fontWeight={600}
              fill={colour}
            >
              {m.trend === 'up' ? '▲' : m.trend === 'down' ? '▼' : '→'} {m.delta}
            </text>
          </g>
        )
      })}
      {/* Hub marker. */}
      <g>
        <circle
          cx={hub.cx}
          cy={hub.cy}
          r={14}
          fill="none"
          stroke="#1a1a1a"
          strokeWidth={1.2}
        />
        <circle cx={hub.cx} cy={hub.cy} r={5} fill="#1a1a1a" />
        <text
          x={hub.cx + 16}
          y={hub.cy + 3}
          fontFamily="'Tiempos Headline','Playfair Display','Georgia',serif"
          fontSize={9}
          letterSpacing="0.18em"
          fontWeight={700}
          fill="#1a1a1a"
        >
          MARKET HUB
        </text>
      </g>
    </g>
  )
}

function commodityLetter(name: string): string {
  const n = name.toLowerCase()
  if (n.includes('chilli')) return 'CH'
  if (n.includes('cotton')) return 'CO'
  if (n.includes('paddy')) return 'PA'
  if (n.includes('turmeric')) return 'TU'
  if (n.includes('tomato')) return 'TM'
  if (n.includes('mango')) return 'MA'
  if (n.includes('maize')) return 'MZ'
  if (n.includes('onion')) return 'ON'
  return name.slice(0, 2).toUpperCase()
}

/* ------------------------------------------------------------------ */
/* Welfare — woven-thread fabric, frayed at-risk patches               */
/* ------------------------------------------------------------------ */

function WelfareOverlay() {
  return (
    <g pointerEvents="none">
      {/* Apply weave pattern to ALL districts — density via opacity below. */}
      {TELANGANA_DISTRICTS.map((d) => (
        <path
          key={d.id}
          d={d.d}
          fill="url(#weaveDense)"
          opacity={0.35}
          stroke="none"
        />
      ))}
      {/* Frayed patches over at-risk districts. */}
      {WELFARE_FEED.atRisk.map((r, i) => {
        const dist = TELANGANA_DISTRICTS.find((x) => x.id === slug(r.district))
        if (!dist) return null
        return (
          <g key={`r-${i}`}>
            <path d={dist.d} fill="url(#weaveSparse)" opacity={0.85} stroke="none" />
            <text
              x={dist.cx + 12}
              y={dist.cy - 12}
              fontFamily="'Tiempos Headline','Playfair Display','Georgia',serif"
              fontSize={9}
              fontStyle="italic"
              letterSpacing="0.16em"
              fontWeight={700}
              fill="#9c2b1f"
            >
              FRAYED
            </text>
          </g>
        )
      })}
      {/* Gold-thread accents over best-covered. */}
      {WELFARE_FEED.bestCovered.map((b, i) => {
        const dist = TELANGANA_DISTRICTS.find((x) => x.id === slug(b.district))
        if (!dist) return null
        return (
          <g key={`b-${i}`}>
            <path d={dist.d} fill="url(#weaveGold)" opacity={0.8} stroke="none" />
            <text
              x={dist.cx + 12}
              y={dist.cy - 12}
              fontFamily="'Tiempos Headline','Playfair Display','Georgia',serif"
              fontSize={9}
              fontStyle="italic"
              letterSpacing="0.16em"
              fontWeight={700}
              fill="#a07a45"
            >
              WOVEN
            </text>
          </g>
        )
      })}
    </g>
  )
}

/* ------------------------------------------------------------------ */
/* Power — living grid, flowing dashes, flickering stressed nodes      */
/* ------------------------------------------------------------------ */

function PowerOverlay() {
  const hub = findCentroid('hyderabad')
  if (!hub) return null
  // Build curved feeder routes from Hyderabad to each stressed district +
  // a few healthy ones (visual richness).
  const healthy = ['warangal', 'karimnagar', 'nizamabad', 'mahbubnagar']
  return (
    <g pointerEvents="none">
      {/* Healthy lines — calm ink-blue flow. */}
      {healthy.map((id, i) => {
        const c = findCentroid(id)
        if (!c) return null
        const dx = c.cx - hub.cx
        const dy = c.cy - hub.cy
        const cpx = hub.cx + dx * 0.55 - dy * 0.18
        const cpy = hub.cy + dy * 0.55 + dx * 0.18
        const d = `M ${hub.cx} ${hub.cy} Q ${cpx} ${cpy} ${c.cx} ${c.cy}`
        return (
          <g key={`h-${i}`}>
            <path d={d} stroke="#1d3557" strokeWidth={1.4} strokeOpacity={0.35} fill="none" />
            <path
              d={d}
              stroke="#1d3557"
              strokeWidth={1.4}
              strokeOpacity={0.85}
              strokeDasharray="3 8"
              fill="none"
              className={styles.gridFlow}
            />
            <SubstationGlyph cx={c.cx} cy={c.cy} colour="#1d3557" />
          </g>
        )
      })}
      {/* Stressed lines — wax-red flicker, pulsing halo. */}
      {POWER_FEED.stressed.map((p, i) => {
        const c = findCentroid(slug(p.district))
        if (!c) return null
        const dx = c.cx - hub.cx
        const dy = c.cy - hub.cy
        const cpx = hub.cx + dx * 0.55 + dy * 0.22
        const cpy = hub.cy + dy * 0.55 - dx * 0.22
        const d = `M ${hub.cx} ${hub.cy} Q ${cpx} ${cpy} ${c.cx} ${c.cy}`
        return (
          <g key={`s-${i}`}>
            <path d={d} stroke="#9c2b1f" strokeWidth={1.6} strokeOpacity={0.4} fill="none" />
            <path
              d={d}
              stroke="#9c2b1f"
              strokeWidth={1.6}
              strokeOpacity={0.95}
              strokeDasharray="4 6"
              fill="none"
              className={`${styles.gridFlow} ${styles.gridFlowStressed}`}
            />
            <g className={styles.flicker}>
              <circle cx={c.cx} cy={c.cy} r={14} fill="#9c2b1f" fillOpacity={0.22} />
              <circle
                cx={c.cx}
                cy={c.cy}
                r={9}
                fill="#9c2b1f"
                stroke="#5a160e"
                strokeWidth={1}
              />
              <text
                x={c.cx}
                y={c.cy + 4}
                textAnchor="middle"
                fontSize={11}
                fontWeight={700}
                fill="#f5f0e6"
              >
                ⚡
              </text>
            </g>
          </g>
        )
      })}
      {/* Hyderabad central hub — glowing transformer. */}
      <g>
        <circle cx={hub.cx} cy={hub.cy} r={20} fill="#1d3557" fillOpacity={0.18} />
        <SubstationGlyph cx={hub.cx} cy={hub.cy} colour="#1d3557" big />
      </g>
    </g>
  )
}

interface SubstationGlyphProps {
  cx: number
  cy: number
  colour: string
  big?: boolean
}

function SubstationGlyph({ cx, cy, colour, big = false }: SubstationGlyphProps) {
  const s = big ? 9 : 6
  return (
    <g>
      <rect
        x={cx - s}
        y={cy - s}
        width={s * 2}
        height={s * 2}
        fill="#faf8f3"
        stroke={colour}
        strokeWidth={1.2}
      />
      {/* Two horizontal bars — transformer winding glyph. */}
      <line
        x1={cx - s * 0.6}
        x2={cx + s * 0.6}
        y1={cy - s * 0.35}
        y2={cy - s * 0.35}
        stroke={colour}
        strokeWidth={1}
      />
      <line
        x1={cx - s * 0.6}
        x2={cx + s * 0.6}
        y1={cy + s * 0.35}
        y2={cy + s * 0.35}
        stroke={colour}
        strokeWidth={1}
      />
    </g>
  )
}

/* ------------------------------------------------------------------ */
/* Stability — turbulent storm cells over stressed, calm wash on stable */
/* ------------------------------------------------------------------ */

function StabilityOverlay() {
  return (
    <g pointerEvents="none">
      {/* Storm cells over stressed districts. */}
      {STABILITY_FEED.mostStressed.map((d, i) => {
        const c = findCentroid(slug(d.district))
        if (!c) return null
        return (
          <g key={`s-${i}`}>
            <ellipse
              cx={c.cx}
              cy={c.cy}
              rx={32}
              ry={20}
              fill="url(#stabilityStorm)"
              filter="url(#turbulent)"
              opacity={0.78}
            />
            <text
              x={c.cx}
              y={c.cy + 4}
              textAnchor="middle"
              fontFamily="'Söhne Mono','IBM Plex Mono','Menlo',monospace"
              fontSize={10}
              fontWeight={700}
              fill="#5a160e"
            >
              {d.score}
            </text>
          </g>
        )
      })}
      {/* Calm golden-hour halos on most-stable. */}
      {STABILITY_FEED.mostStable.map((d, i) => {
        const c = findCentroid(slug(d.district))
        if (!c) return null
        return (
          <g key={`b-${i}`}>
            <circle
              cx={c.cx}
              cy={c.cy}
              r={18}
              fill="url(#stabilityCalm)"
              filter="url(#inkBleed)"
              opacity={0.8}
            />
            <text
              x={c.cx}
              y={c.cy + 4}
              textAnchor="middle"
              fontFamily="'Söhne Mono','IBM Plex Mono','Menlo',monospace"
              fontSize={9.5}
              fontWeight={700}
              fill="#1d3557"
            >
              {d.score}
            </text>
          </g>
        )
      })}
    </g>
  )
}

/* ------------------------------------------------------------------ */
/* Helper                                                              */
/* ------------------------------------------------------------------ */

function slug(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')
}
