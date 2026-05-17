/**
 * CompetitorMentions — horizontal bars showing user vs. competitor
 * entities by article mentions in the current week. The user's bar is
 * red and glowing; competitors are bone.
 *
 * Sprint 1: hardcoded with the four canonical Telangana figures.
 * Sprint 2+: reads a per-week per-entity aggregation from
 * `user_watched_entities` × `articles.matched_entities`.
 */
'use client'

interface CompetitorRow {
  id: string
  name: string
  count: number
  /** Render the row as the user's own (red, glowing). */
  isYou?: boolean
}

interface CompetitorMentionsProps {
  rows?: ReadonlyArray<CompetitorRow>
}

const DEFAULT_ROWS: ReadonlyArray<CompetitorRow> = [
  { id: 'rev',     name: 'Revanth Reddy',          count: 47, isYou: true },
  { id: 'ktr',     name: 'K. T. Rama Rao',         count: 31 },
  { id: 'bandi',   name: 'Bandi Sanjay',           count: 18 },
  { id: 'kcr',     name: 'K. Chandrashekar Rao',   count: 8 },
]

export function CompetitorMentions({ rows }: CompetitorMentionsProps) {
  const data = rows ?? DEFAULT_ROWS
  const max = Math.max(1, ...data.map((r) => r.count))
  return (
    <div>
      {data.map((r) => {
        const pct = (r.count / max) * 100
        return (
          <div
            key={r.id}
            style={{
              display: 'grid',
              gridTemplateColumns: '160px 1fr 50px',
              gap: '14px',
              alignItems: 'center',
              padding: '8px 0',
              borderBottom: '1px solid rgba(255,255,255,0.03)',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--onyx-display)',
                fontSize: '13px',
                color: r.isYou ? 'var(--onyx-red)' : 'var(--onyx-bone)',
              }}
            >
              {r.name}
            </span>
            <div
              style={{
                position: 'relative',
                height: '4px',
                background: 'rgba(255,255,255,0.06)',
              }}
            >
              <i
                style={{
                  position: 'absolute',
                  left: 0,
                  top: 0,
                  bottom: 0,
                  width: `${pct}%`,
                  background: r.isYou ? 'var(--onyx-red)' : 'var(--onyx-bone-2)',
                  boxShadow: r.isYou ? '0 0 8px var(--onyx-red)' : 'none',
                }}
              />
            </div>
            <span
              className="onyx-mono"
              style={{
                fontSize: '11px',
                color: 'var(--onyx-bone)',
                textAlign: 'right',
              }}
            >
              {r.count}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export type { CompetitorRow }
