'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import Navigation from '@/components/Navigation'
import { domainColor, formatTimeAgo } from '@/lib/domainColor'

// ── Types ─────────────────────────────────────────────────────────────────────

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

interface Totals {
  total: number
  tier1: number
  tier2: number
  tier3: number
}

interface FeedResponse {
  articles: Article[]
  pagination: {
    has_more: boolean
    next_cursor: string | null
    returned: number
  }
  totals: Totals
}

interface SearchResponse {
  query: string
  count: number
  articles: Article[]
}

type TierFilter = 'all' | '1' | '1,2'
type SortOption = 'relevance' | 'recency'
type SentimentOption = 'all' | 'FOR_USER' | 'AGAINST_USER' | 'NEUTRAL'

// ── Constants ─────────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const TOPICS = [
  'POLITICS', 'ECONOMICS', 'BUSINESS', 'TECHNOLOGY',
  'HEALTH', 'SCIENCE', 'ENVIRONMENT', 'SECURITY',
  'LEGAL', 'SOCIAL', 'INFRASTRUCTURE', 'AGRICULTURE',
  'EDUCATION', 'SPORTS', 'INTERNATIONAL',
]

const TIER_META: Record<number, { bg: string; label: string }> = {
  1: { bg: '#1B3A6B', label: 'T1' },
  2: { bg: '#2D6B3A', label: 'T2' },
  3: { bg: '#5C5249', label: 'T3' },
}

const SENTIMENT_BORDER: Record<string, string> = {
  FOR_USER: '2px solid #2D6B3A',
  AGAINST_USER: '2px solid #8B1A1A',
  NEUTRAL: 'none',
}

// ── Article card ──────────────────────────────────────────────────────────────

interface ArticleCardProps {
  article: Article
  onClick: () => void
}

function ArticleCard({ article, onClick }: ArticleCardProps) {
  const brandColor = domainColor(article.source_domain || article.source_name)
  const timeAgo = formatTimeAgo(article.collected_at)
  const tierInfo = TIER_META[article.relevance_tier] ?? TIER_META[3]
  const [imgBroken, setImgBroken] = useState(false)
  const hasImage = !!article.thumbnail_url && !imgBroken

  return (
    <div
      onClick={onClick}
      style={{
        backgroundColor: '#F7F4EF',
        border: '1px solid #DDD8D0',
        borderRadius: '2px',
        padding: '16px',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            fontFamily: "'DM Sans', system-ui, sans-serif",
            fontSize: '12px',
            color: '#5C5249',
          }}
        >
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              backgroundColor: brandColor,
              display: 'inline-block',
              marginRight: 6,
            }}
          />
          <span style={{ fontWeight: 500 }}>{article.source_name}</span>
          {timeAgo && (
            <span style={{ marginLeft: 6, color: '#9C928A' }}>
              · {timeAgo}
            </span>
          )}
        </div>

        <span
          style={{
            backgroundColor: tierInfo.bg,
            color: '#F7F4EF',
            fontFamily: "'DM Mono', ui-monospace, monospace",
            fontSize: '10px',
            fontWeight: 600,
            padding: '2px 6px',
            borderRadius: '2px',
            border: SENTIMENT_BORDER[article.sentiment_for_user] || 'none',
            letterSpacing: '0.06em',
          }}
        >
          {tierInfo.label}
        </span>
      </div>

      <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
        {hasImage ? (
          <img
            src={article.thumbnail_url as string}
            alt=""
            onError={() => setImgBroken(true)}
            style={{
              width: '80px',
              height: '80px',
              objectFit: 'cover',
              borderRadius: '2px',
              flexShrink: 0,
            }}
          />
        ) : (
          <div
            style={{
              width: '80px',
              height: '80px',
              backgroundColor: brandColor,
              borderRadius: '2px',
              flexShrink: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <span
              style={{
                fontFamily: "'Playfair Display', Georgia, serif",
                fontSize: '22px',
                fontWeight: 700,
                color: 'rgba(255,255,255,0.9)',
              }}
            >
              {article.source_name.slice(0, 2).toUpperCase()}
            </span>
          </div>
        )}

        <div
          style={{
            fontFamily: "'Playfair Display', Georgia, serif",
            fontSize: '17px',
            fontWeight: 700,
            color: '#1A1614',
            lineHeight: 1.35,
            flex: 1,
          }}
        >
          {article.title}
        </div>
      </div>

      <hr
        style={{
          border: 'none',
          borderTop: '1px dashed #DDD8D0',
          margin: 0,
        }}
      />

      <div
        style={{
          fontFamily: "'DM Sans', system-ui, sans-serif",
          fontSize: '13px',
          color: '#5C5249',
          lineHeight: 1.5,
        }}
      >
        {article.relevance_explanation ||
          'Relevant to your monitored geography and topics'}
      </div>

      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {article.topic_category && (
            <span
              style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '10px',
                letterSpacing: '0.06em',
                color: '#5C5249',
                backgroundColor: '#E8E3DA',
                padding: '2px 6px',
                borderRadius: '2px',
              }}
            >
              {article.topic_category}
            </span>
          )}
          {article.geo_primary && (
            <span
              style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '10px',
                letterSpacing: '0.06em',
                color: '#5C5249',
                backgroundColor: '#E8E3DA',
                padding: '2px 6px',
                borderRadius: '2px',
              }}
            >
              {article.geo_primary}
            </span>
          )}
        </div>
        <span
          style={{
            fontFamily: "'DM Mono', ui-monospace, monospace",
            fontSize: '12px',
            color: '#1B3A6B',
          }}
        >
          {article.score_final.toFixed(2)}
        </span>
      </div>
    </div>
  )
}

