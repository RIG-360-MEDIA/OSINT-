/**
 * /coverage/articles — RAG-integrated analyst surface, onyx theme.
 *
 * Composition (top to bottom):
 *   - OnyxTopBar (radar glyph + Brief/Coverage nav + live readouts)
 *   - BreakingBand (when active)
 *   - AskBar (filter-aware streamed RAG)
 *   - CustomCardsRow (user trackers with 4-section LLM summaries)
 *   - TopFiveStories (chain-of-thought "why this matters")
 *   - All-articles feed (filterable, paginated — uses existing /feed)
 *   - Article reader slide-over (uses existing /article + /summary)
 *   - RightRail (sticky watchlist + quotes + time travel + gaps)
 *   - ContradictionsDrawer (toggleable from rail pill)
 *   - CreateCardModal (toggleable from CustomCardsRow + button)
 *   - ParticleField + GrainOverlay (atmosphere)
 *
 * Existing /api/coverage/feed, /search, /summary, /article endpoints stay
 * intact. New endpoints under coverage_articles_router add the surfaces
 * above. Each new feature is gated by a per-feature env flag so disabling
 * one doesn't block the page.
 */

'use client'

import {
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import { OnyxTopBar } from '@/components/coverage/OnyxTopBar'
import { ParticleField } from '@/components/coverage/ParticleField'
import { GrainOverlay } from '@/components/coverage/GrainOverlay'
import { AskBar } from '@/components/coverage/AskBar'
import { BreakingBand } from '@/components/coverage/BreakingBand'
import { CustomCardsRow } from '@/components/coverage/CustomCardsRow'
import { CreateCardModal } from '@/components/coverage/CreateCardModal'
import { TopFiveStories } from '@/components/coverage/TopFiveStories'
import { RightRail } from '@/components/coverage/RightRail'
import { ContradictionsDrawer } from '@/components/coverage/ContradictionsDrawer'
import {
  DEFAULT_FILTERS,
  type ArticleFilters,
} from '@/lib/articleFilters'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface Article {
  article_id: string
  title: string
  url: string
  thumbnail_url: string | null
  author_name?: string | null
  topic_category: string | null
  geo_primary: string | null
  published_at?: string | null
  collected_at: string | null
  source_name: string
  source_domain: string
  has_full_text?: boolean
  score_final: number
  relevance_tier: number
  relevance_explanation: string | null
  matched_entity_names: string[]
  geo_multiplier?: number
  sentiment_for_user: 'FOR_USER' | 'AGAINST_USER' | 'NEUTRAL'
}

interface FeedResponse {
  articles: Article[]
  pagination: { has_more: boolean; next_cursor: string | null; returned: number }
  totals: { total: number; tier1: number; tier2: number; tier3: number }
}

const formatTimeAgo = (iso: string | null): string => {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}


export default function CoverageArticlesPage() {
  return (
    <Suspense fallback={null}>
      <ArticlesInner />
    </Suspense>
  )
}


function ArticlesInner() {
  const router = useRouter()
  const params = useSearchParams()

  // ── Filter state ──────────────────────────────────────────────
  const [filters, setFilters] = useState<ArticleFilters>(() => ({
    ...DEFAULT_FILTERS,
    tier: (params.get('tier') as string | null) || DEFAULT_FILTERS.tier,
    days: parseInt(params.get('days') || '0', 10) || DEFAULT_FILTERS.days,
    sort: (params.get('sort') as 'relevance' | 'recency' | null) || DEFAULT_FILTERS.sort,
  }))

  // ── Feed state ────────────────────────────────────────────────
  const [articles, setArticles] = useState<Article[]>([])
  const [hasMore, setHasMore] = useState(false)
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  // ── Reader / modal state ──────────────────────────────────────
  const [selectedArticle, setSelectedArticle] = useState<Article | null>(null)
  const [readArticleIds, setReadArticleIds] = useState<Set<string>>(() => {
    if (typeof window === 'undefined') return new Set()
    try {
      const raw = localStorage.getItem('coverage_read_state')
      return new Set(raw ? (JSON.parse(raw) as string[]) : [])
    } catch {
      return new Set()
    }
  })

  // ── Compare state ─────────────────────────────────────────────
  const [compareIds, setCompareIds] = useState<Set<string>>(new Set())
  const [compareOpen, setCompareOpen] = useState(false)

  // ── Drawers ───────────────────────────────────────────────────
  const [contradictionsOpen, setContradictionsOpen] = useState(false)
  const [createCardOpen, setCreateCardOpen] = useState(false)
  const [cardsRefreshTick, setCardsRefreshTick] = useState(0)

  // ── Auth helper ───────────────────────────────────────────────
  const getToken = useCallback(async (): Promise<string | null> => {
    const supabase = createClient()
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) {
      router.push('/login')
      return null
    }
    return session.access_token
  }, [router])

  // ── Feed fetcher ──────────────────────────────────────────────
  const fetchFeed = useCallback(
    async (cursor: string = '', append = false) => {
      const token = await getToken()
      if (!token) return

      const ctrl = new AbortController()
      abortRef.current?.abort()
      abortRef.current = ctrl

      if (append) setLoadingMore(true)
      else setLoading(true)
      setError(null)

      const qs = new URLSearchParams()
      qs.set('tier', filters.tier)
      if (filters.topics.length > 0) qs.set('topic', filters.topics.join(','))
      if (filters.days > 0) qs.set('days', String(filters.days))
      qs.set('sort', filters.sort)
      qs.set('limit', '20')
      if (cursor) qs.set('cursor', cursor)

      try {
        const res = await fetch(`${API_BASE}/api/coverage/feed?${qs}`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: ctrl.signal,
        })
        if (!res.ok) {
          if (res.status === 401) router.push('/login')
          throw new Error(`HTTP ${res.status}`)
        }
        const data = (await res.json()) as FeedResponse
        setArticles((prev) =>
          append ? [...prev, ...data.articles] : data.articles
        )
        setHasMore(data.pagination.has_more)
        setNextCursor(data.pagination.next_cursor)
      } catch (err: unknown) {
        if (ctrl.signal.aborted) return
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        if (append) setLoadingMore(false)
        else setLoading(false)
      }
    },
    [filters, getToken, router]
  )

  // Refetch when filters change
  useEffect(() => {
    void fetchFeed('', false)
  }, [fetchFeed])

  // ── Reader open / close ───────────────────────────────────────
  const openArticle = useCallback((articleId: string) => {
    const found = articles.find((a) => a.article_id === articleId)
    if (found) {
      setSelectedArticle(found)
      // Mark as read in localStorage.
      setReadArticleIds((prev) => {
        if (prev.has(articleId)) return prev
        const next = new Set(prev)
        next.add(articleId)
        try {
          localStorage.setItem(
            'coverage_read_state',
            JSON.stringify(Array.from(next))
          )
        } catch {
          /* ignore */
        }
        return next
      })
      return
    }
    // Article not in current feed — fetch on demand.
    void (async () => {
      const token = await getToken()
      if (!token) return
      try {
        const res = await fetch(`${API_BASE}/api/coverage/article/${articleId}`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (res.ok) {
          const a = (await res.json()) as Article
          setSelectedArticle(a)
        }
      } catch {
        /* silent */
      }
    })()
  }, [articles, getToken])

  const closeArticle = useCallback(() => setSelectedArticle(null), [])

  // ── Compare toggle ────────────────────────────────────────────
  const toggleCompare = useCallback((articleId: string) => {
    setCompareIds((prev) => {
      const next = new Set(prev)
      if (next.has(articleId)) next.delete(articleId)
      else if (next.size < 3) next.add(articleId)
      return next
    })
  }, [])

  // Body scroll lock when reader open
  useEffect(() => {
    if (selectedArticle) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [selectedArticle])

  // Escape closes whichever overlay is on top
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (compareOpen) setCompareOpen(false)
      else if (selectedArticle) closeArticle()
      else if (contradictionsOpen) setContradictionsOpen(false)
      else if (createCardOpen) setCreateCardOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selectedArticle, contradictionsOpen, createCardOpen, compareOpen, closeArticle])

  // ── Render ────────────────────────────────────────────────────
  return (
    <div
      data-theme="onyx"
      style={{
        position: 'relative',
        minHeight: '100vh',
        paddingTop: 'var(--topbar-h)',
        background: 'var(--onyx-bg)',
        color: 'var(--onyx-bone)',
        fontFamily: 'var(--onyx-display)',
        overflow: 'hidden',
      }}
    >
      <ParticleField />
      <GrainOverlay />
      <OnyxTopBar />

      <main
        className="coverage-articles-grid"
        style={{
          position: 'relative',
          zIndex: 5,
          maxWidth: '1480px',
          margin: '0 auto',
          padding: '0 56px 96px',
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr) 320px',
          gap: '64px',
          alignItems: 'start',
        }}
      >
        {/* Center column */}
        <div style={{ minWidth: 0 }}>
          <BreakingBand />

          <AskBar filters={filters} onCiteClick={openArticle} />

          <CustomCardsRow
            onOpenCreate={() => setCreateCardOpen(true)}
            refreshTick={cardsRefreshTick}
          />

          <TopFiveStories
            onRead={openArticle}
            onCompareToggle={toggleCompare}
            selectedForCompare={compareIds}
          />

          <FeedSection
            articles={articles}
            filters={filters}
            setFilters={setFilters}
            loading={loading}
            loadingMore={loadingMore}
            hasMore={hasMore}
            error={error}
            readArticleIds={readArticleIds}
            compareIds={compareIds}
            onCompareToggle={toggleCompare}
            onOpenArticle={openArticle}
            onLoadMore={() => nextCursor && fetchFeed(nextCursor, true)}
          />
        </div>

        {/* Right rail */}
        <RightRail
          onContradictionsClick={() => setContradictionsOpen(true)}
          onArticleClick={openArticle}
        />
      </main>

      {/* Floating Compare action */}
      {compareIds.size >= 2 && !compareOpen && (
        <div
          style={{
            position: 'fixed',
            bottom: '32px',
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 800,
            display: 'flex',
            gap: '12px',
            padding: '12px 18px',
            background: 'var(--onyx-bg)',
            border: '1px solid var(--onyx-cyan)',
            boxShadow: '0 0 24px var(--onyx-cyan-glow)',
            animation: 'onyx-fade-up 0.3s ease both',
          }}
        >
          <button
            type="button"
            onClick={() => setCompareIds(new Set())}
            className="onyx-mono"
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--onyx-dim)',
              fontSize: '10px',
              letterSpacing: '0.32em',
              textTransform: 'uppercase',
              cursor: 'pointer',
              padding: '4px 10px',
            }}
          >
            Clear ({compareIds.size})
          </button>
          <button
            type="button"
            onClick={() => setCompareOpen(true)}
            className="onyx-mono"
            style={{
              background: 'transparent',
              border: '1px solid var(--onyx-cyan)',
              color: 'var(--onyx-cyan)',
              fontSize: '10px',
              letterSpacing: '0.32em',
              textTransform: 'uppercase',
              padding: '8px 18px',
              cursor: 'pointer',
            }}
          >
            Compare {compareIds.size} →
          </button>
        </div>
      )}

      {/* Reader */}
      {selectedArticle && (
        <ArticleReader
          article={selectedArticle}
          onClose={closeArticle}
          getToken={getToken}
        />
      )}

      {/* Drawers / modals */}
      <ContradictionsDrawer
        open={contradictionsOpen}
        onClose={() => setContradictionsOpen(false)}
        onArticleClick={(id) => {
          setContradictionsOpen(false)
          openArticle(id)
        }}
      />
      <CreateCardModal
        open={createCardOpen}
        onClose={() => setCreateCardOpen(false)}
        onCreated={() => setCardsRefreshTick((n) => n + 1)}
      />
      {compareOpen && (
        <CompareOverlay
          articleIds={Array.from(compareIds)}
          onClose={() => setCompareOpen(false)}
          getToken={getToken}
        />
      )}

      {/* Mobile: collapse right rail */}
      <style>{`
        @media (max-width: 1100px) {
          .coverage-articles-grid {
            grid-template-columns: 1fr !important;
          }
          .coverage-articles-grid > aside {
            display: none !important;
          }
        }
      `}</style>
    </div>
  )
}


