'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import Navigation from '@/components/Navigation'
import { Dateline } from '@/components/Dateline'
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

const PLATFORM_LABEL: Record<SignalPost['platform'], string> = {
  twitter: 'The Wire',
  reddit: 'The Forums',
  telegram: 'The Channels',
}

const PLATFORM_SUBLABEL: Record<SignalPost['platform'], string> = {
  twitter: 'Twitter / X',
  reddit: 'Reddit',
  telegram: 'Telegram',
}

const TAB_ORDER: { id: Platform; label: string }[] = [
  { id: 'all', label: 'All wires' },
  { id: 'twitter', label: 'The Wire' },
  { id: 'reddit', label: 'The Forums' },
  { id: 'telegram', label: 'The Channels' },
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

function sentimentLabel(score: number | null): { label: string; tone: 'positive' | 'negative' | 'neutral' } {
  if (score === null || score === undefined) return { label: '—', tone: 'neutral' }
  if (score > 0.1) return { label: 'Favourable', tone: 'positive' }
  if (score < -0.1) return { label: 'Hostile', tone: 'negative' }
  return { label: 'Even', tone: 'neutral' }
}

function sentimentColor(tone: 'positive' | 'negative' | 'neutral'): string {
  if (tone === 'positive') return 'var(--rig-gold)'
  if (tone === 'negative') return 'var(--rig-oxblood)'
  return 'var(--rig-ink-3)'
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

  const total = platformCounts.twitter + platformCounts.reddit + platformCounts.telegram

  return (
    <div style={{ minHeight: '100vh', background: 'var(--rig-paper)' }}>
      <Navigation />

      <div style={{ paddingTop: 'var(--topbar-h)' }}>
        <Dateline issueNumber={total} />

        <main style={{ maxWidth: '1120px', margin: '0 auto', padding: '48px 32px 80px' }}>
          {/* Section head */}
          <header style={{ marginBottom: '36px' }}>
            <div className="rig-kicker" style={{ marginBottom: '10px' }}>
              The Signal Room
            </div>
            <h1
              className="rig-headline"
              style={{
                fontSize: '34px',
                margin: 0,
                letterSpacing: '-0.01em',
                lineHeight: 1.15,
                marginBottom: '22px',
              }}
            >
              The noise of the street,{' '}
              <em style={{ fontWeight: 500, color: 'var(--rig-gold)' }}>
                filtered for signal.
              </em>
            </h1>

            <div style={{ display: 'flex', alignItems: 'center', gap: '32px', flexWrap: 'wrap' }}>
              <PlatformStat label="The Wire" count={platformCounts.twitter} />
              <PlatformStat label="The Forums" count={platformCounts.reddit} />
              <PlatformStat label="The Channels" count={platformCounts.telegram} />
            </div>
          </header>

          <Tabs tab={tab} setTab={setTab} />

          {sentiment.length > 0 && <SentimentLedger data={sentiment} />}

          <div style={{ marginTop: '32px' }}>
            {posts.length === 0 && !loading && !error && (
              <DeskMemo
                kicker="Desk memo"
                headline={
                  tab === 'all'
                    ? 'The street is quiet.'
                    : `Nothing filed from ${PLATFORM_LABEL[tab as Exclude<Platform, 'all'>]} yet.`
                }
                body="Waiting for the next collection cycle. Signals arrive as monitored accounts post."
              />
            )}

            {posts.map((p, i) => (
              <PostCard key={p.post_id} post={p} index={i + 1} />
            ))}

            {hasMore && !loading && (
              <div style={{ textAlign: 'center', marginTop: '24px' }}>
                <button
                  onClick={() => token && cursor && fetchFeed(token, tab, cursor)}
                  className="rig-btn-ghost"
                >
                  Pull more dispatches
                </button>
              </div>
            )}

            {loading && <LoadingState />}

            {error && (
              <DeskMemo
                kicker="Desk memo"
                headline="The wires went silent."
                body={error}
              />
            )}
          </div>
        </main>
      </div>
    </div>
  )
}

/* ── Subcomponents ─────────────────────────────────────────────── */

interface PlatformStatProps {
  label: string
  count: number
}

function PlatformStat({ label, count }: PlatformStatProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <span
        style={{
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontWeight: 500,
          fontSize: '28px',
          lineHeight: 1,
          color: 'var(--rig-ink)',
        }}
      >
        {count}
      </span>
      <span className="rig-kicker" style={{ opacity: 0.75 }}>{label}</span>
    </div>
  )
}

interface TabsProps {
  tab: Platform
  setTab: (t: Platform) => void
}

