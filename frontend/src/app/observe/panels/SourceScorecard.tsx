'use client'

import { useState } from 'react'

import { observeApi } from '@/lib/observe-client'
import { useObservePoll } from '../hooks/useObservePoll'
import { Panel } from './Panel'

type SortKey = 'total' | 'has_summary_pct' | 'has_embedding_pct' | 'source'

export function SourceScorecard() {
  const { data, isLoading, error } = useObservePoll(
    ['source-scorecard'],
    () => observeApi.sourceScorecard(),
    { visibleIntervalMs: 30000, hiddenIntervalMs: 120000 }
  )
  const [sortKey, setSortKey] = useState<SortKey>('total')

  const sorted = data
    ? [...data.sources].sort((a, b) => {
        if (sortKey === 'source') return a.source.localeCompare(b.source)
        return (b[sortKey] as number) - (a[sortKey] as number)
      })
    : []

  return (
    <Panel
      title="Source scorecard"
      subtitle={data ? `${data.sources.length} sources` : ''}
      loading={isLoading}
      error={error}
    >
      <div className="max-h-72 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-neutral-100 dark:bg-neutral-800">
            <tr>
              {([
                ['source', 'Source'],
                ['total', 'Total'],
                ['has_summary_pct', 'Summary %'],
                ['has_embedding_pct', 'Embed %'],
              ] as Array<[SortKey, string]>).map(([k, label]) => (
                <th
                  key={k}
                  onClick={() => setSortKey(k)}
                  className="cursor-pointer px-2 py-1 text-left hover:underline"
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.slice(0, 100).map((s) => (
              <tr key={s.source} className="border-b border-neutral-200">
                <td className="px-2 py-0.5 truncate max-w-[14ch]" title={s.source}>{s.source}</td>
                <td className="px-2 py-0.5 tabular-nums">{s.total.toLocaleString()}</td>
                <td className={`px-2 py-0.5 tabular-nums ${s.has_summary_pct < 70 ? 'text-amber-700' : ''}`}>
                  {s.has_summary_pct}
                </td>
                <td className={`px-2 py-0.5 tabular-nums ${s.has_embedding_pct < 70 ? 'text-amber-700' : ''}`}>
                  {s.has_embedding_pct}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}
