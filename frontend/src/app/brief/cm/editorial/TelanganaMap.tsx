'use client'

import {
  ADDITIONAL_EVENTS_LABEL,
  DISTRICTS,
  PINS,
  STATEWIDE_SUMMARY,
} from './data'
import { TELANGANA_DISTRICTS } from './telangana-geo'
import styles from './styles.module.css'

/* ------------------------------------------------------------------ */
/* Editorial Telangana atlas — engraved aesthetic.                     */
/*                                                                     */
/* Geometry comes from GADM 4.1 India L2 (10 historical districts that */
/* cover today's Telangana). Rendered as a sepia-graded heatmap with   */
/* hand-tuned ink rivers, hatched overlays on high-volatility regions, */
/* and italic-serif margin annotations tethered to wax-seal pins.      */
/* ------------------------------------------------------------------ */

const VB_W = 1000
const VB_H = 820
const ANN_X = 760

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

function shortLabel(name: string): string {
  if (name.length <= 9) return name
  const parts = name.split(' ')
  if (parts.length >= 2) {
    // Compound names — keep the first word if short, else "X.SECOND".
    if (parts[0].length <= 8) return parts[0]
    return `${parts[0][0]}.${parts[1]}`
  }
  return name.slice(0, 7) + '.'
}

/** Naive word-wrap to N chars — adequate for short annotations. */
function wrap(text: string, maxChars: number): string[] {
  const words = text.split(' ')
  const lines: string[] = []
  let cur = ''
  for (const w of words) {
    if ((cur + ' ' + w).trim().length > maxChars) {
      if (cur) lines.push(cur.trim())
      cur = w
    } else {
      cur = `${cur} ${w}`
    }
  }
  if (cur) lines.push(cur.trim())
  return lines
}

