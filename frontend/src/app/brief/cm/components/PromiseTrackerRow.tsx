'use client'

import type { PromiseRow } from '../types'

const STATUS_COLOR: Record<PromiseRow['status'], string> = {
  kept: 'var(--rig-gold)',
  in_progress: 'var(--rig-ink-2)',
  stalled: 'var(--rig-oxblood)',
  broken: 'var(--rig-oxblood-2)',
  unknown: 'var(--rig-ink-3)',
}

const STATUS_COPY: Record<PromiseRow['status'], string> = {
  kept: 'KEPT',
  in_progress: 'IN PROGRESS',
  stalled: 'STALLED',
  broken: 'BROKEN',
  unknown: 'UNKNOWN',
}

export function PromiseTrackerTable({ rows }: { rows: PromiseRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="rig-prose" style={{ fontStyle: 'italic', color: 'var(--rig-ink-3)' }}>
        Manifesto ledger not yet loaded.
      </p>
    )
  }
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr>
          {['Promise', 'Owner', 'Deadline', 'Status', 'Exploitation'].map((h) => (
            <th
              key={h}
              className="rig-byline"
              style={{
                textAlign: 'left',
                color: 'var(--rig-ink-3)',
                paddingBottom: 8,
                borderBottom: '1px solid var(--rig-ink-4)',
              }}
            >
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id} style={{ borderBottom: '1px solid var(--rig-ink-4)' }}>
            <td style={{ padding: '10px 8px 10px 0', verticalAlign: 'top' }}>
              <span
                style={{
                  fontFamily: 'var(--font-serif)',
                  fontSize: 15,
                  color: 'var(--rig-ink)',
                  fontStyle: 'italic',
                }}
              >
                {r.pledge_short || r.pledge_text}
              </span>
              {r.source_url && (
                <a
                  href={r.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="rig-byline"
                  style={{ display: 'block', marginTop: 4, color: 'var(--rig-ink-3)', textDecoration: 'underline' }}
                >
                  source
                </a>
              )}
            </td>
            <td style={{ padding: '10px 8px', verticalAlign: 'top' }}>
              <span className="rig-byline" style={{ color: 'var(--rig-ink-2)' }}>
                {r.owner_party}
              </span>
            </td>
            <td style={{ padding: '10px 8px', verticalAlign: 'top' }}>
              <span className="rig-byline" style={{ color: 'var(--rig-ink-3)' }}>
                {r.deadline ? new Date(r.deadline).toLocaleDateString('en-IN') : '—'}
              </span>
            </td>
            <td style={{ padding: '10px 8px', verticalAlign: 'top' }}>
              <span
                className="rig-byline"
                style={{
                  padding: '3px 8px',
                  border: `1px solid ${STATUS_COLOR[r.status]}`,
                  color: STATUS_COLOR[r.status],
                }}
              >
                {STATUS_COPY[r.status]}
              </span>
              {typeof r.status_confidence === 'number' && (
                <span className="rig-byline" style={{ color: 'var(--rig-ink-3)', marginLeft: 8 }}>
                  {(r.status_confidence * 100).toFixed(0)}%
                </span>
              )}
            </td>
            <td style={{ padding: '10px 0 10px 8px', verticalAlign: 'top', minWidth: 110 }}>
              <div
                style={{
                  position: 'relative',
                  height: 6,
                  background: 'var(--rig-paper-2)',
                  border: '1px solid var(--rig-ink-4)',
                }}
              >
                <div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    width: `${Math.min(100, r.exploitation_index)}%`,
                    background: 'var(--rig-oxblood)',
                  }}
                />
              </div>
              <span className="rig-byline" style={{ color: 'var(--rig-ink-3)' }}>
                {r.exploitation_index.toFixed(0)}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default PromiseTrackerTable
