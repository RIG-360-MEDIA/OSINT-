'use client'

import { useRouter } from 'next/navigation'
import { useState } from 'react'

import { STATEWIDE_SUMMARY } from './data'
import { LayerOverlays } from './LayerOverlays'
import { DEFAULT_LAYER_ID, getLayer } from './layers'
import { TELANGANA_DISTRICTS, TELANGANA_VIEWBOX } from './telangana-geo'
import styles from './styles.module.css'

/* ------------------------------------------------------------------ */
/* Editorial Telangana atlas — minimal, data-only.                    */
/*                                                                     */
/* Per CM v3 feedback: the map is now stripped of every ornament that */
/* wasn't actual data. Pins, river paths, river labels, compass rose, */
/* scale bar, margin annotations — all gone. What remains:            */
/*   - 33 district polygons (geoBoundaries gbOpen IND ADM2 2021)      */
/*   - sepia heatmap fill + cross-hatch overlay on volatile districts */
/*   - district labels                                                */
/*   - statewide summary sentence at the foot                         */
/* ------------------------------------------------------------------ */

const VB_W = TELANGANA_VIEWBOX.width
const VB_H = TELANGANA_VIEWBOX.height

/** Sepia ramp — pale ivory through warm sepia to deep ink. */
function sepiaForVolatility(v: number): string {
  if (v < 0.18) return '#f5f0e6'
  if (v < 0.3) return '#ebd9b6'
  if (v < 0.42) return '#dabf8a'
  if (v < 0.55) return '#c9a373'
  if (v < 0.7) return '#a07a45'
  if (v < 0.82) return '#7a5224'
  return '#5a3613'
}

/** Tighter shortLabel — keeps text inside small polygons. */
function shortLabel(name: string): string {
  if (name.length <= 9) return name
  const parts = name.split(' ')
  if (parts.length >= 2) {
    if (parts[0].length <= 8) return parts[0]
    return `${parts[0][0]}.${parts[1]}`
  }
  return name.slice(0, 7) + '.'
}

/** Skip labels for the two tiniest urban districts — Hyderabad and
 *  Medchal sit packed inside Rangareddy and there's no room for type. */
const SKIP_LABEL = new Set(['hyderabad', 'medchal'])

interface TelanganaMapProps {
  /** Highlights a single district with a wax-red ring and dims the rest. */
  highlightDistrictId?: string
  /** When true, suppresses click navigation (used inside DistrictBrief). */
  disableNavigation?: boolean
  /** Active layer id from layers.ts. Defaults to 'news-hotspot'. */
  activeLayerId?: string
  /** Override click behaviour — if provided, called instead of router.push. */
  onDistrictClick?: (districtId: string) => void
}