export function TelanganaMap() {
  const volById = new Map<string, number>(
    DISTRICTS.map((d) => [d.id, d.volatility]),
  )
  const districtById = new Map(TELANGANA_DISTRICTS.map((d) => [d.id, d]))

  /* River paths — hand-tuned beziers calibrated to the projected geo
   * bounds (lon 77.235–81.794, lat 15.827–19.916) inside our 0–700 ×
   * 0–800 map area. Approximate but visually faithful. */
  const godavari =
    'M 30,165 C 130,158 230,205 340,178 S 520,215 600,195 S 670,180 700,150'
  const krishna =
    'M 80,700 C 200,710 310,735 405,712 S 545,705 625,718 S 690,720 700,705'

  return (
    <div className={styles.mapWrap} aria-label="Live intelligence map of Telangana">
      <svg
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        role="img"
        aria-label="Telangana sentiment-volatility atlas"
        className={styles.mapSvg}
      >
        <defs>
          {/* Cross-hatch pattern for high-volatility overlay. */}
          <pattern
            id="hatch"
            patternUnits="userSpaceOnUse"
            width={5}
            height={5}
            patternTransform="rotate(45)"
          >
            <line x1={0} y1={0} x2={0} y2={5} stroke="#3a2a1a" strokeWidth={0.6} opacity={0.22} />
          </pattern>
          {/* Wax-seal red halo behind pins. */}
          <radialGradient id="pinHalo" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#9c2b1f" stopOpacity="0.55" />
            <stop offset="60%" stopColor="#9c2b1f" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#9c2b1f" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* Soft underglow shadow giving the state silhouette a sense of paper depth. */}
        <g opacity={0.22} transform="translate(2.5,3.5)">
          {TELANGANA_DISTRICTS.map((d) => (
            <path key={d.id} d={d.d} fill="#3a2a1a" stroke="none" />
          ))}
        </g>

        {/* District polygons — sepia heatmap fill + ink boundary. */}
        <g>
          {TELANGANA_DISTRICTS.map((d) => {
            const vol = volById.get(d.id) ?? 0.3
            return (
              <path
                key={d.id}
                d={d.d}
                fill={sepiaForVolatility(vol)}
                stroke="#3a2a1a"
                strokeWidth={1.2}
                strokeLinejoin="round"
              />
            )
          })}
        </g>

        {/* Cross-hatching overlay on volatile districts. */}
        <g pointerEvents="none">
          {TELANGANA_DISTRICTS.map((d) => {
            const vol = volById.get(d.id) ?? 0.3
            if (vol < 0.55) return null
            return <path key={d.id} d={d.d} fill="url(#hatch)" stroke="none" />
          })}
        </g>

        {/* State outline — subtle double-stroke to suggest hand-drawing. */}
        <g pointerEvents="none">
          {TELANGANA_DISTRICTS.map((d) => (
            <path
              key={d.id}
              d={d.d}
              fill="none"
              stroke="#1a1a1a"
              strokeWidth={0.4}
              strokeOpacity={0.35}
              transform="translate(0.6,0.6)"
            />
          ))}
        </g>

        {/* Krishna + Godavari rivers — ink-blue threads. */}
        <g
          stroke="#1d3557"
          strokeWidth={2.2}
          fill="none"
          opacity={0.78}
          strokeLinecap="round"
          pointerEvents="none"
        >
          <path d={godavari} />
          <path d={krishna} />
          <path
            d="M 320,180 C 340,250 360,320 380,400"
            strokeWidth={1.2}
            opacity={0.55}
          />
          <path
            d="M 540,200 C 560,260 575,330 585,420"
            strokeWidth={1.1}
            opacity={0.5}
          />
        </g>

        {/* River labels in italic serif. */}
        <g
          fontFamily="'Tiempos Text','Lora','Georgia',serif"
          fontStyle="italic"
          fontSize={11}
          fill="#1d3557"
          opacity={0.78}
          pointerEvents="none"
        >
          <text x={130} y={188} transform="rotate(-3 130 188)">
            Godavari
          </text>
          <text x={150} y={730} transform="rotate(-1 150 730)">
            Krishna
          </text>
        </g>

        {/* District labels at centroids — sepia-aware contrast.
         *  9pt for 33 districts; tight letter-spacing keeps the type
         *  inside the smaller polygons. */}
        <g
          fontFamily="'Tiempos Headline','Playfair Display','Georgia',serif"
          fontSize={9}
          letterSpacing="0.04em"
          pointerEvents="none"
        >
          {TELANGANA_DISTRICTS.map((d) => {
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

        {/* Wax-seal pins + tethers + margin annotations. */}
        {PINS.map((pin, idx) => {
          const dist = districtById.get(pin.districtId)
          if (!dist) return null
          const px = dist.cx
          const py = dist.cy
          const annY = 200 + idx * 110
          const tetherD = `M ${px},${py} C ${px + 50},${py - 5} ${ANN_X - 70},${annY - 10} ${ANN_X - 6},${annY - 4}`
          return (
            <g key={pin.id}>
              {/* breathing halo */}
              <circle
                cx={px}
                cy={py}
                r={18}
                fill="url(#pinHalo)"
                className={styles.pinPulse}
              />
              {/* wax-seal red dot */}
              <circle
                cx={px}
                cy={py}
                r={6}
                fill="#9c2b1f"
                stroke="#5a160e"
                strokeWidth={0.9}
              />
              {/* tether — pen-drawn arc */}
              <path
                d={tetherD}
                stroke="#3a2a1a"
                strokeWidth={0.9}
                fill="none"
                strokeDasharray="2 2.4"
                opacity={0.6}
              />
              {/* annotation block */}
              <text
                x={ANN_X}
                y={annY - 14}
                fontFamily="'Tiempos Text','Lora','Georgia',serif"
                fontStyle="italic"
                fontSize={13}
                fill="#9c2b1f"
                fontWeight={600}
              >
                {pin.marker}.
              </text>
              <text
                x={ANN_X + 14}
                y={annY - 14}
                fontFamily="'Tiempos Headline','Playfair Display','Georgia',serif"
                fontSize={14}
                fill="#1a1a1a"
                fontWeight={600}
              >
                {pin.city}
              </text>
              <text
                x={ANN_X}
                y={annY + 6}
                fontFamily="'Tiempos Text','Lora','Georgia',serif"
                fontStyle="italic"
                fontSize={12.5}
                fill="#3a2a1a"
              >
                {wrap(pin.annotation, 38).map((line, i) => (
                  <tspan key={i} x={ANN_X} dy={i === 0 ? 0 : 15}>
                    {line}
                  </tspan>
                ))}
              </text>
            </g>
          )
        })}

        {/* "+ N more events" affordance. */}
        <text
          x={ANN_X}
          y={200 + PINS.length * 110 + 6}
          fontFamily="'Tiempos Text','Lora','Georgia',serif"
          fontStyle="italic"
          fontSize={12}
          fill="#7a6a55"
        >
          {ADDITIONAL_EVENTS_LABEL}
        </text>

        {/* Compass rose. */}
        <g transform="translate(60,740)" stroke="#3a2a1a" strokeWidth={1} fill="none">
          <circle cx={0} cy={0} r={22} opacity={0.6} />
          <path d="M 0,-22 L 0,22 M -22,0 L 22,0" opacity={0.4} />
          <path d="M 0,-22 L 4,0 L 0,22 L -4,0 Z" fill="#3a2a1a" opacity={0.85} />
          <text
            x={0}
            y={-28}
            textAnchor="middle"
            fontFamily="'Tiempos Text','Lora','Georgia',serif"
            fontStyle="italic"
            fontSize={10}
            fill="#3a2a1a"
            stroke="none"
          >
            N
          </text>
        </g>

        {/* Scale bar, bottom-right of map area. */}
        <g
          transform="translate(540,750)"
          fontFamily="'Tiempos Text','Lora','Georgia',serif"
          fontStyle="italic"
          fontSize={10}
          fill="#3a2a1a"
        >
          <line x1={0} y1={0} x2={120} y2={0} stroke="#3a2a1a" strokeWidth={1.2} />
          <line x1={0} y1={-4} x2={0} y2={4} stroke="#3a2a1a" strokeWidth={1.2} />
          <line x1={60} y1={-3} x2={60} y2={3} stroke="#3a2a1a" strokeWidth={1.2} />
          <line x1={120} y1={-4} x2={120} y2={4} stroke="#3a2a1a" strokeWidth={1.2} />
          <text x={0} y={16}>0</text>
          <text x={60} y={16} textAnchor="middle">50</text>
          <text x={120} y={16} textAnchor="end">100 km</text>
        </g>

        {/* Hairline rule + statewide summary line. */}
        <line
          x1={40}
          y1={788}
          x2={960}
          y2={788}
          stroke="#7a6a55"
          strokeWidth={0.6}
          opacity={0.55}
        />
        <text
          x={500}
          y={808}
          textAnchor="middle"
          fontFamily="'Tiempos Text','Lora','Georgia',serif"
          fontSize={15}
          fill="#1a1a1a"
        >
          {STATEWIDE_SUMMARY}
        </text>
      </svg>
    </div>
  )
}
