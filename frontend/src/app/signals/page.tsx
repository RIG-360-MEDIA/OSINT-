'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import Navigation from '@/components/Navigation'
import { createClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

type Platform = 'all' | 'twitter' | 'reddit' | 'telegram'

interface SignalPost {
  post_id: string
  platform: 'twitter' | 'reddit' | 'telegram'
  author_username: string | null
  post_text: string
  post_text_translated: string | null
  post_url: string | null
  upvotes: number
  comment_count: number
  share_count: number
  forward_count: number
  forwarded_from: string | null
  has_document: boolean
  sentiment_score: number | null
  matched_entities: string[]
  monitor_name: string | null
  posted_at: string | null
  collected_at: string
}

interface FeedResponse {
  posts: SignalPost[]
  has_more: boolean
  next_cursor: string | null
}

interface MonitorSentiment {
  platform: 'twitter' | 'reddit' | 'telegram'
  display_name: string | null
  identifier: string
  post_count: number
  avg_sentiment: number
  positive_count: number
  negative_count: number
  neutral_count: number
}

interface SentimentResponse {
  sentiment_by_monitor: MonitorSentiment[]
}

const PLATFORM_COLOR: Record<SignalPost['platform'], string> = {
  twitter:  '#1DA1F2',
  reddit:   '#FF4500',
  telegram: '#229ED9',
}

const PLATFORM_LABEL: Record<SignalPost['platform'], string> = {
  twitter:  'Twitter / X',
  reddit:   'Reddit',
  telegram: 'Telegram',
}

const TAB_ORDER: { id: Platform; label: string }[] = [
  { id: 'all',      label: 'All' },
  { id: 'twitter',  label: 'Twitter / X' },
  { id: 'reddit',   label: 'Reddit' },
  { id: 'telegram', label: 'Telegram' },
]

function relativeTime(iso: string | null): string {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  const diff = Date.now() - t
  if (diff < 60_000) return 'just now'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`
  return `${Math.floor(diff / 86_400_000)}d ago`
}

function sentimentLabel(score: number | null): { label: string; color: string } {
  if (score === null || score === undefined) return { label: '—', color: '#94A3B8' }
  if (score >  0.1) return { label: 'POSITIVE', color: '#10B981' }
  if (score < -0.1) return { label: 'NEGATIVE', color: '#F43F5E' }
  return { label: 'NEUTRAL',  color: '#94A3B8' }
}

export default function SignalsPage() {
  const router = useRouter()
  const [token, setToken] = useState<string | null>(null)
  const [tab, setTab] = useState<Platform>('all')
  const [posts, setPosts] = useState<SignalPost[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sentiment, setSentiment] = useState<MonitorSentiment[]>([])
  const firstLoad = useRef(true)

  const fetchFeed = useCallback(
    async (authToken: string, platform: Platform, nextCursor: string) => {
      setLoading(true)
      setError(null)
      try {
        const params = new URLSearchParams({
          platform,
          days: '7',
          limit: '30',
        })
        if (nextCursor) params.set('cursor', nextCursor)
        const res = await fetch(`${API_BASE}/api/signals/feed?${params}`, {
          headers: { Authorization: `Bearer ${authToken}` },
        })
        if (!res.ok) throw new Error(`feed ${res.status}`)
        const data = (await res.json()) as FeedResponse
        setPosts(prev => (nextCursor ? [...prev, ...data.posts] : data.posts))
        setCursor(data.next_cursor)
        setHasMore(data.has_more)
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'feed failed')
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  const fetchSentiment = useCallback(async (authToken: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/signals/sentiment?days=7`, {
        headers: { Authorization: `Bearer ${authToken}` },
      })
      if (!res.ok) return
      const data = (await res.json()) as SentimentResponse
      setSentiment(data.sentiment_by_monitor)
    } catch {
      // non-critical
    }
  }, [])

  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) {
        router.push('/login')
        return
      }
      setToken(session.access_token)
    })
  }, [router])

  useEffect(() => {
    if (!token) return
    if (firstLoad.current) firstLoad.current = false
    setPosts([])
    setCursor(null)
    void fetchFeed(token, tab, '')
    void fetchSentiment(token)
  }, [token, tab, fetchFeed, fetchSentiment])

  const platformCounts = useMemo(() => {
    const counts = { twitter: 0, reddit: 0, telegram: 0 }
    for (const p of posts) counts[p.platform]++
    return counts
  }, [posts])

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#F1F5F9' }}>
      <Navigation />
      <main style={{
        paddingTop: '56px',
        maxWidth:   '1160px',
        margin:     '0 auto',
        padding:    '56px 24px 80px',
      }}>
        <Header counts={platformCounts} />
        <Tabs tab={tab} setTab={setTab} />
        <SentimentBar data={sentiment} />

        <div style={{ marginTop: '24px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {posts.length === 0 && !loading && (
            <EmptyState platform={tab} />
          )}
          {posts.map(p => (
            <PostCard key={p.post_id} post={p} />
          ))}
          {hasMore && !loading && (
            <button
              onClick={() => token && cursor && fetchFeed(token, tab, cursor)}
              style={loadMoreBtnStyle}
            >
              Load more
            </button>
          )}
          {loading && <LoadingRow />}
          {error && (
            <div style={errorBoxStyle}>Error: {error}</div>
          )}
        </div>
      </main>
    </div>
  )
}

