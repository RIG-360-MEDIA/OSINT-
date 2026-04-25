'use client'

import { useEffect, useState } from 'react'

interface DatelineProps {
  issueNumber?: number | string
  filedAt?: string
  sources?: number
  languages?: number
  extra?: string[]
}

function formatDateIST(): string {
  try {
    const d = new Date()
    return d
      .toLocaleDateString('en-IN', {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        year: 'numeric',
        timeZone: 'Asia/Kolkata',
      })
      .toUpperCase()
  } catch {
    return ''
  }
}

export function Dateline({ issueNumber, filedAt, sources, languages, extra }: DatelineProps) {
  const [date, setDate] = useState<string>('')

  useEffect(() => {
    setDate(formatDateIST())
  }, [])

  const parts: string[] = ['VOL. I']
  if (issueNumber != null) parts.push(`№. ${issueNumber}`)
  if (date) parts.push(date)
  if (filedAt) parts.push(`FILED ${filedAt}`)
  if (sources != null) parts.push(`${sources.toLocaleString()} SOURCES`)
  if (languages != null) parts.push(`${languages} LANGUAGES`)
  if (extra) parts.push(...extra)

  return (
    <div
      style={{
        height: 'var(--dateline-h)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        borderTop: '1px solid var(--rig-rule-hair)',
        borderBottom: '1px solid var(--rig-rule)',
        background: 'var(--rig-paper)',
        padding: '0 28px',
      }}
      className="rig-dateline"
    >
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '18px',
          flexWrap: 'wrap',
          justifyContent: 'center',
          textAlign: 'center',
        }}
      >
        {parts.map((p, i) => (
          <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: '18px' }}>
            {p}
            {i < parts.length - 1 && (
              <span aria-hidden="true" style={{ opacity: 0.4 }}>·</span>
            )}
          </span>
        ))}
      </span>
    </div>
  )
}
