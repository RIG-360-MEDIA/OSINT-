'use client'

import { observeApi } from '@/lib/observe-client'
import { useObservePoll } from './hooks/useObservePoll'
import styles from './observe.module.css'

function compact(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'k'
  return String(n)
}

export function CorpusBanner() {
  const { data } = useObservePoll(
    ['corpus-overview'],
    () => observeApi.corpusOverview(),
    { visibleIntervalMs: 60_000, hiddenIntervalMs: 300_000 }
  )

  return (
    <div className={styles.bannerWrap}>
      <div className={styles.bannerRow}>
        <Stat icon="📰" label="Articles" value={data ? compact(data.total_articles) : '—'} sub={data ? `${compact(data.articles_24h)} in 24h` : ''} />
        <Stat icon="🌐" label="Sources" value={data ? String(data.total_sources) : '—'} sub={data ? `${data.languages} languages` : ''} />
        <Stat icon="📚" label="Stories live" value={data ? String(data.active_stories) : '—'} sub="multi-source clusters" />
        <Stat icon="💬" label="Quotes" value={data ? compact(data.total_quotes) : '—'} />
        <Stat icon="📍" label="Locations" value={data ? compact(data.total_locations) : '—'} />
        <Stat icon="📅" label="Events" value={data ? compact(data.total_events) : '—'} />
        <Stat icon="🧾" label="Claims" value={data ? compact(data.total_claims) : '—'} />
      </div>
    </div>
  )
}

function Stat({ icon, label, value, sub }: { icon: string; label: string; value: string; sub?: string }) {
  return (
    <div className={styles.bannerStat}>
      <span className={styles.bannerIcon} aria-hidden="true">{icon}</span>
      <div>
        <div className={styles.bannerValue}>{value}</div>
        <div className={styles.bannerLabel}>{label}</div>
        {sub && <div className={styles.bannerSub}>{sub}</div>}
      </div>
    </div>
  )
}
