/**
 * Deterministic warm muted RGB for a given source domain.
 * Same domain always returns the same color.
 */
export function domainColor(domain: string): string {
  let hash = 0
  for (let i = 0; i < domain.length; i++) {
    hash = ((hash << 5) - hash) + domain.charCodeAt(i)
    hash = hash & hash
  }
  const h = Math.abs(hash)
  const r = 80 + (h % 120)
  const g = 60 + ((h >> 8) % 100)
  const b = 40 + ((h >> 16) % 80)
  return `rgb(${r},${g},${b})`
}

export function formatTimeAgo(dateStr: string | null): string {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  if (diffMins < 1) return 'now'
  if (diffMins < 60) return `${diffMins}m`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}h`
  const diffDays = Math.floor(diffHours / 24)
  return `${diffDays}d`
}
