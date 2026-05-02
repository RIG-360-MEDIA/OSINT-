'use client'

/**
 * Intelligence Feed — replaces the old Intelligence Desk grid.
 *
 * Pure text cards, no charts. Each card is one piece of incoming
 * intel. The "newest" indicator (a thin wax-red left rail + faint
 * background tint) cycles through items every 6 seconds to give a
 * live-streaming feel without the jarring DOM churn of true reorder.
 *
 * 3 columns desktop · 2 tablet · 1 mobile.
 */

import { useEffect, useState } from 'react'

import { INTEL_FEED, type IntelItem, type IntelPriority } from './intel-items'
import styles from './styles.module.css'

const NEWEST_ROTATION_MS = 6000

export function IntelFeed() {
  const [newestIdx, setNewestIdx] = useState(0)
  useEffect(() => {
    const id = window.setInterval(() => {
      setNewestIdx((i) => (i + 1) % INTEL_FEED.length)
    }, NEWEST_ROTATION_MS)
    return () => window.clearInterval(id)
  }, [])

  return (
    <div className={styles.intelFeedGrid}>
      {INTEL_FEED.map((item, i) => (
        <IntelCard
          key={i}
          item={item}
          isNewest={i === newestIdx}
          enterDelayMs={i * 60}
        />
      ))}
    </div>
  )
}

interface IntelCardProps {
  item: IntelItem
  isNewest: boolean
  enterDelayMs: number
}

function IntelCard({ item, isNewest, enterDelayMs }: IntelCardProps) {
  return (
    <article
      className={`${styles.intelCard} ${isNewest ? styles.intelCardNewest : ''}`}
      style={{ animationDelay: `${enterDelayMs}ms` }}
    >
      <header className={styles.intelCardHeader}>
        <span className={styles.intelTime}>{item.time}</span>
        <span className={styles.intelDot}>·</span>
        <span className={styles.intelDistrict}>{item.district}</span>
        <span className={styles.intelSpacer} />
        <span
          className={`${styles.intelPriority} ${priorityClass(item.priority)}`}
        >
          {item.priority}
        </span>
      </header>
      <div
        className={`${styles.intelCategory} ${categoryClass(item.category)}`}
      >
        {item.category}
        {isNewest && <span className={styles.intelNewBadge}>● NEW</span>}
      </div>
      <p className={styles.intelText}>{item.text}</p>
      <footer className={styles.intelSource}>{item.source}</footer>
    </article>
  )
}

function priorityClass(p: IntelPriority): string {
  if (p === 'P0') return styles.intelPriorityP0
  if (p === 'P1') return styles.intelPriorityP1
  if (p === 'P2') return styles.intelPriorityP2
  return styles.intelPriorityInfo
}

function categoryClass(c: string): string {
  // BREAKING / ALERT / ACTION → wax-red eyebrow
  // OPPOSITION / POLITICAL / COURT → ink-blue
  // POWER / WEATHER / WELFARE / LABOUR / INDUSTRIAL / MARKET → sepia
  // METRO / POSITIVE / INTEL → muted
  if (['BREAKING', 'ALERT', 'ACTION'].includes(c))
    return styles.intelCategoryUrgent
  if (['OPPOSITION', 'POLITICAL', 'COURT'].includes(c))
    return styles.intelCategoryPolitical
  if (
    ['POWER', 'WEATHER', 'WELFARE', 'LABOUR', 'INDUSTRIAL', 'MARKET'].includes(
      c,
    )
  )
    return styles.intelCategorySector
  return styles.intelCategoryMuted
}
