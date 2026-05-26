'use client'

import { observeApi } from '@/lib/observe-client'
import { useObservePoll } from '../hooks/useObservePoll'
import styles from '../observe.module.css'
import { Panel } from './Panel'

const FIELD_LABELS: Record<string, string> = {
  primary_subject_score:    'Subject (who/what)',
  summary_executive_score:  'Summary text',
  article_type_score:       'Article type',
  actors_score:             'People & orgs',
  event_dates_score:        'Event dates',
  overall_score:            'Overall',
}

function Gauge({ label, value }: { label: string; value: number }) {
  const pct = Math.min(100, Math.max(0, (value / 10) * 100))
  const fillClass =
    value < 7 ? styles.gaugeCrit :
    value < 9 ? styles.gaugeWarn :
    styles.gaugeOk
  return (
    <div className={styles.gaugeRow}>
      <span className={styles.gaugeLabel}>{label}</span>
      <div className={styles.gaugeTrack}>
        <div className={`${styles.gaugeFill} ${fillClass}`} style={{ width: `${pct}%` }} />
      </div>
      <span className={styles.gaugeValue}>{value.toFixed(1)}</span>
    </div>
  )
}

export function QualityMonitor() {
  const { data, isLoading, error } = useObservePoll(
    ['quality-monitor'],
    () => observeApi.qualityMonitor(),
    { visibleIntervalMs: 60000, hiddenIntervalMs: 300000 }
  )

  const status =
    !data ? null :
    !data.regression?.passed ? 'crit' :
    data.live.claims_placeholder_pct > 10 ? 'crit' :
    data.live.claims_placeholder_pct > 1 ? 'warn' :
    'ok'

  return (
    <Panel
      title="Quality Monitor"
      subtitle="Field-by-field accuracy across the corpus"
      help="0–10 score from the LLM-judge. Below: live anomaly counts."
      status={status}
      loading={isLoading}
      error={error}
    >
      {data && (
        <>
          {data.judge && (
            <section style={{ marginBottom: '1.25rem' }}>
              <h3 className={styles.sectionLabel}>Extraction accuracy</h3>
              {Object.entries(data.judge.median_scores).map(([k, v]) => (
                <Gauge key={k} label={FIELD_LABELS[k] ?? k} value={v} />
              ))}
              <p style={{ marginTop: 6, fontSize: 11, color: 'var(--color-navy-600)', fontStyle: 'italic' }}>
                Judged on {data.judge.successes.toLocaleString()} articles ({data.judge.sampled.toLocaleString()} sampled).
              </p>
            </section>
          )}

          {data.regression && (
            <section style={{ marginBottom: '1.25rem' }}>
              <h3 className={styles.sectionLabel}>
                Nightly regression
                <span className={`${styles.regressionChip} ${data.regression.passed ? styles.chipPass : styles.chipFail}`}>
                  {data.regression.passed ? `✓ PASS ${data.regression.matched}/${data.regression.gold_size}` : 'FAIL'}
                </span>
              </h3>
            </section>
          )}

          <section>
            <h3 className={styles.sectionLabel}>Live anomaly counters</h3>
            <div className={styles.cellGrid}>
              <Cell
                label="Hallucinated subjects"
                value={`${data.live.claims_placeholder_pct}%`}
                detail={`${data.live.claims_placeholder.toLocaleString()} of ${data.live.claims_total.toLocaleString()} claims`}
                tone={data.live.claims_placeholder_pct > 5 ? 'crit' : 'ok'}
              />
              <Cell
                label="Thin summaries"
                value={`${data.live.thin_summary_pct}%`}
                detail={`${data.live.thin_summary.toLocaleString()} articles`}
                tone={data.live.thin_summary_pct > 5 ? 'warn' : 'ok'}
              />
              <Cell
                label="500-char cliff"
                value={data.live.cliff_500.toLocaleString()}
                detail="Possibly truncated"
                tone={data.live.cliff_500 > 100 ? 'warn' : 'ok'}
              />
              <Cell
                label="Missing embeddings"
                value={data.live.null_embedding.toLocaleString()}
                detail="LaBSE vector NULL"
                tone={data.live.null_embedding > 100 ? 'warn' : 'ok'}
              />
            </div>
          </section>
        </>
      )}
    </Panel>
  )
}

function Cell({
  label, value, detail, tone,
}: { label: string; value: string; detail: string; tone: 'ok' | 'warn' | 'crit' }) {
  const cls = tone === 'crit' ? styles.cellCrit : tone === 'warn' ? styles.cellWarn : styles.cellOk
  return (
    <div className={`${styles.cell} ${cls}`}>
      <div className={styles.cellValue}>{value}</div>
      <div className={styles.cellLabel}>{label}</div>
      <div className={styles.cellDetail}>{detail}</div>
    </div>
  )
}
