'use client'

/**
 * <CMEditorialBrief> — the new "Editorial Intelligence" view.
 *
 * Demo composition. All data is hardcoded in ./editorial/data.ts so
 * the page reads as live without depending on any backend. The shape
 * of the data mirrors what a real feed would deliver, so swapping in
 * a live source later is a one-file change.
 *
 * Mounted at /brief/cm and /brief?view=cm — props match the previous
 * CMSituationRoom so the swap is name-only at the call site.
 */
import { useEffect, useMemo, useState } from 'react'

import {
  ACTIONS,
  FORECAST_CAPTION,
  FORECAST_NARRATIVE,
  FORECAST_POINTS,
  HEADER,
  HERO,
  NEWS_DESK,
  OPPOSITION_DESK,
  STATEWIDE_SUMMARY,
  THREATS,
  TICKER_EVENTS,
  VOICE_SHARE,
  WATCHLIST,
} from './editorial/data'
import { TelanganaMap } from './editorial/TelanganaMap'
import styles from './editorial/styles.module.css'

interface CMEditorialBriefProps {
  /** Kept for signature parity with the previous component; demo mode
   *  ignores the token entirely. */
  token?: string | null
  /** When mounted inside the Brief page wrapper, skip the deckled edge
   *  and outer paper background to avoid double-padding. */
  embedded?: boolean
}

export function CMEditorialBrief({ embedded = false }: CMEditorialBriefProps) {
  return (
    <section
      className={styles.shell}
      data-embedded={embedded ? 'true' : 'false'}
    >
      <div className={styles.frame}>
        <Header />
        <div className={styles.body}>
          <div className={styles.demoWatermark} aria-hidden="true">
            <span>DEMO</span>
          </div>
          <TelanganaMap />
          <RightStack />
        </div>
        <Ticker />
        <p className={styles.editorsNote}>
          Editor’s note · three signals deserve the CM’s attention before 18:00
          today — Musi rehab counter-narrative, Khammam farmer assembly, and the
          Group-1 transparency briefing.
        </p>
        <p className={styles.demoDisclaimer}>
          Preview build · figures and quotations are illustrative, generated for
          layout review · not derived from live intelligence.
        </p>
      </div>
    </section>
  )
}

export default CMEditorialBrief

/* ------------------------------------------------------------------ */
/* Header                                                              */
/* ------------------------------------------------------------------ */

function Header() {
  return (
    <header className={styles.header}>
      <div className={styles.headerLeft}>
        <span className={styles.ornament} aria-hidden="true" />
        <span>
          {HEADER.briefTitle} · {HEADER.region}
        </span>
      </div>
      <div className={styles.headerCenter}>{HEADER.dateline} · {useClock()}</div>
      <div className={styles.headerRight}>
        <span className={styles.demoStamp}>Preview · Demo data</span>
        <span className={styles.liveStamp}>
          <span className={styles.liveDot} />
          <span>As of {HEADER.asOf} · Live feed</span>
        </span>
        <span className={styles.cmName}>
          <span className={styles.cmAvatar}>R</span>
          <span>
            {HEADER.cmName} · {HEADER.cmParty}
          </span>
        </span>
      </div>
    </header>
  )
}

/** Demo clock — ticks every second so the page feels alive even without a feed. */
function useClock(): string {
  const [now, setNow] = useState<string>(() => HEADER.asOf + ':22 IST')
  useEffect(() => {
    const fmt = () => {
      const d = new Date()
      const hh = String(d.getHours()).padStart(2, '0')
      const mm = String(d.getMinutes()).padStart(2, '0')
      const ss = String(d.getSeconds()).padStart(2, '0')
      return `${hh}:${mm}:${ss} IST`
    }
    setNow(fmt())
    const id = window.setInterval(() => setNow(fmt()), 1000)
    return () => window.clearInterval(id)
  }, [])
  return now
}

/* ------------------------------------------------------------------ */
/* Right column — hero panel + 6 cards.                                */
/* ------------------------------------------------------------------ */

function RightStack() {
  return (
    <div className={styles.stack}>
      <Hero />
      <div className={styles.cards}>
        <NewsCard />
        <OppositionCard />
        <ActionsCard />
        <WatchlistCard />
        <ThreatsCard />
        <ForecastCard />
      </div>
    </div>
  )
}

function Hero() {
  return (
    <article className={styles.heroPanel}>
      <div className={styles.heroEyebrow}>{HERO.eyebrow}</div>
      <h2 className={styles.heroHeadline}>{HERO.headline}</h2>
      <div className={styles.heroFooter}>
        <a className={styles.heroLink} href="#source">
          {HERO.link} →
        </a>
        <Sparkline values={[...HERO.sparkline]} className={styles.heroSpark} />
      </div>
    </article>
  )
}

