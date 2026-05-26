'use client'

import { useState } from 'react'

import { observeApi } from '@/lib/observe-client'
import { useObservePoll } from '../hooks/useObservePoll'
import styles from '../observe.module.css'
import { Panel } from './Panel'

export function CrossTabAnalyst() {
  const [actor, setActor] = useState('')
  const [days, setDays] = useState(60)
  const [submitted, setSubmitted] = useState<{ actor: string; days: number } | null>(null)

  const { data, isLoading, error } = useObservePoll(
    ['crosstab', submitted?.actor || '', submitted?.days || 0],
    () => observeApi.crossTab(submitted!.actor, submitted!.days),
    { enabled: !!submitted?.actor, visibleIntervalMs: 60000, hiddenIntervalMs: 300000 }
  )

  return (
    <Panel
      title="Crosstab Analyst"
      subtitle="Search a person or organisation across sources & time"
      help='Type "Modi", "Revanth Reddy", "ED" etc. Matches the actors list.'
      loading={isLoading}
      error={error}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (actor.trim()) setSubmitted({ actor: actor.trim(), days })
        }}
        className={styles.ctForm}
      >
        <input
          value={actor}
          onChange={(e) => setActor(e.target.value)}
          placeholder="e.g. Modi, Revanth Reddy"
          className={styles.ctInput}
        />
        <div className={styles.ctDays}>
          <input
            type="number"
            value={days}
            onChange={(e) => setDays(Math.max(1, Math.min(365, Number(e.target.value) || 30)))}
            className={styles.ctDaysInput}
          />
          <span style={{ fontSize: 12, color: 'var(--color-navy-600)' }}>days</span>
        </div>
        <button type="submit" className={styles.btnPrimary} disabled={!actor.trim()}>
          Search
        </button>
      </form>

      {!submitted ? (
        <p className={styles.empty}>Enter an actor name to begin.</p>
      ) : data && (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Source</th><th>Week</th><th style={{ textAlign: 'right' }}>Events</th><th style={{ textAlign: 'right' }}>Articles</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.length === 0 ? (
                <tr><td colSpan={4} className={styles.empty}>No matches for “{submitted.actor}” in last {submitted.days} days.</td></tr>
              ) : data.rows.map((r, i) => (
                <tr key={`${r.source}-${r.week}-${i}`}>
                  <td style={{ maxWidth: '18ch', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={r.source}>{r.source}</td>
                  <td>{r.week ?? '?'}</td>
                  <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{r.n_events}</td>
                  <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{r.n_articles}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}
