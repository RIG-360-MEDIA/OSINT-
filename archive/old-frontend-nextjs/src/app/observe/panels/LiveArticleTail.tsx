'use client'

import { observeApi } from '@/lib/observe-client'
import { useObservePoll } from '../hooks/useObservePoll'
import styles from '../observe.module.css'
import { Panel } from './Panel'

function timeAgo(iso: string | null): string {
  if (!iso) return '—'
  const t = new Date(iso).getTime()
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

export function LiveArticleTail() {
  const { data, isLoading, error } = useObservePoll(
    ['live-tail'],
    () => observeApi.liveTail(undefined, 30),
    { visibleIntervalMs: 5000, hiddenIntervalMs: 30000 }
  )

  return (
    <Panel
      title="Live Article Tail"
      subtitle="The 30 most recently collected articles"
      help="Updates every 5 seconds."
      loading={isLoading}
      error={error}
    >
      <ul className={styles.tailList}>
        {data?.articles.map((a) => (
          <li key={a.aid} className={styles.tailItem}>
            <p className={styles.tailTitle} title={a.title}>{a.title || '(no title)'}</p>
            <div className={styles.tailMeta}>
              <strong>{a.source}</strong>
              <span>·</span>
              <span>{timeAgo(a.collected_at)}</span>
              <span>·</span>
              <span className={styles.chip}>{a.lang ?? '?'}</span>
              <span className={styles.chip}>v{a.extraction_version}</span>
              <span className={styles.chip}>{a.summary_len}c</span>
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  )
}