/* ───────────────────────────────────────────────────────────────
   FeedSection — filterable article list (uses existing /feed)
   ─────────────────────────────────────────────────────────────── */

interface FeedSectionProps {
  articles: Article[]
  filters: ArticleFilters
  setFilters: (f: ArticleFilters) => void
  loading: boolean
  loadingMore: boolean
  hasMore: boolean
  error: string | null
  readArticleIds: Set<string>
  compareIds: Set<string>
  onCompareToggle: (id: string) => void
  onOpenArticle: (id: string) => void
  onLoadMore: () => void
}

function FeedSection({
  articles,
  filters,
  setFilters,
  loading,
  loadingMore,
  hasMore,
  error,
  readArticleIds,
  compareIds,
  onCompareToggle,
  onOpenArticle,
  onLoadMore,
}: FeedSectionProps) {
  return (
    <section style={{ padding: '48px 0 32px' }}>
      <header style={{ marginBottom: '24px' }}>
        <div
          className="onyx-mono"
          style={{
            fontSize: '10px',
            letterSpacing: '0.42em',
            textTransform: 'uppercase',
            color: 'var(--onyx-dim)',
          }}
        >
          All articles ({articles.length})
        </div>
        <hr className="onyx-hairline-dim" style={{ marginTop: '12px' }} />
      </header>

      <FilterBar filters={filters} setFilters={setFilters} />

      {error && (
        <div
          className="onyx-mono"
          style={{
            fontSize: '11px',
            color: 'var(--onyx-red)',
            letterSpacing: '0.24em',
            padding: '12px 0',
          }}
        >
          {error}
        </div>
      )}

      {loading && (
        <div
          className="onyx-mono"
          style={{
            fontSize: '11px',
            letterSpacing: '0.32em',
            color: 'var(--onyx-dim)',
            padding: '40px 0',
          }}
        >
          Loading…
        </div>
      )}

      {!loading && articles.length === 0 && (
        <div
          className="onyx-italic"
          style={{
            fontStyle: 'italic',
            fontSize: '15px',
            color: 'var(--onyx-bone-2)',
            padding: '40px 0',
          }}
        >
          No articles match those filters.
        </div>
      )}

      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {articles.map((a) => (
          <ArticleRow
            key={a.article_id}
            article={a}
            isRead={readArticleIds.has(a.article_id)}
            isInCompare={compareIds.has(a.article_id)}
            onOpen={() => onOpenArticle(a.article_id)}
            onCompareToggle={() => onCompareToggle(a.article_id)}
          />
        ))}
      </ul>

      {hasMore && (
        <div style={{ textAlign: 'center', padding: '32px 0' }}>
          <button
            type="button"
            onClick={onLoadMore}
            disabled={loadingMore}
            className="onyx-mono"
            style={{
              background: 'transparent',
              border: '1px solid var(--onyx-rule-hair)',
              color: 'var(--onyx-bone-2)',
              fontSize: '10px',
              letterSpacing: '0.32em',
              textTransform: 'uppercase',
              padding: '14px 32px',
              cursor: loadingMore ? 'not-allowed' : 'pointer',
              transition: 'border-color 0.3s, color 0.3s',
            }}
          >
            {loadingMore ? 'Loading…' : 'Load more →'}
          </button>
        </div>
      )}
    </section>
  )
}