// ── Tier separator ────────────────────────────────────────────────────────────

function TierSeparator({ label }: { label: string }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        margin: '24px 0 8px',
      }}
    >
      <div style={{ flex: 1, height: '1px', backgroundColor: '#DDD8D0' }} />
      <span
        style={{
          fontFamily: "'DM Sans', system-ui, sans-serif",
          fontSize: '11px',
          letterSpacing: '0.15em',
          textTransform: 'uppercase',
          color: '#9C928A',
        }}
      >
        {label}
      </span>
      <div style={{ flex: 1, height: '1px', backgroundColor: '#DDD8D0' }} />
    </div>
  )
}

// ── Article dialog ────────────────────────────────────────────────────────────

interface DialogProps {
  article: Article
  summary: string | null
  summaryLoading: boolean
  summaryError: string | null
  onClose: () => void
  onGenerateSummary: () => void
}

function ArticleDialog({
  article,
  summary,
  summaryLoading,
  summaryError,
  onClose,
  onGenerateSummary,
}: DialogProps) {
  const brandColor = domainColor(article.source_domain || article.source_name)
  const tierInfo = TIER_META[article.relevance_tier] ?? TIER_META[3]
  const [imgBroken, setImgBroken] = useState(false)
  const hasImage = !!article.thumbnail_url && !imgBroken

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(26,22,20,0.4)',
        zIndex: 200,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          position: 'fixed',
          top: 0,
          right: 0,
          width: '560px',
          maxWidth: '100vw',
          height: '100vh',
          backgroundColor: '#F7F4EF',
          overflowY: 'auto',
          boxShadow: '-4px 0 24px rgba(26,22,20,0.15)',
        }}
      >
        <button
          onClick={onClose}
          aria-label="Close"
          style={{
            position: 'absolute',
            top: '16px',
            right: '16px',
            background: 'none',
            border: 'none',
            fontFamily: "'DM Sans', system-ui, sans-serif",
            fontSize: '20px',
            color: '#9C928A',
            cursor: 'pointer',
            zIndex: 1,
            lineHeight: 1,
          }}
        >
          ×
        </button>

        {hasImage ? (
          <img
            src={article.thumbnail_url as string}
            alt=""
            onError={() => setImgBroken(true)}
            style={{
              width: '100%',
              height: '240px',
              objectFit: 'cover',
              display: 'block',
            }}
          />
        ) : (
          <div
            style={{
              width: '100%',
              height: '240px',
              backgroundColor: brandColor,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <span
              style={{
                fontFamily: "'Playfair Display', Georgia, serif",
                fontSize: '64px',
                fontWeight: 700,
                color: 'rgba(255,255,255,0.9)',
              }}
            >
              {article.source_name.slice(0, 2).toUpperCase()}
            </span>
          </div>
        )}

        <div style={{ padding: '24px 32px 40px' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              fontFamily: "'DM Sans', system-ui, sans-serif",
              fontSize: '12px',
              color: '#5C5249',
              marginBottom: '12px',
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                backgroundColor: brandColor,
                display: 'inline-block',
                marginRight: 6,
              }}
            />
            <span style={{ fontWeight: 500 }}>{article.source_name}</span>
            {article.collected_at && (
              <span style={{ marginLeft: 6, color: '#9C928A' }}>
                · {formatTimeAgo(article.collected_at)}
              </span>
            )}
            {article.author_name && (
              <span style={{ marginLeft: 6, color: '#9C928A' }}>
                · by {article.author_name}
              </span>
            )}
          </div>

          <h2
            style={{
              fontFamily: "'Playfair Display', Georgia, serif",
              fontSize: '26px',
              fontWeight: 700,
              lineHeight: 1.3,
              color: '#1A1614',
              margin: '16px 0',
            }}
          >
            {article.title}
          </h2>

          <div
            style={{
              backgroundColor: '#FDF0EF',
              borderLeft: '3px solid #8B1A1A',
              padding: '12px 16px',
              borderRadius: '2px',
              marginBottom: '20px',
            }}
          >
            <div
              style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '10px',
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
                color: '#9C928A',
                marginBottom: '6px',
              }}
            >
              Why This Matters To You
            </div>
            <div
              style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '14px',
                color: '#1A1614',
                lineHeight: 1.6,
              }}
            >
              {article.relevance_explanation ||
                'Relevant to your monitored geography and topics'}
            </div>
          </div>

          {!summary && !summaryLoading && !summaryError && (
            <button
              onClick={onGenerateSummary}
              style={{
                background: 'none',
                border: 'none',
                padding: 0,
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '13px',
                color: '#8B1A1A',
                cursor: 'pointer',
                marginTop: '4px',
              }}
            >
              Generate Summary →
            </button>
          )}

          {summaryLoading && (
            <p
              style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '13px',
                color: '#9C928A',
                fontStyle: 'italic',
              }}
            >
              Generating...
            </p>
          )}

          {summaryError && !summaryLoading && (
            <p
              style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '13px',
                color: '#8B1A1A',
              }}
            >
              {summaryError}{' '}
              <button
                onClick={onGenerateSummary}
                style={{
                  background: 'none',
                  border: 'none',
                  padding: 0,
                  fontFamily: "'DM Sans', system-ui, sans-serif",
                  fontSize: '13px',
                  color: '#5C5249',
                  cursor: 'pointer',
                  textDecoration: 'underline',
                }}
              >
                Retry
              </button>
            </p>
          )}

          {summary && (
            <p
              style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '15px',
                lineHeight: 1.7,
                color: '#1A1614',
                margin: 0,
              }}
            >
              {summary}
            </p>
          )}

          {article.matched_entity_names.length > 0 && (
            <div style={{ marginTop: '28px' }}>
              <div
                style={{
                  fontFamily: "'DM Sans', system-ui, sans-serif",
                  fontSize: '10px',
                  letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                  color: '#9C928A',
                  marginBottom: '8px',
                }}
              >
                Matched Entities
              </div>
              <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                {article.matched_entity_names.map((e) => (
                  <span
                    key={e}
                    style={{
                      fontFamily: "'DM Sans', system-ui, sans-serif",
                      fontSize: '12px',
                      backgroundColor: '#EEF3FA',
                      color: '#1B3A6B',
                      padding: '3px 8px',
                      borderRadius: '2px',
                    }}
                  >
                    {e}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div
            style={{
              marginTop: '24px',
              paddingTop: '16px',
              borderTop: '1px solid #DDD8D0',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              flexWrap: 'wrap',
            }}
          >
            {article.topic_category && (
              <span
                style={{
                  fontFamily: "'DM Sans', system-ui, sans-serif",
                  fontSize: '11px',
                  letterSpacing: '0.06em',
                  color: '#5C5249',
                  backgroundColor: '#E8E3DA',
                  padding: '3px 8px',
                  borderRadius: '2px',
                }}
              >
                {article.topic_category}
              </span>
            )}
            {article.geo_primary && (
              <span
                style={{
                  fontFamily: "'DM Sans', system-ui, sans-serif",
                  fontSize: '11px',
                  letterSpacing: '0.06em',
                  color: '#5C5249',
                  backgroundColor: '#E8E3DA',
                  padding: '3px 8px',
                  borderRadius: '2px',
                }}
              >
                {article.geo_primary}
              </span>
            )}
            <span
              style={{
                backgroundColor: tierInfo.bg,
                color: '#F7F4EF',
                fontFamily: "'DM Mono', ui-monospace, monospace",
                fontSize: '10px',
                fontWeight: 600,
                padding: '2px 6px',
                borderRadius: '2px',
                border: SENTIMENT_BORDER[article.sentiment_for_user] || 'none',
              }}
            >
              {tierInfo.label}
            </span>
            <span
              style={{
                marginLeft: 'auto',
                fontFamily: "'DM Mono', ui-monospace, monospace",
                fontSize: '13px',
                color: '#1B3A6B',
              }}
            >
              {article.score_final.toFixed(2)}
            </span>
          </div>

          <div style={{ marginTop: '28px' }}>
            <div
              style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '10px',
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
                color: '#9C928A',
                marginBottom: '8px',
              }}
            >
              Journalist Coverage Bias
            </div>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                marginBottom: '4px',
              }}
            >
              <div
                style={{
                  flex: 1,
                  height: '6px',
                  backgroundColor: '#E8E3DA',
                  borderRadius: '2px',
                }}
              />
              <span
                style={{
                  fontFamily: "'DM Sans', system-ui, sans-serif",
                  fontSize: '11px',
                  color: '#9C928A',
                }}
              >
                No data yet
              </span>
            </div>
            <p
              style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '12px',
                color: '#9C928A',
                fontStyle: 'italic',
                margin: 0,
              }}
            >
              Journalist bias tracking coming soon
            </p>
          </div>

          <div
            style={{
              marginTop: '28px',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <span
              title="Coming in Collections"
              style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '13px',
                color: '#9C928A',
                cursor: 'default',
              }}
            >
              ♦ Save to Collection
            </span>
            <a
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '13px',
                color: '#8B1A1A',
                textDecoration: 'none',
              }}
            >
              Read Original →
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Filter sidebar ────────────────────────────────────────────────────────────

