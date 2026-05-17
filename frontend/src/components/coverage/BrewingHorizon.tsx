/**
 * BrewingHorizon — five "unborn stories" plotted on a horizontal line.
 * Position left = closer to breaking; right = farther. Each node glows
 * by stage: brightest at stage-4 (about to break), faintest at stage-1.
 * Hover reveals a tooltip with stage / headline / source-count.
 *
 * Sprint 1: hardcoded with five realistic Telangana stories at different
 * stages of formation.
 * Sprint 2+: reads from a `tasks.detect_brewing_stories` aggregation
 * over watched entities.
 */
'use client'

import { useState } from 'react'

interface BrewingNode {
  id: string
  positionPct: number          // 0–100 across the horizon (low = closer to breaking)
  stage: 1 | 2 | 3 | 4
  headline: string
  detail: string
  sourceCount: number
}

interface BrewingHorizonProps {
  nodes?: ReadonlyArray<BrewingNode>
}

const DEFAULT_NODES: ReadonlyArray<BrewingNode> = [
  {
    id: 'b1',
    positionPct: 8,
    stage: 4,
    headline: 'Anti-Dharani drumbeat about to cross to mainstream',
    detail:
      'Three opposition channels carrying near-identical phrasing in 36h. ' +
      'Mainstream pickup probability 70% in next 12h.',
    sourceCount: 3,
  },
  {
    id: 'b2',
    positionPct: 24,
    stage: 3,
    headline: 'Bot cluster amplifying irrigation file',
    detail:
      '12 accounts younger than 21 days posting in lockstep. ' +
      'Stage 3 expected in 18h if no response.',
    sourceCount: 12,
  },
  {
    id: 'b3',
    positionPct: 46,
    stage: 2,
    headline: 'Power-tariff narrative seeded in 2 channels',
    detail:
      'Specific phrasing about rural feeder cuts appearing in adversarial ' +
      'Telegram. No mainstream signal yet. Lead time ~36h.',
    sourceCount: 2,
  },
  {
    id: 'b4',
    positionPct: 68,
    stage: 2,
    headline: 'Khammam contractor allegations forming',
    detail:
      'Local-press only so far. One Reddit thread building. Watch for ' +
      'crossover to Telugu YouTube panel discussions.',
    sourceCount: 1,
  },
  {
    id: 'b5',
    positionPct: 88,
    stage: 1,
    headline: 'Cabinet-reshuffle speculation seeded',
    detail:
      'Single source. Specific named ministers. Speculative phase. May die ' +
      'or grow over 72h.',
    sourceCount: 1,
  },
]

function nodeSize(stage: BrewingNode['stage']): { px: number; opacity: number } {
  switch (stage) {
    case 4: return { px: 12, opacity: 1 }
    case 3: return { px: 11, opacity: 0.7 }
    case 2: return { px: 9,  opacity: 0.5 }
    case 1: return { px: 8,  opacity: 0.3 }
  }
}

export function BrewingHorizon({ nodes }: BrewingHorizonProps) {
  const data = nodes ?? DEFAULT_NODES
  const [hovered, setHovered] = useState<string | null>(null)

  const active = data.find((n) => n.id === hovered)
  return (
    <div style={{ position: 'relative', height: '130px' }}>
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: '60px',
          height: '1px',
          background: 'var(--onyx-red-hair, rgba(255,45,45,0.3))',
        }}
      />
      {data.map((n) => {
        const sz = nodeSize(n.stage)
        return (
          <button
            key={n.id}
            type="button"
            aria-label={`Brewing story: ${n.headline}`}
            onMouseEnter={() => setHovered(n.id)}
            onMouseLeave={() => setHovered((h) => (h === n.id ? null : h))}
            onFocus={() => setHovered(n.id)}
            onBlur={() => setHovered((h) => (h === n.id ? null : h))}
            style={{
              position: 'absolute',
              left: `${n.positionPct}%`,
              top: '60px',
              transform: 'translate(-50%, -50%)',
              width: `${sz.px}px`,
              height: `${sz.px}px`,
              borderRadius: '50%',
              border: 'none',
              padding: 0,
              cursor: 'pointer',
              background: `rgba(255,45,45,${sz.opacity})`,
              boxShadow: `0 0 ${10 + sz.px}px rgba(255,45,45,${sz.opacity})`,
              animation: 'onyx-pulse-cyan 2.4s ease-in-out infinite',
            }}
          />
        )
      })}

      {/* Axis labels */}
      <span
        className="onyx-mono"
        style={{
          position: 'absolute',
          left: 0,
          bottom: '6px',
          fontSize: '8.5px',
          color: 'var(--onyx-dim)',
          letterSpacing: '0.3em',
          textTransform: 'uppercase',
        }}
      >
        closer to breaking ←
      </span>
      <span
        className="onyx-mono"
        style={{
          position: 'absolute',
          right: 0,
          bottom: '6px',
          fontSize: '8.5px',
          color: 'var(--onyx-dim)',
          letterSpacing: '0.3em',
          textTransform: 'uppercase',
        }}
      >
        → farther
      </span>

      {/* Tooltip card */}
      {active && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: `${active.positionPct}%`,
            transform: 'translate(-50%, -100%)',
            width: '260px',
            padding: '12px 14px',
            background: 'rgba(10,10,12,0.96)',
            border: '1px solid var(--onyx-red-hair, rgba(255,45,45,0.3))',
            pointerEvents: 'none',
            zIndex: 5,
          }}
        >
          <div
            className="onyx-mono"
            style={{
              fontSize: '9px',
              letterSpacing: '0.42em',
              color: 'var(--onyx-red)',
              textTransform: 'uppercase',
              marginBottom: '6px',
            }}
          >
            {`Stage ${active.stage} of 4`}
          </div>
          <div
            style={{
              fontFamily: 'var(--onyx-display)',
              fontSize: '13px',
              fontWeight: 500,
              color: 'var(--onyx-bone)',
              lineHeight: 1.3,
              marginBottom: '6px',
            }}
          >
            {active.headline}
          </div>
          <p
            style={{
              margin: 0,
              fontStyle: 'italic',
              fontSize: '11px',
              color: 'var(--onyx-bone-2)',
              lineHeight: 1.4,
            }}
          >
            {active.detail}
          </p>
          <div
            className="onyx-mono"
            style={{
              marginTop: '8px',
              fontSize: '8.5px',
              letterSpacing: '0.28em',
              color: 'var(--onyx-dim)',
              textTransform: 'uppercase',
            }}
          >
            {`${active.sourceCount} ${active.sourceCount === 1 ? 'source' : 'sources'}`}
          </div>
        </div>
      )}
    </div>
  )
}

export type { BrewingNode }
