'use client'

import { useEffect, useState } from 'react'

import { useAuthedFetch } from './useNewsroomApi'
import type { NewsroomDossierResponse } from '@/types/newsroom'

interface WatchedEntity { id: string; name: string; type: string }

export function DossierMode() {
  const { ready, fetcher } = useAuthedFetch()
  const [watched, setWatched] = useState<WatchedEntity[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [days, setDays] = useState(7)
  const [data, setData] = useState<NewsroomDossierResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!ready) return
    fetcher<{ entities: WatchedEntity[] }>('/api/newsroom/me/entities').then((r) => {
      setWatched(r.entities ?? [])
      if ((r.entities ?? []).length > 0) setSelected(r.entities[0].id)
    }).catch(() => setWatched([]))
  }, [ready, fetcher])

  useEffect(() => {
    if (!ready || !selected) return
    fetcher<NewsroomDossierResponse>(`/api/newsroom/dossier?entity_id=${selected}&days=${days}`)
      .then(setData).catch((e) => setError(e.message))
  }, [ready, selected, days, fetcher])

  const selectedEntity = watched.find((w) => w.id === selected)

  return (
    <div style={{ padding: '4px 0 24px' }}>
      {/* Controls */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
        padding: '10px 16px', marginBottom: 24,
        background: 'var(--onyx-bg-2)',
        border: '1px solid rgba(168,173,184,0.10)',
      }}>
        <span style={{
          font: '500 10px/1 var(--onyx-mono)',
          color: 'var(--onyx-bone-2)',
          letterSpacing: '0.2em',
          textTransform: 'uppercase',
        }}>dossier · entity overview</span>
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
            <option key={w.id} value={w.id}>{w.name}</option>
          ))}
        </select>
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
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
          <option value={1}>1 day</option>
          <option value={7}>7 days</option>
          <option value={14}>14 days</option>
          <option value={30}>30 days</option>
        </select>
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
          <br/><span style={{ color: 'var(--onyx-bone-2)' }}>then this view shows mention deltas, sentiment trend, and top quotes for each</span>
        </p>
      ) : !data ? (
        <p style={{
          padding: '60px 24px', textAlign: 'center',
          font: '400 12px/1.5 var(--onyx-mono)',
          color: 'var(--onyx-dim)',
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
        }}>· loading dossier ·</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
          {/* Vital stats row */}
          <section style={{
            display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16,
          }}>
            <Stat label={`mentions / ${days}d`} value={data.this_period.toString()} />
            <Stat
              label="vs prior period"
              value={data.delta_pct == null ? '—' : `${data.delta_pct > 0 ? '+' : ''}${data.delta_pct.toFixed(1)}%`}
              accent={data.delta_pct != null && data.delta_pct > 20 ? 'red' : 'bone'}
            />
            <Stat
              label="avg sentiment"
              value={data.sentiment_avg != null ? data.sentiment_avg.toFixed(2) : '—'}
              accent={data.sentiment_avg != null && data.sentiment_avg < -0.2 ? 'red' : 'bone'}
            />
            <Stat label="entity" value={selectedEntity?.name ?? '—'} />
          </section>

          {/* Top channels */}
          <section>
            <h3 style={{
              font: '500 11px/1 var(--onyx-mono)',
              color: 'var(--onyx-bone-2)',
              letterSpacing: '0.22em',
              textTransform: 'uppercase',
              margin: '0 0 12px',
            }}>top channels carrying</h3>
            <ol style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {data.top_channels.map((c, i) => (
                <li key={c.channel_name} style={{
                  display: 'grid',
                  gridTemplateColumns: '24px 1fr 80px',
                  gap: 12, padding: '10px 16px',
                  borderBottom: '1px solid rgba(168,173,184,0.06)',
                  font: '400 13px/1 var(--onyx-display)',
                  color: 'var(--onyx-bone)',
                }}>
                  <span style={{ color: 'var(--onyx-dim)' }}>{i + 1}</span>
                  <span>{c.channel_name}</span>
                  <span style={{ textAlign: 'right', color: 'var(--onyx-bone-2)' }}>{c.n}</span>
                </li>
              ))}
            </ol>
          </section>

          {/* Top quotes */}
          <section>
            <h3 style={{
              font: '500 11px/1 var(--onyx-mono)',
              color: 'var(--onyx-bone-2)',
              letterSpacing: '0.22em',
              textTransform: 'uppercase',
              margin: '0 0 12px',
            }}>top quotes</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {data.top_quotes.length === 0 && (
                <p style={{ color: 'var(--onyx-dim)', font: '400 11px var(--onyx-mono)' }}>
                  no direct quotes in this window
                </p>
              )}
              {data.top_quotes.map((q) => (
                <article key={q.segment_id} style={{
                  background: 'var(--onyx-bg-2)',
                  border: '1px solid rgba(168,173,184,0.10)',
                  padding: '14px 18px',
                }}>
                  <p style={{
                    margin: 0,
                    font: '400 14px/1.5 var(--onyx-italic)',
                    fontStyle: 'italic',
                    color: 'var(--onyx-bone)',
                  }}>“{q.text_en ?? q.text_native}”</p>
                  <footer style={{
                    marginTop: 8,
                    font: '400 10px/1 var(--onyx-mono)',
                    color: 'var(--onyx-dim)',
                    letterSpacing: '0.16em',
                    textTransform: 'uppercase',
                  }}>{q.channel_name} · {new Date(q.created_at).toLocaleString('en-IN')} · {q.framing}</footer>
                </article>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: 'red' | 'bone' }) {
  const color = accent === 'red' ? 'var(--onyx-red)' : 'var(--onyx-bone)'
  return (
    <div className="onyx-hud-corners" style={{
      position: 'relative',
      background: 'var(--onyx-bg-2)',
      border: '1px solid rgba(168,173,184,0.10)',
      padding: '20px 18px',
    }}>
      <p style={{
        margin: 0,
        font: '400 9px/1 var(--onyx-mono)',
        color: 'var(--onyx-dim)',
        letterSpacing: '0.22em',
        textTransform: 'uppercase',
      }}>{label}</p>
      <p style={{
        margin: '8px 0 0',
        font: '500 26px/1 var(--onyx-display)',
        color,
        letterSpacing: '0.02em',
      }}>{value}</p>
    </div>
  )
}
