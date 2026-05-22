'use client'

import { useState } from 'react'

import { observeApi } from '@/lib/observe-client'
import { useObservePoll } from '../hooks/useObservePoll'
import { Panel } from './Panel'

export function CrossTabAnalyst() {
  const [actor, setActor] = useState('')
  const [days, setDays] = useState(60)
  const [submitted, setSubmitted] = useState<{ actor: string; days: number } | null>(null)

  const { data, isLoading, error } = useObservePoll(
    ['crosstab', submitted?.actor || '', submitted?.days || 0],
    () => observeApi.crossTab(submitted!.actor, submitted!.days),
    { enabled: !!submitted?.actor, visibleIntervalMs: 60000, hiddenIntervalMs: 300000 }
  )

  return (
    <Panel
      title="Crosstab analyst"
      subtitle="Source × week for any actor (substring match)"
      loading={isLoading}
      error={error}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (actor.trim()) setSubmitted({ actor: actor.trim(), days })
        }}
        className="mb-2 flex items-center gap-2 text-xs"
      >
        <input
          value={actor}
          onChange={(e) => setActor(e.target.value)}
          placeholder="actor name (e.g. Modi)"
          className="flex-1 rounded border border-neutral-300 px-2 py-1"
          data-testid="crosstab-actor"
        />
        <input
          type="number"
          value={days}
          onChange={(e) => setDays(Math.max(1, Math.min(365, Number(e.target.value) || 30)))}
          className="w-16 rounded border border-neutral-300 px-2 py-1"
          aria-label="days"
        />
        <button type="submit" className="rounded bg-emerald-600 px-2 py-1 text-white">
          Run
        </button>
      </form>
      {data && (
        <div className="max-h-56 overflow-y-auto text-xs">
          <table className="w-full">
            <thead className="sticky top-0 bg-neutral-100">
              <tr>
                <th className="px-2 py-1 text-left">Source</th>
                <th className="px-2 py-1 text-left">Week</th>
                <th className="px-2 py-1 text-right">Events</th>
                <th className="px-2 py-1 text-right">Articles</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r, i) => (
                <tr key={`${r.source}-${r.week}-${i}`} className="border-b border-neutral-200">
                  <td className="px-2 py-0.5 truncate max-w-[18ch]" title={r.source}>{r.source}</td>
                  <td className="px-2 py-0.5">{r.week ?? '?'}</td>
                  <td className="px-2 py-0.5 text-right tabular-nums">{r.n_events}</td>
                  <td className="px-2 py-0.5 text-right tabular-nums">{r.n_articles}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}
