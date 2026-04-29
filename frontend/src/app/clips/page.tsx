'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import Navigation from '@/components/Navigation'
import { Dateline } from '@/components/Dateline'
import { formatTimeAgo } from '@/lib/domainColor'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const FETCH_TIMEOUT_MS = 20_000

async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  ms: number = FETCH_TIMEOUT_MS,
): Promise<Response> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), ms)
  try {
    return await fetch(url, { ...init, signal: ctrl.signal })
  } finally {
    clearTimeout(timer)
  }
}

interface Clip {
  clip_id: string
  video_id: string
  video_title: string
  channel_name: string
  channel_id: string
  video_url: string
  embed_url: string
  clip_start_seconds: number
  clip_end_seconds: number
  transcript_segment: string
  transcript_translated: string | null
  matched_entity: string
  transcript_language: string
  video_published_at: string | null
  collected_at: string
  transcript_source?: string | null
  confidence?: number | null
}

interface Channel {
  channel_id: string
  channel_name: string
  clip_count: number
}

interface FeedResponse {
  clips: Clip[]
  has_more: boolean
  next_cursor: string | null
  total: number
  channels: Channel[]
  user_entities: string[]
}

interface StoryGroup {
  video_id: string
  video_title: string
  channel_name: string
  channel_id: string
  video_url: string
  video_published_at: string | null
  collected_at: string
  moments: Clip[]
  entities: string[]
}