function Tabs({ tab, setTab }: TabsProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '2px',
        borderBottom: '1px solid var(--rig-rule)',
        marginBottom: '24px',
      }}
    >
      {TAB_ORDER.map(t => {
        const active = tab === t.id
        return (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              position: 'relative',
              border: 'none',
              background: 'transparent',
              padding: '12px 18px',
              cursor: 'pointer',
              fontFamily: 'var(--font-mono)',
              fontSize: '10px',
              letterSpacing: '0.26em',
              textTransform: 'uppercase',
              color: active ? 'var(--rig-ink)' : 'var(--rig-ink-3)',
              transition: 'color 0.15s',
            }}
          >
            {t.label}
            {active && (
              <span
                style={{
                  position: 'absolute',
                  left: '18px',
                  right: '18px',
                  bottom: '-1px',
                  height: '1px',
                  background: 'var(--rig-gold)',
                }}
              />
            )}
          </button>
        )
      })}
    </div>
  )
}

/* ── Sentiment ledger ─────────────────────────────────────────── */

function SentimentLedger({ data }: { data: MonitorSentiment[] }) {
  return (
    <section
      style={{
        padding: '22px 24px',
        background: 'var(--rig-paper-2)',
        border: '1px solid var(--rig-rule)',
        marginBottom: '12px',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          marginBottom: '16px',
          borderBottom: '1px solid var(--rig-rule-hair)',
          paddingBottom: '8px',
        }}
      >
        <span className="rig-kicker">The sentiment ledger</span>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '9px',
            letterSpacing: '0.22em',
            textTransform: 'uppercase',
            color: 'var(--rig-ink-3)',
          }}
        >
          Past seven days
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {data.map(m => (
          <SentimentRow key={`${m.platform}-${m.identifier}`} m={m} />
        ))}
      </div>
    </section>
  )
}

function SentimentRow({ m }: { m: MonitorSentiment }) {
  const total = m.positive_count + m.negative_count + m.neutral_count
  const pos = total > 0 ? (m.positive_count / total) * 100 : 0
  const neu = total > 0 ? (m.neutral_count / total) * 100 : 0
  const neg = total > 0 ? (m.negative_count / total) * 100 : 0

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '240px 1fr 110px',
        alignItems: 'center',
        gap: '16px',
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0 }}>
        <span
          style={{
            fontFamily: 'var(--font-serif)',
            fontWeight: 500,
            fontSize: '14px',
            color: 'var(--rig-ink)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {m.display_name || m.identifier}
        </span>
        <span className="rig-byline" style={{ fontSize: '9px' }}>
          {PLATFORM_SUBLABEL[m.platform]}
        </span>
      </div>
      <div
        style={{
          display: 'flex',
          height: '4px',
          overflow: 'hidden',
          background: 'var(--rig-paper)',
          border: '1px solid var(--rig-rule-hair)',
        }}
      >
        <span style={{ width: `${pos}%`, background: 'var(--rig-gold)' }} />
        <span style={{ width: `${neu}%`, background: 'var(--rig-ink-3)', opacity: 0.35 }} />
        <span style={{ width: `${neg}%`, background: 'var(--rig-oxblood)' }} />
      </div>
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '10px',
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
          color: 'var(--rig-ink-3)',
          textAlign: 'right',
        }}
      >
        {total} posts
      </div>
    </div>
  )
}

/* ── Post card ─────────────────────────────────────────────────── */

interface PostCardProps {
  post: SignalPost
  index: number
}