interface SparklineProps {
  values: number[]
  className?: string
}

function Sparkline({ values, className }: SparklineProps) {
  if (values.length < 2) return null
  const W = 180
  const H = 36
  const padX = 6
  const padY = 6
  const min = Math.min(...values) - 0.02
  const max = Math.max(...values) + 0.02
  const w = W - padX * 2
  const h = H - padY * 2
  const points = values.map((v, i) => {
    const x = padX + (i / (values.length - 1)) * w
    const y = padY + ((max - v) / (max - min)) * h
    return [x, y] as const
  })
  const linePath = `M ${points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' L ')}`
  return (
    <svg
      className={className}
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Sentiment sparkline since 09:00"
    >
      <path
        d={linePath}
        fill="none"
        stroke="#3a2a1a"
        strokeWidth={1.4}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle
        cx={points[points.length - 1][0]}
        cy={points[points.length - 1][1]}
        r={2.4}
        fill="#9c2b1f"
      />
    </svg>
  )
}

/* ------------------------------------------------------------------ */
/* News Desk                                                           */
/* ------------------------------------------------------------------ */

function NewsCard() {
  return (
    <section className={styles.card}>
      <div className={styles.deskHeader}>
        <span>News Desk</span>
        <span className={styles.deskMeta}>{NEWS_DESK.length} stories</span>
      </div>
      {NEWS_DESK.map((item, i) => (
        <div key={i} className={styles.row}>
          <span className={styles.sourcePill}>{item.source}</span>
          <span className={styles.rowBody}>{item.headline}</span>
          <span className={styles.rowMeta}>
            {item.ageLabel}
            {item.reach ? ` · ${item.reach}` : ''}
          </span>
        </div>
      ))}
    </section>
  )
}

/* ------------------------------------------------------------------ */
/* Opposition Desk                                                     */
/* ------------------------------------------------------------------ */

