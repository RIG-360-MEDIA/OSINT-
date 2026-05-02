'use client'

import {
  ADDITIONAL_EVENTS_LABEL,
  DISTRICTS,
  PINS,
  STATEWIDE_SUMMARY,
  type DistrictDatum,
} from './data'

import styles from './styles.module.css'

/* ------------------------------------------------------------------ */
/* Hex-cartogram geometry.                                             */
/*                                                                     */
/* This is a stylised hex cartogram of Telangana, not a GIS rendering. */
/* Hex placement preserves rough relative geography (Hyderabad south-  */
/* central, Karimnagar north-east, Khammam east, Adilabad far north,   */
/* Mahbubnagar south) so the page reads as Telangana at a glance.      */
/* ------------------------------------------------------------------ */

const HEX_R = 46
const HEX_W = HEX_R * Math.sqrt(3)
const ROW_DY = HEX_R * 1.5
const START_X = 110
const START_Y = 90

interface HexPos {
  col: number
  row: number
}

const HEX_POS: Record<string, HexPos> = {
  // Row 0 — far north
  adilabad: { col: 3, row: 0 },
  'kumram-bheem': { col: 4, row: 0 },
  // Row 1
  nirmal: { col: 2, row: 1 },
  mancherial: { col: 3, row: 1 },
  // Row 2 — north-central
  nizamabad: { col: 1, row: 2 },
  jagtial: { col: 3, row: 2 },
  peddapalli: { col: 4, row: 2 },
  karimnagar: { col: 5, row: 2 },
  // Row 3
  kamareddy: { col: 1, row: 3 },
  'rajanna-sircilla': { col: 2, row: 3 },
  siddipet: { col: 3, row: 3 },
  hanamkonda: { col: 4, row: 3 },
  mulugu: { col: 5, row: 3 },
  jayashankar: { col: 6, row: 3 },
  // Row 4 — central tier
  medak: { col: 0, row: 4 },
  sangareddy: { col: 1, row: 4 },
  jangaon: { col: 3, row: 4 },
  warangal: { col: 4, row: 4 },
  mahabubabad: { col: 5, row: 4 },
  // Row 5 — Hyderabad belt
  vikarabad: { col: 0, row: 5 },
  medchal: { col: 1, row: 5 },
  hyderabad: { col: 2, row: 5 },
  yadadri: { col: 3, row: 5 },
  suryapet: { col: 4, row: 5 },
  bhadradri: { col: 5, row: 5 },
  khammam: { col: 6, row: 5 },
  // Row 6
  rangareddy: { col: 1, row: 6 },
  nalgonda: { col: 3, row: 6 },
  // Row 7 — south
  narayanpet: { col: 0, row: 7 },
  mahbubnagar: { col: 1, row: 7 },
  wanaparthy: { col: 2, row: 7 },
  jogulamba: { col: 3, row: 7 },
  // Row 8
  nagarkurnool: { col: 1, row: 8 },
}

interface HexCenter {
  cx: number
  cy: number
}

function hexCenter(col: number, row: number): HexCenter {
  const offset = row % 2 === 1 ? HEX_W / 2 : 0
  return {
    cx: START_X + col * HEX_W + offset,
    cy: START_Y + row * ROW_DY,
  }
}

function hexPoints(cx: number, cy: number, r: number = HEX_R - 2.5): string {
  const pts: string[] = []
  for (let i = 0; i < 6; i++) {
    const angle = -Math.PI / 2 + (i * Math.PI) / 3
    pts.push(
      `${(cx + r * Math.cos(angle)).toFixed(1)},${(cy + r * Math.sin(angle)).toFixed(1)}`,
    )
  }
  return pts.join(' ')
}

/** Sepia heatmap ramp — pale ivory through warm sepia to deep ink. */
function sepiaForVolatility(v: number): string {
  if (v < 0.18) return '#f5f0e6'
  if (v < 0.3) return '#ebd9b6'
  if (v < 0.42) return '#dabf8a'
  if (v < 0.55) return '#c9a373'
  if (v < 0.7) return '#a07a45'
  if (v < 0.82) return '#7a5224'
  return '#5a3613'
}

