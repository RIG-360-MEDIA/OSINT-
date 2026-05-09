'use client'

import { useEffect, useState } from 'react'

import { QuoteCard } from './QuoteCard'
import { useAuthedFetch } from './useNewsroomApi'
import type { NewsroomEchoResponse } from '@/types/newsroom'

interface WatchedEntity { id: string; name: string; type: string }

export function EchoMode() {
  const { ready, fetcher } = useAuthedFetch()
  const [watched, setWatched] = useState<WatchedEntity[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [hours, setHours] = useState(24)
  const [data, setData] = useState<NewsroomEchoResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Pull the user's watched entities from the existing /me/entities endpoint
  useEffect(() => {
    if (!ready) return
    fetcher<{ entities: WatchedEntity[] }>('/api/me/entities').then((r) => {
      setWatched(r.entities ?? [])
      if ((r.entities ?? []).length > 0) setSelected(r.entities[0].id)
    }).catch(() => setWatched([]))
  }, [ready, fetcher])

  // Refetch echo when entity / hours change
  useEffect(() => {
    if (!ready || !selected) return
    fetcher<NewsroomEchoResponse>(`/api/newsroom/echo?entity_id=${selected}&hours=${hours}`)
      .then(setData).catch((e) => setError(e.message))
  }, [ready, selected, hours, fetcher])

  return (
    <div style={{ padding: '4px 0 24px' }}>
      {/* Controls */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
        padding: '10px 16px', marginBottom: 16,
        background: 'var(--onyx-bg-2)',
        border: '1px solid rgba(168,173,184,0.10)',
      }}>
        <span style={{
          font: '500 10px/1 var(--onyx-mono)',
          color: 'var(--onyx-bone-2)',
          letterSpacing: '0.2em',
          textTransform: 'uppercase',
        }}>echo · what they're saying about</span>
        <select
          value={selected ?? ''}
          onChange={(e) => setSelected(e.target.value)}
          style={{
            background: 'var(--onyx-bg)',
            color: 'var(--onyx-bone)',
            border: '1px solid var(--onyx-red)',
            padding: '6px 12px',
            font: '500 11px/1 var(--onyx-display)',
            letterSpacing: '0.04em',
          }}
        >
          {watched.length === 0 && <option value="">(no watched entities)</option>}
          {watched.map((w) => (
            <option key={w.id} value={w.id}>{w.name} ({w.type})</option>
          ))}
        </select>
        <select
          value={hours}
          onChange={(e) => setHours(Number(e.target.value))}
          style={{
            background: 'var(--onyx-bg)',
            color: 'var(--onyx-bone)',
            border: '1px solid rgba(168,173,184,0.32)',
            padding: '6px 12px',
            font: '500 10px/1 var(--onyx-mono)',
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
          }}
        >
          <option value={4}>last 4h</option>
          <option value={24}>last 24h</option>
          <option value={72}>last 72h</option>
          <option value={168}>last week</option>
        </select>
        {data && (
          <span style={{ flex: 1, textAlign: 'right',
            font: '500 10px/1 var(--onyx-mono)',
            color: 'var(--onyx-bone-2)',
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
          }}>
            {data.total_mentions} mentions · {data.cross_channel_count} channels
          </span>
        )}
      </div>

      {error && <p style={{ color: 'var(--onyx-red)', font: '400 12px var(--onyx-mono)' }}>{error}</p>}

      {watched.length === 0 ? (
        <p style={{
          padding: '60px 24px', textAlign: 'center',
          font: '400 12px/1.7 var(--onyx-mono)',
          color: 'var(--onyx-dim)',
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
        }}>
          no watched entities · add some at /onboarding
          <br/><span style={{ color: 'var(--onyx-bone-2)' }}>then this view shows everything they say about each one</span>
        </p>
      ) : !selected ? null : !data ? (
        <p style={{
          padding: '60px 24px', textAlign: 'center',
          font: '400 12px/1.5 var(--onyx-mono)',
          color: 'var(--onyx-dim)',
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
        }}>· loading echo ·</p>
      ) : data.items.length === 0 ? (
        <p style={{
          padding: '60px 24px', textAlign: 'center',
          font: '400 12px/1.5 var(--onyx-mono)',
          color: 'var(--onyx-dim)',
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
        }}>nothing said about this entity in the window</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {data.items.map((it) => <QuoteCard key={it.segment_id} item={it} />)}
        </div>
      )}
    </div>
  )
}