function OppositionCard() {
  const total = VOICE_SHARE.parts.reduce((acc, p) => acc + p.value, 0)
  return (
    <section className={styles.card}>
      <div className={styles.deskHeader}>
        <span>Opposition Desk</span>
        <span className={styles.deskMeta}>{OPPOSITION_DESK.length} actors</span>
      </div>
      {OPPOSITION_DESK.map((item, i) => (
        <div key={i} className={styles.row}>
          <span className={styles.sourcePill}>
            {item.actor}{' '}
            <span style={{ opacity: 0.6, fontStyle: 'normal' }}>
              ({item.party})
            </span>
          </span>
          <span className={styles.rowBody}>{item.summary}</span>
          <span className={styles.rowMeta}>
            <span className={styles.chip}>{item.sentiment.toFixed(1)}</span>{' '}
            {item.ageLabel}
          </span>
        </div>
      ))}

      <div className={styles.voiceBar}>
        {VOICE_SHARE.parts.map((p) => {
          const pct = (p.value / total) * 100
          const fill =
            p.party === 'BRS'
              ? '#6b3f1d'
              : p.party === 'BJP'
                ? '#c9a373'
                : '#1d3557'
          const color = p.party === 'BJP' ? '#1a1a1a' : '#f5f0e6'
          return (
            <div
              key={p.party}
              className={styles.voiceSegment}
              style={{ width: `${pct}%`, background: fill, color }}
            >
              {p.party} {p.value}%
            </div>
          )
        })}
      </div>
      <div className={styles.voiceLegend}>
        <span>{VOICE_SHARE.label}</span>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ */
/* Action Items                                                        */
/* ------------------------------------------------------------------ */

function ActionsCard() {
  return (
    <section className={styles.card}>
      <div className={styles.deskHeader}>
        <span>Action Items</span>
        <span className={styles.deskMeta}>for the chair</span>
      </div>
      {ACTIONS.map((a, i) => (
        <div key={i} className={styles.actionRow}>
          <span className={styles.checkbox} aria-hidden="true" />
          <span
            className={`${styles.priorityChip} ${
              a.priority === 'P0'
                ? styles.priorityP0
                : a.priority === 'P1'
                  ? styles.priorityP1
                  : styles.priorityP2
            }`}
          >
            {a.priority}
          </span>
          <span style={{ flex: 1 }}>{a.text}</span>
        </div>
      ))}
    </section>
  )
}

/* ------------------------------------------------------------------ */
/* Watchlist                                                           */
/* ------------------------------------------------------------------ */

function WatchlistCard() {
  return (
    <section className={styles.card}>
      <div className={styles.deskHeader}>
        <span>Watchlist</span>
        <span className={styles.deskMeta}>{WATCHLIST.length} entities</span>
      </div>
      {WATCHLIST.map((w) => {
        const cls = w.flat
          ? styles.watchDeltaFlat
          : (w.delta ?? 0) > 0
            ? styles.watchDeltaUp
            : styles.watchDeltaDown
        const arrow = w.flat ? '→' : (w.delta ?? 0) > 0 ? '↑' : '↓'
        const text = w.flat
          ? 'flat'
          : `${arrow} ${(w.delta ?? 0) > 0 ? '+' : ''}${w.delta}%`
        return (
          <div key={w.label} className={styles.watchRow}>
            <span className={styles.watchLabel}>{w.label}</span>
            <span className={`${styles.watchDelta} ${cls}`}>{text}</span>
          </div>
        )
      })}
    </section>
  )
}

/* ------------------------------------------------------------------ */
/* Threat cartouche — 3×3 matrix.                                      */
/* ------------------------------------------------------------------ */

function ThreatsCard() {
  // viewBox 0 0 240 170; x = impact 0..2, y = likelihood 0..2 (inverted)
  const PAD_L = 36
  const PAD_R = 16
  const PAD_T = 14
  const PAD_B = 36
  const W = 240
  const H = 170
  const plotW = W - PAD_L - PAD_R
  const plotH = H - PAD_T - PAD_B
  function px(impact: number) {
    return PAD_L + (impact / 2) * plotW
  }
  function py(likelihood: number) {
    return PAD_T + ((2 - likelihood) / 2) * plotH
  }
  return (
    <section className={styles.card}>
      <div className={styles.deskHeader}>
        <span>Threat Matrix</span>
        <span className={styles.deskMeta}>{THREATS.length} tracked</span>
      </div>
      <div className={styles.cartouche}>
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Threat matrix">
          {/* grid */}
          {[0, 1, 2].map((i) => (
            <g key={i}>
              <line
                x1={px(i)}
                y1={PAD_T}
                x2={px(i)}
                y2={H - PAD_B}
                stroke="#3a2a1a"
                strokeOpacity={0.18}
                strokeWidth={0.7}
              />
              <line
                x1={PAD_L}
                y1={py(i)}
                x2={W - PAD_R}
                y2={py(i)}
                stroke="#3a2a1a"
                strokeOpacity={0.18}
                strokeWidth={0.7}
              />
            </g>
          ))}
          {/* axes */}
          <line
            x1={PAD_L}
            y1={H - PAD_B}
            x2={W - PAD_R}
            y2={H - PAD_B}
            stroke="#3a2a1a"
            strokeWidth={1}
          />
          <line
            x1={PAD_L}
            y1={PAD_T}
            x2={PAD_L}
            y2={H - PAD_B}
            stroke="#3a2a1a"
            strokeWidth={1}
          />
          {/* axis labels */}
          <text
            x={W / 2}
            y={H - 8}
            textAnchor="middle"
            fontFamily="'Tiempos Text','Lora','Georgia',serif"
            fontStyle="italic"
            fontSize={11}
            fill="#3a2a1a"
          >
            Impact →
          </text>
          <text
            x={10}
            y={H / 2}
            textAnchor="middle"
            fontFamily="'Tiempos Text','Lora','Georgia',serif"
            fontStyle="italic"
            fontSize={11}
            fill="#3a2a1a"
            transform={`rotate(-90 10 ${H / 2})`}
          >
            Likelihood ↑
          </text>
          {/* plotted dots */}
          {THREATS.map((t, i) => {
            const cx = px(t.impact)
            const cy = py(t.likelihood)
            const isMed = t.level === 'MED' || t.level === 'LOW-MED'
            return (
              <g key={i}>
                <circle
                  cx={cx}
                  cy={cy}
                  r={isMed ? 5.5 : 4}
                  fill={isMed ? '#9c2b1f' : '#1a1a1a'}
                  fillOpacity={isMed ? 0.85 : 0.7}
                  stroke={isMed ? '#5a160e' : '#1a1a1a'}
                  strokeWidth={0.8}
                />
                <text
                  x={cx + 8}
                  y={cy + 3}
                  fontFamily="'Tiempos Text','Lora','Georgia',serif"
                  fontStyle="italic"
                  fontSize={10}
                  fill="#3a2a1a"
                >
                  {t.label} [{t.level}]
                </text>
              </g>
            )
          })}
        </svg>
        <div className={styles.cartoucheCaption}>
          plotted by likelihood × impact, rebalanced every 30 minutes
        </div>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ */
/* Forecast — line + confidence fan.                                   */
/* ------------------------------------------------------------------ */

function ForecastCard() {
  const W = 240
  const H = 110
  const PAD_L = 26
  const PAD_R = 10
  const PAD_T = 10
  const PAD_B = 22
  const plotW = W - PAD_L - PAD_R
  const plotH = H - PAD_T - PAD_B
  const minY = -0.55
  const maxY = -0.25
  const points = FORECAST_POINTS.map((p, i) => {
    const x = PAD_L + (i / (FORECAST_POINTS.length - 1)) * plotW
    const y = PAD_T + ((maxY - p.sentiment) / (maxY - minY)) * plotH
    const yU =
      PAD_T + ((maxY - (p.sentiment + p.band)) / (maxY - minY)) * plotH
    const yL =
      PAD_T + ((maxY - (p.sentiment - p.band)) / (maxY - minY)) * plotH
    return { x, y, yU, yL, day: p.day }
  })
  const linePath = `M ${points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' L ')}`
  const upper = points.map((p) => `${p.x.toFixed(1)},${p.yU.toFixed(1)}`)
  const lower = [...points]
    .reverse()
    .map((p) => `${p.x.toFixed(1)},${p.yL.toFixed(1)}`)
  const bandPath = `M ${[...upper, ...lower].join(' L ')} Z`

  return (
    <section className={styles.card}>
      <div className={styles.deskHeader}>
        <span>Forecast · 7 Days</span>
        <span className={styles.deskMeta}>±0.06 band</span>
      </div>
      <div className={styles.cartouche}>
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="7-day sentiment forecast">
          {/* axes */}
          <line
            x1={PAD_L}
            y1={H - PAD_B}
            x2={W - PAD_R}
            y2={H - PAD_B}
            stroke="#3a2a1a"
            strokeWidth={0.9}
          />
          <line
            x1={PAD_L}
            y1={PAD_T}
            x2={PAD_L}
            y2={H - PAD_B}
            stroke="#3a2a1a"
            strokeWidth={0.9}
          />
          {/* zero-ish reference rule */}
          <line
            x1={PAD_L}
            y1={PAD_T + ((maxY - -0.4) / (maxY - minY)) * plotH}
            x2={W - PAD_R}
            y2={PAD_T + ((maxY - -0.4) / (maxY - minY)) * plotH}
            stroke="#3a2a1a"
            strokeOpacity={0.18}
            strokeDasharray="2 3"
            strokeWidth={0.7}
          />
          {/* confidence band */}
          <path d={bandPath} fill="#6b3f1d" fillOpacity={0.16} stroke="none" />
          {/* line */}
          <path
            d={linePath}
            fill="none"
            stroke="#3a2a1a"
            strokeWidth={1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {/* dots */}
          {points.map((p, i) => (
            <circle key={i} cx={p.x} cy={p.y} r={1.8} fill="#3a2a1a" />
          ))}
          {/* x-axis day labels — first / mid / last to keep it sparse */}
          {[0, Math.floor(points.length / 2), points.length - 1].map((i) => (
            <text
              key={i}
              x={points[i].x}
              y={H - 8}
              textAnchor={i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle'}
              fontFamily="'Söhne Mono','IBM Plex Mono','Menlo',monospace"
              fontSize={9}
              fill="#3a2a1a"
              opacity={0.78}
            >
              {points[i].day}
            </text>
          ))}
          {/* y-axis labels */}
          <text
            x={PAD_L - 4}
            y={PAD_T + 4}
            textAnchor="end"
            fontFamily="'Söhne Mono','IBM Plex Mono','Menlo',monospace"
            fontSize={9}
            fill="#3a2a1a"
            opacity={0.78}
          >
            -0.25
          </text>
          <text
            x={PAD_L - 4}
            y={H - PAD_B}
            textAnchor="end"
            fontFamily="'Söhne Mono','IBM Plex Mono','Menlo',monospace"
            fontSize={9}
            fill="#3a2a1a"
            opacity={0.78}
          >
            -0.55
          </text>
        </svg>
        <div className={styles.forecastCaption}>{FORECAST_CAPTION}</div>
      </div>
      <p className={styles.forecastNarrative}>{FORECAST_NARRATIVE}</p>
    </section>
  )
}

/* ------------------------------------------------------------------ */
/* Bottom cross-fading ticker.                                         */
/* ------------------------------------------------------------------ */

function Ticker() {
  const [idx, setIdx] = useState(0)
  const events = useMemo(() => TICKER_EVENTS, [])
  useEffect(() => {
    const id = window.setInterval(() => {
      setIdx((i) => (i + 1) % events.length)
    }, 4000)
    return () => window.clearInterval(id)
  }, [events.length])
  return (
    <div className={styles.tickerRail} aria-live="polite">
      {events.map((e, i) => (
        <div
          key={i}
          className={`${styles.tickerEvent} ${i === idx ? styles.tickerEventActive : ''}`}
        >
          <span className={styles.tickerArrow}>»</span>
          <span className={styles.tickerTime}>{e.time}</span>
          <span>{e.text}</span>
          <span className={styles.tickerArrow}>«</span>
        </div>
      ))}
    </div>
  )
}