function formatTimestamp(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

const SAFE_EMBED_RE = /^https:\/\/(www\.)?youtube\.com\/embed\//
const SAFE_WATCH_RE = /^https:\/\/(www\.)?youtube\.com\/watch/

function isSafeEmbedUrl(url: string): boolean {
  return typeof url === 'string' && SAFE_EMBED_RE.test(url)
}

function isSafeWatchUrl(url: string): boolean {
  return typeof url === 'string' && SAFE_WATCH_RE.test(url)
}

/**
 * Build the iframe-ready URL by setting `autoplay=1` cleanly.
 *
 * The collector emits embed URLs with `autoplay=0` baked in. Naively
 * appending `&autoplay=1` produces a URL with both params; YouTube uses
 * the last one so it works, but it's noisy in DevTools. URLSearchParams
 * also collapses dupes if any sneak in upstream. (clips audit P3-NEW)
 */
function withAutoplay(embedUrl: string): string {
  try {
    const u = new URL(embedUrl)
    u.searchParams.set('autoplay', '1')
    return u.toString()
  } catch {
    // Fallback: keep prior behaviour rather than break the iframe.
    return embedUrl + '&autoplay=1'
  }
}

function groupClipsByVideo(clips: Clip[]): StoryGroup[] {
  const map = new Map<string, StoryGroup>()
  for (const c of clips) {
    const g = map.get(c.video_id)
    if (g) {
      g.moments.push(c)
      if (!g.entities.includes(c.matched_entity)) g.entities.push(c.matched_entity)
    } else {
      map.set(c.video_id, {
        video_id: c.video_id,
        video_title: c.video_title,
        channel_name: c.channel_name,
        channel_id: c.channel_id,
        video_url: c.video_url,
        video_published_at: c.video_published_at,
        collected_at: c.collected_at,
        moments: [c],
        entities: [c.matched_entity],
      })
    }
  }
  for (const g of map.values()) {
    g.moments.sort((a, b) => a.clip_start_seconds - b.clip_start_seconds)
  }
  return Array.from(map.values())
}

/* ── Story card ────────────────────────────────────────────────── */

interface StoryCardProps {
  group: StoryGroup
  index: number
  onInvestigate: (q: string) => void
}

function StoryCard({ group, index, onInvestigate }: StoryCardProps) {
  const [activeMomentId, setActiveMomentId] = useState<string>(group.moments[0].clip_id)
  const [playing, setPlaying] = useState(false)
  const [showOriginal, setShowOriginal] = useState(false)
  const [expanded, setExpanded] = useState(false)

  const activeMoment =
    group.moments.find(m => m.clip_id === activeMomentId) ?? group.moments[0]
  const otherMoments = group.moments.filter(m => m.clip_id !== activeMomentId)

  const thumbnailSrc = `https://i.ytimg.com/vi/${group.video_id}/hqdefault.jpg`

  const englishText = activeMoment.transcript_translated ?? null
  const originalText = activeMoment.transcript_segment ?? ''
  const isNonEnglish =
    activeMoment.transcript_language &&
    activeMoment.transcript_language !== 'en' &&
    originalText.trim().length > 0
  const hasTranslation = !!englishText
  const primaryText = hasTranslation ? englishText! : originalText
  const showOriginalToggle = isNonEnglish && hasTranslation

  const handleInvestigate = () => {
    const context = (englishText ?? originalText).slice(0, 160)
    const q = `What did ${activeMoment.matched_entity} say in this clip? Context: ${context}`
    onInvestigate(q)
  }

  const switchMoment = (clipId: string) => {
    setActiveMomentId(clipId)
    setPlaying(false)
    setShowOriginal(false)
  }

  return (
    <article
      style={{
        display: 'flex',
        flexDirection: 'column',
        border: '1px solid var(--rig-rule)',
        background: 'var(--rig-paper)',
        boxShadow: '0 1px 0 var(--rig-rule-hair)',
        position: 'relative',
      }}
    >
      {/* Numeral badge */}
      <div
        style={{
          position: 'absolute',
          top: '10px',
          left: '12px',
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontWeight: 400,
          fontSize: '20px',
          color: 'var(--rig-paper)',
          background: 'rgba(0,0,0,0.78)',
          padding: '2px 10px',
          letterSpacing: '0.04em',
          zIndex: 2,
        }}
      >
        {String(index).padStart(2, '0')}
      </div>

      {/* Player / Thumbnail */}
      <div
        style={{
          position: 'relative',
          width: '100%',
          aspectRatio: '16/9',
          background: '#000',
          borderBottom: '1px solid var(--rig-rule)',
          overflow: 'hidden',
        }}
      >
        {playing && isSafeEmbedUrl(activeMoment.embed_url) ? (
          <iframe
            key={activeMoment.clip_id}
            src={withAutoplay(activeMoment.embed_url)}
            title={group.video_title}
            sandbox="allow-scripts allow-same-origin allow-presentation"
            allow="autoplay; encrypted-media"
            allowFullScreen
            style={{
              position: 'absolute',
              inset: 0,
              width: '100%',
              height: '100%',
              border: 'none',
            }}
          />
        ) : (
          <button
            onClick={() => setPlaying(true)}
            style={{
              position: 'absolute',
              inset: 0,
              padding: 0,
              border: 'none',
              background: 'none',
              cursor: 'pointer',
            }}
            aria-label="Play clip"
          >
            <img
              src={thumbnailSrc}
              alt={group.video_title}
              referrerPolicy="no-referrer"
              loading="lazy"
              onError={e => {
                const img = e.currentTarget as HTMLImageElement
                if (img.dataset.fallback !== '1') {
                  img.dataset.fallback = '1'
                  img.src = `https://i.ytimg.com/vi/${group.video_id}/mqdefault.jpg`
                  return
                }
                if (img.dataset.fallback === '1') {
                  img.dataset.fallback = '2'
                  img.src = `https://img.youtube.com/vi/${group.video_id}/0.jpg`
                  return
                }
                img.style.visibility = 'hidden'
              }}
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                display: 'block',
                filter: 'grayscale(0.15) contrast(1.02)',
              }}
            />
            <div
              style={{
                position: 'absolute',
                inset: 0,
                background:
                  'linear-gradient(180deg, transparent 50%, rgba(0,0,0,0.55))',
              }}
            />
            <div
              style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <span
                style={{
                  fontFamily: 'var(--font-serif)',
                  fontStyle: 'italic',
                  fontWeight: 500,
                  fontSize: '32px',
                  color: 'var(--rig-paper)',
                  textShadow: '0 2px 12px rgba(0,0,0,0.6)',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '10px',
                }}
              >
                ▷
                <span
                  style={{
                    fontSize: '11px',
                    fontStyle: 'normal',
                    fontFamily: 'var(--font-mono)',
                    letterSpacing: '0.26em',
                    textTransform: 'uppercase',
                  }}
                >
                  Roll tape
                </span>
              </span>
            </div>
            <div
              style={{
                position: 'absolute',
                bottom: '8px',
                right: '10px',
                background: 'rgba(0,0,0,0.82)',
                padding: '3px 8px',
                fontFamily: 'var(--font-mono)',
                fontSize: '10px',
                color: 'var(--rig-paper)',
                letterSpacing: '0.04em',
              }}
            >
              {formatTimestamp(activeMoment.clip_start_seconds)} –{' '}
              {formatTimestamp(activeMoment.clip_end_seconds)}
            </div>
          </button>
        )}
      </div>

      {/* Body */}
      <div style={{ padding: '18px 20px 20px', display: 'flex', flexDirection: 'column', gap: '12px', flex: 1 }}>
        {/* Byline */}
        <div
          className="rig-byline"
          style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}
        >
          <span style={{ fontWeight: 600 }}>{group.channel_name}</span>
          <span style={{ opacity: 0.7 }}>{formatTimeAgo(group.collected_at)}</span>
        </div>

        {/* Headline */}
        <h2
          className="rig-headline"
          style={{
            fontSize: '18px',
            margin: 0,
            color: 'var(--rig-ink)',
            lineHeight: 1.3,
          }}
        >
          {group.video_title}
        </h2>

        {/* Entities */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          {group.entities.map(ent => (
            <span
              key={ent}
              style={{
                padding: '3px 8px',
                border: '1px solid var(--rig-gold)',
                background: 'color-mix(in srgb, var(--rig-gold) 8%, transparent)',
                fontFamily: 'var(--font-mono)',
                fontSize: '9px',
                letterSpacing: '0.18em',
                textTransform: 'uppercase',
                color: 'var(--rig-copper)',
              }}
            >
              {ent}
            </span>
          ))}
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '9px',
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              color: 'var(--rig-ink-3)',
              alignSelf: 'center',
            }}
          >
            Heard at {formatTimestamp(activeMoment.clip_start_seconds)}
          </span>
        </div>

        {/* Primary text — English summary first */}
        <div className="rig-pullquote" style={{ margin: 0 }}>
          <span
            style={{
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              color: 'var(--rig-gold)',
              fontSize: '24px',
              lineHeight: 0,
              verticalAlign: '-0.1em',
              marginRight: '4px',
            }}
          >
            “
          </span>
          {primaryText || <em style={{ color: 'var(--rig-ink-3)' }}>No summary available.</em>}
          <span
            style={{
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              color: 'var(--rig-gold)',
              fontSize: '24px',
              lineHeight: 0,
              verticalAlign: '-0.4em',
              marginLeft: '2px',
            }}
          >
            ”
          </span>
        </div>

        {/* Original-language opt-in (only when translation differs) */}
        {showOriginalToggle && (
          <div>
            <button
              onClick={() => setShowOriginal(v => !v)}
              aria-expanded={showOriginal}
              className="rig-btn-ghost"
              style={{
                fontSize: '9px',
                padding: '4px 10px',
                letterSpacing: '0.2em',
              }}
            >
              {showOriginal
                ? `Hide ${activeMoment.transcript_language.toUpperCase()} original`
                : `Show original (${activeMoment.transcript_language.toUpperCase()})`}
            </button>
            {showOriginal && (
              <div
                style={{
                  marginTop: '8px',
                  padding: '12px 14px',
                  borderLeft: '2px solid var(--rig-rule)',
                  background: 'var(--rig-paper-2)',
                  fontFamily: 'var(--font-serif)',
                  fontSize: '14px',
                  lineHeight: 1.55,
                  color: 'var(--rig-ink-2)',
                }}
              >
                {originalText}
              </div>
            )}
          </div>
        )}

        {/* +N more moments */}
        {otherMoments.length > 0 && (
          <div style={{ borderTop: '1px solid var(--rig-rule-hair)', paddingTop: '10px' }}>
            <button
              onClick={() => setExpanded(v => !v)}
              aria-expanded={expanded}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: 0,
                fontFamily: 'var(--font-mono)',
                fontSize: '10px',
                letterSpacing: '0.22em',
                textTransform: 'uppercase',
                color: 'var(--rig-copper)',
              }}
            >
              {expanded
                ? '— Hide other moments'
                : `+${otherMoments.length} more moment${otherMoments.length === 1 ? '' : 's'} in this video`}
            </button>
            {expanded && (
              <ul
                style={{
                  listStyle: 'none',
                  padding: 0,
                  margin: '10px 0 0',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                }}
              >
                {otherMoments.map(m => (
                  <li
                    key={m.clip_id}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '70px 1fr',
                      gap: '10px',
                      padding: '8px 10px',
                      background: 'var(--rig-paper-2)',
                      border: '1px solid var(--rig-rule-hair)',
                      cursor: 'pointer',
                    }}
                    onClick={() => switchMoment(m.clip_id)}
                  >
                    <span
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: '10px',
                        letterSpacing: '0.06em',
                        color: 'var(--rig-copper)',
                        alignSelf: 'start',
                        paddingTop: '2px',
                      }}
                    >
                      {formatTimestamp(m.clip_start_seconds)}
                    </span>
                    <div style={{ minWidth: 0 }}>
                      <div
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: '8px',
                          letterSpacing: '0.18em',
                          textTransform: 'uppercase',
                          color: 'var(--rig-ink-3)',
                          marginBottom: '3px',
                        }}
                      >
                        {m.matched_entity}
                      </div>
                      <div
                        style={{
                          fontFamily: 'var(--font-serif)',
                          fontSize: '13px',
                          lineHeight: 1.4,
                          color: 'var(--rig-ink-2)',
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                        }}
                      >
                        {m.transcript_translated ?? m.transcript_segment ?? '—'}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Actions */}
        <div
          style={{
            display: 'flex',
            gap: '8px',
            alignItems: 'center',
            flexWrap: 'wrap',
            marginTop: 'auto',
            paddingTop: '8px',
          }}
        >
          <button
            onClick={() => setPlaying(true)}
            disabled={playing}
            className={playing ? 'rig-btn-ghost' : 'rig-btn-primary'}
            style={{ cursor: playing ? 'default' : 'pointer', fontSize: '10px' }}
          >
            {playing ? 'Playing' : 'Roll the tape'}
          </button>
          <button
            onClick={handleInvestigate}
            className="rig-btn-ghost"
            style={{ fontSize: '10px' }}
          >
            Take to Analyst →
          </button>
          <a
            href={
              isSafeWatchUrl(group.video_url)
                ? `${group.video_url}&t=${activeMoment.clip_start_seconds}`
                : '#'
            }
            target="_blank"
            rel="noopener noreferrer"
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '9px',
              letterSpacing: '0.22em',
              textTransform: 'uppercase',
              color: 'var(--rig-ink-3)',
              textDecoration: 'none',
              padding: '6px 4px',
              marginLeft: 'auto',
            }}
          >
            Full broadcast ↗
          </a>
        </div>
      </div>
    </article>
  )
}

