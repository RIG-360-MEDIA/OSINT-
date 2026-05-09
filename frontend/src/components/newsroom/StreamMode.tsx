'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import { EntityChip } from './EntityChip'
import { useAuthedFetch } from './useNewsroomApi'
import type { NewsroomStreamItem, NewsroomStreamResponse } from '@/types/newsroom'

export function StreamMode() {
  const { ready, fetcher } = useAuthedFetch()
  const [items, setItems] = useState<NewsroomStreamItem[]>([])
  const [paused, setPaused] = useState(false)
  const [filterLang, setFilterLang] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  const cursorRef = useRef<string | null>(null)

  const load = useCallback(async (reset: boolean) => {
    try {
      const params = new URLSearchParams({ limit: '50' })
      if (filterLang) params.set('lang', filterLang)
      if (!reset && cursorRef.current) params.set('cursor', cursorRef.current)
      const data = await fetcher<NewsroomStreamResponse>(`/api/newsroom/stream?${params}`)
      cursorRef.current = data.next_cursor
      setItems(reset ? data.items : (prev) => [...prev, ...data.items])
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed')
    }
  }, [fetcher, filterLang])

  useEffect(() => {
    if (!ready) return
    void load(true)
  }, [ready, load])

  // Auto-refresh top of feed every 12s unless paused
  useEffect(() => {
    if (!ready || paused) return
    const t = setInterval(() => { cursorRef.current = null; void load(true) }, 12_000)
    return () => clearInterval(t)
  }, [ready, paused, load])

  return (
    <div style={{ padding: '4px 0 24px' }}>
      {/* Controls strip */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 14,
        padding: '10px 16px', marginBottom: 16,
        background: 'var(--onyx-bg-2)',
        border: '1px solid rgba(168,173,184,0.10)',
      }}>
        <button
          onClick={() => setPaused(p => !p)}
          style={{
            background: 'transparent',
            color: paused ? 'var(--onyx-red)' : 'var(--onyx-bone)',
            border: '1px solid currentColor',
            padding: '6px 12px',
            font: '500 10px/1 var(--onyx-mono)',
            letterSpacing: '0.2em',
            textTransform: 'uppercase',
            cursor: 'pointer',
          }}
        >{paused ? 'paused — resume' : 'live — pause'}</button>
        <span style={{ flex: 1 }} />
        <select
          value={filterLang}
          onChange={(e) => setFilterLang(e.target.value)}
          style={{
            background: 'var(--onyx-bg)',
            color: 'var(--onyx-bone)',
            border: '1px solid rgba(168,173,184,0.32)',
            padding: '6px 10px',
            font: '500 10px/1 var(--onyx-mono)',
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
          }}
        >
          <option value="">ALL LANGUAGES</option>
          <option value="te">TELUGU</option>
          <option value="hi">HINDI</option>
          <option value="en">ENGLISH</option>
        </select>
      </div>

      {error && <p style={{ color: 'var(--onyx-red)', font: '400 12px var(--onyx-mono)' }}>{error}</p>}

      {/* Feed */}
      <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 0 }}>
        {items.map((s) => (
          <li
            key={s.segment_id}
            style={{
              display: 'grid',
              gridTemplateColumns: '120px 1fr 200px',
              gap: 16,
              padding: '14px 16px',
              borderBottom: '1px solid rgba(168,173,184,0.06)',
              animation: 'onyx-fade-up 0.3s ease',
            }}
          >
            {/* timestamp */}
            <div style={{
              font: '400 10px/1.4 var(--onyx-mono)',
              color: 'var(--onyx-dim)',
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
            }}>
              {new Date(s.created_at).toLocaleTimeString('en-IN')}
              <br/>
              <span style={{ color: 'var(--onyx-bone-2)', fontSize: 9 }}>
                {Math.round(s.start_sec)}–{Math.round(s.end_sec)}s
              </span>
            </div>
            {/* text */}
            <div>
              <p style={{
                margin: 0,
                font: '400 14px/1.5 var(--onyx-italic)',
                fontStyle: 'italic',
                color: 'var(--onyx-bone)',
              }}>{s.text_en ?? s.text_native}</p>
              {s.text_native && s.text_en && (
                <p style={{
                  margin: '4px 0 0',
                  font: '300 11px/1.4 var(--onyx-mono)',
                  color: 'var(--onyx-dim)',
                }}>{s.text_native}</p>
              )}
            </div>
            {/* meta */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
              <span style={{
                font: '500 11px/1 var(--onyx-display)',
                color: 'var(--onyx-bone)',
                letterSpacing: '0.04em',
              }}>{s.channel_name}</span>
              <div style={{ display: 'flex', gap: 6 }}>
                <EntityChip label={s.language} variant="language" />
                {s.is_quote && <EntityChip label="quote" variant="default" />}
                {s.is_editorial && <EntityChip label="editorial" variant="live" />}
              </div>
            </div>
          </li>
        ))}
      </ol>

      {items.length > 0 && cursorRef.current && (
        <button
          onClick={() => void load(false)}
          style={{
            display: 'block', margin: '24px auto',
            background: 'transparent',
            color: 'var(--onyx-bone-2)',
            border: '1px solid rgba(168,173,184,0.32)',
            padding: '10px 24px',
            font: '500 10px/1 var(--onyx-mono)',
            letterSpacing: '0.2em',
            textTransform: 'uppercase',
            cursor: 'pointer',
          }}
        >load older</button>
      )}
    </div>
  )
}
