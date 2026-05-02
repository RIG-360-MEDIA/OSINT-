'use client'

/**
 * Per-layer SVG overlays — the visual language each layer draws ON
 * the map (in addition to the choropleth fill underneath).
 *
 * Rendered inside the TelanganaMap SVG, on top of polygons + cross-hatch
 * but below the district labels. Pure SVG, no images.
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
/* News Hotspot — pulsing rings on the top stories                     */
/* ------------------------------------------------------------------ */

function NewsHotspotOverlay() {
  // Take the top 3 unique-district stories.
  const seen = new Set<string>()
  const top = NEWS_FEED.filter((n) => {
    const id = n.district.toLowerCase()
    if (seen.has(id)) return false
    seen.add(id)
    return id !== 'statewide'
  }).slice(0, 3)
  return (
    <g pointerEvents="none">
      {top.map((n, i) => {
        const c = findCentroid(slug(n.district))
        if (!c) return null
        return (
          <g key={i}>
            <circle
              cx={c.cx}
              cy={c.cy}
              r={20}
              fill="none"
              stroke="#9c2b1f"
              strokeOpacity={0.35}
              strokeWidth={1}
              className={styles.pulseRingOuter}
            />
            <circle
              cx={c.cx}
              cy={c.cy}
              r={12}
              fill="none"
              stroke="#9c2b1f"
              strokeOpacity={0.55}
              strokeWidth={1.2}
              className={styles.pulseRingInner}
            />
            <circle cx={c.cx} cy={c.cy} r={4.5} fill="#9c2b1f" />
            <text
              x={c.cx + 9}
              y={c.cy - 9}
              fontSize={8.5}
              fontWeight={700}
              fontFamily="'Söhne Mono','IBM Plex Mono','Menlo',monospace"
              fill="#9c2b1f"
            >
              #{i + 1}
            </text>
          </g>
        )
      })}
    </g>
  )
}

/* ------------------------------------------------------------------ */
/* Sentiment — big ▼ glyphs, size by negativity                        */
/* ------------------------------------------------------------------ */

function SentimentOverlay() {
  return (
    <g pointerEvents="none">
      {SENTIMENT_FEED.topNegativeDistricts.map((d, i) => {
        const c = findCentroid(slug(d.name))
        if (!c) return null
        const intensity = Math.min(1, Math.abs(d.value))
        const size = 14 + intensity * 14 // 14..28pt
        return (
          <g key={i}>
            <circle
              cx={c.cx}
              cy={c.cy}
              r={14}
              fill="#9c2b1f"
              fillOpacity={0.12}
            />
            <text
              x={c.cx}
              y={c.cy + size * 0.35}
              textAnchor="middle"
              fontFamily="'Tiempos Headline','Playfair Display','Georgia',serif"
              fontStyle="italic"
              fontSize={size}
              fontWeight={700}
              fill="#9c2b1f"
            >
              ▼
            </text>
          </g>
        )
      })}
    </g>
  )
}

/* ------------------------------------------------------------------ */
/* ACLED — bright event markers with type glyph + size by count        */
/* ------------------------------------------------------------------ */

