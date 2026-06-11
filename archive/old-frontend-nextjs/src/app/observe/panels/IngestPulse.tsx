'use client'

import { observeApi } from '@/lib/observe-client'
import { useObservePoll } from '../hooks/useObservePoll'
import styles from '../observe.module.css'
import { Panel } from './Panel'

export function IngestPulse() {
  const { data, isLoading, error } = useObservePoll(
    ['ingest-pulse'],
    () => observeApi.ingestPulse(),
    { visibleIntervalMs: 5000, hiddenIntervalMs: 30000 }
  )

  const stalled = data?.stalled_sources.length ?? 0
  const status = !data ? null : stalled > 100 ? 'crit' : stalled > 30 ? 'warn' : 'ok'
  const max = data ? Math.max(...data.by_hour.map((x) => x.n), 1) : 1

  return (
    <Panel
      title="Ingest Pulse"
      subtitle="How many articles arrived in the last 24 hours"
      help="Updates every 5 seconds. Healthy ≤ 30 stalled sources."
      status={status}
      loading={isLoading}
      error={error}
    >
      {data && (
        <>
          <div>
            <span className={styles.bigNumber}>{data.total_24h.toLocaleString()}</span>
            <span className={styles.bigCaption}>articles · last 24h</span>
          </div>

          <div className={styles.barRow}>
            <div className={styles.barAxis}>
              <span>24h ago</span><span>now</span>
            </div>
            <div className={styles.barCanvas} data-testid="hourly-bars">
              {data.by_hour.map((b) => (
                <div
                  key={b.hour}
                  className={styles.bar}
                  style={{ height: `${Math.max(3, (b.n / max) * 48)}px` }}
                  title={`${b.hour}: ${b.n} articles`}
                />
              ))}
            </div>
          </div>

          <div className={styles.miniRow}>
            <div className={styles.mini}>
              <div className={styles.miniValue}>{data.per_source.length - stalled}</div>
              <div className={styles.miniLabel}>Active</div>
            </div>
            <div className={`${styles.mini} ${stalled > 30 ? styles.miniWarn : ''}`}>
              <div className={styles.miniValue}>{stalled}</div>
              <div className={styles.miniLabel}>Stalled</div>
            </div>
            <div className={styles.mini}>
              <div className={styles.miniValue}>{data.per_source.length}</div>
              <div className={styles.miniLabel}>Total</div>
            </div>
          </div>

          {stalled > 0 && (
            <details className={styles.disclosure}>
              <summary>Show {stalled} stalled sources</summary>
              <ul className={styles.stalledList}>
                {data.stalled_sources.slice(0, 50).map((s) => (
                  <li key={s.source} className={styles.stalledItem}>
                    <span>{s.source}</span>
                    <span>{s.hours_since.toFixed(0)}h</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </Panel>
  )
}
