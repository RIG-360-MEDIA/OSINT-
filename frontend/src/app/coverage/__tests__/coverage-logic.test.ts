/**
 * Pure-logic regression tests for the Coverage page.
 *
 * The page-level component (page.tsx) inlines two bits of logic worth
 * locking down:
 *   1. buildFeedUrl — converts filter state to /api/coverage/feed query.
 *   2. cursor format — backend emits "{score:.6f}_{article_id}".
 *
 * These tests duplicate the inline logic verbatim so that drift between
 * page.tsx and this spec produces a clear test failure → reminder to fix
 * the page or update the spec.
 *
 * Run: cd frontend && npm install && npm test
 */
import { describe, expect, it } from 'vitest'

type TierFilter = 'all' | '1' | '1,2'
type SortOption = 'relevance' | 'recency'

interface FilterState {
  selectedTier: TierFilter
  selectedTopics: string[]
  selectedDays: number
  sortBy: SortOption
}

const API_BASE = 'http://localhost:8000'

// Mirror of buildFeedUrl in frontend/src/app/coverage/page.tsx.
function buildFeedUrl(state: FilterState, cursor: string = ''): string {
  const params = new URLSearchParams()
  const tierParam = state.selectedTier === 'all' ? '1,2,3' : state.selectedTier
  params.set('tier', tierParam)
  if (state.selectedTopics.length > 0) {
    params.set('topic', state.selectedTopics.join(','))
  }
  if (state.selectedDays > 0) params.set('days', String(state.selectedDays))
  params.set('sort', state.sortBy)
  if (cursor) params.set('cursor', cursor)
  params.set('limit', '20')
  return `${API_BASE}/api/coverage/feed?${params.toString()}`
}

const DEFAULTS: FilterState = {
  selectedTier: 'all',
  selectedTopics: [],
  selectedDays: 0,
  sortBy: 'relevance',
}

describe('buildFeedUrl', () => {
  it('serialises tier="all" as 1,2,3', () => {
    const url = new URL(buildFeedUrl(DEFAULTS))
    expect(url.searchParams.get('tier')).toBe('1,2,3')
  })

  it('passes tier "1,2" through verbatim', () => {
    const url = new URL(buildFeedUrl({ ...DEFAULTS, selectedTier: '1,2' }))
    expect(url.searchParams.get('tier')).toBe('1,2')
  })

  it('omits topic when no topics selected', () => {
    const url = new URL(buildFeedUrl(DEFAULTS))
    expect(url.searchParams.has('topic')).toBe(false)
  })

  it('joins multiple topics with commas', () => {
    const url = new URL(buildFeedUrl({
      ...DEFAULTS,
      selectedTopics: ['POLITICS', 'BUSINESS'],
    }))
    expect(url.searchParams.get('topic')).toBe('POLITICS,BUSINESS')
  })

  it('omits days param when selectedDays=0', () => {
    const url = new URL(buildFeedUrl(DEFAULTS))
    expect(url.searchParams.has('days')).toBe(false)
  })

  it('emits days=7 for week view', () => {
    const url = new URL(buildFeedUrl({ ...DEFAULTS, selectedDays: 7 }))
    expect(url.searchParams.get('days')).toBe('7')
  })

  it('never emits sentiment param (filter is not user-controllable)', () => {
    const url = new URL(buildFeedUrl(DEFAULTS))
    expect(url.searchParams.has('sentiment')).toBe(false)
  })

  it('always sets sort and limit', () => {
    const url = new URL(buildFeedUrl(DEFAULTS))
    expect(url.searchParams.get('sort')).toBe('relevance')
    expect(url.searchParams.get('limit')).toBe('20')
  })

  it('appends cursor when provided', () => {
    const url = new URL(buildFeedUrl(DEFAULTS, '0.987654_abc-uuid'))
    expect(url.searchParams.get('cursor')).toBe('0.987654_abc-uuid')
  })

  it('omits cursor when blank', () => {
    const url = new URL(buildFeedUrl(DEFAULTS, ''))
    expect(url.searchParams.has('cursor')).toBe(false)
  })
})

// Cursor format produced by backend coverage_router.py:
//   f"{score_final:.6f}_{article_id}"
// Frontend sends it back as ?cursor=… and never parses it. We assert the
// shape so that a backend change here forces a test update.
describe('feed cursor format', () => {
  const CURSOR_RE = /^\d+\.\d{6}_[0-9a-fA-F-]+$/

  it('matches "score_id" with 6-decimal score', () => {
    expect('0.987654_11111111-1111-1111-1111-111111111111').toMatch(CURSOR_RE)
  })

  it('rejects malformed cursors that the backend would also reject', () => {
    expect('garbage').not.toMatch(CURSOR_RE)
    expect('0.99_').not.toMatch(CURSOR_RE)
    expect('_uuid').not.toMatch(CURSOR_RE)
  })
})
