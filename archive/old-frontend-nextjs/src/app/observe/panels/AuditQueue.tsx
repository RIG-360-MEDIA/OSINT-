'use client'

import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { observeApi, type AuditQueue as AuditQueueT, type Verdict } from '@/lib/observe-client'
import { useObservePoll } from '../hooks/useObservePoll'
import styles from '../observe.module.css'
import { Panel } from './Panel'

const FLAG_LABEL: Record<string, { label: string; explain: string }> = {
  placeholder_subject:        { label: 'Hallucinated subject',    explain: 'LLM wrote literal "article" instead of the real subject.' },
  is_future_contradicts_date: { label: 'is_future but past date', explain: 'Flagged as future but extracted event date is in the past.' },
  lang_mistag_telugu:         { label: 'EN-tagged + Telugu chars',explain: 'language_detected=en but title has Telugu characters.' },
}

const VERDICTS: Array<{ k: Verdict; emoji: string; label: string; cls: string }> = [
  { k: 'correct', emoji: '✓', label: 'Correct', cls: styles.verdictCorrect },
  { k: 'wrong',   emoji: '✗', label: 'Wrong',   cls: styles.verdictWrong   },
  { k: 'unsure',  emoji: '?', label: 'Unsure',  cls: styles.verdictUnsure  },
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
        article_id: aid, field_name: flag, extraction_version: 3, verdict,
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
      title="Audit Queue"
      subtitle="Articles flagged by automated checks — mark Correct / Wrong / Unsure"
      help="Marked items leave the queue."
      status={!data ? null : data.queue.length > 20 ? 'warn' : 'ok'}
      loading={isLoading}
      error={error ?? lastError}
      span2
    >
      {data?.queue.length === 0 ? (
        <div className={styles.emptyState}>
          <div className={styles.emptyEmoji}>✨</div>
          <div className={styles.emptyText}>Queue is empty — nothing flagged right now.</div>
        </div>
      ) : (
        <ul className={styles.queueList} data-testid="audit-queue-list">
          {data?.queue.map((r) => {
            const id = r.aid + ':' + r.flag
            const meta = FLAG_LABEL[r.flag] ?? { label: r.flag, explain: '' }
            return (
              <li key={id} className={`${styles.queueItem} ${r.existing_verdict ? styles.decided : ''}`}>
                <div className={styles.queueBody}>
                  <p className={styles.queueTitle} title={r.title}>{r.title || '(no title)'}</p>
                  <div className={styles.queueMeta}>
                    <span className={styles.flagChip} title={meta.explain}>{meta.label}</span>
                    <span>{r.source}</span>
                    {r.hint && <span className={styles.queueHint}>“{r.hint}”</span>}
                  </div>
                </div>
                <div className={styles.verdictRow}>
                  {VERDICTS.map((v) => (
                    <button
                      key={v.k}
                      onClick={() => decide(r.aid, r.flag, v.k)}
                      disabled={pendingId === id}
                      title={v.label}
                      className={`${styles.verdict} ${v.cls} ${r.existing_verdict === v.k ? styles.verdictActive : ''}`}
                    >
                      {v.emoji}
                    </button>
                  ))}
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </Panel>
  )
}
