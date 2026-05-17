/**
 * Shared filter state for /coverage/articles.
 * Mirrors the existing /api/coverage/feed query params and the
 * ArticleFilters Pydantic model on the backend.
 */

export interface ArticleFilters {
  tier: string  // "all" | "1" | "1,2" | "1,2,3"
  topics: string[]
  days: number  // 0 = all time
  sentiment: 'all' | 'FOR_USER' | 'AGAINST_USER' | 'NEUTRAL'
  sort: 'relevance' | 'recency'
}

export const DEFAULT_FILTERS: ArticleFilters = {
  tier: '1,2,3',
  topics: [],
  days: 0,
  sentiment: 'all',
  sort: 'relevance',
}

export const TOPICS: ReadonlyArray<string> = [
  'POLITICS', 'ECONOMICS', 'BUSINESS', 'TECHNOLOGY',
  'HEALTH', 'SCIENCE', 'ENVIRONMENT', 'SECURITY',
  'LEGAL', 'SOCIAL', 'INFRASTRUCTURE', 'AGRICULTURE',
  'EDUCATION', 'SPORTS', 'INTERNATIONAL',
] as const

export function filtersToQueryString(f: ArticleFilters): string {
  const p = new URLSearchParams()
  if (f.tier && f.tier !== 'all') p.set('tier', f.tier)
  if (f.topics.length > 0) p.set('topic', f.topics.join(','))
  if (f.days > 0) p.set('days', String(f.days))
  if (f.sentiment !== 'all') p.set('sentiment', f.sentiment)
  if (f.sort) p.set('sort', f.sort)
  return p.toString()
}
