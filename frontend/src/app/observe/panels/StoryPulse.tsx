'use client'

import { observeApi } from '@/lib/observe-client'
import { useObservePoll } from '../hooks/useObservePoll'
import { Panel } from './Panel'

export function StoryPulse() {
  const { data, isLoading, error } = useObservePoll(
    ['story-pulse'],
    () => observeApi.storyPulse(20),
    { visibleIntervalMs: 15000, hiddenIntervalMs: 60000 }
  )

  return (
    <Panel
      title="Story pulse"
      subtitle={data ? `${data.clusters.length} active multi-source clusters` : ''}
      loading={isLoading}
      error={error}
    >
      <ul className="space-y-1 text-xs max-h-72 overflow-y-auto">
        {data?.clusters.map((c) => (
          <li key={c.cluster_id} className="border-b border-neutral-200 py-1">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium truncate" title={c.headline}>
                {c.headline}
              </span>
              <span className="shrink-0 text-neutral-500 font-mono">
                {c.source_count}×srcs / {c.article_count}arts
                {c.new_24h > 0 && (
                  <span className="ml-1 text-emerald-700">+{c.new_24h}/24h</span>
                )}
              </span>
            </div>
            {c.event_type && (
              <span className="rounded bg-neutral-100 px-1 py-0.5 text-[10px] text-neutral-600">
                {c.event_type}
              </span>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  )
}
