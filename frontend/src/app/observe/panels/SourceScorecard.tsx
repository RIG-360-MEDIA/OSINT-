'use client'

import { useMemo, useState } from 'react'

import { observeApi } from '@/lib/observe-client'
import { useObservePoll } from '../hooks/useObservePoll'
import styles from '../observe.module.css'
import { Panel } from './Panel'

type SortKey = 'total' | 'has_summary_pct' | 'has_embedding_pct' | 'source'

function dotColor(pct: number): string {
  return pct >= 90 ? 'var(--color-emerald)' : pct >= 70 ? 'var(--color-amber)' : 'var(--color-rose)'
}

export function SourceScorecard() {
  const { data, isLoading, error } = useObservePoll(
    ['source-scorecard'],
    () => observeApi.sourceScorecard(),
    { visibleIntervalMs: 30000, hiddenIntervalMs: 120000 }
  )
  const [sortKey, setSortKey] = useState<SortKey>('total')
  const [filter, setFilter] = useState('')

  const sorted = useMemo(() => {
    if (!data) return []
    const filtered = filter
      ? data.sources.filter((s) => s.source.toLowerCase().includes(filter.toLowerCase()))
      : data.sources
    return [...filtered].sort((a, b) => {
      if (sortKey === 'source') return a.source.localeCompare(b.source)
      return (b[sortKey] as number) - (a[sortKey] as number)
    })
  }, [data, sortKey, filter])

  const cols: Array<[SortKey, string]> = [
    ['source', 'Source'],
    ['total', 'Articles'],
    ['has_summary_pct', 'Summary %'],
    ['has_embedding_pct', 'Embed %'],
  ]

  return (
    <Panel
      title="Source Scorecard"
      subtitle={data ? `${data.sources.length} sources · click headers to sort` : ''}
      help="Green dot ≥ 90%, amber ≥ 70%, rose below."
      loading={isLoading}
      error={error}
    >
      <input
        type="search"
        placeholder="Filter sources…"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        className={styles.filter}
      />
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              {cols.map(([k, label]) => (
                <th key={k} onClick={() => setSortKey(k)}>
                  {label} {sortKey === k && '▾'}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.slice(0, 100).map((s) => (
              <tr key={s.source}>
                <td style={{ maxWidth: '14ch', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={s.source}>{s.source}</td>
                <td style={{ fontVariantNumeric: 'tabular-nums' }}>{s.total.toLocaleString()}</td>
                <td style={{ fontVariantNumeric: 'tabular-nums' }}>
                  <span className={styles.healthDot} style={{ background: dotColor(s.has_summary_pct) }} />{s.has_summary_pct}
                </td>
                <td style={{ fontVariantNumeric: 'tabular-nums' }}>
                  <span className={styles.healthDot} style={{ background: dotColor(s.has_embedding_pct) }} />{s.has_embedding_pct}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}