function AcledOverlay() {
  // Aggregate events per district from the feed.
  const counts: Record<string, { protest: number; strategic: number; riot: number; total: number }> = {}
  for (const e of ACLED_FEED.events) {
    const id = slug(e.district)
    counts[id] = counts[id] ?? { protest: 0, strategic: 0, riot: 0, total: 0 }
    if (e.type === 'Riot') counts[id].riot++
    else if (e.type === 'Strategic Development') counts[id].strategic++
    else counts[id].protest++
    counts[id].total++
  }
  return (
    <>
      {/* Soft cream wash — desaturates the choropleth so events POP. */}
      <rect
        x={0}
        y={0}
        width={1000}
        height={900}
        fill="#faf8f3"
        opacity={0.4}
        pointerEvents="none"
      />
      <g pointerEvents="none">
        {Object.entries(counts).map(([id, c]) => {
          const cen = findCentroid(id)
          if (!cen) return null
          const size = 10 + Math.min(c.total, 6) * 2.2
          return (
            <g key={id}>
              <circle
                cx={cen.cx}
                cy={cen.cy}
                r={size + 5}
                fill="#9c2b1f"
                fillOpacity={0.16}
                className={styles.pulseSlow}
              />
              <circle
                cx={cen.cx}
                cy={cen.cy}
                r={size}
                fill="#9c2b1f"
                stroke="#5a160e"
                strokeWidth={1}
              />
              <text
                x={cen.cx}
                y={cen.cy + 3.4}
                textAnchor="middle"
                fontFamily="'Söhne Mono','IBM Plex Mono','Menlo',monospace"
                fontSize={9.5}
                fontWeight={700}
                fill="#f5f0e6"
              >
                {c.total}
              </text>
              <text
                x={cen.cx + size + 3}
                y={cen.cy - size + 1}
                fontSize={8}
                fontFamily="'Söhne Mono','IBM Plex Mono','Menlo',monospace"
                fill="#3a2a1a"
              >
                {c.protest > 0 && `P${c.protest} `}
                {c.strategic > 0 && `S${c.strategic} `}
                {c.riot > 0 && `R${c.riot}`}
              </text>
            </g>
          )
        })}
      </g>
    </>
  )
}

/* ------------------------------------------------------------------ */
/* Mandi — commodity letter badges at markets, with price arrows       */
/* ------------------------------------------------------------------ */