/* ── Header ──────────────────────────────────────────────────────────── */

function Header({ counts }: { counts: { twitter: number; reddit: number; telegram: number } }) {
  return (
    <header style={{
      display:        'flex',
      alignItems:     'baseline',
      justifyContent: 'space-between',
      gap:            '16px',
      marginBottom:   '18px',
    }}>
      <div>
        <div style={{
          fontFamily:    "'DM Sans', system-ui, sans-serif",
          fontSize:      '11px',
          fontWeight:    600,
          letterSpacing: '0.14em',
          textTransform: 'uppercase',
          color:         '#64748B',
        }}>Intelligence Floor</div>
        <h1 style={{
          fontFamily:    "'DM Sans', system-ui, sans-serif",
          fontSize:      '28px',
          fontWeight:    700,
          letterSpacing: '-0.02em',
          color:         '#0F172A',
          margin:        '4px 0 0',
        }}>SIGNAL ROOM</h1>
      </div>
      <div style={{ display: 'flex', gap: '10px', fontFamily: "'DM Mono', ui-monospace, monospace", fontSize: '11px' }}>
        <CountChip color="#1DA1F2" label="twitter" value={counts.twitter} />
        <CountChip color="#FF4500" label="reddit"  value={counts.reddit}  />
        <CountChip color="#229ED9" label="telegram" value={counts.telegram} />
      </div>
    </header>
  )
}

function CountChip({ color, label, value }: { color: string; label: string; value: number }) {
  return (
    <div style={{
      display:         'flex',
      alignItems:      'center',
      gap:             '6px',
      padding:         '4px 10px',
      borderRadius:    '6px',
      backgroundColor: '#FFFFFF',
      border:          '1px solid #E2E8F0',
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: color }} />
      <span style={{ color: '#475569', letterSpacing: '0.04em' }}>{value} {label}</span>
    </div>
  )
}

/* ── Tabs ────────────────────────────────────────────────────────────── */

function Tabs({ tab, setTab }: { tab: Platform; setTab: (t: Platform) => void }) {
  return (
    <div style={{
      display:      'flex',
      gap:          '4px',
      borderBottom: '1px solid #E2E8F0',
      marginBottom: '14px',
    }}>
      {TAB_ORDER.map(t => {
        const active = tab === t.id
        return (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              position:        'relative',
              border:          'none',
              background:      'transparent',
              padding:         '10px 16px',
              cursor:          'pointer',
              fontFamily:      "'DM Sans', system-ui, sans-serif",
              fontSize:        '14px',
              fontWeight:      active ? 600 : 500,
              color:           active ? '#0F172A' : '#64748B',
              letterSpacing:   '-0.01em',
            }}
          >
            {t.label}
            {active && (
              <span style={{
                position:        'absolute',
                left:            0,
                right:           0,
                bottom:          '-1px',
                height:          '2px',
                backgroundColor: '#F43F5E',
              }} />
            )}
          </button>
        )
      })}
    </div>
  )
}

/* ── Sentiment bar ───────────────────────────────────────────────────── */

