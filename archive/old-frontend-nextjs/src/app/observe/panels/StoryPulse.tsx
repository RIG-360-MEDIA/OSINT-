'use client'

import { observeApi } from '@/lib/observe-client'
import { useObservePoll } from '../hooks/useObservePoll'
import styles from '../observe.module.css'
import { Panel } from './Panel'

export function StoryPulse() {
  const { data, isLoading, error } = useObservePoll(
    ['story-pulse'],
    () => observeApi.storyPulse(20),
    { visibleIntervalMs: 15000, hiddenIntervalMs: 60000 }
  )

  return (
    <Panel
      title="Story Pulse"
      subtitle="Multi-source stories breaking right now"
      help="Each row = story covered by ≥2 outlets. +N today = fresh articles in last 24h."
      status={!data ? null : data.clusters.length === 0 ? 'warn' : 'ok'}
      loading={isLoading}
      error={error}
    >
      {data?.clusters.length === 0 ? (
        <div className={styles.empty}>No multi-source stories active.</div>
      ) : (
        <ol className={styles.storyList}>
          {data?.clusters.map((c, i) => (
            <li key={c.cluster_id} className={styles.storyItem}>
              <span className={styles.storyIdx}>{String(i + 1).padStart(2, '0')}</span>
              <div className={styles.storyBody}>
                <p className={styles.storyHead} title={c.headline}>{c.headline}</p>
                <div className={styles.storyMeta}>
                  {c.importance != null && (
                    <span
                      className={styles.tag}
                      style={{
                        background:
                          c.importance >= 5 ? 'var(--color-amber-soft)' :
                          c.importance >= 3.5 ? 'var(--color-surface-2)' :
                          'var(--color-bg)',
                        fontWeight: 600,
                        fontVariantNumeric: 'tabular-nums',
                      }}
                      title="Importance score (0-10)"
                    >
                      ★ {c.importance.toFixed(1)}
                    </span>
                  )}
                  {c.event_type && <span className={styles.tag}>{c.event_type}</span>}
                  <span><strong>{c.source_count}</strong> sources</span>
                  <span>·</span>
                  <span><strong>{c.article_count}</strong> articles</span>
                  {c.new_24h > 0 && <span className={styles.tagFresh}>+{c.new_24h} today</span>}
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  )
}