/* ── Page ──────────────────────────────────────────────────────── */

export default function ClipsPage() {
  const router = useRouter()
  const [clips, setClips] = useState<Clip[]>([])
  const [channels, setChannels] = useState<Channel[]>([])
  const [userEntities, setUserEntities] = useState<string[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [activeEntity, setActiveEntity] = useState('')
  const [activeChannel, setActiveChannel] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [appendError, setAppendError] = useState('')
  const [hasMore, setHasMore] = useState(false)
  const tokenRef = useRef<string>('')
  const initialLoadRef = useRef(true)
  const cursorRef = useRef<string | null>(null)
  const inFlightRef = useRef(false)
  const sentinelRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) { router.push('/login'); return }
      tokenRef.current = session.access_token
      loadFeed()
    })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const loadFeed = async (
    entity = activeEntity,
    channel = activeChannel,
    mode: 'fresh' | 'append' = 'fresh',
  ) => {
    if (inFlightRef.current) return
    inFlightRef.current = true

    if (mode === 'append') {
      setLoadingMore(true)
      setAppendError('')
    } else if (initialLoadRef.current) {
      setLoading(true)
      setError('')
    } else {
      setRefreshing(true)
      setError('')
    }

    try {
      const params = new URLSearchParams({ limit: '40' })
      if (entity) params.set('entity', entity)
      if (channel) params.set('channel', channel)
      if (mode === 'append' && cursorRef.current) {
        params.set('cursor', cursorRef.current)
      }

      // One retry on the very first load — the dev backend reloads on
      // file change, and a request that lands mid-reload throws a network
      // TypeError before the server is back. A 1.5s backoff covers it.
      let res: Response
      try {
        res = await fetchWithTimeout(
          `${API_BASE}/api/clips/feed?${params}`,
          { headers: { Authorization: `Bearer ${tokenRef.current}` } },
        )
      } catch (netErr: unknown) {
        if (mode === 'fresh' && initialLoadRef.current) {
          await new Promise(r => setTimeout(r, 1500))
          res = await fetchWithTimeout(
            `${API_BASE}/api/clips/feed?${params}`,
            { headers: { Authorization: `Bearer ${tokenRef.current}` } },
          )
        } else {
          throw netErr
        }
      }

      if (res.status === 401) {
        router.push('/login')
        return
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      const data = (await res.json()) as Partial<FeedResponse>
      const incoming = Array.isArray(data.clips) ? data.clips : []

      if (mode === 'append') {
        setClips(prev => {
          const seen = new Set(prev.map(c => c.clip_id))
          const merged = [...prev]
          for (const c of incoming) {
            if (!seen.has(c.clip_id)) merged.push(c)
          }
          return merged
        })
      } else {
        setClips(incoming)
        setChannels(Array.isArray(data.channels) ? data.channels : [])
        setUserEntities(Array.isArray(data.user_entities) ? data.user_entities : [])
        setTotal(typeof data.total === 'number' ? data.total : 0)
      }

      cursorRef.current =
        typeof data.next_cursor === 'string' ? data.next_cursor : null
      setHasMore(!!data.has_more && !!data.next_cursor)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to load clips'
      if (mode === 'append') {
        setAppendError(msg)
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
      setRefreshing(false)
      setLoadingMore(false)
      initialLoadRef.current = false
      inFlightRef.current = false
    }
  }

  // IntersectionObserver — fetch the next page when the sentinel scrolls into view
  useEffect(() => {
    const el = sentinelRef.current
    if (!el || !hasMore) return
    const obs = new IntersectionObserver(entries => {
      if (entries[0]?.isIntersecting && !inFlightRef.current && hasMore) {
        loadFeed(activeEntity, activeChannel, 'append')
      }
    }, { rootMargin: '300px' })
    obs.observe(el)
    return () => obs.disconnect()
  }, [hasMore, activeEntity, activeChannel]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleEntityFilter = (entity: string) => {
    const next = entity === activeEntity ? '' : entity
    setActiveEntity(next)
    cursorRef.current = null
    setHasMore(false)
    loadFeed(next, activeChannel, 'fresh')
  }

  const handleChannelFilter = (channelId: string) => {
    const next = channelId === activeChannel ? '' : channelId
    setActiveChannel(next)
    cursorRef.current = null
    setHasMore(false)
    loadFeed(activeEntity, next, 'fresh')
  }

  const handleInvestigate = (question: string) => {
    router.push(`/analyst?question=${encodeURIComponent(question)}`)
  }

  const groups = useMemo(() => groupClipsByVideo(clips), [clips])

  return (
    <div style={{ minHeight: '100vh', background: 'var(--rig-paper)' }}>
      <Navigation />

      <div style={{ paddingTop: 'var(--topbar-h)' }}>
        <Dateline
          issueNumber={total}
          extra={[
            ...(channels.length > 0 ? [`${channels.length} CHANNELS`] : []),
            ...(groups.length > 0 ? [`${groups.length} STORIES`] : []),
          ]}
        />
        <span
          role="status"
          aria-live="polite"
          aria-atomic="true"
          style={{
            position: 'absolute',
            width: 1,
            height: 1,
            padding: 0,
            margin: -1,
            overflow: 'hidden',
            clip: 'rect(0, 0, 0, 0)',
            whiteSpace: 'nowrap',
            border: 0,
          }}
        >
          {refreshing
            ? 'Refreshing clips'
            : `${total} clip${total === 1 ? '' : 's'} on file`}
        </span>
        {refreshing && (
          <div
            role="status"
            aria-label="Refreshing clip feed"
            style={{
              height: '2px',
              background: 'linear-gradient(90deg, transparent, var(--rig-gold), transparent)',
              animation: 'rig-shimmer 1.4s linear infinite',
            }}
          />
        )}

        <main style={{ maxWidth: '1320px', margin: '0 auto', padding: '40px 28px 80px' }}>
          {/* Section head */}
          <header style={{ marginBottom: '28px' }}>
            <div className="rig-kicker" style={{ marginBottom: '10px' }}>
              TV
            </div>
            <h1
              className="rig-headline"
              style={{
                fontSize: '34px',
                margin: 0,
                letterSpacing: '-0.01em',
                lineHeight: 1.15,
              }}
            >
              Footage of the record,{' '}
              <em style={{ fontWeight: 500, color: 'var(--rig-gold)' }}>
                timestamped and quoted.
              </em>
            </h1>
          </header>

          {/* Filters bar */}
          {(userEntities.length > 0 || channels.length > 0) && (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                gap: '20px',
                marginBottom: '28px',
                paddingBottom: '20px',
                borderBottom: '1px solid var(--rig-rule)',
              }}
            >
              {userEntities.length > 0 && (
                <div>
                  <div className="rig-kicker" style={{ marginBottom: '8px', opacity: 0.7 }}>
                    Figures on watch
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                    <FilterPill
                      label="All"
                      active={activeEntity === ''}
                      onClick={() => handleEntityFilter('')}
                    />
                    {userEntities.map(entity => (
                      <FilterPill
                        key={entity}
                        label={entity}
                        active={activeEntity === entity}
                        onClick={() => handleEntityFilter(entity)}
                      />
                    ))}
                  </div>
                </div>
              )}

              {channels.length > 0 && (
                <div>
                  <div className="rig-kicker" style={{ marginBottom: '8px', opacity: 0.7 }}>
                    Channels
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                    {channels.map(ch => (
                      <FilterPill
                        key={ch.channel_id}
                        label={`${ch.channel_name} · ${ch.clip_count}`}
                        active={activeChannel === ch.channel_id}
                        onClick={() => handleChannelFilter(ch.channel_id)}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* States */}
          {loading && <LoadingState />}

          {!loading && error && (
            <DeskMemo
              kicker="Desk memo"
              headline="The feed is refusing to return."
              body={error}
            />
          )}

          {!loading && !error && groups.length === 0 && (
            <DeskMemo
              kicker="Desk memo"
              headline="No clips on the wire yet."
              body="Footage appears when your monitored entities are mentioned on watched channels. The next sweep runs automatically."
            />
          )}

          {!loading && !error && groups.length > 0 && (
            <>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(420px, 1fr))',
                  gap: '24px',
                  alignItems: 'start',
                }}
              >
                {groups.map((group, i) => (
                  <StoryCard
                    key={group.video_id}
                    group={group}
                    index={i + 1}
                    onInvestigate={handleInvestigate}
                  />
                ))}
              </div>

              {/* Infinite-scroll sentinel + status footer */}
              <div
                ref={sentinelRef}
                aria-hidden="true"
                style={{ height: '1px', marginTop: '12px' }}
              />
              <div
                role="status"
                aria-live="polite"
                style={{
                  padding: '32px 0',
                  textAlign: 'center',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '10px',
                  letterSpacing: '0.22em',
                  textTransform: 'uppercase',
                  color: appendError ? 'var(--rig-copper)' : 'var(--rig-ink-3)',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '10px',
                }}
              >
                {loadingMore && <span>Pulling more footage…</span>}
                {!loadingMore && appendError && (
                  <>
                    <span>Couldn’t load more — {appendError}</span>
                    <button
                      onClick={() =>
                        loadFeed(activeEntity, activeChannel, 'append')
                      }
                      className="rig-btn-ghost"
                      style={{ fontSize: '10px' }}
                    >
                      Retry
                    </button>
                  </>
                )}
                {!loadingMore && !appendError && (
                  <span>{hasMore ? 'Scroll for more' : '— End of the reel —'}</span>
                )}
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  )
}

/* ── Subcomponents ─────────────────────────────────────────────── */

interface FilterPillProps {
  label: string
  active: boolean
  onClick: () => void
}

function FilterPill({ label, active, onClick }: FilterPillProps) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      style={{
        padding: '5px 12px',
        cursor: 'pointer',
        fontFamily: 'var(--font-mono)',
        fontSize: '10px',
        letterSpacing: '0.2em',
        textTransform: 'uppercase',
        border: '1px solid',
        borderColor: active ? 'var(--rig-ink)' : 'var(--rig-rule)',
        background: active
          ? 'color-mix(in srgb, var(--rig-paper-2) 60%, transparent)'
          : 'transparent',
        color: active ? 'var(--rig-ink)' : 'var(--rig-ink-3)',
        transition: 'all 0.15s',
      }}
    >
      {label}
    </button>
  )
}

function LoadingState() {
  return (
    <div
      style={{
        padding: '72px 0',
        textAlign: 'center',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '14px',
      }}
    >
      <span
        className="rig-headline"
        style={{
          fontStyle: 'italic',
          fontSize: '20px',
          color: 'var(--rig-ink-2)',
        }}
      >
        Cueing up the footage…
      </span>
      <span
        style={{
          width: '160px',
          height: '1px',
          background:
            'linear-gradient(90deg, transparent, var(--rig-gold), transparent)',
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