function FilterBar({
  filters,
  setFilters,
}: {
  filters: ArticleFilters
  setFilters: (f: ArticleFilters) => void
}) {
  return (
    <div
      style={{
        display: 'flex',
        gap: '20px',
        flexWrap: 'wrap',
        padding: '16px 0',
        marginBottom: '24px',
        borderBottom: '1px solid var(--onyx-rule-dim)',
      }}
    >
      <FilterGroup label="Tier">
        {(['1', '1,2', '1,2,3'] as const).map((t) => (
          <FilterChip
            key={t}
            active={filters.tier === t}
            onClick={() => setFilters({ ...filters, tier: t })}
          >
            {t === '1' ? 'I' : t === '1,2' ? 'I-II' : 'All'}
          </FilterChip>
        ))}
      </FilterGroup>

      <FilterGroup label="Window">
        {[
          { v: 0, l: 'All' },
          { v: 1, l: 'Today' },
          { v: 7, l: 'Week' },
          { v: 30, l: 'Month' },
        ].map((d) => (
          <FilterChip
            key={d.v}
            active={filters.days === d.v}
            onClick={() => setFilters({ ...filters, days: d.v })}
          >
            {d.l}
          </FilterChip>
        ))}
      </FilterGroup>

      <FilterGroup label="Sort">
        {(['relevance', 'recency'] as const).map((s) => (
          <FilterChip
            key={s}
            active={filters.sort === s}
            onClick={() => setFilters({ ...filters, sort: s })}
          >
            {s}
          </FilterChip>
        ))}
      </FilterGroup>
    </div>
  )
}


function FilterGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
      <span
        className="onyx-mono"
        style={{
          fontSize: '9px',
          letterSpacing: '0.32em',
          textTransform: 'uppercase',
          color: 'var(--onyx-dim)',
        }}
      >
        {label}
      </span>
      <div style={{ display: 'flex', gap: '6px' }}>{children}</div>
    </div>
  )
}


function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="onyx-mono"
      style={{
        background: 'transparent',
        border: `1px solid ${active ? 'var(--onyx-cyan)' : 'var(--onyx-rule-dim)'}`,
        color: active ? 'var(--onyx-cyan)' : 'var(--onyx-bone-2)',
        fontSize: '10px',
        letterSpacing: '0.24em',
        textTransform: 'uppercase',
        padding: '6px 12px',
        cursor: 'pointer',
        transition: 'all 0.3s',
      }}
    >
      {children}
    </button>
  )
}


function ArticleRow({
  article,
  isRead,
  isInCompare,
  onOpen,
  onCompareToggle,
}: {
  article: Article
  isRead: boolean
  isInCompare: boolean
  onOpen: () => void
  onCompareToggle: () => void
}) {
  return (
    <li
      style={{
        display: 'grid',
        gridTemplateColumns: '1fr auto',
        gap: '16px',
        padding: '20px 0',
        borderBottom: '1px solid var(--onyx-rule-dim)',
        opacity: isRead ? 0.6 : 1,
        transition: 'opacity 0.3s',
      }}
    >
      <div>
        <button
          type="button"
          onClick={onOpen}
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--onyx-bone)',
            fontFamily: 'var(--onyx-italic)',
            fontStyle: 'normal',
            fontSize: '20px',
            lineHeight: 1.25,
            textAlign: 'left',
            padding: 0,
            cursor: 'pointer',
            display: 'block',
          }}
        >
          {article.title}
        </button>

        {article.relevance_explanation && (
          <p
            style={{
              fontFamily: 'var(--onyx-italic)',
              fontStyle: 'italic',
              fontSize: '13.5px',
              lineHeight: 1.55,
              color: 'var(--onyx-bone-2)',
              margin: '8px 0 0',
              maxWidth: '70ch',
            }}
          >
            {article.relevance_explanation}
          </p>
        )}

        <div
          className="onyx-mono"
          style={{
            marginTop: '10px',
            fontSize: '9px',
            letterSpacing: '0.28em',
            textTransform: 'uppercase',
            color: 'var(--onyx-dim)',
            display: 'flex',
            gap: '12px',
            flexWrap: 'wrap',
          }}
        >
          <span>{article.source_name}</span>
          {article.topic_category && (
            <>
              <span style={{ opacity: 0.4 }}>·</span>
              <span>{article.topic_category}</span>
            </>
          )}
          {article.geo_primary && (
            <>
              <span style={{ opacity: 0.4 }}>·</span>
              <span>{article.geo_primary}</span>
            </>
          )}
          <span style={{ opacity: 0.4 }}>·</span>
          <span>{formatTimeAgo(article.collected_at)}</span>
          <span style={{ opacity: 0.4 }}>·</span>
          <span>Tier {article.relevance_tier}</span>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', alignItems: 'flex-end' }}>
        <button
          type="button"
          onClick={onOpen}
          className="onyx-mono"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--onyx-dim)',
            fontSize: '10px',
            letterSpacing: '0.32em',
            textTransform: 'uppercase',
            padding: 0,
            cursor: 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          Read →
        </button>
        <button
          type="button"
          onClick={onCompareToggle}
          className="onyx-mono"
          style={{
            background: 'transparent',
            border: 'none',
            color: isInCompare ? 'var(--onyx-cyan)' : 'var(--onyx-dim)',
            fontSize: '10px',
            letterSpacing: '0.32em',
            textTransform: 'uppercase',
            padding: 0,
            cursor: 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          {isInCompare ? '✓ Compare' : 'Compare'}
        </button>
      </div>
    </li>
  )
}