function MandiOverlay() {
  return (
    <g pointerEvents="none">
      {MANDI_FEED.topMovers.map((m, i) => {
        const c = findCentroid(slug(m.district))
        if (!c) return null
        const ox = (i % 2 === 0 ? -1 : 1) * 8
        const oy = i * 1.5 // slight stagger so multiple commodities at same market don't overlap
        const colour = m.trend === 'up' ? '#9c2b1f' : m.trend === 'down' ? '#1d3557' : '#7a6a55'
        const letter = commodityLetter(m.commodity)
        return (
          <g key={i}>
            <rect
              x={c.cx + ox - 9}
              y={c.cy + oy - 9}
              width={18}
              height={18}
              rx={2}
              fill="#faf8f3"
              stroke={colour}
              strokeWidth={1.2}
            />
            <text
              x={c.cx + ox}
              y={c.cy + oy + 3.5}
              textAnchor="middle"
              fontFamily="'Tiempos Headline','Playfair Display','Georgia',serif"
              fontSize={11}
              fontWeight={700}
              fill={colour}
            >
              {letter}
            </text>
            <text
              x={c.cx + ox + 12}
              y={c.cy + oy - 4}
              fontFamily="'Söhne Mono','IBM Plex Mono','Menlo',monospace"
              fontSize={8.5}
              fontWeight={600}
              fill={colour}
            >
              {m.trend === 'up' ? '▲' : m.trend === 'down' ? '▼' : '→'} {m.delta}
            </text>
          </g>
        )
      })}
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
/* Welfare — best-covered ★ + at-risk dashed-ring flags                */
/* ------------------------------------------------------------------ */

function WelfareOverlay() {
  return (
    <g pointerEvents="none">
      {WELFARE_FEED.bestCovered.map((d, i) => {
        const c = findCentroid(slug(d.district))
        if (!c) return null
        return (
          <g key={`b-${i}`}>
            <circle cx={c.cx} cy={c.cy} r={11} fill="#1d3557" fillOpacity={0.85} />
            <text
              x={c.cx}
              y={c.cy + 4}
              textAnchor="middle"
              fontSize={12}
              fontWeight={700}
              fill="#f5f0e6"
            >
              ★
            </text>
          </g>
        )
      })}
      {WELFARE_FEED.atRisk.map((d, i) => {
        const c = findCentroid(slug(d.district))
        if (!c) return null
        return (
          <g key={`r-${i}`}>
            <circle
              cx={c.cx}
              cy={c.cy}
              r={13}
              fill="none"
              stroke="#9c2b1f"
              strokeWidth={1.5}
              strokeDasharray="2.5 2.5"
            />
            <text
              x={c.cx}
              y={c.cy + 4}
              textAnchor="middle"
              fontFamily="'Tiempos Headline','Playfair Display','Georgia',serif"
              fontSize={13}
              fontWeight={700}
              fill="#9c2b1f"
            >
              !
            </text>
          </g>
        )
      })}
    </g>
  )
}

/* ------------------------------------------------------------------ */
/* Power — Hyderabad hub + dashed lines + ⚡ flags at stressed nodes    */
/* ------------------------------------------------------------------ */

function PowerOverlay() {
  const hyd = findCentroid('hyderabad')
  if (!hyd) return null
  return (
    <g pointerEvents="none">
      {/* Lines from Hyderabad to every stressed feeder district. */}
      {POWER_FEED.stressed.map((p, i) => {
        const c = findCentroid(slug(p.district))
        if (!c) return null
        return (
          <line
            key={`l-${i}`}
            x1={hyd.cx}
            y1={hyd.cy}
            x2={c.cx}
            y2={c.cy}
            stroke="#9c2b1f"
            strokeWidth={1.4}
            strokeOpacity={0.55}
            strokeDasharray="3 3"
          />
        )
      })}
      {/* Hyderabad central hub — square substation marker. */}
      <rect
        x={hyd.cx - 7}
        y={hyd.cy - 7}
        width={14}
        height={14}
        fill="#1d3557"
        stroke="#f5f0e6"
        strokeWidth={1}
      />
      <text
        x={hyd.cx}
        y={hyd.cy + 3.5}
        textAnchor="middle"
        fontFamily="'Söhne Mono','IBM Plex Mono','Menlo',monospace"
        fontSize={8}
        fontWeight={700}
        fill="#f5f0e6"
      >
        HUB
      </text>
      {/* Lightning glyphs at stressed feeders. */}
      {POWER_FEED.stressed.map((p, i) => {
        const c = findCentroid(slug(p.district))
        if (!c) return null
        return (
          <g key={`f-${i}`}>
            <circle
              cx={c.cx}
              cy={c.cy}
              r={11}
              fill="#9c2b1f"
              fillOpacity={0.18}
              className={styles.pulseSlow}
            />
            <circle
              cx={c.cx}
              cy={c.cy}
              r={8}
              fill="#9c2b1f"
              stroke="#5a160e"
              strokeWidth={1}
            />
            <text
              x={c.cx}
              y={c.cy + 3.5}
              textAnchor="middle"
              fontSize={11}
              fontWeight={700}
              fill="#f5f0e6"
            >
              ⚡
            </text>
          </g>
        )
      })}
    </g>
  )
}

/* ------------------------------------------------------------------ */
/* Stability — composite mini-donuts at top stressed and most-stable   */
/* ------------------------------------------------------------------ */

function StabilityOverlay() {
  const r = 10
  const C = 2 * Math.PI * r
  const districts = [
    ...STABILITY_FEED.mostStressed.map((d) => ({ ...d, kind: 'stressed' as const })),
    ...STABILITY_FEED.mostStable.map((d) => ({ ...d, kind: 'stable' as const })),
  ]
  return (
    <g pointerEvents="none">
      {districts.map((d, i) => {
        const c = findCentroid(slug(d.district))
        if (!c) return null
        const offset = C * (1 - d.score / 100)
        const colour = d.kind === 'stable' ? '#1d3557' : '#9c2b1f'
        return (
          <g key={i}>
            <circle cx={c.cx} cy={c.cy} r={r + 2} fill="#faf8f3" fillOpacity={0.9} />
            <circle
              cx={c.cx}
              cy={c.cy}
              r={r}
              fill="none"
              stroke="rgba(58,42,26,0.18)"
              strokeWidth={3}
            />
            <circle
              cx={c.cx}
              cy={c.cy}
              r={r}
              fill="none"
              stroke={colour}
              strokeWidth={3}
              strokeDasharray={C}
              strokeDashoffset={offset}
              strokeLinecap="round"
              transform={`rotate(-90 ${c.cx} ${c.cy})`}
            />
            <text
              x={c.cx}
              y={c.cy + 3.4}
              textAnchor="middle"
              fontFamily="'Söhne Mono','IBM Plex Mono','Menlo',monospace"
              fontSize={8.5}
              fontWeight={700}
              fill={colour}
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

/** "Komaram Bheem" → "komaram-bheem", "Hyderabad" → "hyderabad". */
function slug(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')
}
