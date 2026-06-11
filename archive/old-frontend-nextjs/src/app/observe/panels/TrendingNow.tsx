'use client'

import { observeApi } from '@/lib/observe-client'
import { useObservePoll } from '../hooks/useObservePoll'
import styles from '../observe.module.css'
import { Panel } from './Panel'

export function TrendingNow() {
  const { data, isLoading, error } = useObservePoll(
    ['trending'],
    () => observeApi.trending(20),
    { visibleIntervalMs: 60_000, hiddenIntervalMs: 300_000 }
  )

  const max = data && data.entities.length ? data.entities[0].mentions_today : 1

  return (
    <Panel
      title="Trending Now"
      subtitle="Who & what is being talked about today"
      help="Mentions across claims + quotes + stances in the last 24h. 🔥 = surging vs 7-day baseline. ✨ = first time we see them."
      status={!data ? null : data.entities.length > 0 ? 'ok' : 'warn'}
      loading={isLoading}
      error={error}
    >
      <ol className={styles.trendList}>
        {data?.entities.map((e, i) => {
          const widthPct = (e.mentions_today / max) * 100
          return (
            <li key={`${e.entity}-${i}`} className={styles.trendItem}>
              <div className={styles.trendBg} style={{ width: `${widthPct}%` }} />
              <div className={styles.trendContent}>
                <span className={styles.trendRank}>{String(i + 1).padStart(2, '0')}</span>
                <span className={styles.trendName} title={e.entity}>{e.entity}</span>
                <span className={styles.trendBadges}>
                  {e.is_new && <span className={styles.trendNew}>✨ new</span>}
                  {e.is_surging && (
                    <span className={styles.trendSurge}>
                      🔥 {e.surge_ratio ? `${e.surge_ratio.toFixed(1)}×` : 'surging'}
                    </span>
                  )}
                </span>
                <span className={styles.trendCount}>
                  {e.mentions_today} <span className={styles.trendSrc}>({e.sources_today} src)</span>
                </span>
              </div>
            </li>
          )
        })}
      </ol>
    </Panel>
  )
}
