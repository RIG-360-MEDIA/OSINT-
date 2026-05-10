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

  return (
    <>
      <div
        style={{
          position: 'relative',
          background: '#050507',
          border: `1px solid ${isBreaking ? '#FF2D2D' : isActuallyLive ? 'rgba(255,45,45,0.55)' : 'rgba(168,173,184,0.10)'}`,
          aspectRatio: '16 / 9',
          padding: '14px 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
          overflow: 'hidden',
        }}
      >
        {/* HUD corner brackets */}
        <Corner pos="tl" red={showLiveStyle} />
        <Corner pos="br" red={showLiveStyle} />

        {/* Header: channel + live pip */}
        <header style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {showLiveStyle && (
            <span style={{
              display: 'inline-block', width: 7, height: 7, borderRadius: '50%',
              background: '#FF2D2D',
              boxShadow: '0 0 10px 2px rgba(255,45,45,0.55)',
              animation: 'onyx-pulse-red 1.6s ease-in-out infinite',
            }} aria-label="live" />
          )}
          <span style={{
            fontFamily: '"Space Grotesk", "Inter", system-ui',
            fontSize: 13, fontWeight: 500,
            color: isBreaking ? '#FF2D2D' : '#ECEEF1',
            letterSpacing: '0.04em',
          }}>{tile.channel_name}</span>
          <span style={{ flex: 1 }} />
          {isActuallyLive && (
            <span style={{
              fontFamily: '"JetBrains Mono", "DM Mono", monospace',
              fontSize: 9, fontWeight: 500,
              letterSpacing: '0.22em', textTransform: 'uppercase',
              padding: '3px 7px',
              border: '1px solid #FF2D2D',
              color: '#FF2D2D',
            }}>LIVE NOW</span>
          )}
          <EntityChip label={tile.language} variant="language" />
        </header>

        {/* Body: live title (if live) OR transcript captions */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, flex: 1, minHeight: 0 }}>
          {isActuallyLive && tile.current_live_title && (
            <p style={{
              margin: 0,
              fontFamily: '"Space Grotesk", "Inter", system-ui',
              fontSize: 12, fontWeight: 500,
              color: '#ECEEF1',
              lineHeight: 1.35,
              display: '-webkit-box',
              WebkitBoxOrient: 'vertical',
              WebkitLineClamp: 2,
              overflow: 'hidden',
            }} title={tile.current_live_title}>{tile.current_live_title}</p>
          )}
          {top3.length === 0 && !isActuallyLive ? (
            <span style={{
              fontFamily: '"JetBrains Mono", "DM Mono", monospace',
              fontSize: 10, fontWeight: 300, lineHeight: 1.4,
              color: '#5A6070', letterSpacing: '0.04em',
            }}>· · ·  awaiting first segment  · · ·</span>
          ) : (
            top3.slice(0, isActuallyLive ? 1 : 3).map((s) => (
              <p
                key={s.segment_id}
                style={{
                  fontFamily: '"Inter", system-ui',
                  fontSize: 12.5, fontStyle: 'italic',
                  color: '#A8ADB8',
                  margin: 0, lineHeight: 1.45,
                  animation: 'onyx-fade-up 0.45s ease',
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

        {/* Footer: beat + Watch Live button or last seen */}
        <footer style={{
          display: 'flex', alignItems: 'center', gap: 10,
          fontFamily: '"JetBrains Mono", "DM Mono", monospace',
          fontSize: 9, fontWeight: 400,
          color: '#5A6070', letterSpacing: '0.18em',
          textTransform: 'uppercase',
        }}>
          <span>{tile.beat.replace(/_/g, ' ')}</span>
          <span style={{ flex: 1 }} />
          {isActuallyLive ? (
            <button
              onClick={() => setShowPlayer(true)}
              style={{
                background: 'transparent',
                color: '#FF2D2D',
                border: '1px solid #FF2D2D',
                padding: '4px 9px',
                fontFamily: 'inherit', fontSize: 9, letterSpacing: '0.22em',
                textTransform: 'uppercase', cursor: 'pointer',
              }}
              title="Watch live in popup player"
            >▶ watch live</button>
          ) : tile.last_live_at ? (
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

      {/* Lightbox — YouTube embed for live channel */}
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

function Corner({ pos, red }: { pos: 'tl' | 'br'; red: boolean }) {
  const base: React.CSSProperties = {
    position: 'absolute', width: 14, height: 14,
    pointerEvents: 'none',
    borderColor: red ? '#FF2D2D' : 'rgba(168,173,184,0.55)',
  }
  if (pos === 'tl') return <span style={{ ...base, top: 6, left: 6, borderTop: '1px solid', borderLeft: '1px solid' }} />
  return <span style={{ ...base, bottom: 6, right: 6, borderBottom: '1px solid', borderRight: '1px solid' }} />
}
