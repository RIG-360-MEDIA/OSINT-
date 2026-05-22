'use client'

import type { ReactNode } from 'react'

interface PanelProps {
  title: string
  subtitle?: string
  loading?: boolean
  error?: unknown
  children: ReactNode
  actions?: ReactNode
}

export function Panel({ title, subtitle, loading, error, children, actions }: PanelProps) {
  return (
    <section className="rounded border border-neutral-300 bg-white/60 p-4 shadow-sm dark:bg-neutral-900/60">
      <header className="mb-3 flex items-baseline justify-between">
        <div>
          <h2 className="font-serif text-lg font-semibold tracking-tight">{title}</h2>
          {subtitle && (
            <p className="text-xs text-neutral-500" data-testid={`panel-subtitle-${title}`}>
              {subtitle}
            </p>
          )}
        </div>
        {actions}
      </header>
      {loading && <div className="text-sm text-neutral-500">Loading…</div>}
      {error != null && (
        <div className="rounded border border-red-300 bg-red-50 p-2 text-xs text-red-800">
          {(error as Error).message || String(error)}
        </div>
      )}
      {!loading && !error && children}
    </section>
  )
}
