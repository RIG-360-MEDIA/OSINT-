'use client'

import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { observeApi, type AuditQueue as AuditQueueT, type Verdict } from '@/lib/observe-client'
import { useObservePoll } from '../hooks/useObservePoll'
import { Panel } from './Panel'

const VERDICTS: Array<{ k: Verdict; label: string; tone: string }> = [
  { k: 'correct', label: '✓', tone: 'bg-emerald-600' },
  { k: 'wrong', label: '✗', tone: 'bg-red-600' },
  { k: 'unsure', label: '?', tone: 'bg-neutral-500' },
]

export function AuditQueue() {
  const qc = useQueryClient()
  const { data, isLoading, error } = useObservePoll<AuditQueueT>(
    ['audit-queue'],
    () => observeApi.auditQueue(30),
    { visibleIntervalMs: 30000, hiddenIntervalMs: 120000 }
  )
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [lastError, setLastError] = useState<string | null>(null)

  const decide = async (aid: string, flag: string, verdict: Verdict) => {
    setPendingId(aid + ':' + flag)
    setLastError(null)
    try {
      await observeApi.auditDecision({
        article_id: aid,
        field_name: flag,
        extraction_version: 3,
        verdict,
      })
      await qc.invalidateQueries({ queryKey: ['audit-queue'] })
    } catch (e) {
      setLastError((e as Error).message)
    } finally {
      setPendingId(null)
    }
  }

  return (
    <Panel
      title="Audit queue"
      subtitle={data ? `${data.queue.length} flagged for review` : ''}
      loading={isLoading}
      error={error ?? lastError}
    >
      <ul className="space-y-1 text-xs max-h-80 overflow-y-auto" data-testid="audit-queue-list">
        {data?.queue.map((r) => {
          const id = r.aid + ':' + r.flag
          return (
            <li key={id} className="border-b border-neutral-200/60 py-1">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate" title={r.title}>
                  {r.title || '(no title)'}
                </span>
                <span className="flex gap-1">
                  {VERDICTS.map((v) => (
                    <button
                      key={v.k}
                      onClick={() => decide(r.aid, r.flag, v.k)}
                      disabled={pendingId === id}
                      className={`rounded px-1.5 py-0.5 text-white ${v.tone} ${r.existing_verdict === v.k ? 'ring-2 ring-yellow-400' : ''} ${pendingId === id ? 'opacity-50' : ''}`}
                      data-testid={`verdict-${v.k}`}
                      aria-label={`mark ${v.k}`}
                    >
                      {v.label}
                    </button>
                  ))}
                </span>
              </div>
              <div className="flex justify-between text-[10px] text-neutral-500">
                <span>
                  <span className="rounded bg-amber-100 px-1 text-amber-800">{r.flag}</span> ·{' '}
                  {r.source}
                </span>
                <span>{r.hint}</span>
              </div>
            </li>
          )
        })}
      </ul>
    </Panel>
  )
}
