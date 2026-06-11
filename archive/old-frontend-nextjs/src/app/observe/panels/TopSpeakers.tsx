'use client'

import { observeApi } from '@/lib/observe-client'
import { useObservePoll } from '../hooks/useObservePoll'
import styles from '../observe.module.css'
import { Panel } from './Panel'

export function TopSpeakers() {
  const { data, isLoading, error } = useObservePoll(
    ['top-speakers'],
    () => observeApi.topSpeakers(15),
    { visibleIntervalMs: 60_000, hiddenIntervalMs: 300_000 }
  )

  return (
    <Panel
      title="💬 Speakers Today"
      subtitle="Most-quoted people in the last 24h"
      help="Aggregated from article_quotes. Hover a row to see a sample quote."
      status={!data ? null : data.speakers.length > 0 ? 'ok' : 'warn'}
      loading={isLoading}
      error={error}
    >
      <ol className={styles.speakerList}>
        {data?.speakers.map((s, i) => (
          <li
            key={s.speaker + i}
            className={styles.speakerItem}
            title={s.sample_quote ? `“${s.sample_quote}”` : undefined}
          >
            <span className={styles.speakerRank}>{String(i + 1).padStart(2, '0')}</span>
            <span className={styles.speakerName}>{s.speaker}</span>
            <span className={styles.speakerCount}>
              <strong>{s.n_quotes}</strong>
              <span className={styles.trendSrc}> · {s.n_sources}src</span>
            </span>
          </li>
        ))}
      </ol>
    </Panel>
  )
}
