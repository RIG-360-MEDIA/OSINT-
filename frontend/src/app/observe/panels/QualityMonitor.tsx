'use client'

import { observeApi } from '@/lib/observe-client'
import { useObservePoll } from '../hooks/useObservePoll'
import { Panel } from './Panel'

function Gauge({ label, value, max = 10, danger }: { label: string; value: number; max?: number; danger?: boolean }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  const color = danger || value < max * 0.7 ? 'bg-amber-500' : 'bg-emerald-500'
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-32 truncate text-neutral-600">{label}</span>
      <div className="relative h-3 flex-1 rounded bg-neutral-200">
        <div className={`absolute inset-y-0 left-0 rounded ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-10 tabular-nums text-right font-mono">{value.toFixed(1)}</span>
    </div>
  )
}

export function QualityMonitor() {
  const { data, isLoading, error } = useObservePoll(
    ['quality-monitor'],
    () => observeApi.qualityMonitor(),
    { visibleIntervalMs: 60000, hiddenIntervalMs: 300000 }
  )

  return (
    <Panel
      title="Quality monitor"
      subtitle={
        data?.judge
          ? `LLM judge: ${data.judge.successes}/${data.judge.sampled} successes`
          : 'Field accuracy (live + last judge run)'
      }
      loading={isLoading}
      error={error}
    >
      {data && (
        <div className="space-y-2">
          {data.judge && (
            <div className="space-y-1">
              {Object.entries(data.judge.median_scores).map(([k, v]) => (
                <Gauge key={k} label={k.replace(/_score$/, '').replace(/_/g, ' ')} value={v} />
              ))}
            </div>
          )}
          {data.regression && (
            <>
              <hr className="my-2 border-neutral-200" />
              <div className="text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-semibold">Gold regression</span>
                  <span className={data.regression.passed ? 'text-emerald-700' : 'text-red-700'}>
                    {data.regression.passed ? 'PASS' : 'FAIL'} · {data.regression.matched}/{data.regression.gold_size}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
                  {Object.entries(data.regression.failures).map(([k, v]) => (
                    <Stat key={k} label={k} value={v} danger={v > 0} />
                  ))}
                  {Object.entries(data.regression.info).map(([k, v]) => (
                    <Stat key={k} label={`${k} (info)`} value={v} />
                  ))}
                </div>
              </div>
            </>
          )}
          <hr className="my-2 border-neutral-200" />
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
            <Stat label="V3-OK articles" value={data.live.v3_ok_total} />
            <Stat label="Placeholder claims %" value={data.live.claims_placeholder_pct} danger={data.live.claims_placeholder_pct > 5} />
            <Stat label="Thin summary %" value={data.live.thin_summary_pct} danger={data.live.thin_summary_pct > 5} />
            <Stat label="500-char cliff" value={data.live.cliff_500} danger={data.live.cliff_500 > 100} />
            <Stat label="1000-char cliff" value={data.live.cliff_1000} danger={data.live.cliff_1000 > 100} />
            <Stat label="Null embeddings" value={data.live.null_embedding} danger={data.live.null_embedding > 100} />
          </div>
        </div>
      )}
    </Panel>
  )
}

function Stat({ label, value, danger }: { label: string; value: number; danger?: boolean }) {
  return (
    <div className="flex justify-between border-b border-neutral-200/50 py-0.5">
      <span className="text-neutral-600">{label}</span>
      <span className={`tabular-nums font-mono ${danger ? 'text-amber-700' : ''}`}>
        {typeof value === 'number' ? value.toLocaleString() : String(value)}
      </span>
    </div>
  )
}
