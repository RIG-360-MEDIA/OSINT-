'use client'

import { observeApi } from '@/lib/observe-client'
import { useObservePoll } from '../hooks/useObservePoll'
import { Panel } from './Panel'

export function IngestPulse() {
  const { data, isLoading, error } = useObservePoll(
    ['ingest-pulse'],
    () => observeApi.ingestPulse(),
    { visibleIntervalMs: 5000, hiddenIntervalMs: 30000 }
  )

  const totalLine =
    data ? `${data.total_24h.toLocaleString()} articles in last 24h · ${data.stalled_sources.length} sources stalled` : ''

  return (
    <Panel
      title="Ingest pulse"
      subtitle={totalLine}
      loading={isLoading}
      error={error}
    >
      {data && (
        <div className="space-y-2">
          {/* Hourly sparkline (text bars — no chart lib needed) */}
          <div className="flex h-12 items-end gap-px" data-testid="hourly-bars">
            {data.by_hour.map((b) => {
              const max = Math.max(...data.by_hour.map((x) => x.n), 1)
              const h = Math.max(2, Math.round((b.n / max) * 48))
              return (
                <div
                  key={b.hour}
                  className="flex-1 bg-emerald-500/70"
                  style={{ height: `${h}px` }}
                  title={`${b.hour}: ${b.n}`}
                />
              )
            })}
          </div>
          {data.stalled_sources.length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer text-amber-700">
                {data.stalled_sources.length} stalled (&gt;24h)
              </summary>
              <ul className="mt-1 max-h-40 overflow-y-auto">
                {data.stalled_sources.slice(0, 50).map((s) => (
                  <li key={s.source} className="flex justify-between border-b border-neutral-200 py-0.5">
                    <span>{s.source}</span>
                    <span className="text-neutral-500">{s.hours_since.toFixed(1)}h</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </Panel>
  )
}
