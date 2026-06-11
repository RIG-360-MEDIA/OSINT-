'use client'

import { useState } from 'react'

import { observeApi } from '@/lib/observe-client'
import { useObservePoll } from '../hooks/useObservePoll'
import styles from '../observe.module.css'
import { Panel } from './Panel'

type Level = 'country' | 'state' | 'district'

export function GeoHeatmap() {
  const [level, setLevel] = useState<Level>('country')
  const { data, isLoading, error } = useObservePoll(
    ['geo-heatmap', level],
    () => observeApi.geoHeatmap(level),
    { visibleIntervalMs: 60000, hiddenIntervalMs: 300000 }
  )
  const max = data?.regions.length ? Math.max(...data.regions.map((r) => r.n)) : 1

  return (
    <Panel
      title="Geo Heatmap"
      subtitle="Where extracted events are happening"
      help="From article_locations. Bar width is relative to the top region."
      loading={isLoading}
      error={error}
      actions={
        <select
          className={styles.select}
          value={level}
          onChange={(e) => setLevel(e.target.value as Level)}
        >
          <option value="country">Country</option>
          <option value="state">State / region</option>
          <option value="district">City / district</option>
        </select>
      }
    >
      {data && (
        <ul className={styles.geoList}>
          {data.regions.slice(0, 40).map((r) => (
            <li key={r.region} className={styles.geoRow}>
              <div className={styles.geoBar} style={{ width: `${(r.n / max) * 100}%` }} />
              <div className={styles.geoText}>
                <span className={styles.geoName}>{r.region}</span>
                <span className={styles.geoCount}>{r.n.toLocaleString()}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}
