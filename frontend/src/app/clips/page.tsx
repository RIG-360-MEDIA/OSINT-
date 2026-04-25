'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import Navigation from '@/components/Navigation'
import { Dateline } from '@/components/Dateline'
import { formatTimeAgo } from '@/lib/domainColor'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

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

function formatTimestamp(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

/* ── Clip card ─────────────────────────────────────────────────── */

interface ClipCardProps {
  clip: Clip
  index: number
  onInvestigate: (q: string) => void
}

function ClipCard({ clip, index, onInvestigate }: ClipCardProps) {
  const [playing, setPlaying] = useState(false)
  const [langMode, setLangMode] = useState<'en' | 'orig'>('en')
  const thumbnailSrc = `https://img.youtube.com/vi/${clip.video_id}/mqdefault.jpg`

  const displayText =
    langMode === 'en' && clip.transcript_translated
      ? clip.transcript_translated
      : clip.transcript_segment

  const handleInvestigate = () => {
    const q = `What did ${clip.matched_entity} say about this topic? Context: ${clip.transcript_segment.slice(0, 120)}`
    onInvestigate(q)
  }

  return (
    <article
      style={{
        display: 'grid',
        gridTemplateColumns: '56px 1fr',
        gap: '20px',
        paddingTop: '32px',
        paddingBottom: '32px',
        borderBottom: '1px solid var(--rig-rule-hair)',
      }}
    >
      {/* Numeral */}
      <div
        style={{
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontWeight: 400,
          fontSize: '34px',
          color: 'var(--rig-ink-3)',
          lineHeight: 1,
          paddingTop: '6px',
        }}
      >
        {String(index).padStart(2, '0')}
      </div>

      {/* Body */}
      <div>
        {/* Byline row */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
            marginBottom: '8px',
          }}
          className="rig-byline"
        >
          <span>{clip.channel_name}</span>
          <span style={{ opacity: 0.7 }}>
            {formatTimeAgo(clip.collected_at)}
          </span>
        </div>

        {/* Headline */}
        <h2
          className="rig-headline"
          style={{
            fontSize: '22px',
            margin: 0,
            marginBottom: '16px',
            color: 'var(--rig-ink)',
            lineHeight: 1.25,
          }}
        >
          {clip.video_title}
        </h2>

        {/* Player / Thumbnail */}
        <div
          style={{
            position: 'relative',
            width: '100%',
            aspectRatio: '16/9',
            background: '#000',
            border: '1px solid var(--rig-rule)',
            overflow: 'hidden',
            marginBottom: '16px',
          }}
        >
          {playing ? (
            <iframe
              src={clip.embed_url + '&autoplay=1'}
              title={clip.video_title}
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
                alt={clip.video_title}
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
                    fontSize: '42px',
                    color: 'var(--rig-paper)',
                    textShadow: '0 2px 12px rgba(0,0,0,0.6)',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '10px',
                  }}
                >
                  ▷ <span style={{ fontSize: '14px', fontStyle: 'normal', fontFamily: 'var(--font-mono)', letterSpacing: '0.26em', textTransform: 'uppercase' }}>Roll tape</span>
                </span>
              </div>
              <div
                style={{
                  position: 'absolute',
                  bottom: '10px',
                  right: '12px',
                  background: 'rgba(0,0,0,0.82)',
                  padding: '3px 8px',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '11px',
                  color: 'var(--rig-paper)',
                  letterSpacing: '0.04em',
                }}
              >
                {formatTimestamp(clip.clip_start_seconds)} – {formatTimestamp(clip.clip_end_seconds)}
              </div>
            </button>
          )}
        </div>

        {/* Entity overlay */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            marginBottom: '14px',
            flexWrap: 'wrap',
          }}
        >
          <span
            style={{
              padding: '4px 10px',
              border: '1px solid var(--rig-gold)',
              background: 'color-mix(in srgb, var(--rig-gold) 8%, transparent)',
              fontFamily: 'var(--font-mono)',
              fontSize: '10px',
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              color: 'var(--rig-copper)',
            }}
          >
            {clip.matched_entity}
          </span>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '10px',
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              color: 'var(--rig-ink-3)',
            }}
          >
            Heard at {formatTimestamp(clip.clip_start_seconds)}
          </span>
        </div>

        {/* Language toggle */}
        {clip.transcript_translated && clip.transcript_language !== 'en' && (
          <div style={{ display: 'flex', gap: '6px', marginBottom: '10px' }}>
            {(['en', 'orig'] as const).map(mode => (
              <button
                key={mode}
                onClick={() => setLangMode(mode)}
                style={{
                  padding: '4px 10px',
                  cursor: 'pointer',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '10px',
                  letterSpacing: '0.18em',
                  textTransform: 'uppercase',
                  border: '1px solid',
                  borderColor: langMode === mode ? 'var(--rig-ink)' : 'var(--rig-rule)',
                  background: 'transparent',
                  color: langMode === mode ? 'var(--rig-ink)' : 'var(--rig-ink-3)',
                  transition: 'all 0.15s',
                }}
              >
                {mode === 'en' ? 'English' : clip.transcript_language.toUpperCase()}
              </button>
            ))}
          </div>
        )}

        {/* Transcript as pullquote */}
        <div className="rig-pullquote" style={{ margin: '4px 0 18px' }}>
          <span
            style={{
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              color: 'var(--rig-gold)',
              fontSize: '28px',
              lineHeight: 0,
              verticalAlign: '-0.1em',
              marginRight: '4px',
            }}
          >
            “
          </span>
          {displayText}
          <span
            style={{
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              color: 'var(--rig-gold)',
              fontSize: '28px',
              lineHeight: 0,
              verticalAlign: '-0.4em',
              marginLeft: '2px',
            }}
          >
            ”
          </span>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            onClick={() => setPlaying(true)}
            disabled={playing}
            className={playing ? 'rig-btn-ghost' : 'rig-btn-primary'}
            style={{ cursor: playing ? 'default' : 'pointer' }}
          >
            {playing ? 'Playing' : 'Roll the tape'}
          </button>

          <button
            onClick={handleInvestigate}
            className="rig-btn-ghost"
          >
            Take to Analyst →
          </button>

          <a
            href={`${clip.video_url}&t=${clip.clip_start_seconds}`}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '10px',
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
  const tokenRef = useRef<string>('')

  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) { router.push('/login'); return }
      tokenRef.current = session.access_token
      loadFeed()
    })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const loadFeed = async (entity = activeEntity, channel = activeChannel) => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ limit: '20' })
      if (entity) params.set('entity', entity)
      if (channel) params.set('channel', channel)

      const res = await fetch(`${API_BASE}/api/clips/feed?${params}`, {
        headers: { Authorization: `Bearer ${tokenRef.current}` },
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      const data: FeedResponse = await res.json()
      setClips(data.clips)
      setChannels(data.channels)
      setUserEntities(data.user_entities)
      setTotal(data.total)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load clips')
    } finally {
      setLoading(false)
    }
  }

  const handleEntityFilter = (entity: string) => {
    const next = entity === activeEntity ? '' : entity
    setActiveEntity(next)
    loadFeed(next, activeChannel)
  }

  const handleChannelFilter = (channelId: string) => {
    const next = channelId === activeChannel ? '' : channelId
    setActiveChannel(next)
    loadFeed(activeEntity, next)
  }

  const handleInvestigate = (question: string) => {
    router.push(`/analyst?question=${encodeURIComponent(question)}`)
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--rig-paper)' }}>
      <Navigation />

      <div style={{ paddingTop: 'var(--topbar-h)' }}>
        <Dateline
          issueNumber={total}
          extra={channels.length > 0 ? [`${channels.length} CHANNELS`] : undefined}
        />

        <main style={{ maxWidth: '860px', margin: '0 auto', padding: '48px 32px 80px' }}>
          {/* Section head */}
          <header style={{ marginBottom: '36px' }}>
            <div className="rig-kicker" style={{ marginBottom: '10px' }}>
              The Clip Room
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

          {/* Entity filters */}
          {userEntities.length > 0 && (
            <div style={{ marginBottom: '14px' }}>
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

          {/* Channel filters */}
          {channels.length > 0 && (
            <div style={{ marginBottom: '28px', paddingBottom: '18px', borderBottom: '1px solid var(--rig-rule)' }}>
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

          {/* States */}
          {loading && <LoadingState />}

          {!loading && error && (
            <DeskMemo
              kicker="Desk memo"
              headline="The feed is refusing to return."
              body={error}
            />
          )}

          {!loading && !error && clips.length === 0 && (
            <DeskMemo
              kicker="Desk memo"
              headline="No clips on the wire yet."
              body="Footage appears when your monitored entities are mentioned on watched channels. The next sweep runs automatically."
            />
          )}

          {!loading && !error && clips.length > 0 && (
            <div>
              {clips.map((clip, i) => (
                <ClipCard
                  key={clip.clip_id}
                  clip={clip}
                  index={i + 1}
                  onInvestigate={handleInvestigate}
                />
              ))}
            </div>
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