function SentimentBar({ data }: { data: MonitorSentiment[] }) {
  if (data.length === 0) return null
  return (
    <section style={{
      padding:         '14px 16px',
      backgroundColor: '#FFFFFF',
      border:          '1px solid #E2E8F0',
      borderRadius:    '6px',
      display:         'flex',
      flexDirection:   'column',
      gap:             '8px',
    }}>
      <div style={{
        fontFamily:    "'DM Sans', system-ui, sans-serif",
        fontSize:      '11px',
        letterSpacing: '0.14em',
        textTransform: 'uppercase',
        color:         '#64748B',
        fontWeight:    600,
      }}>
        Sentiment · last 7 days
      </div>
      {data.map(m => (
        <SentimentRow key={`${m.platform}-${m.identifier}`} m={m} />
      ))}
    </section>
  )
}

function SentimentRow({ m }: { m: MonitorSentiment }) {
  const total = m.positive_count + m.negative_count + m.neutral_count
  const pos = total > 0 ? (m.positive_count / total) * 100 : 0
  const neu = total > 0 ? (m.neutral_count  / total) * 100 : 0
  const neg = total > 0 ? (m.negative_count / total) * 100 : 0
  const platformColor = PLATFORM_COLOR[m.platform]

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr 96px', alignItems: 'center', gap: '12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: platformColor }} />
        <span style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: '13px', color: '#0F172A', fontWeight: 500 }}>
          {m.display_name || m.identifier}
        </span>
      </div>
      <div style={{
        display:         'flex',
        height:          '8px',
        borderRadius:    '4px',
        overflow:        'hidden',
        backgroundColor: '#F1F5F9',
      }}>
        <span style={{ width: `${pos}%`, backgroundColor: '#10B981' }} />
        <span style={{ width: `${neu}%`, backgroundColor: '#E2E8F0' }} />
        <span style={{ width: `${neg}%`, backgroundColor: '#F43F5E' }} />
      </div>
      <div style={{
        fontFamily:  "'DM Mono', ui-monospace, monospace",
        fontSize:    '11px',
        color:       '#64748B',
        textAlign:   'right',
      }}>
        {total} posts
      </div>
    </div>
  )
}

/* ── Post card ───────────────────────────────────────────────────────── */

function PostCard({ post }: { post: SignalPost }) {
  const s = sentimentLabel(post.sentiment_score)
  const border = PLATFORM_COLOR[post.platform]
  const viral = post.forward_count > 10

  return (
    <article style={{
      backgroundColor:  '#FFFFFF',
      borderRadius:     '6px',
      border:           '1px solid #E2E8F0',
      borderLeft:       `4px solid ${border}`,
      padding:          '16px 18px',
      display:          'flex',
      flexDirection:    'column',
      gap:              '10px',
    }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
        <span style={{
          fontFamily:   "'DM Sans', system-ui, sans-serif",
          fontSize:     '11px',
          fontWeight:   600,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          color:        border,
        }}>
          {PLATFORM_LABEL[post.platform]}
        </span>
        {post.author_username && (
          <span style={{ fontFamily: "'DM Mono', ui-monospace, monospace", fontSize: '12px', color: '#0F172A' }}>
            @{post.author_username}
          </span>
        )}
        {post.monitor_name && (
          <span style={{ fontFamily: "'DM Sans', system-ui, sans-serif", fontSize: '12px', color: '#94A3B8' }}>
            · {post.monitor_name}
          </span>
        )}
        <span style={{ fontFamily: "'DM Mono', ui-monospace, monospace", fontSize: '11px', color: '#94A3B8', marginLeft: 'auto' }}>
          {relativeTime(post.posted_at || post.collected_at)}
        </span>
      </header>

      <p style={{
        margin:      0,
        fontFamily:  "'DM Sans', system-ui, sans-serif",
        fontSize:    '14px',
        lineHeight:  1.6,
        color:       '#18181B',
        whiteSpace:  'pre-wrap',
      }}>
        {post.post_text}
      </p>

      {post.has_document && (
        <div style={{
          fontFamily:  "'DM Sans', system-ui, sans-serif",
          fontSize:    '11px',
          color:       '#F43F5E',
          fontWeight:  600,
          letterSpacing: '0.04em',
        }}>
          📄 DOCUMENT ATTACHED — forwarded to Document Room for processing
        </div>
      )}
      {post.forwarded_from && (
        <div style={{
          fontFamily:  "'DM Mono', ui-monospace, monospace",
          fontSize:    '11px',
          color:       '#94A3B8',
        }}>
          ↗ FORWARDED FROM {post.forwarded_from}
        </div>
      )}
      {viral && (
        <div style={{
          fontFamily:    "'DM Sans', system-ui, sans-serif",
          fontSize:      '11px',
          fontWeight:    600,
          color:         '#F43F5E',
          letterSpacing: '0.04em',
        }}>
          🔥 {post.forward_count} forwards — VIRAL
        </div>
      )}

      {post.matched_entities.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          {post.matched_entities.map(e => (
            <span key={e} style={{
              fontFamily:      "'DM Sans', system-ui, sans-serif",
              fontSize:        '11px',
              padding:         '2px 8px',
              borderRadius:    '6px',
              backgroundColor: '#FFF1F2',
              color:           '#9F1239',
              border:          '1px solid #FECDD3',
            }}>
              {e}
            </span>
          ))}
        </div>
      )}

      <footer style={{
        display:       'flex',
        alignItems:    'center',
        gap:           '18px',
        fontFamily:    "'DM Mono', ui-monospace, monospace",
        fontSize:      '12px',
        color:         '#64748B',
      }}>
        <span>▲ {post.upvotes.toLocaleString()}</span>
        <span>💬 {post.comment_count.toLocaleString()}</span>
        {post.share_count > 0 && <span>🔁 {post.share_count.toLocaleString()}</span>}
        <span style={{ display: 'flex', alignItems: 'center', gap: '6px', marginLeft: 'auto' }}>
          <span style={{ fontFamily: "'DM Sans', system-ui, sans-serif", color: s.color, fontWeight: 600, letterSpacing: '0.06em' }}>
            {s.label}
          </span>
          {post.sentiment_score !== null && (
            <span style={{ color: '#94A3B8' }}>
              ({post.sentiment_score.toFixed(2)})
            </span>
          )}
        </span>
      </footer>

      <div style={{ display: 'flex', gap: '8px' }}>
        {post.post_url && (
          <a
            href={post.post_url}
            target="_blank"
            rel="noopener noreferrer"
            style={linkBtnStyle}
          >
            Open Original ↗
          </a>
        )}
      </div>
    </article>
  )
}

