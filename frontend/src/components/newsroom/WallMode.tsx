'use client'

import { useEffect, useState } from 'react'

import { LiveTile } from './LiveTile'
import { useAuthedFetch } from './useNewsroomApi'
import type {
  NewsroomBreakingResponse,
  NewsroomWallResponse,
  NewsroomWallTile,
} from '@/types/newsroom'

export function WallMode() {
  const { ready, fetcher } = useAuthedFetch()
  const [tiles, setTiles] = useState<NewsroomWallTile[]>([])
  const [breakingChannelIds, setBreakingChannelIds] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!ready) return
    let cancelled = false
    const load = async () => {
      try {
        const [wall, breaking] = await Promise.all([
          fetcher<NewsroomWallResponse>('/api/newsroom/wall?per_channel=5'),
          fetcher<NewsroomBreakingResponse>('/api/newsroom/breaking?hours=4'),
        ])
        if (cancelled) return
        setTiles(wall.tiles)
        // A tile is "breaking" if any segment in its channel is in a
        // breaking cluster — we don't have channel id on cluster row,
        // so we approximate by flagging the top-severity-3+ clusters.
        const ids = new Set<string>()
        for (const c of breaking.clusters) {
          if (c.severity >= 3) ids.add(c.id) // placeholder: hook segment→channel later
        }
        setBreakingChannelIds(ids)
        setError(null)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'failed to load wall')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    const t = setInterval(() => { void load() }, 30_000)
    return () => { cancelled = true; clearInterval(t) }
  }, [ready, fetcher])

  if (loading) return <ModeMessage>· LOADING WALL ·</ModeMessage>
  if (error) return <ModeMessage>error: {error}</ModeMessage>
  if (tiles.length === 0) return (
    <ModeMessage>
      no channels seeded yet — add a row to <code>newsroom_channels</code>
      and ingest at least one broadcast
    </ModeMessage>
  )

  // Pad to a 3×3 grid with empty placeholder tiles for layout consistency.
  const grid = [...tiles]
  while (grid.length < 9) grid.push({
    channel_id: `placeholder-${grid.length}`,
    channel_name: 'awaiting',
    language: '—',
    beat: '—',
    segments: [],
  })

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(3, 1fr)',
      gap: 14,
      padding: '4px 0 24px',
    }}>
      {grid.slice(0, 9).map((t, i) => (
        <LiveTile
          key={t.channel_id || `slot-${i}`}
          tile={t}
          isLive={t.segments.length > 0}
          isBreaking={breakingChannelIds.has(t.channel_id)}
        />
      ))}
    </div>
  )
}

function ModeMessage({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'center', alignItems: 'center',
      padding: '60px 24px',
      font: '400 12px/1.5 var(--onyx-mono)',
      color: 'var(--onyx-dim)',
      letterSpacing: '0.18em',
      textTransform: 'uppercase',
      textAlign: 'center',
    }}>{children}</div>
  )
}
