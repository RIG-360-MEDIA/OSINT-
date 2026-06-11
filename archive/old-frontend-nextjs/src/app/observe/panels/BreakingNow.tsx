'use client'

import { observeApi } from '@/lib/observe-client'
import { useObservePoll } from '../hooks/useObservePoll'
import styles from '../observe.module.css'
import { Panel } from './Panel'

function timeAgo(iso: string | null): string {
  if (!iso) return ''
  const s = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  return `${Math.floor(s / 3600)}h ago`
}

export function BreakingNow() {
  const { data, isLoading, error } = useObservePoll(
    ['breaking-now'],
    () => observeApi.breakingNow(12),
    { visibleIntervalMs: 30_000, hiddenIntervalMs: 120_000 }
  )

  return (
    <Panel
      title="🔴 Breaking Now"
      subtitle="Articles flagged register_is_breaking in last 24h"
      help="From v3 extraction — the LLM tags stories that read as breaking news."
      status={!data ? null : data.items.length > 5 ? 'crit' : 'warn'}
      loading={isLoading}
      error={error}
      span2
    >
      {data?.items.length === 0 ? (
        <div className={styles.empty}>Nothing flagged breaking right now.</div>
      ) : (
        <ul className={styles.breakingList}>
          {data?.items.map((it) => (
            <li key={it.aid} className={styles.breakingItem}>
              <div className={styles.breakingDot} />
              <div className={styles.breakingBody}>
                <p className={styles.breakingTitle} title={it.title}>{it.title}</p>
                <p className={styles.breakingSubject} title={it.subject}>{it.subject}</p>
                <div className={styles.breakingMeta}>
                  <span className={styles.breakingSource}>{it.source}</span>
                  <span className={styles.chip}>{it.lang ?? '?'}</span>
                  <span>{timeAgo(it.collected_at)}</span>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}
