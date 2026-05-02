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
/* Editorial Telangana atlas — engraved aesthetic, 33 districts.       */
/*                                                                     */
/* Geometry: geoBoundaries gbOpen IND ADM2 (2021), simplified to       */
/* 0.0012° tolerance, equirectangular-projected into a 700×800 area.   */
/*                                                                     */
/* Design rules followed in this rewrite:                              */
/*   - Pin markers (i, ii, iii) are assigned in top-to-bottom order so */
/*     tethers never cross.                                            */
/*   - Districts that already carry a pin do NOT get an in-map label   */
/*     (their name appears in the margin annotation instead).          */
/*   - The smallest urban districts (Hyderabad, Medchal) skip labels   */
/*     entirely — their fill colour + position is enough at this zoom. */
/*   - Cross-hatching is dialed back to 0.10 opacity so it reads as a  */
/*     subtle paper texture, not aggressive scratch.                   */
/*   - Pin halos are tightened from 18 → 11 px so they don't bleed     */
/*     into adjacent districts.                                        */
/*   - Rivers follow real Telangana geography rather than horizontal   */
/*     squiggles: Godavari arcs north-east through the upper half,     */
/*     Krishna traces the southern silhouette.                         */
/* ------------------------------------------------------------------ */

const VB_W = 1000
const VB_H = 820
const ANN_X = 760
const ANN_Y_START = 200
const ANN_Y_STEP = 110

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

const ROMAN = ['i', 'ii', 'iii', 'iv', 'v'] as const

/** Districts whose name we never draw inside the polygon — either too small
 *  to fit, or already labeled by a margin annotation. Computed from PINS so
 *  the two are guaranteed in sync. */
function buildSkipLabelSet(): Set<string> {
  const s = new Set<string>(['hyderabad', 'medchal'])
  for (const p of PINS) s.add(p.districtId)
  return s
}