export function TelanganaMap({
  highlightDistrictId,
  disableNavigation = false,
  activeLayerId = DEFAULT_LAYER_ID,
  onDistrictClick,
}: TelanganaMapProps = {}) {
  const router = useRouter()
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const layer = getLayer(activeLayerId)

  const handleClick = (districtId: string) => {
    if (disableNavigation) return
    if (onDistrictClick) {
      onDistrictClick(districtId)
      return
    }
    router.push(`/brief/cm/preview/${districtId}`)
  }

  return (
    <div className={styles.mapWrap} aria-label="Live intelligence map of Telangana">
      <svg
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        role="img"
        aria-label="Telangana sentiment-volatility atlas — click a district to focus"
        className={styles.mapSvg}
      >
        <defs>
          <pattern
            id="hatch"
            patternUnits="userSpaceOnUse"
            width={4.5}
            height={4.5}
            patternTransform="rotate(45)"
          >
            <line x1={0} y1={0} x2={0} y2={4.5} stroke="#3a2a1a" strokeWidth={0.55} opacity={0.42} />
          </pattern>
          <filter id="paperShadow" x="-4%" y="-4%" width="108%" height="108%">
            <feGaussianBlur in="SourceAlpha" stdDeviation="2.4" />
            <feOffset dx="2" dy="3" result="offsetblur" />
            <feComponentTransfer>
              <feFuncA type="linear" slope="0.32" />
            </feComponentTransfer>
            <feMerge>
              <feMergeNode />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Soft Gaussian bleed — wax-red ink soaking into paper. */}
          <filter id="inkBleed" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="6" />
          </filter>

          {/* Turbulence-displaced edges — irregular blot / cloud shapes. */}
          <filter id="turbulent" x="-30%" y="-30%" width="160%" height="160%">
            <feTurbulence type="fractalNoise" baseFrequency="0.06" numOctaves="2" seed="7" />
            <feDisplacementMap in="SourceGraphic" scale="11" />
          </filter>
          <filter id="turbulentSoft" x="-30%" y="-30%" width="160%" height="160%">
            <feTurbulence type="fractalNoise" baseFrequency="0.04" numOctaves="2" seed="3" />
            <feDisplacementMap in="SourceGraphic" scale="6" />
          </filter>

          {/* Bloom gradients. */}
          <radialGradient id="bloomNews" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#9c2b1f" stopOpacity="0.7" />
            <stop offset="50%" stopColor="#9c2b1f" stopOpacity="0.32" />
            <stop offset="100%" stopColor="#9c2b1f" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="stormCloud" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#5a160e" stopOpacity="0.55" />
            <stop offset="55%" stopColor="#9c2b1f" stopOpacity="0.32" />
            <stop offset="100%" stopColor="#9c2b1f" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="stabilityStorm" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#9c2b1f" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#5a160e" stopOpacity="0.05" />
          </radialGradient>
          <radialGradient id="stabilityCalm" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#c9a373" stopOpacity="0.7" />
            <stop offset="100%" stopColor="#c9a373" stopOpacity="0" />
          </radialGradient>

          {/* Welfare fabric patterns. */}
          <pattern id="weaveDense" patternUnits="userSpaceOnUse" width={4} height={4} patternTransform="rotate(45)">
            <line x1={0} y1={0} x2={0} y2={4} stroke="#3a2a1a" strokeWidth={0.45} opacity={0.55} />
            <line x1={0} y1={0} x2={4} y2={0} stroke="#3a2a1a" strokeWidth={0.45} opacity={0.55} />
          </pattern>
          <pattern id="weaveSparse" patternUnits="userSpaceOnUse" width={9} height={9} patternTransform="rotate(45)">
            <line x1={0} y1={0} x2={0} y2={3} stroke="#9c2b1f" strokeWidth={0.6} opacity={0.85} />
            <line x1={5} y1={5} x2={9} y2={5} stroke="#9c2b1f" strokeWidth={0.6} opacity={0.85} />
          </pattern>
          <pattern id="weaveGold" patternUnits="userSpaceOnUse" width={4} height={4} patternTransform="rotate(45)">
            <line x1={0} y1={0} x2={0} y2={4} stroke="#a07a45" strokeWidth={0.6} opacity={0.95} />
            <line x1={2} y1={0} x2={2} y2={4} stroke="#c9a373" strokeWidth={0.45} opacity={0.7} />
          </pattern>
        </defs>

        {/* District polygons — fill driven by the active layer. Click
         *  either calls onDistrictClick (modal mode) or navigates to
         *  /brief/cm/preview/<district-id>. */}
        <g filter="url(#paperShadow)">
          {TELANGANA_DISTRICTS.map((d) => {
            const value = layer.valueFor(d.id)
            const fill = layer.colorFor(value)
            const isHighlighted = highlightDistrictId === d.id
            const isHovered = hoveredId === d.id
            const dimmed =
              !!highlightDistrictId && highlightDistrictId !== d.id
            return (
              <path
                key={d.id}
                d={d.d}
                fill={fill}
                stroke={isHighlighted ? '#9c2b1f' : '#3a2a1a'}
                strokeWidth={isHighlighted ? 2.4 : isHovered ? 1.8 : 1.0}
                strokeLinejoin="round"
                strokeOpacity={isHighlighted ? 1 : isHovered ? 1 : 0.85}
                opacity={dimmed ? 0.45 : 1}
                onClick={() => handleClick(d.id)}
                onMouseEnter={() => setHoveredId(d.id)}
                onMouseLeave={() => setHoveredId(null)}
                style={{
                  cursor: disableNavigation ? 'default' : 'pointer',
                  transition:
                    'fill 0.45s ease, stroke-width 0.15s ease, opacity 0.2s ease',
                }}
              >
                <title>
                  {d.name} · {layer.label}
                </title>
              </path>
            )
          })}
        </g>

        {/* Cross-hatch only on news-hotspot — other layers use cleaner fills. */}
        {activeLayerId === 'news-hotspot' && (
          <g pointerEvents="none">
            {TELANGANA_DISTRICTS.map((d) => {
              const v = layer.valueFor(d.id)
              if (v < 0.55) return null
              return (
                <path
                  key={d.id}
                  d={d.d}
                  fill="url(#hatch)"
                  stroke="none"
                  opacity={0.28}
                />
              )
            })}
          </g>
        )}

        {/* Layer-specific overlays — each layer has its own visual
         *  language (pulsing rings for News, ▼ glyphs for Sentiment,
         *  event badges + connector wash for ACLED, commodity
         *  letter-badges for Mandi, ★/! flags for Welfare, hub-and-
         *  spoke + ⚡ for Power, composite donuts for Stability). */}
        <LayerOverlays activeLayerId={activeLayerId} />

        {/* District labels at centroids — sepia-aware contrast based on
         *  underlying layer intensity. */}
        <g
          fontFamily="'Tiempos Headline','Playfair Display','Georgia',serif"
          fontSize={9}
          letterSpacing="0.04em"
          pointerEvents="none"
        >
          {TELANGANA_DISTRICTS.map((d) => {
            if (SKIP_LABEL.has(d.id)) return null
            const v = layer.valueFor(d.id)
            const dark = v >= 0.55
            return (
              <text
                key={d.id}
                x={d.cx}
                y={d.cy + 3}
                textAnchor="middle"
                fill={dark ? '#f5f0e6' : '#1a1a1a'}
                fillOpacity={0.92}
              >
                {shortLabel(d.name)}
              </text>
            )
          })}
        </g>

      </svg>
      {/* Statewide summary now lives as an HTML element below the SVG so
       *  the SVG itself is just the atlas, with no in-SVG chrome. */}
      <p className={styles.atlasSummary}>{STATEWIDE_SUMMARY}</p>
    </div>
  )
}
