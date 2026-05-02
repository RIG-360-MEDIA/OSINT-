'use client'

import { useRouter } from 'next/navigation'
import { useState } from 'react'

import { DISTRICTS, STATEWIDE_SUMMARY } from './data'
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
}

export function TelanganaMap({
  highlightDistrictId,
  disableNavigation = false,
}: TelanganaMapProps = {}) {
  const router = useRouter()
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const volById = new Map<string, number>(
    DISTRICTS.map((d) => [d.id, d.volatility]),
  )

  const handleClick = (districtId: string) => {
    if (disableNavigation) return
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
        </defs>

        {/* District polygons — sepia heatmap fill + ink boundary, with a
         *  soft drop shadow for paper depth. Clickable: each path
         *  navigates to /brief/cm/preview/<district-id>. */}
        <g filter="url(#paperShadow)">
          {TELANGANA_DISTRICTS.map((d) => {
            const vol = volById.get(d.id) ?? 0.3
            const isHighlighted = highlightDistrictId === d.id
            const isHovered = hoveredId === d.id
            const dimmed =
              !!highlightDistrictId && highlightDistrictId !== d.id
            return (
              <path
                key={d.id}
                d={d.d}
                fill={sepiaForVolatility(vol)}
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
                  transition: 'stroke-width 0.15s ease, opacity 0.2s ease',
                }}
              >
                <title>{d.name}</title>
              </path>
            )
          })}
        </g>

        {/* Subtle cross-hatch on volatile districts (texture, not noise). */}
        <g pointerEvents="none">
          {TELANGANA_DISTRICTS.map((d) => {
            const vol = volById.get(d.id) ?? 0.3
            if (vol < 0.55) return null
            return <path key={d.id} d={d.d} fill="url(#hatch)" stroke="none" opacity={0.28} />
          })}
        </g>

        {/* District labels at centroids — sepia-aware contrast. */}
        <g
          fontFamily="'Tiempos Headline','Playfair Display','Georgia',serif"
          fontSize={9}
          letterSpacing="0.04em"
          pointerEvents="none"
        >
          {TELANGANA_DISTRICTS.map((d) => {
            if (SKIP_LABEL.has(d.id)) return null
            const vol = volById.get(d.id) ?? 0.3
            const dark = vol >= 0.55
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