/** District labels ride inside their hex — abbreviated to fit. */
function shortLabel(name: string): string {
  if (name.length <= 9) return name
  // keep first word and an initial of the second word for compounds
  const parts = name.split(' ')
  if (parts.length === 1) return name.slice(0, 9)
  return `${parts[0]}.`
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

export function TelanganaMap() {
  const districtsById = new Map<string, DistrictDatum>(
    DISTRICTS.map((d) => [d.id, d]),
  )

  /* River paths — hand-tuned bezier approximations.                   */
  const godavari =
    'M 35,260 C 120,250 220,290 320,235 S 520,170 600,205 S 730,240 760,200'
  const krishna =
    'M 60,720 C 160,705 260,745 360,720 S 540,690 660,725 S 780,745 820,710'

  /* Annotation x-positions — the right margin column.                 */
  const ANN_X = 760

  return (
    <div className={styles.mapWrap} aria-label="Live intelligence map of Telangana">
      <svg
        viewBox="0 0 1000 920"
        role="img"
        aria-label="Telangana sentiment-volatility map"
        className={styles.mapSvg}
      >
        {/* Defs — paper texture + soft pin halo. */}
        <defs>
          <radialGradient id="pinHalo" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#9c2b1f" stopOpacity="0.55" />
            <stop offset="60%" stopColor="#9c2b1f" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#9c2b1f" stopOpacity="0" />
          </radialGradient>
          <filter id="paperRough" x="-2%" y="-2%" width="104%" height="104%">
            <feTurbulence
              type="fractalNoise"
              baseFrequency="0.65"
              numOctaves="2"
              seed="3"
            />
            <feDisplacementMap in="SourceGraphic" scale="0.6" />
          </filter>
        </defs>

        {/* District hexes. */}
        <g>
          {DISTRICTS.map((d) => {
            const pos = HEX_POS[d.id]
            if (!pos) return null
            const { cx, cy } = hexCenter(pos.col, pos.row)
            const fill = sepiaForVolatility(d.volatility)
            const isDark = d.volatility >= 0.55
            return (
              <g key={d.id}>
                <polygon
                  points={hexPoints(cx, cy)}
                  fill={fill}
                  stroke="#3a2a1a"
                  strokeWidth={0.9}
                  strokeOpacity={0.75}
                />
                <text
                  x={cx}
                  y={cy + 4}
                  textAnchor="middle"
                  fontSize={11}
                  fontStyle="italic"
                  fontFamily="'Tiempos Text','Lora','Georgia',serif"
                  fill={isDark ? '#f5f0e6' : '#3a2a1a'}
                  opacity={0.92}
                >
                  {shortLabel(d.name)}
                </text>
              </g>
            )
          })}
        </g>

        {/* Krishna + Godavari rivers, ink-blue threads. */}
        <g
          stroke="#1d3557"
          strokeWidth={2.2}
          fill="none"
          opacity={0.78}
          strokeLinecap="round"
        >
          <path d={godavari} />
          <path d={krishna} />
          {/* tributary hints */}
          <path
            d="M 380,235 C 400,290 420,340 440,400"
            strokeWidth={1.2}
            opacity={0.6}
          />
          <path
            d="M 520,200 C 540,260 555,320 565,380"
            strokeWidth={1.1}
            opacity={0.55}
          />
        </g>

        {/* River labels in italic serif, low opacity. */}
        <g
          fontFamily="'Tiempos Text','Lora','Georgia',serif"
          fontStyle="italic"
          fontSize={11}
          fill="#1d3557"
          opacity={0.7}
        >
          <text x={130} y={245} transform="rotate(-3 130 245)">
            Godavari
          </text>
          <text x={140} y={715} transform="rotate(-1 140 715)">
            Krishna
          </text>
        </g>

        {/* Three event pins with hand-drawn tethers to margin annotations. */}
        {PINS.map((pin, idx) => {
          const annY = 200 + idx * 110
          // arc from pin to annotation
          const tetherD = `M ${pin.x},${pin.y} C ${pin.x + 60},${pin.y - 10} ${ANN_X - 80},${annY - 10} ${ANN_X - 6},${annY - 4}`
          return (
            <g key={pin.id}>
              {/* breathing halo */}
              <circle
                cx={pin.x}
                cy={pin.y}
                r={18}
                fill="url(#pinHalo)"
                className={styles.pinPulse}
              />
              {/* wax-seal red dot */}
              <circle
                cx={pin.x}
                cy={pin.y}
                r={5.5}
                fill="#9c2b1f"
                stroke="#5a160e"
                strokeWidth={0.8}
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
              <g>
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
                {/* Wrap annotation text across two lines via tspan. */}
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

        {/* Compass rose, bottom-left. */}
        <g transform="translate(60,820)" stroke="#3a2a1a" strokeWidth={1} fill="none">
          <circle cx={0} cy={0} r={22} opacity={0.6} />
          <path d="M 0,-22 L 0,22 M -22,0 L 22,0" opacity={0.45} />
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
          transform="translate(540,830)"
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

        {/* Hairline sepia rule beneath map area. */}
        <line
          x1={40}
          y1={870}
          x2={960}
          y2={870}
          stroke="#7a6a55"
          strokeWidth={0.6}
          opacity={0.55}
        />

        {/* Statewide summary line. */}
        <text
          x={500}
          y={898}
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