/* ── Misc UI pieces ──────────────────────────────────────────────────── */

function EmptyState({ platform }: { platform: Platform }) {
  const label = platform === 'all' ? 'any platform' : PLATFORM_LABEL[platform as Exclude<Platform, 'all'>]
  return (
    <div style={{
      backgroundColor: '#FFFFFF',
      border:          '1px dashed #CBD5E1',
      borderRadius:    '6px',
      padding:         '40px 20px',
      textAlign:       'center',
      fontFamily:      "'DM Sans', system-ui, sans-serif",
      color:           '#64748B',
    }}>
      <div style={{ fontSize: '14px', fontWeight: 600, color: '#0F172A' }}>No signals yet</div>
      <div style={{ fontSize: '13px', marginTop: '6px' }}>
        Waiting for the next collection cycle from {label}.
      </div>
    </div>
  )
}

function LoadingRow() {
  return (
    <div style={{
      padding:         '18px',
      fontFamily:      "'DM Mono', ui-monospace, monospace",
      fontSize:        '12px',
      color:           '#94A3B8',
      textAlign:       'center',
    }}>
      loading…
    </div>
  )
}

const loadMoreBtnStyle: React.CSSProperties = {
  alignSelf:       'center',
  padding:         '8px 16px',
  backgroundColor: '#FFFFFF',
  border:          '1px solid #CBD5E1',
  borderRadius:    '6px',
  fontFamily:      "'DM Sans', system-ui, sans-serif",
  fontSize:        '13px',
  color:           '#0F172A',
  cursor:          'pointer',
}

const linkBtnStyle: React.CSSProperties = {
  fontFamily:    "'DM Sans', system-ui, sans-serif",
  fontSize:      '12px',
  color:         '#0F172A',
  textDecoration: 'none',
  padding:       '6px 12px',
  borderRadius:  '6px',
  border:        '1px solid #E2E8F0',
  backgroundColor: '#F8FAFC',
}

const errorBoxStyle: React.CSSProperties = {
  padding:         '14px 18px',
  backgroundColor: '#FFF1F2',
  border:          '1px solid #FECDD3',
  borderRadius:    '6px',
  fontFamily:      "'DM Sans', system-ui, sans-serif",
  fontSize:        '13px',
  color:           '#9F1239',
}