interface FilterSidebarProps {
  selectedTopics: string[]
  onToggleTopic: (topic: string) => void
  selectedTier: TierFilter
  onTierChange: (tier: TierFilter) => void
  selectedDays: number
  onDaysChange: (days: number) => void
  selectedSentiment: SentimentOption
  onSentimentChange: (s: SentimentOption) => void
  sortBy: SortOption
  onSortChange: (s: SortOption) => void
  onClearFilters: () => void
}

function FilterSidebar(props: FilterSidebarProps) {
  const labelStyle = {
    fontFamily: "'DM Sans', system-ui, sans-serif",
    fontSize: '10px',
    letterSpacing: '0.12em',
    textTransform: 'uppercase' as const,
    color: '#9C928A',
    marginBottom: '8px',
    marginTop: '20px',
  }
  const optionStyle = {
    fontFamily: "'DM Sans', system-ui, sans-serif",
    fontSize: '13px',
    color: '#1A1614',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '3px 0',
    cursor: 'pointer',
  }

  return (
    <aside
      style={{
        width: '200px',
        flexShrink: 0,
        paddingRight: '16px',
        position: 'sticky',
        top: '16px',
        alignSelf: 'flex-start',
        maxHeight: 'calc(100vh - 32px)',
        overflowY: 'auto',
      }}
    >
      <div style={labelStyle}>Topic</div>
      {TOPICS.map((t) => (
        <label key={t} style={optionStyle}>
          <input
            type="checkbox"
            checked={props.selectedTopics.includes(t)}
            onChange={() => props.onToggleTopic(t)}
          />
          {t}
        </label>
      ))}

      <div style={labelStyle}>Tier</div>
      {(
        [
          ['all', 'All tiers'],
          ['1', 'Tier 1 only'],
          ['1,2', 'Tier 1 + 2'],
        ] as const
      ).map(([v, lbl]) => (
        <label key={v} style={optionStyle}>
          <input
            type="radio"
            name="tier"
            checked={props.selectedTier === v}
            onChange={() => props.onTierChange(v)}
          />
          {lbl}
        </label>
      ))}

      <div style={labelStyle}>Time</div>
      {(
        [
          [0, 'All time'],
          [7, 'This week'],
          [1, 'Today'],
        ] as const
      ).map(([v, lbl]) => (
        <label key={v} style={optionStyle}>
          <input
            type="radio"
            name="days"
            checked={props.selectedDays === v}
            onChange={() => props.onDaysChange(v)}
          />
          {lbl}
        </label>
      ))}

      <div style={labelStyle}>Sentiment</div>
      {(
        [
          ['all', 'All'],
          ['FOR_USER', 'Supports you'],
          ['AGAINST_USER', 'Against you'],
          ['NEUTRAL', 'Neutral'],
        ] as const
      ).map(([v, lbl]) => (
        <label key={v} style={optionStyle}>
          <input
            type="radio"
            name="sent"
            checked={props.selectedSentiment === v}
            onChange={() => props.onSentimentChange(v)}
          />
          {lbl}
        </label>
      ))}

      <div style={labelStyle}>Sort</div>
      {(
        [
          ['relevance', 'By relevance'],
          ['recency', 'By recency'],
        ] as const
      ).map(([v, lbl]) => (
        <label key={v} style={optionStyle}>
          <input
            type="radio"
            name="sort"
            checked={props.sortBy === v}
            onChange={() => props.onSortChange(v)}
          />
          {lbl}
        </label>
      ))}

      <button
        onClick={props.onClearFilters}
        style={{
          marginTop: '24px',
          background: 'none',
          border: 'none',
          padding: 0,
          fontFamily: "'DM Sans', system-ui, sans-serif",
          fontSize: '12px',
          color: '#8B1A1A',
          cursor: 'pointer',
        }}
      >
        Clear filters
      </button>
    </aside>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function CoveragePage() {
  const router = useRouter()

  // Always get a fresh token — Supabase auto-refreshes expired sessions.
  // Never store stale token in a ref; call this before every API request.
  const getToken = useCallback(async (): Promise<string | null> => {
    const supabase = createClient()
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) {
      router.push('/login')
      return null
    }
    return session.access_token
  }, [router])

  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [articles, setArticles] = useState<Article[]>([])
  const [hasMore, setHasMore] = useState(false)
  const [nextCursor, setNextCursor] = useState<string>('')
  const [totals, setTotals] = useState<Totals>({
    total: 0, tier1: 0, tier2: 0, tier3: 0,
  })
  const [errorMsg, setErrorMsg] = useState<string>('')

  const [selectedTopics, setSelectedTopics] = useState<string[]>([])
  const [selectedTier, setSelectedTier] = useState<TierFilter>('all')
  const [selectedDays, setSelectedDays] = useState<number>(0)
  const [selectedSentiment, setSelectedSentiment] =
    useState<SentimentOption>('all')
  const [sortBy, setSortBy] = useState<SortOption>('relevance')

  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<Article[] | null>(null)
  const [isSearching, setIsSearching] = useState(false)

  const [selectedArticle, setSelectedArticle] = useState<Article | null>(null)
  const [summariesById, setSummariesById] = useState<Record<string, string>>({})
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summaryError, setSummaryError] = useState<string | null>(null)

  const buildFeedUrl = useCallback(
    (cursor: string = '') => {
      const params = new URLSearchParams()
      const tierParam = selectedTier === 'all' ? '1,2,3' : selectedTier
      params.set('tier', tierParam)
      if (selectedTopics.length > 0) {
        params.set('topic', selectedTopics.join(','))
      }
      if (selectedDays > 0) params.set('days', String(selectedDays))
      if (selectedSentiment !== 'all') {
        params.set('sentiment', selectedSentiment)
      }
      params.set('sort', sortBy)
      if (cursor) params.set('cursor', cursor)
      params.set('limit', '20')
      return `${API_BASE}/api/coverage/feed?${params.toString()}`
    },
    [selectedTier, selectedTopics, selectedDays, selectedSentiment, sortBy]
  )

  const fetchFeed = useCallback(
    async (cursor: string = '', append = false) => {
      const token = await getToken()
      if (!token) return
      if (append) {
        setLoadingMore(true)
      } else {
        setLoading(true)
      }
      setErrorMsg('')

      try {
        const res = await fetch(buildFeedUrl(cursor), {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!res.ok) {
          setErrorMsg(`Feed request failed (${res.status})`)
          return
        }
        const data: FeedResponse = await res.json()
        setArticles((prev) =>
          append ? [...prev, ...data.articles] : data.articles
        )
        setHasMore(data.pagination.has_more)
        setNextCursor(data.pagination.next_cursor ?? '')
        setTotals(data.totals)
      } catch (e: unknown) {
        setErrorMsg(
          e instanceof Error ? e.message : 'Network error'
        )
      } finally {
        setLoading(false)
        setLoadingMore(false)
      }
    },
    [buildFeedUrl, getToken]
  )

  // Auth check + initial fetch
  useEffect(() => {
    void fetchFeed('', false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Re-fetch when filters change (but not on initial mount)
  const filtersKey = `${selectedTier}|${selectedTopics.join(',')}|${selectedDays}|${selectedSentiment}|${sortBy}`
  const didMountRef = useRef(false)
  useEffect(() => {
    if (!didMountRef.current) {
      didMountRef.current = true
      return
    }
    void fetchFeed('', false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtersKey])

  const handleLoadMore = () => {
    if (!hasMore || !nextCursor) return
    void fetchFeed(nextCursor, true)
  }

  const handleSearchEnter = async () => {
    if (searchQuery.trim().length < 2) return
    const token = await getToken()
    if (!token) return
    setIsSearching(true)
    try {
      const params = new URLSearchParams()
      params.set('q', searchQuery.trim())
      const tierParam = selectedTier === 'all' ? '1,2,3' : selectedTier
      params.set('tier', tierParam)
      const res = await fetch(
        `${API_BASE}/api/coverage/search?${params.toString()}`,
        { headers: { Authorization: `Bearer ${token}` } }
      )
      if (res.ok) {
        const data: SearchResponse = await res.json()
        setSearchResults(data.articles)
      }
    } catch {
      // ignore
    } finally {
      setIsSearching(false)
    }
  }

  const clearSearch = () => {
    setSearchQuery('')
    setSearchResults(null)
  }

  const handleToggleTopic = (topic: string) => {
    setSelectedTopics((prev) =>
      prev.includes(topic)
        ? prev.filter((t) => t !== topic)
        : [...prev, topic]
    )
  }

  const clearFilters = () => {
    setSelectedTopics([])
    setSelectedTier('all')
    setSelectedDays(0)
    setSelectedSentiment('all')
    setSortBy('relevance')
  }

  const handleOpenArticle = (article: Article) => {
    setSelectedArticle(article)
    setSummaryError(null)
  }

  const handleCloseDialog = () => {
    setSelectedArticle(null)
    setSummaryError(null)
  }

  const handleGenerateSummary = async () => {
    if (!selectedArticle) return
    const id = selectedArticle.article_id
    if (summariesById[id]) return
    const token = await getToken()
    if (!token) return
    setSummaryLoading(true)
    setSummaryError(null)
    try {
      const res = await fetch(
        `${API_BASE}/api/coverage/summary/${id}`,
        {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
        }
      )
      if (!res.ok) {
        setSummaryError('Summary generation failed')
        return
      }
      const data: { summary: string } = await res.json()
      setSummariesById((prev) => ({ ...prev, [id]: data.summary }))
    } catch {
      setSummaryError('Network error generating summary')
    } finally {
      setSummaryLoading(false)
    }
  }

  // Determine visible list
  const serverSearchActive = searchResults !== null
  const clientFilterActive =
    !serverSearchActive && searchQuery.trim().length >= 2
  const visibleArticles: Article[] = serverSearchActive
    ? (searchResults as Article[])
    : clientFilterActive
      ? articles.filter((a) =>
          a.title.toLowerCase().includes(searchQuery.trim().toLowerCase())
        )
      : articles

  // Tier grouping for separators
  const renderArticleList = () => {
    const rendered: React.ReactNode[] = []
    let lastTier = 0
    visibleArticles.forEach((a) => {
      if (
        !serverSearchActive &&
        !clientFilterActive &&
        sortBy === 'relevance' &&
        a.relevance_tier !== lastTier
      ) {
        if (a.relevance_tier === 2) {
          rendered.push(
            <TierSeparator key="sep-t2" label="Tier 2 — Notable" />
          )
        } else if (a.relevance_tier === 3) {
          rendered.push(
            <TierSeparator key="sep-t3" label="Tier 3 — Background" />
          )
        }
        lastTier = a.relevance_tier
      }
      rendered.push(
        <ArticleCard
          key={a.article_id}
          article={a}
          onClick={() => handleOpenArticle(a)}
        />
      )
    })
    return rendered
  }

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#F7F4EF' }}>
      <Navigation />

      <main
        style={{
          marginLeft: '200px',
          padding: '0',
        }}
      >
        <div
          style={{
            position: 'sticky',
            top: 0,
            zIndex: 50,
            backgroundColor: '#F7F4EF',
            borderBottom: '1px solid #DDD8D0',
            padding: '20px 32px 12px',
          }}
        >
          <div
            style={{
              fontFamily: "'DM Sans', system-ui, sans-serif",
              fontSize: '11px',
              letterSpacing: '0.15em',
              textTransform: 'uppercase',
              color: '#9C928A',
            }}
          >
            Coverage Room
          </div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginTop: '4px',
            }}
          >
            <div
              style={{
                fontFamily: "'DM Mono', ui-monospace, monospace",
                fontSize: '12px',
                color: '#9C928A',
              }}
            >
              {totals.total.toLocaleString()} articles ranked
              {' · '}T1: {totals.tier1}
              {' · '}T2: {totals.tier2}
              {' · '}T3: {totals.tier3}
            </div>
          </div>

          <div
            style={{
              marginTop: '14px',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              flexWrap: 'wrap',
            }}
          >
            <div style={{ position: 'relative', flex: 1, minWidth: '240px' }}>
              <input
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value)
                  if (searchResults !== null) setSearchResults(null)
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void handleSearchEnter()
                }}
                placeholder="Search articles..."
                style={{
                  width: '100%',
                  padding: '8px 30px 8px 10px',
                  border: '1px solid #DDD8D0',
                  borderRadius: '2px',
                  backgroundColor: '#F7F4EF',
                  fontFamily: "'DM Sans', system-ui, sans-serif",
                  fontSize: '13px',
                  color: '#1A1614',
                  outline: 'none',
                }}
              />
              {searchQuery && (
                <button
                  onClick={clearSearch}
                  aria-label="Clear search"
                  style={{
                    position: 'absolute',
                    right: '6px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: '#9C928A',
                    fontSize: '16px',
                    lineHeight: 1,
                    padding: '2px 6px',
                  }}
                >
                  ×
                </button>
              )}
            </div>

            <div style={{ display: 'flex', gap: '4px' }}>
              {(
                [
                  ['relevance', 'Relevance'],
                  ['recency', 'Recency'],
                ] as const
              ).map(([v, lbl]) => {
                const active = sortBy === v
                return (
                  <button
                    key={v}
                    onClick={() => setSortBy(v)}
                    style={{
                      padding: '6px 10px',
                      border: `1px solid ${active ? '#8B1A1A' : '#DDD8D0'}`,
                      backgroundColor: active ? '#FDF0EF' : 'transparent',
                      fontFamily: "'DM Sans', system-ui, sans-serif",
                      fontSize: '12px',
                      color: active ? '#8B1A1A' : '#5C5249',
                      borderRadius: '2px',
                      cursor: 'pointer',
                    }}
                  >
                    {lbl}
                  </button>
                )
              })}
            </div>
          </div>

          {clientFilterActive && (
            <div
              style={{
                marginTop: '10px',
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '12px',
                color: '#5C5249',
              }}
            >
              Showing {visibleArticles.length} of {articles.length} matching
              &ldquo;{searchQuery}&rdquo; — press Enter to search all articles
            </div>
          )}

          {serverSearchActive && (
            <div
              style={{
                marginTop: '10px',
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '12px',
                color: '#5C5249',
              }}
            >
              {(searchResults as Article[]).length} articles mention
              {' '}&ldquo;{searchQuery}&rdquo;
            </div>
          )}

          {isSearching && (
            <div
              style={{
                marginTop: '10px',
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '12px',
                color: '#9C928A',
                fontStyle: 'italic',
              }}
            >
              Searching...
            </div>
          )}
        </div>

        <div
          style={{
            display: 'flex',
            gap: '24px',
            padding: '24px 32px 80px',
          }}
        >
          <FilterSidebar
            selectedTopics={selectedTopics}
            onToggleTopic={handleToggleTopic}
            selectedTier={selectedTier}
            onTierChange={setSelectedTier}
            selectedDays={selectedDays}
            onDaysChange={setSelectedDays}
            selectedSentiment={selectedSentiment}
            onSentimentChange={setSelectedSentiment}
            sortBy={sortBy}
            onSortChange={setSortBy}
            onClearFilters={clearFilters}
          />

          <section style={{ flex: 1, minWidth: 0 }}>
            {loading && (
              <div
                style={{
                  padding: '60px 0',
                  textAlign: 'center',
                  fontFamily: "'DM Mono', ui-monospace, monospace",
                  fontSize: '12px',
                  color: '#9C928A',
                }}
              >
                Loading feed...
              </div>
            )}

            {errorMsg && !loading && (
              <div
                style={{
                  padding: '24px 0',
                  fontFamily: "'DM Sans', system-ui, sans-serif",
                  fontSize: '13px',
                  color: '#8B1A1A',
                }}
              >
                {errorMsg}
              </div>
            )}

            {!loading && !errorMsg && visibleArticles.length === 0 && (
              <div
                style={{
                  padding: '60px 0',
                  textAlign: 'center',
                  fontFamily: "'DM Sans', system-ui, sans-serif",
                  fontSize: '14px',
                  color: '#9C928A',
                }}
              >
                No articles match your filters.
              </div>
            )}

            {!loading && visibleArticles.length > 0 && (
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '16px',
                }}
              >
                {renderArticleList()}
              </div>
            )}

            {!loading &&
              !serverSearchActive &&
              !clientFilterActive &&
              hasMore && (
                <div style={{ textAlign: 'center', marginTop: '32px' }}>
                  <button
                    onClick={handleLoadMore}
                    disabled={loadingMore}
                    style={{
                      background: 'none',
                      border: 'none',
                      padding: 0,
                      fontFamily: "'DM Sans', system-ui, sans-serif",
                      fontSize: '13px',
                      color: '#5C5249',
                      cursor: loadingMore ? 'default' : 'pointer',
                      textDecoration: 'underline',
                    }}
                  >
                    {loadingMore ? 'Loading...' : 'Load more articles'}
                  </button>
                </div>
              )}

            {serverSearchActive && (
              <div
                style={{
                  marginTop: '24px',
                  padding: '16px',
                  border: '1px dashed #DDD8D0',
                  borderRadius: '2px',
                  textAlign: 'center',
                }}
              >
                <span
                  title="Coming soon"
                  style={{
                    fontFamily: "'DM Sans', system-ui, sans-serif",
                    fontSize: '13px',
                    color: '#9C928A',
                    cursor: 'default',
                  }}
                >
                  Want deeper analysis? Ask the Analyst →
                </span>
              </div>
            )}
          </section>
        </div>
      </main>

      {selectedArticle && (
        <ArticleDialog
          article={selectedArticle}
          summary={summariesById[selectedArticle.article_id] ?? null}
          summaryLoading={summaryLoading}
          summaryError={summaryError}
          onClose={handleCloseDialog}
          onGenerateSummary={handleGenerateSummary}
        />
      )}
    </div>
  )
}