/* ───────────────────────────────────────────────────────────────
   ArticleReader — slide-in right panel
   ─────────────────────────────────────────────────────────────── */

function ArticleReader({
  article,
  onClose,
  getToken,
}: {
  article: Article
  onClose: () => void
  getToken: () => Promise<string | null>
}) {
  const [summary, setSummary] = useState<string | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summaryError, setSummaryError] = useState<string | null>(null)

  const generateSummary = useCallback(async () => {
    if (summary || summaryLoading) return
    const token = await getToken()
    if (!token) return
    setSummaryLoading(true)
    setSummaryError(null)
    try {
      const res = await fetch(
        `${API_BASE}/api/coverage/summary/${article.article_id}`,
        {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
        }
      )
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = (await res.json()) as { summary: string }
      setSummary(data.summary)
    } catch (err: unknown) {
      setSummaryError(err instanceof Error ? err.message : 'Failed')
    } finally {
      setSummaryLoading(false)
    }
  }, [article.article_id, summary, summaryLoading, getToken])

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0, 0, 0, 0.65)',
        backdropFilter: 'blur(4px)',
        zIndex: 950,
        display: 'flex',
        justifyContent: 'flex-end',
        animation: 'onyx-fade-up 0.3s ease both',
      }}
    >
      <article
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 'min(720px, 100vw)',
          height: '100vh',
          background: 'var(--onyx-bg)',
          borderLeft: '1px solid var(--onyx-red-hair)',
          padding: '32px 48px 64px',
          overflowY: 'auto',
        }}
      >
        <button
          type="button"
          onClick={onClose}
          className="onyx-mono"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--onyx-dim)',
            fontSize: '10px',
            letterSpacing: '0.32em',
            textTransform: 'uppercase',
            cursor: 'pointer',
            padding: 0,
            marginBottom: '24px',
          }}
        >
          ← Close
        </button>

        <div
          className="onyx-mono"
          style={{
            fontSize: '10px',
            letterSpacing: '0.32em',
            textTransform: 'uppercase',
            color: 'var(--onyx-dim)',
            marginBottom: '8px',
            display: 'flex',
            gap: '12px',
            flexWrap: 'wrap',
          }}
        >
          <span>{article.source_name}</span>
          {article.topic_category && <span style={{ opacity: 0.4 }}>· {article.topic_category}</span>}
          <span style={{ opacity: 0.4 }}>· {formatTimeAgo(article.collected_at)}</span>
          <span style={{ opacity: 0.4 }}>· Tier {article.relevance_tier}</span>
        </div>

        <h1
          style={{
            fontFamily: 'var(--onyx-italic)',
            fontStyle: 'normal',
            fontSize: '36px',
            lineHeight: 1.1,
            fontWeight: 400,
            color: 'var(--onyx-bone)',
            letterSpacing: '-0.012em',
            margin: '0 0 16px',
          }}
        >
          {article.title}
        </h1>

        {article.relevance_explanation && (
          <p
            style={{
              fontFamily: 'var(--onyx-italic)',
              fontStyle: 'italic',
              fontSize: '17px',
              lineHeight: 1.6,
              color: 'var(--onyx-bone-2)',
              marginBottom: '24px',
            }}
          >
            {article.relevance_explanation}
          </p>
        )}

        <div style={{ display: 'flex', gap: '12px', marginBottom: '32px', flexWrap: 'wrap' }}>
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="onyx-mono"
            style={{
              background: 'transparent',
              border: '1px solid var(--onyx-rule-hair)',
              color: 'var(--onyx-bone-2)',
              fontSize: '10px',
              letterSpacing: '0.32em',
              textTransform: 'uppercase',
              padding: '10px 18px',
              textDecoration: 'none',
              cursor: 'pointer',
            }}
          >
            Open original →
          </a>
          <button
            type="button"
            onClick={generateSummary}
            disabled={summaryLoading || !!summary}
            className="onyx-mono"
            style={{
              background: 'transparent',
              border: '1px solid var(--onyx-cyan)',
              color: summary ? 'var(--onyx-dim)' : 'var(--onyx-cyan)',
              fontSize: '10px',
              letterSpacing: '0.32em',
              textTransform: 'uppercase',
              padding: '10px 18px',
              cursor: summary ? 'default' : 'pointer',
            }}
          >
            {summaryLoading ? '…' : summary ? '✓ Summarised' : 'Generate summary'}
          </button>
        </div>

        {summaryError && (
          <div
            className="onyx-mono"
            style={{
              fontSize: '10px',
              color: 'var(--onyx-red)',
              letterSpacing: '0.24em',
              marginBottom: '16px',
            }}
          >
            {summaryError}
          </div>
        )}

        {summary && (
          <div
            style={{
              padding: '20px 22px',
              border: '1px solid var(--onyx-rule-hair)',
              marginBottom: '32px',
            }}
          >
            <div
              className="onyx-mono"
              style={{
                fontSize: '9px',
                letterSpacing: '0.32em',
                textTransform: 'uppercase',
                color: 'var(--onyx-dim)',
                marginBottom: '10px',
              }}
            >
              Summary
            </div>
            <p
              style={{
                fontFamily: 'var(--onyx-italic)',
                fontStyle: 'italic',
                fontSize: '15px',
                lineHeight: 1.65,
                color: 'var(--onyx-bone-2)',
                margin: 0,
              }}
            >
              {summary}
            </p>
          </div>
        )}

        <RelatedStrip articleId={article.article_id} />
      </article>
    </div>
  )
}


