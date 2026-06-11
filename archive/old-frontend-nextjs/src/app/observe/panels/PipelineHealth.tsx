'use client'

import { observeApi } from '@/lib/observe-client'
import { useObservePoll } from '../hooks/useObservePoll'
import styles from '../observe.module.css'
import { Panel } from './Panel'

function ProgressBar({ pct, accent }: { pct: number; accent: 'amber' | 'emerald' | 'navy' }) {
  const bgVar =
    accent === 'amber' ? 'var(--color-amber)' :
    accent === 'emerald' ? 'var(--color-emerald)' : 'var(--color-navy)'
  return (
    <div className={styles.progressTrack}>
      <div
        className={styles.progressFill}
        style={{ width: `${Math.min(100, Math.max(0, pct))}%`, background: bgVar }}
      />
      <span className={styles.progressLabel}>{pct.toFixed(1)}%</span>
    </div>
  )
}

export function PipelineHealth() {
  const { data, isLoading, error } = useObservePoll(
    ['pipeline-health'],
    () => observeApi.pipelineHealth(),
    { visibleIntervalMs: 15_000, hiddenIntervalMs: 60_000 }
  )

  const status =
    !data ? null :
    !data.latest_regression?.passed ? 'crit' :
    data.t4_backfill.pct < 100 || data.v3_upgrade.v2 > 100 ? 'warn' : 'ok'

  return (
    <Panel
      title="Pipeline Health"
      subtitle="What's running on the corpus right now"
      help="Tracks backfills, regression results, and v3 upgrade progress."
      status={status}
      loading={isLoading}
      error={error}
    >
      {data && (
        <div className={styles.pipelineWrap}>
          {/* T4 placeholder backfill */}
          <div className={styles.pipelineRow}>
            <div className={styles.pipelineHead}>
              <span className={styles.pipelineIcon}>🔧</span>
              <span className={styles.pipelineName}>
                Placeholder backfill (T4)
              </span>
              <span className={styles.pipelineBadge}>
                {data.t4_backfill.running ? 'running' : 'idle'}
              </span>
            </div>
            <ProgressBar pct={data.t4_backfill.pct} accent="amber" />
            <div className={styles.pipelineDetail}>
              {data.t4_backfill.completed.toLocaleString()} / {data.t4_backfill.target.toLocaleString()} articles refilled
            </div>
          </div>

          {/* v3 upgrade */}
          <div className={styles.pipelineRow}>
            <div className={styles.pipelineHead}>
              <span className={styles.pipelineIcon}>⬆️</span>
              <span className={styles.pipelineName}>
                v3 upgrade pass
              </span>
              <span className={styles.pipelineBadge}>
                {data.v3_upgrade.v2 > 0 ? 'in progress' : 'complete'}
              </span>
            </div>
            <ProgressBar pct={data.v3_upgrade.pct_v3} accent="emerald" />
            <div className={styles.pipelineDetail}>
              {data.v3_upgrade.v3.toLocaleString()} v3 · {data.v3_upgrade.v2.toLocaleString()} pending
            </div>
          </div>

          {/* Latest gold regression */}
          {data.latest_regression && (
            <div className={styles.pipelineRow}>
              <div className={styles.pipelineHead}>
                <span className={styles.pipelineIcon}>🏆</span>
                <span className={styles.pipelineName}>Gold regression (nightly)</span>
                <span
                  className={`${styles.regressionChip} ${data.latest_regression.passed ? styles.chipPass : styles.chipFail}`}
                >
                  {data.latest_regression.passed ? `✓ PASS ${data.latest_regression.matched}/${data.latest_regression.gold_size}` : 'FAIL'}
                </span>
              </div>
              {data.latest_regression.source_file && (
                <div className={styles.pipelineDetail}>
                  Latest: {data.latest_regression.source_file}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </Panel>
  )
}
