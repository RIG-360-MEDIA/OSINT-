'use client'

import { useState } from 'react'

import { EntityChip } from './EntityChip'
import type { NewsroomWallTile } from '@/types/newsroom'

interface Props {
  tile: NewsroomWallTile
  isLive?: boolean
  isBreaking?: boolean
}

function formatRelative(iso: string | null | undefined): string {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  const ms = Date.now() - t
  if (ms < 60_000) return 'just now'
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m ago`
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}h ago`
  return `${Math.floor(ms / 86_400_000)}d ago`
}

export function LiveTile({ tile, isLive, isBreaking }: Props) {
  const [showPlayer, setShowPlayer] = useState(false)
  const isActuallyLive = !!tile.current_live_video_id
  const top3 = tile.segments.slice(0, 3)
  const showLiveStyle: boolean = isActuallyLive || !!isLive || !!isBreaking

  if (isActuallyLive) {
    const hasDigest = !!tile.digest_summary || (tile.digest_phrases && tile.digest_phrases.length > 0)
    return (
      <>
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            background: '#0A0A0C',
            border: `1px solid ${isBreaking ? '#FF2D2D' : 'rgba(255,45,45,0.55)'}`,
            overflow: 'hidden',
          }}
        >
          {/* Video block — 16:9 click-to-expand */}
          <div
            onClick={() => setShowPlayer(true)}
            style={{
              position: 'relative',
              background: '#000',
              aspectRatio: '16 / 9',
              cursor: 'pointer',
              overflow: 'hidden',
            }}
            title={tile.current_live_title ?? tile.channel_name}
          >
            <iframe
              src={`https://www.youtube.com/embed/${tile.current_live_video_id}?autoplay=1&mute=1&modestbranding=1&controls=0&playsinline=1&rel=0`}
              allow="autoplay; encrypted-media; picture-in-picture"
              style={{
                position: 'absolute', inset: 0,
                width: '100%', height: '100%',
                border: 0,
                pointerEvents: 'none',
              }}
              title={tile.channel_name}
            />
            {/* Top overlay only — channel name + LIVE pip */}
            <div style={{
              position: 'absolute', top: 0, left: 0, right: 0,
              padding: '8px 10px',
              display: 'flex', alignItems: 'center', gap: 8,
              background: 'linear-gradient(to bottom, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0) 100%)',
              pointerEvents: 'none',
              zIndex: 2,
            }}>
              <span style={{
                display: 'inline-block', width: 7, height: 7, borderRadius: '50%',
                background: '#FF2D2D',
                boxShadow: '0 0 10px 2px rgba(255,45,45,0.55)',
                animation: 'onyx-pulse-red 1.6s ease-in-out infinite',
              }} aria-label="live" />
              <span style={{
                fontFamily: '"Space Grotesk", "Inter", system-ui',
                fontSize: 12, fontWeight: 500,
                color: isBreaking ? '#FF2D2D' : '#ECEEF1',
                letterSpacing: '0.04em',
                textShadow: '0 1px 2px rgba(0,0,0,0.6)',
              }}>{tile.channel_name}</span>
              <span style={{ flex: 1 }} />
              <span style={{
                fontFamily: '"JetBrains Mono", "DM Mono", monospace',
                fontSize: 8, fontWeight: 500,
                letterSpacing: '0.22em', textTransform: 'uppercase',
                padding: '2px 6px',
                border: '1px solid #FF2D2D',
                color: '#FF2D2D',
                background: 'rgba(0,0,0,0.6)',
              }}>LIVE</span>
            </div>
          </div>

          {/* Digest block — connected directly below the video */}
          <div style={{
            padding: '10px 12px 12px',
            display: 'flex', flexDirection: 'column', gap: 6,
            borderTop: '1px solid rgba(255,45,45,0.18)',
            background: '#0A0A0C',
          }}>
            {hasDigest ? (
              <>
                {tile.digest_summary && (
                  <p style={{
                    margin: 0,
                    fontFamily: '"Inter", system-ui',
                    fontSize: 12.5, fontWeight: 500,
                    color: '#ECEEF1',
                    lineHeight: 1.4,
                  }}>{tile.digest_summary}</p>
                )}
                {tile.digest_phrases && tile.digest_phrases.length > 0 && (
                  <ul style={{
                    listStyle: 'none', margin: 0, padding: 0,
                    display: 'flex', flexWrap: 'wrap', gap: 4,
                  }}>
                    {tile.digest_phrases.slice(0, 5).map((p, i) => (
                      <li
                        key={i}
                        style={{
                          fontFamily: '"JetBrains Mono", "DM Mono", monospace',
                          fontSize: 9.5, fontWeight: 400,
                          letterSpacing: '0.03em',
                          color: '#A8ADB8',
                          border: '1px solid rgba(168,173,184,0.22)',
                          background: 'rgba(255,255,255,0.02)',
                          padding: '2px 7px',
                          maxWidth: '100%',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >· {p}</li>
                    ))}
                  </ul>
                )}
              </>
            ) : (
              <span style={{
                fontFamily: '"JetBrains Mono", "DM Mono", monospace',
                fontSize: 10, fontWeight: 400,
                letterSpacing: '0.18em', textTransform: 'uppercase',
                color: '#5A6070',
              }}>· indexing live ·</span>
            )}
          </div>
        </div>

        {/* Lightbox: full-size player on tile click */}
        {showPlayer && tile.current_live_video_id && (
          <div
            onClick={() => setShowPlayer(false)}
            style={{
              position: 'fixed', inset: 0,
              background: 'rgba(0, 0, 0, 0.92)',
              backdropFilter: 'blur(8px)',
              zIndex: 200,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              padding: '40px',
            }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                width: 'min(1280px, 92vw)',
                aspectRatio: '16 / 9',
                background: '#000',
                border: '1px solid rgba(255,45,45,0.32)',
                position: 'relative',
              }}
            >
              <button
                onClick={() => setShowPlayer(false)}
                style={{
                  position: 'absolute', top: -34, right: 0,
                  background: 'transparent',
                  border: '1px solid rgba(168,173,184,0.32)',
                  color: '#ECEEF1',
                  padding: '6px 14px',
                  fontFamily: '"JetBrains Mono", monospace',
                  fontSize: 10, letterSpacing: '0.22em', textTransform: 'uppercase',
                  cursor: 'pointer',
                }}
              >close</button>
              <iframe
                src={`https://www.youtube.com/embed/${tile.current_live_video_id}?autoplay=1&modestbranding=1`}
                title={tile.current_live_title ?? tile.channel_name}
                allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
                allowFullScreen
                style={{ width: '100%', height: '100%', border: 0 }}
              />
              <div style={{
                position: 'absolute', bottom: -32, left: 0,
                fontFamily: '"JetBrains Mono", monospace',
                fontSize: 10, color: '#A8ADB8', letterSpacing: '0.18em',
                textTransform: 'uppercase',
              }}>{tile.channel_name}{tile.current_live_title ? ` · ${tile.current_live_title}` : ''}</div>
            </div>
          </div>
        )}
      </>
    )
  }

  /* ── Non-live tile (channel known but currently off-air) ───────────── */
  return (
    <div
      style={{
        position: 'relative',
        background: '#050507',
        border: '1px solid rgba(168,173,184,0.10)',
        aspectRatio: '16 / 9',
        padding: '14px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        overflow: 'hidden',
      }}
    >
      <Corner pos="tl" red={showLiveStyle} />
      <Corner pos="br" red={showLiveStyle} />

      <header style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{
          fontFamily: '"Space Grotesk", "Inter", system-ui',
          fontSize: 13, fontWeight: 500,
          color: '#ECEEF1',
          letterSpacing: '0.04em',
        }}>{tile.channel_name}</span>
        <span style={{ flex: 1 }} />
        <EntityChip label={tile.language} variant="language" />
      </header>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, flex: 1, minHeight: 0 }}>
        {top3.length === 0 ? (
          <span style={{
            fontFamily: '"JetBrains Mono", "DM Mono", monospace',
            fontSize: 10, fontWeight: 300, lineHeight: 1.4,
            color: '#5A6070', letterSpacing: '0.04em',
          }}>· · ·  off-air  · · ·</span>
        ) : (
          top3.slice(0, 3).map((s) => (
            <p
              key={s.segment_id}
              style={{
                fontFamily: '"Inter", system-ui',
                fontSize: 12.5, fontStyle: 'italic',
                color: '#A8ADB8',
                margin: 0, lineHeight: 1.45,
                display: '-webkit-box',
                WebkitBoxOrient: 'vertical',
                WebkitLineClamp: 2,
                overflow: 'hidden',
              }}
              title={s.text_native ?? s.text_en ?? ''}
            >{s.text_en ?? s.text_native}</p>
          ))
        )}
      </div>

      <footer style={{
        display: 'flex', alignItems: 'center', gap: 10,
        fontFamily: '"JetBrains Mono", "DM Mono", monospace',
        fontSize: 9, fontWeight: 400,
        color: '#5A6070', letterSpacing: '0.18em',
        textTransform: 'uppercase',
      }}>
        <span>{tile.beat.replace(/_/g, ' ')}</span>
        <span style={{ flex: 1 }} />
        {tile.last_live_at ? (
          <span title={`last seen live: ${new Date(tile.last_live_at).toLocaleString('en-IN')}`}>
            last live · {formatRelative(tile.last_live_at)}
          </span>
        ) : top3.length > 0 ? (
          <span>{new Date(top3[0].created_at).toLocaleTimeString('en-IN')}</span>
        ) : (
          <span>—</span>
        )}
      </footer>
    </div>
  )
}

function Corner({ pos, red }: { pos: 'tl' | 'br'; red: boolean }) {
  const base: React.CSSProperties = {
    position: 'absolute', width: 14, height: 14,
    pointerEvents: 'none',
    borderColor: red ? '#FF2D2D' : 'rgba(168,173,184,0.55)',
  }
  if (pos === 'tl') return <span style={{ ...base, top: 6, left: 6, borderTop: '1px solid', borderLeft: '1px solid' }} />
  return <span style={{ ...base, bottom: 6, right: 6, borderBottom: '1px solid', borderRight: '1px solid' }} />
}
