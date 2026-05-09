'use client'

import { EntityChip } from './EntityChip'
import type { NewsroomWallTile } from '@/types/newsroom'

interface Props {
  tile: NewsroomWallTile
  isLive?: boolean
  isBreaking?: boolean
}

/**
 * One channel tile in the WALL grid. Renders:
 *   - Channel name + LIVE pip (if live)
 *   - Top 3 latest segment captions, scrolling
 *   - HUD-corner brackets, red on live/breaking, bone otherwise
 *
 * Doesn't auto-update; the parent re-renders when SSE pushes new
 * segments to the in-memory channel store.
 */
export function LiveTile({ tile, isLive, isBreaking }: Props) {
  const top3 = tile.segments.slice(0, 3)
  const liveClass = isLive || isBreaking ? 'onyx-hud-live' : ''
  return (
    <div
      className={`onyx-hud-corners ${liveClass}`}
      style={{
        position: 'relative',
        background: 'var(--onyx-bg-2)',
        border: `1px solid ${isBreaking ? 'var(--onyx-red)' : 'rgba(168,173,184,0.10)'}`,
        aspectRatio: '16 / 9',
        padding: '14px 16px',
        display: 'flex', flexDirection: 'column', gap: 10,
        overflow: 'hidden',
      }}
    >
      {/* Header: channel + live pip */}
      <header style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {(isLive || isBreaking) && <span className="onyx-pip" aria-label="live" />}
        <span style={{
          font: '500 13px/1 var(--onyx-display)',
          color: isBreaking ? 'var(--onyx-red)' : 'var(--onyx-bone)',
          letterSpacing: '0.04em',
        }}>{tile.channel_name}</span>
        <span style={{ flex: 1 }} />
        <EntityChip label={tile.language} variant="language" />
      </header>

      {/* Caption stream */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, flex: 1 }}>
        {top3.length === 0 ? (
          <span style={{
            font: '300 11px/1.4 var(--onyx-mono)',
            color: 'var(--onyx-dim)',
            letterSpacing: '0.04em',
          }}>· · ·  awaiting first segment  · · ·</span>
        ) : top3.map((s) => (
          <p
            key={s.segment_id}
            style={{
              font: '400 12.5px/1.45 var(--onyx-italic)',
              color: 'var(--onyx-bone-2)',
              fontStyle: 'italic',
              margin: 0,
              animation: 'onyx-fade-up 0.45s ease',
              display: '-webkit-box',
              WebkitBoxOrient: 'vertical',
              WebkitLineClamp: 2,
              overflow: 'hidden',
            }}
            title={s.text_native ?? s.text_en ?? ''}
          >
            {s.text_en ?? s.text_native}
          </p>
        ))}
      </div>

      {/* Footer: beat + last seen */}
      <footer style={{
        display: 'flex', alignItems: 'center', gap: 10,
        font: '400 9px/1 var(--onyx-mono)',
        color: 'var(--onyx-dim)',
        letterSpacing: '0.18em',
        textTransform: 'uppercase',
      }}>
        <span>{tile.beat.replace(/_/g, ' ')}</span>
        <span style={{ flex: 1 }} />
        <span>{top3.length > 0 ? new Date(top3[0].created_at).toLocaleTimeString('en-IN') : '—'}</span>
      </footer>
    </div>
  )
}