export function TelanganaMap() {
  const volById = new Map<string, number>(
    DISTRICTS.map((d) => [d.id, d.volatility]),
  )
  const districtById = new Map(TELANGANA_DISTRICTS.map((d) => [d.id, d]))
  const skipLabel = buildSkipLabelSet()

  /* Resolve each PIN to its district centroid, then sort by Y so markers
   * read top-to-bottom and the tethers don't cross. */
  const resolvedPins = PINS.map((pin) => {
    const dist = districtById.get(pin.districtId)
    return dist ? { pin, dist } : null
  })
    .filter((x): x is { pin: (typeof PINS)[number]; dist: NonNullable<ReturnType<typeof districtById.get>> } => x !== null)
    .sort((a, b) => a.dist.cy - b.dist.cy)

  /* Hand-tuned river paths — calibrated to the projected geography of
   * the 33-district map. Godavari curves NW → NE, then south through
   * Mahabubabad/Bhadradri border. Krishna traces the southern edge. */
  const godavari =
    'M 60,140 C 150,160 230,150 290,200 S 410,260 470,260 S 540,300 580,360 S 610,440 640,470'
  const krishna =
    'M 30,720 C 130,728 220,738 320,728 S 470,710 580,704 S 660,706 700,690'

  return (
    <div className={styles.mapWrap} aria-label="Live intelligence map of Telangana">
      <svg
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        role="img"
        aria-label="Telangana sentiment-volatility atlas"
        className={styles.mapSvg}
      >
        <defs>
          {/* Cross-hatch — toned down so it reads as engraved texture. */}
          <pattern
            id="hatch"
            patternUnits="userSpaceOnUse"
            width={4.5}
            height={4.5}
            patternTransform="rotate(45)"
          >
            <line x1={0} y1={0} x2={0} y2={4.5} stroke="#3a2a1a" strokeWidth={0.55} opacity={0.42} />
          </pattern>
          {/* Soft halo behind pins — small, contained. */}
          <radialGradient id="pinHalo" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#9c2b1f" stopOpacity="0.55" />
            <stop offset="55%" stopColor="#9c2b1f" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#9c2b1f" stopOpacity="0" />
          </radialGradient>
          {/* Drop shadow for the entire state silhouette — paper depth. */}
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
          {/* Clip path = union of every district. Used to keep the rivers
           *  inside the state outline — without this the bezier curves
           *  drift into empty paper. */}
          <clipPath id="stateClip">
            {TELANGANA_DISTRICTS.map((d) => (
              <path key={d.id} d={d.d} />
            ))}
          </clipPath>
        </defs>

        {/* District polygons — sepia heatmap fill + ink boundary. The whole
         *  group gets a soft drop shadow for paper depth. */}
        <g filter="url(#paperShadow)">
          {TELANGANA_DISTRICTS.map((d) => {
            const vol = volById.get(d.id) ?? 0.3
            return (
              <path
                key={d.id}
                d={d.d}
                fill={sepiaForVolatility(vol)}
                stroke="#3a2a1a"
                strokeWidth={1.0}
                strokeLinejoin="round"
                strokeOpacity={0.85}
              />
            )
          })}
        </g>

        {/* Cross-hatching overlay on volatile districts — subtle. */}
        <g pointerEvents="none">
          {TELANGANA_DISTRICTS.map((d) => {
            const vol = volById.get(d.id) ?? 0.3
            if (vol < 0.55) return null
            return <path key={d.id} d={d.d} fill="url(#hatch)" stroke="none" opacity={0.28} />
          })}
        </g>

        {/* Krishna + Godavari rivers — clipped to the state silhouette so
         *  they cannot drift past the eastern edge into blank paper. */}
        <g
          clipPath="url(#stateClip)"
          stroke="#1d3557"
          strokeWidth={2.2}
          fill="none"
          strokeLinecap="round"
          pointerEvents="none"
          opacity={0.72}
        >
          <path d={godavari} />
          <path d={krishna} />
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
          <text x={205} y={170} transform="rotate(-8 205 170)">
            Godavari
          </text>
          <text x={170} y={744} transform="rotate(-2 170 744)">
            Krishna
          </text>
        </g>

        {/* District labels at centroids — sepia-aware contrast.
         *  Pinned districts and tiny urban ones are skipped. */}
        <g
          fontFamily="'Tiempos Headline','Playfair Display','Georgia',serif"
          fontSize={9}
          letterSpacing="0.04em"
          pointerEvents="none"
        >
          {TELANGANA_DISTRICTS.map((d) => {
            if (skipLabel.has(d.id)) return null
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

        {/* Wax-seal pins, top-to-bottom. No tethers — a small italic
         *  numeral next to each pin pairs it with its margin annotation. */}
        {resolvedPins.map(({ pin, dist }, idx) => {
          const px = dist.cx
          const py = dist.cy
          const annY = ANN_Y_START + idx * ANN_Y_STEP
          const marker = ROMAN[idx] ?? `${idx + 1}`
          return (
            <g key={pin.id}>
              {/* compact breathing halo */}
              <circle
                cx={px}
                cy={py}
                r={11}
                fill="url(#pinHalo)"
                className={styles.pinPulse}
              />
              {/* wax-seal red dot */}
              <circle
                cx={px}
                cy={py}
                r={5}
                fill="#9c2b1f"
                stroke="#5a160e"
                strokeWidth={0.9}
              />
              {/* small marker numeral floating up-and-right of the pin */}
              <text
                x={px + 9}
                y={py - 7}
                fontFamily="'Tiempos Headline','Playfair Display','Georgia',serif"
                fontStyle="italic"
                fontSize={12}
                fill="#9c2b1f"
                fontWeight={700}
                pointerEvents="none"
              >
                {marker}.
              </text>
              {/* margin annotation */}
              <text
                x={ANN_X}
                y={annY - 14}
                fontFamily="'Tiempos Text','Lora','Georgia',serif"
                fontStyle="italic"
                fontSize={13}
                fill="#9c2b1f"
                fontWeight={600}
              >
                {marker}.
              </text>
              <text
                x={ANN_X + 16}
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
          y={ANN_Y_START + resolvedPins.length * ANN_Y_STEP + 6}
          fontFamily="'Tiempos Text','Lora','Georgia',serif"
          fontStyle="italic"
          fontSize={12}
          fill="#7a6a55"
        >
          {ADDITIONAL_EVENTS_LABEL}
        </text>

        {/* Compass rose, tucked into the bottom-left of the map zone. */}
        <g transform="translate(60,740)" stroke="#3a2a1a" strokeWidth={1} fill="none">
          <circle cx={0} cy={0} r={20} opacity={0.55} />
          <path d="M 0,-20 L 0,20 M -20,0 L 20,0" opacity={0.35} />
          <path d="M 0,-20 L 4,0 L 0,20 L -4,0 Z" fill="#3a2a1a" opacity={0.85} />
          <text
            x={0}
            y={-26}
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
