'use client'

import { observeApi } from '@/lib/observe-client'
import { useObservePoll } from '../hooks/useObservePoll'
import { Panel } from './Panel'

export function LiveArticleTail() {
  const { data, isLoading, error } = useObservePoll(
    ['live-tail'],
    () => observeApi.liveTail(undefined, 30),
    { visibleIntervalMs: 5000, hiddenIntervalMs: 30000 }
  )

  return (
    <Panel
      title="Live article tail"
      subtitle="Most recent 30 articles (5s polling)"
      loading={isLoading}
      error={error}
    >
      <ul className="space-y-1 text-xs max-h-80 overflow-y-auto" data-testid="live-tail-list">
        {data?.articles.map((a) => (
          <li key={a.aid} className="border-b border-neutral-200/60 py-0.5">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate" title={a.title}>
                {a.title || '(no title)'}
              </span>
              <span className="shrink-0 font-mono text-[10px] text-neutral-500">
                {a.lang ?? '?'} · v{a.extraction_version} · {a.summary_len}c
              </span>
            </div>
            <div className="text-[10px] text-neutral-500">
              {a.source} ·{' '}
              {a.collected_at ? new Date(a.collected_at).toLocaleTimeString() : '?'}
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  )
}
