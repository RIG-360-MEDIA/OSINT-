/**
 * LiveClock — monospace UTC + IST timestamp ticking every second.
 *
 * Renders a stable string on the server (UTC) so we don't get hydration
 * mismatches, then takes over with a 1Hz interval client-side. The IST
 * column is a fixed +5:30 offset from UTC.
 */

'use client'

import { useEffect, useState } from 'react'

const formatHMS = (d: Date, offsetMin = 0): string => {
  const t = new Date(d.getTime() + offsetMin * 60_000)
  const h = String(t.getUTCHours()).padStart(2, '0')
  const m = String(t.getUTCMinutes()).padStart(2, '0')
  const s = String(t.getUTCSeconds()).padStart(2, '0')
  return `${h}:${m}:${s}`
}

export function LiveClock() {
  const [now, setNow] = useState<Date | null>(null)

  useEffect(() => {
    setNow(new Date())
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  // SSR / first-render placeholder
  const utc = now ? formatHMS(now) : '--:--:--'
  const ist = now ? formatHMS(now, 330) : '--:--:--'

  return (
    <span
      className="onyx-mono"
      style={{ fontSize: '11px', letterSpacing: '0.18em' }}
    >
      <span style={{ opacity: 0.6 }}>UTC</span>{' '}{utc}
      <span style={{ margin: '0 12px', opacity: 0.3 }}>·</span>
      <span style={{ opacity: 0.6 }}>IST</span>{' '}{ist}
    </span>
  )
}
