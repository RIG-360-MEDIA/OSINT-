'use client'

import type { ReactNode } from 'react'

import styles from '../observe.module.css'

interface PanelProps {
  title: string
  subtitle?: string
  help?: string
  loading?: boolean
  error?: unknown
  status?: 'ok' | 'warn' | 'crit' | null
  children: ReactNode
  actions?: ReactNode
  span2?: boolean
}

export function Panel({
  title, subtitle, help, loading, error, status, children, actions, span2,
}: PanelProps) {
  const statusClass =
    status === 'ok' ? styles.statusOk :
    status === 'warn' ? styles.statusWarn :
    status === 'crit' ? styles.statusCrit : ''

  return (
    <section className={`${styles.panel} ${span2 ? styles.span2 : ''}`}>
      <header className={styles.panelHead}>
        <div className={styles.panelTitleRow}>
          {status && <span className={`${styles.statusDot} ${statusClass}`} title={status} />}
          <h2 className={styles.panelTitle}>{title}</h2>
          {help && <span className={styles.help} title={help}>ⓘ</span>}
        </div>
        {actions}
      </header>

      {subtitle && <p className={styles.panelSub}>{subtitle}</p>}

      {loading && (
        <div className={styles.skeleton}>
          <span className={styles.skeletonDot} />
          Loading data…
        </div>
      )}
      {error != null && !loading && (
        <div className={styles.errorBox}>
          <div className={styles.errorTitle}>Couldn’t load this panel.</div>
          <div className={styles.errorMsg}>{(error as Error).message || String(error)}</div>
        </div>
      )}
      {!loading && !error && <div>{children}</div>}
    </section>
  )
}
