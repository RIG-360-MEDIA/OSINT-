'use client'

import { useState } from 'react'

import { observeApi } from '@/lib/observe-client'
import { useObservePoll } from '../hooks/useObservePoll'
import { Panel } from './Panel'

type Level = 'country' | 'state' | 'district'

export function GeoHeatmap() {
  const [level, setLevel] = useState<Level>('country')
  const { data, isLoading, error } = useObservePoll(
    ['geo-heatmap', level],
    () => observeApi.geoHeatmap(level),
    { visibleIntervalMs: 60000, hiddenIntervalMs: 300000 }
  )

  const max = data && data.regions.length ? Math.max(...data.regions.map((r) => r.n)) : 1

  return (
    <Panel
      title="Geo heatmap"
      subtitle={data ? `${data.regions.length} regions @ ${level}` : ''}
      loading={isLoading}
      error={error}
      actions={
        <select
          className="rounded border border-neutral-300 bg-white px-2 py-0.5 text-xs"
          value={level}
          onChange={(e) => setLevel(e.target.value as Level)}
          data-testid="geo-level-select"
        >
          <option value="country">country</option>
          <option value="state">state</option>
          <option value="district">district</option>
        </select>
      }
    >
      {data && (
        <ul className="grid grid-cols-2 gap-x-3 text-xs max-h-64 overflow-y-auto">
          {data.regions.slice(0, 60).map((r) => {
            const pct = (r.n / max) * 100
            return (
              <li key={r.region} className="relative border-b border-neutral-200/50 py-0.5">
                <div
                  className="absolute inset-y-0 left-0 -z-10 bg-sky-200/60"
                  style={{ width: `${pct}%` }}
                />
                <div className="flex justify-between">
                  <span className="truncate max-w-[18ch]">{r.region}</span>
                  <span className="tabular-nums font-mono">{r.n}</span>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </Panel>
  )
}