/* ───────────────────────────────────────────────────────────────
   RelatedStrip — bottom of reader, top-5 semantic neighbours
   ─────────────────────────────────────────────────────────────── */

interface RelatedItem {
  article_id: string
  title: string
  source_name: string
  source_domain: string
  published_at: string | null
}

function RelatedStrip({ articleId }: { articleId: string }) {
  const [items, setItems] = useState<RelatedItem[] | null>(null)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      const supabase = createClient()
      const { data: { session } } = await supabase.auth.getSession()
      const token = session?.access_token
      if (!token) return
      const res = await fetch(
        `${API_BASE}/api/coverage/related/${articleId}?k=5`,
        { headers: { Authorization: `Bearer ${token}` }, cache: 'no-store' }
      )
      if (!res.ok || cancelled) return
      const json = (await res.json()) as { related: RelatedItem[] }
      if (!cancelled) setItems(json.related || [])
    })()
    return () => { cancelled = true }
  }, [articleId])

  if (!items || items.length === 0) return null

  return (
    <section style={{ borderTop: '1px solid var(--onyx-rule-dim)', paddingTop: '24px' }}>
      <div
        className="onyx-mono"
        style={{
          fontSize: '9px',
          letterSpacing: '0.42em',
          textTransform: 'uppercase',
          color: 'var(--onyx-dim)',
          marginBottom: '16px',
        }}
      >
        Related
      </div>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {items.map((r) => (
          <li key={r.article_id}>
            <div
              style={{
                fontFamily: 'var(--onyx-italic)',
                fontStyle: 'normal',
                fontSize: '14px',
                color: 'var(--onyx-bone-2)',
                marginBottom: '4px',
              }}
            >
              {r.title}
            </div>
            <div
              className="onyx-mono"
              style={{
                fontSize: '9px',
                letterSpacing: '0.28em',
                textTransform: 'uppercase',
                color: 'var(--onyx-dim)',
              }}
            >
              {r.source_name} · {formatTimeAgo(r.published_at)}
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}


/* ───────────────────────────────────────────────────────────────
   CompareOverlay — side-by-side claim alignment via /api/compare
   ─────────────────────────────────────────────────────────────── */

interface CompareArticle {
  article_id: string
  title: string
  body: string
  source_name: string
  source_domain: string
}

interface CompareDispute {
  a_says: string
  b_says: string
  topic: string
}

interface CompareAnalysis {
  synthesis: string
  agreements: string[]
  partials: string[]
  disputes: CompareDispute[]
}

function CompareOverlay({
  articleIds,
  onClose,
  getToken,
}: {
  articleIds: string[]
  onClose: () => void
  getToken: () => Promise<string | null>
}) {
  const [data, setData] = useState<{
    articles: CompareArticle[]
    analysis: CompareAnalysis
  } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      const token = await getToken()
      if (!token) return
      try {
        const res = await fetch(`${API_BASE}/api/coverage/compare`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ article_ids: articleIds }),
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const json = await res.json() as {
          articles: CompareArticle[]
          analysis: CompareAnalysis
        }
        if (!cancelled) setData(json)
      } catch (err: unknown) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [articleIds, getToken])

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0, 0, 0, 0.85)',
        backdropFilter: 'blur(8px)',
        zIndex: 1100,
        animation: 'onyx-fade-up 0.3s ease both',
        overflowY: 'auto',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          maxWidth: '1280px',
          margin: '32px auto',
          padding: '40px',
          background: 'var(--onyx-bg)',
          border: '1px solid var(--onyx-cyan)',
          minHeight: 'calc(100vh - 64px)',
        }}
      >
        <button
          type="button"
          onClick={onClose}
          className="onyx-mono"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--onyx-dim)',
            fontSize: '10px',
            letterSpacing: '0.32em',
            textTransform: 'uppercase',
            cursor: 'pointer',
            padding: 0,
            marginBottom: '32px',
          }}
        >
          ← Close
        </button>

        <h2
          style={{
            fontFamily: 'var(--onyx-display)',
            fontWeight: 500,
            fontSize: '28px',
            color: 'var(--onyx-bone)',
            margin: 0,
            marginBottom: '24px',
          }}
        >
          Compare ({articleIds.length})
        </h2>

        {loading && <div className="onyx-mono" style={{ color: 'var(--onyx-dim)' }}>Aligning claims…</div>}

        {error && <div style={{ color: 'var(--onyx-red)' }}>{error}</div>}

        {data && (
          <>
            <p
              style={{
                fontFamily: 'var(--onyx-italic)',
                fontStyle: 'italic',
                fontSize: '18px',
                lineHeight: 1.6,
                color: 'var(--onyx-bone)',
                marginBottom: '40px',
                padding: '20px 24px',
                background: 'rgba(0, 194, 255, 0.04)',
                borderLeft: '2px solid var(--onyx-cyan)',
              }}
            >
              {data.analysis.synthesis}
            </p>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: `repeat(${data.articles.length}, 1fr)`,
                gap: '32px',
                marginBottom: '40px',
              }}
            >
              {data.articles.map((a, i) => (
                <article key={a.article_id}>
                  <div
                    className="onyx-mono"
                    style={{
                      fontSize: '10px',
                      letterSpacing: '0.42em',
                      textTransform: 'uppercase',
                      color: 'var(--onyx-cyan)',
                      marginBottom: '8px',
                    }}
                  >
                    {String.fromCharCode(65 + i)} · {a.source_name}
                  </div>
                  <h3
                    style={{
                      fontFamily: 'var(--onyx-italic)',
                      fontStyle: 'normal',
                      fontSize: '20px',
                      lineHeight: 1.25,
                      color: 'var(--onyx-bone)',
                      margin: '0 0 12px',
                    }}
                  >
                    {a.title}
                  </h3>
                  <p
                    style={{
                      fontFamily: 'var(--onyx-italic)',
                      fontStyle: 'italic',
                      fontSize: '14px',
                      lineHeight: 1.55,
                      color: 'var(--onyx-bone-2)',
                    }}
                  >
                    {a.body.slice(0, 500)}
                    {a.body.length > 500 ? '…' : ''}
                  </p>
                </article>
              ))}
            </div>

            <ClaimsBlock title="Both agree" tone="cyan" items={data.analysis.agreements} />
            <ClaimsBlock title="Only one mentions" tone="dim" items={data.analysis.partials} />
            {data.analysis.disputes.length > 0 && (
              <section style={{ marginTop: '32px' }}>
                <div
                  className="onyx-mono"
                  style={{
                    fontSize: '10px',
                    letterSpacing: '0.42em',
                    textTransform: 'uppercase',
                    color: 'var(--onyx-red)',
                    marginBottom: '16px',
                  }}
                >
                  They disagree
                </div>
                <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  {data.analysis.disputes.map((d, i) => (
                    <li key={i} style={{ borderLeft: '2px solid var(--onyx-red)', paddingLeft: '16px' }}>
                      <div
                        className="onyx-mono"
                        style={{
                          fontSize: '9px',
                          letterSpacing: '0.32em',
                          textTransform: 'uppercase',
                          color: 'var(--onyx-dim)',
                          marginBottom: '6px',
                        }}
                      >
                        {d.topic}
                      </div>
                      <div style={{ fontFamily: 'var(--onyx-italic)', fontStyle: 'italic', fontSize: '14px', color: 'var(--onyx-bone-2)', marginBottom: '4px' }}>
                        <strong style={{ fontStyle: 'normal' }}>A:</strong> {d.a_says}
                      </div>
                      <div style={{ fontFamily: 'var(--onyx-italic)', fontStyle: 'italic', fontSize: '14px', color: 'var(--onyx-bone-2)' }}>
                        <strong style={{ fontStyle: 'normal' }}>B:</strong> {d.b_says}
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
      </div>
    </div>
  )
}


function ClaimsBlock({
  title,
  tone,
  items,
}: {
  title: string
  tone: 'cyan' | 'dim'
  items: string[]
}) {
  if (items.length === 0) return null
  return (
    <section style={{ marginTop: '32px' }}>
      <div
        className="onyx-mono"
        style={{
          fontSize: '10px',
          letterSpacing: '0.42em',
          textTransform: 'uppercase',
          color: tone === 'cyan' ? 'var(--onyx-cyan)' : 'var(--onyx-dim)',
          marginBottom: '12px',
        }}
      >
        {title}
      </div>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {items.map((it, i) => (
          <li
            key={i}
            style={{
              fontFamily: 'var(--onyx-italic)',
              fontStyle: 'italic',
              fontSize: '15px',
              lineHeight: 1.5,
              color: 'var(--onyx-bone-2)',
              paddingLeft: '14px',
              position: 'relative',
            }}
          >
            <span
              style={{
                position: 'absolute',
                left: 0,
                color: tone === 'cyan' ? 'var(--onyx-cyan)' : 'var(--onyx-dim)',
              }}
            >
              ·
            </span>
            {it}
          </li>
        ))}
      </ul>
    </section>
  )
}
