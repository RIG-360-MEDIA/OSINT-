/**
 * SentimentTrajectory — 14-day sentiment line chart for the user's
 * primary watched entity. SVG, no external chart library. Wave events
 * marked with red dots inline.
 *
 * Sprint 1: hardcoded 15-point series for Revanth Reddy showing the
 * three Dharani waves landing.
 * Sprint 2+: reads from a per-entity sentiment-aggregation endpoint.
 */
'use client'

interface SentimentPoint {
  readonly day: string       // 'DD MMM'
  readonly value: number     // sentiment in [-1, +1]
  readonly note?: string     // e.g. 'Wave 1'
}

interface SentimentTrajectoryProps {
  entityName?: string
  series?: ReadonlyArray<SentimentPoint>
  thirtyDayAvg?: number
  todayValue?: number
}

const DEFAULT_SERIES: ReadonlyArray<SentimentPoint> = [
  { day: '28 Apr', value:  0.12 },
  { day: '29 Apr', value:  0.10 },
  { day: '30 Apr', value:  0.04 },
  { day: '01 May', value:  0.02 },
  { day: '02 May', value: -0.04 },
  { day: '03 May', value: -0.08 },
  { day: '04 May', value: -0.12, note: 'Wave 1' },
  { day: '05 May', value: -0.18 },
  { day: '06 May', value: -0.22 },
  { day: '07 May', value: -0.26, note: 'Wave 2' },
  { day: '08 May', value: -0.30 },
  { day: '09 May', value: -0.36, note: 'Wave 3' },
  { day: '10 May', value: -0.38 },
  { day: '11 May', value: -0.34 },
]

export function SentimentTrajectory({
  entityName = 'Revanth Reddy',
  series = DEFAULT_SERIES,
  thirtyDayAvg = -0.18,
  todayValue = -0.34,
}: SentimentTrajectoryProps) {
  const N = series.length
  const w = 800
  const h = 100
  const xStep = w / Math.max(1, N - 1)
  const toY = (v: number): number => h / 2 - (v * h) / 2 // map -1..+1 to h..0

  const pathD = series
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${i * xStep},${toY(p.value)}`)
    .join(' ')
  const area = `${pathD} L ${w},${h} L 0,${h} Z`

  return (
    <div
      style={{
        background: 'rgba(8, 8, 12, 0.5)',
        border: '1px solid rgba(255,255,255,0.04)',
        padding: '14px 18px',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          marginBottom: '8px',
        }}
      >
        <h6
          style={{
            margin: 0,
            fontFamily: 'var(--onyx-display)',
            fontSize: '13px',
            color: 'var(--onyx-bone)',
            fontWeight: 500,
          }}
        >
          {`Sentiment toward ${entityName}`}
        </h6>
        <span
          className="onyx-mono"
          style={{
            fontSize: '10px',
            letterSpacing: '0.28em',
            color: 'var(--onyx-bone-2)',
            textTransform: 'uppercase',
          }}
        >
          {'30D AVG '}
          <b style={{ color: 'var(--onyx-red)' }}>{thirtyDayAvg.toFixed(2)}</b>
          {' · today '}
          <b style={{ color: 'var(--onyx-red)' }}>{todayValue.toFixed(2)}</b>
        </span>
      </div>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        preserveAspectRatio="none"
        style={{ width: '100%', height: '120px' }}
        role="img"
        aria-label={`Sentiment trajectory toward ${entityName} over ${N} days`}
      >
        <defs>
          <linearGradient id="sentGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#FF2D2D" stopOpacity="0.22" />
            <stop offset="1" stopColor="#FF2D2D" stopOpacity="0" />
          </linearGradient>
        </defs>
        <line
          x1={0}
          y1={h / 2}
          x2={w}
          y2={h / 2}
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={1}
        />
        <path d={area} fill="url(#sentGrad)" />
        <path d={pathD} stroke="#FF2D2D" strokeWidth={1.4} fill="none" />
        {series.map((p, i) =>
          p.note ? (
            <g key={`note-${i}`}>
              <circle
                cx={i * xStep}
                cy={toY(p.value)}
                r={3}
                fill="#FF2D2D"
              />
              <text
                x={i * xStep + 6}
                y={toY(p.value) - 6}
                fontFamily="JetBrains Mono, monospace"
                fontSize={9}
                fill="#A8ADB8"
              >
                {p.note}
              </text>
            </g>
          ) : null,
        )}
        <circle
          cx={(N - 1) * xStep}
          cy={toY(series[N - 1].value)}
          r={4}
          fill="#FF2D2D"
          stroke="#fff"
          strokeWidth={0.5}
        />
      </svg>
    </div>
  )
}

export type { SentimentPoint }
