'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
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

// ── Clip Card ────────────────────────────────────────────────────────────────

function ClipCard({ clip, onInvestigate }: { clip: Clip; onInvestigate: (q: string) => void }) {
  const [playing, setPlaying]       = useState(false)
  const [langMode, setLangMode]     = useState<'en' | 'orig'>('en')
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
    <div
      className="card-lift"
      style={{
        backgroundColor: '#FFFFFF',
        border:          '1px solid #E2E8F0',
        borderRadius:    '6px',
        padding:         '20px',
        marginBottom:    '12px',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
        <span style={{ fontFamily: "'DM Mono', monospace", fontSize: '11px', color: '#94A3B8', letterSpacing: '0.02em' }}>
          {clip.channel_name}
        </span>
        <span style={{ fontFamily: "'DM Mono', monospace", fontSize: '11px', color: '#94A3B8' }}>
          {formatTimeAgo(clip.collected_at)}
        </span>
      </div>

      {/* Video title */}
      <div style={{ fontFamily: "'DM Sans', sans-serif", fontSize: '15px', fontWeight: 600, color: '#18181B', marginBottom: '14px', lineHeight: 1.4 }}>
        {clip.video_title}
      </div>

      {/* Player / Thumbnail */}
      <div style={{ position: 'relative', width: '100%', aspectRatio: '16/9', backgroundColor: '#0F0F0F', borderRadius: '4px', overflow: 'hidden', marginBottom: '14px' }}>
        {playing ? (
          <iframe
            src={clip.embed_url + '&autoplay=1'}
            title={clip.video_title}
            allow="autoplay; encrypted-media"
            allowFullScreen
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', border: 'none' }}
          />
        ) : (
          <>
            <img
              src={thumbnailSrc}
              alt={clip.video_title}
              style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
            />
            <div style={{
              position: 'absolute', inset: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: 'rgba(0,0,0,0.25)',
            }}>
              <div style={{
                width: '52px', height: '36px', backgroundColor: '#FF0000',
                borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <span style={{ color: '#fff', fontSize: '18px', lineHeight: 1, marginLeft: '2px' }}>▶</span>
              </div>
            </div>
            {/* Timestamp chip */}
            <div style={{
              position: 'absolute', bottom: '8px', right: '8px',
              backgroundColor: 'rgba(0,0,0,0.8)',
              padding: '2px 6px', borderRadius: '3px',
              fontFamily: "'DM Mono', monospace", fontSize: '11px', color: '#fff',
            }}>
              {formatTimestamp(clip.clip_start_seconds)} – {formatTimestamp(clip.clip_end_seconds)}
            </div>
          </>
        )}
      </div>

      {/* Entity + timestamp */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
        <span style={{
          display: 'inline-block',
          padding: '2px 8px',
          borderRadius: '4px',
          border: '1px solid rgba(245,158,11,0.4)',
          backgroundColor: 'rgba(245,158,11,0.08)',
          fontFamily: "'DM Sans', sans-serif", fontSize: '11px', fontWeight: 600,
          color: '#D97706', letterSpacing: '0.02em',
        }}>
          {clip.matched_entity}
        </span>
        <span style={{ fontFamily: "'DM Mono', monospace", fontSize: '11px', color: '#94A3B8' }}>
          at {formatTimestamp(clip.clip_start_seconds)}
        </span>
      </div>

      {/* Transcript quote */}
      <div style={{ marginBottom: '12px' }}>
        {/* Language toggle */}
        {clip.transcript_translated && clip.transcript_language !== 'en' && (
          <div style={{ display: 'flex', gap: '4px', marginBottom: '8px' }}>
            {(['en', 'orig'] as const).map(mode => (
              <button
                key={mode}
                onClick={() => setLangMode(mode)}
                style={{
                  padding: '2px 8px', borderRadius: '4px', cursor: 'pointer',
                  fontFamily: "'DM Mono', monospace", fontSize: '10px', fontWeight: 500,
                  border: langMode === mode ? '1px solid #CBD5E1' : '1px solid #E2E8F0',
                  backgroundColor: langMode === mode ? '#F1F5F9' : 'transparent',
                  color: langMode === mode ? '#475569' : '#94A3B8',
                  transition: 'all 0.15s',
                }}
              >
                {mode === 'en' ? 'English' : clip.transcript_language.toUpperCase()}
              </button>
            ))}
          </div>
        )}

        <blockquote style={{
          margin: 0,
          paddingLeft: '12px',
          borderLeft: '2px solid #DDD8D0',
          fontFamily: "'DM Sans', sans-serif",
          fontSize: '14px',
          lineHeight: 1.6,
          color: '#475569',
          fontStyle: 'italic',
        }}>
          {displayText}
        </blockquote>
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
        <button
          onClick={() => setPlaying(true)}
          style={{
            padding: '6px 14px', borderRadius: '4px', cursor: 'pointer',
            fontFamily: "'DM Sans', sans-serif", fontSize: '13px', fontWeight: 500,
            border: '1px solid #E2E8F0',
            backgroundColor: playing ? '#F1F5F9' : '#18181B',
            color: playing ? '#64748B' : '#F8FAFC',
            transition: 'all 0.15s',
          }}
        >
          {playing ? '▶ Playing' : '▶ Play Clip'}
        </button>

        <button
          onClick={handleInvestigate}
          style={{
            padding: '6px 14px', borderRadius: '4px', cursor: 'pointer',
            fontFamily: "'DM Sans', sans-serif", fontSize: '13px', fontWeight: 500,
            border: '1px solid rgba(245,158,11,0.35)',
            backgroundColor: 'rgba(245,158,11,0.06)',
            color: '#D97706',
            transition: 'all 0.15s',
          }}
        >
          Investigate →
        </button>

        {playing && (
          <a
            href={`${clip.video_url}&t=${clip.clip_start_seconds}`}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              padding: '6px 14px', borderRadius: '4px',
              fontFamily: "'DM Sans', sans-serif", fontSize: '13px',
              border: '1px solid #E2E8F0', color: '#64748B',
              textDecoration: 'none', backgroundColor: 'transparent',
            }}
          >
            Full video →
          </a>
        )}
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ClipsPage() {
  const router = useRouter()
  const [clips, setClips]               = useState<Clip[]>([])
  const [channels, setChannels]         = useState<Channel[]>([])
  const [userEntities, setUserEntities] = useState<string[]>([])
  const [total, setTotal]               = useState(0)
  const [loading, setLoading]           = useState(true)
  const [error, setError]               = useState('')
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
      if (entity)  params.set('entity',  entity)
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
    <div style={{ paddingTop: '56px', minHeight: '100vh', backgroundColor: '#F8FAFC' }}>
      <div style={{ maxWidth: '820px', margin: '0 auto', padding: '32px 24px' }}>

        {/* Page header */}
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: '24px' }}>
          <div>
            <div style={{
              fontFamily: "'DM Sans', sans-serif", fontSize: '11px', fontWeight: 600,
              color: '#94A3B8', letterSpacing: '0.15em', textTransform: 'uppercase',
              marginBottom: '4px',
            }}>
              Clip Room
            </div>
            <h1 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: '22px', fontWeight: 700, color: '#18181B', margin: 0 }}>
              Video Intelligence Feed
            </h1>
          </div>
          {!loading && (
            <span style={{ fontFamily: "'DM Mono', monospace", fontSize: '12px', color: '#94A3B8' }}>
              {total.toLocaleString()} clip{total !== 1 ? 's' : ''} · {channels.length} channel{channels.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>

        {/* Entity filter pills */}
        {userEntities.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '16px' }}>
            <button
              onClick={() => handleEntityFilter('')}
              style={{
                padding: '4px 12px', borderRadius: '4px', cursor: 'pointer',
                fontFamily: "'DM Sans', sans-serif", fontSize: '12px', fontWeight: 500,
                border: activeEntity === '' ? '1px solid #DC2626' : '1px solid #E2E8F0',
                backgroundColor: activeEntity === '' ? 'rgba(220,38,38,0.06)' : '#FFFFFF',
                color: activeEntity === '' ? '#DC2626' : '#64748B',
                transition: 'all 0.15s',
              }}
            >
              All
            </button>
            {userEntities.map(entity => (
              <button
                key={entity}
                onClick={() => handleEntityFilter(entity)}
                style={{
                  padding: '4px 12px', borderRadius: '4px', cursor: 'pointer',
                  fontFamily: "'DM Sans', sans-serif", fontSize: '12px', fontWeight: 500,
                  border: activeEntity === entity ? '1px solid #DC2626' : '1px solid #E2E8F0',
                  backgroundColor: activeEntity === entity ? 'rgba(220,38,38,0.06)' : '#FFFFFF',
                  color: activeEntity === entity ? '#DC2626' : '#64748B',
                  transition: 'all 0.15s',
                }}
              >
                {entity}
              </button>
            ))}
          </div>
        )}

        {/* Channel filter pills */}
        {channels.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '24px' }}>
            {channels.map(ch => (
              <button
                key={ch.channel_id}
                onClick={() => handleChannelFilter(ch.channel_id)}
                style={{
                  padding: '3px 10px', borderRadius: '4px', cursor: 'pointer',
                  fontFamily: "'DM Mono', monospace", fontSize: '11px',
                  border: activeChannel === ch.channel_id ? '1px solid #3B82F6' : '1px solid #E2E8F0',
                  backgroundColor: activeChannel === ch.channel_id ? 'rgba(59,130,246,0.06)' : 'transparent',
                  color: activeChannel === ch.channel_id ? '#2563EB' : '#94A3B8',
                  transition: 'all 0.15s',
                }}
              >
                {ch.channel_name} ({ch.clip_count})
              </button>
            ))}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {[1, 2, 3].map(i => (
              <div key={i} className="skeleton" style={{ height: '220px', borderRadius: '6px' }} />
            ))}
          </div>
        )}

        {/* Error */}
        {!loading && error && (
          <div style={{
            padding: '16px', borderRadius: '6px',
            border: '1px solid rgba(239,68,68,0.2)', backgroundColor: 'rgba(239,68,68,0.05)',
            fontFamily: "'DM Sans', sans-serif", fontSize: '14px', color: '#DC2626',
          }}>
            {error}
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && clips.length === 0 && (
          <div style={{
            padding: '48px 24px', textAlign: 'center',
            border: '1px solid #E2E8F0', borderRadius: '6px', backgroundColor: '#FFFFFF',
          }}>
            <div style={{ fontFamily: "'DM Sans', sans-serif", fontSize: '15px', fontWeight: 600, color: '#18181B', marginBottom: '8px' }}>
              No clips yet
            </div>
            <div style={{ fontFamily: "'DM Sans', sans-serif", fontSize: '14px', color: '#64748B', lineHeight: 1.6, marginBottom: '20px', maxWidth: '420px', margin: '0 auto 20px' }}>
              Clips appear when your monitored entities are mentioned in YouTube videos.
              Add channels below to start collecting.
            </div>
            <a
              href="/analyst"
              style={{
                display: 'inline-block', padding: '8px 16px', borderRadius: '4px',
                fontFamily: "'DM Sans', sans-serif", fontSize: '13px', fontWeight: 500,
                border: '1px solid #E2E8F0', color: '#475569',
                textDecoration: 'none', backgroundColor: '#F8FAFC',
              }}
            >
              Go to Analyst →
            </a>
          </div>
        )}

        {/* Clip cards */}
        {!loading && !error && clips.length > 0 && (
          <div>
            {clips.map(clip => (
              <ClipCard key={clip.clip_id} clip={clip} onInvestigate={handleInvestigate} />
            ))}
          </div>
        )}

      </div>
    </div>
  )
}