function PostCard({ post, index }: PostCardProps) {
  const s = sentimentLabel(post.sentiment_score)
  const viral = post.forward_count > 10

  return (
    <article
      style={{
        display: 'grid',
        gridTemplateColumns: '56px 1fr',
        gap: '20px',
        paddingTop: '28px',
        paddingBottom: '28px',
        borderBottom: '1px solid var(--rig-rule-hair)',
        borderLeft: viral ? '2px solid var(--rig-oxblood)' : '2px solid transparent',
        paddingLeft: '14px',
        marginLeft: '-14px',
      }}
    >
      {/* Numeral */}
      <div
        style={{
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontWeight: 400,
          fontSize: '28px',
          color: 'var(--rig-ink-3)',
          lineHeight: 1,
          paddingTop: '4px',
        }}
      >
        {String(index).padStart(2, '0')}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {/* Byline */}
        <header
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            flexWrap: 'wrap',
          }}
          className="rig-byline"
        >
          <span style={{ color: 'var(--rig-copper)' }}>
            {PLATFORM_LABEL[post.platform]}
          </span>
          {post.author_username && (
            <>
              <span aria-hidden="true" style={{ opacity: 0.4 }}>·</span>
              <span style={{ textTransform: 'none', letterSpacing: 'normal', fontSize: '11px' }}>
                @{post.author_username}
              </span>
            </>
          )}
          {post.monitor_name && (
            <>
              <span aria-hidden="true" style={{ opacity: 0.4 }}>·</span>
              <span>{post.monitor_name}</span>
            </>
          )}
          <span style={{ marginLeft: 'auto', opacity: 0.7 }}>
            {relativeTime(post.posted_at || post.collected_at)}
          </span>
        </header>

        {/* Post body as serif body */}
        <p
          style={{
            margin: 0,
            fontFamily: 'var(--font-serif)',
            fontSize: '16px',
            lineHeight: 1.55,
            color: 'var(--rig-ink)',
            whiteSpace: 'pre-wrap',
          }}
        >
          {post.post_text}
        </p>

        {/* Badges */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px 18px', alignItems: 'center' }}>
          {post.has_document && (
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '10px',
                letterSpacing: '0.2em',
                textTransform: 'uppercase',
                color: 'var(--rig-oxblood)',
              }}
            >
              ◆ Document attached — routed to the Archive
            </span>
          )}
          {post.forwarded_from && (
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '10px',
                letterSpacing: '0.2em',
                textTransform: 'uppercase',
                color: 'var(--rig-ink-3)',
              }}
            >
              ↗ Forwarded from {post.forwarded_from}
            </span>
          )}
          {viral && (
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '10px',
                letterSpacing: '0.2em',
                textTransform: 'uppercase',
                color: 'var(--rig-oxblood)',
              }}
            >
              ▲ Travelling — {post.forward_count} forwards
            </span>
          )}
        </div>

        {/* Entity chips */}
        {post.matched_entities.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {post.matched_entities.map(e => (
              <span
                key={e}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '10px',
                  letterSpacing: '0.14em',
                  textTransform: 'uppercase',
                  padding: '3px 9px',
                  border: '1px solid var(--rig-rule)',
                  color: 'var(--rig-ink-2)',
                  background: 'transparent',
                }}
              >
                {e}
              </span>
            ))}
          </div>
        )}

        {/* Footer row */}
        <footer
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '18px',
            paddingTop: '8px',
            borderTop: '1px solid var(--rig-rule-hair)',
            fontFamily: 'var(--font-mono)',
            fontSize: '10px',
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            color: 'var(--rig-ink-3)',
          }}
        >
          <span>▲ {post.upvotes.toLocaleString()}</span>
          <span>✎ {post.comment_count.toLocaleString()}</span>
          {post.share_count > 0 && <span>↻ {post.share_count.toLocaleString()}</span>}

          <span
            style={{
              marginLeft: 'auto',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <span style={{ color: sentimentColor(s.tone), fontWeight: 500 }}>
              {s.label}
            </span>
            {post.sentiment_score !== null && (
              <span style={{ opacity: 0.55, letterSpacing: '0.04em', textTransform: 'none' }}>
                ({post.sentiment_score.toFixed(2)})
              </span>
            )}
          </span>

          {post.post_url && (
            <a
              href={post.post_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                color: 'var(--rig-ink-2)',
                textDecoration: 'none',
                borderBottom: '1px solid var(--rig-rule)',
                paddingBottom: '1px',
              }}
            >
              Open original ↗
            </a>
          )}
        </footer>
      </div>
    </article>
  )
}

/* ── Misc ──────────────────────────────────────────────────────── */

function LoadingState() {
  return (
    <div
      style={{
        padding: '48px 0',
        textAlign: 'center',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '12px',
      }}
    >
      <span
        className="rig-headline"
        style={{ fontStyle: 'italic', fontSize: '18px', color: 'var(--rig-ink-2)' }}
      >
        Pulling the wires…
      </span>
      <span
        style={{
          width: '140px',
          height: '1px',
          background: 'linear-gradient(90deg, transparent, var(--rig-gold), transparent)',
        }}
      />
    </div>
  )
}

interface DeskMemoProps {
  kicker: string
  headline: string
  body: string
}

function DeskMemo({ kicker, headline, body }: DeskMemoProps) {
  return (
    <div
      style={{
        padding: '56px 32px',
        textAlign: 'center',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '12px',
        border: '1px solid var(--rig-rule)',
        background: 'var(--rig-paper-2)',
      }}
    >
      <span className="rig-kicker">{kicker}</span>
      <span
        className="rig-headline"
        style={{ fontStyle: 'italic', fontSize: '22px', color: 'var(--rig-ink-2)' }}
      >
        {headline}
      </span>
      <span
        style={{
          fontFamily: 'var(--font-sans)',
          fontSize: '14px',
          color: 'var(--rig-ink-3)',
          maxWidth: '440px',
          lineHeight: 1.55,
        }}
      >
        {body}
      </span>
    </div>
  )
}
