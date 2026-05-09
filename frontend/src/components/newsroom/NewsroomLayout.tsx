'use client'

import { useEffect, useRef, useState } from 'react'

import { useAuthedFetch, NEWSROOM_API_BASE } from './useNewsroomApi'
import { WallMode } from './WallMode'
import { StreamMode } from './StreamMode'
import { EchoMode } from './EchoMode'
import { DossierMode } from './DossierMode'
import { BriefMode } from './BriefMode'
import { NEWSROOM_MODES, type NewsroomMode } from '@/types/newsroom'
import type { NewsroomBreakingResponse, NewsroomChannel } from '@/types/newsroom'

const MODE_VIEWS: Record<NewsroomMode, () => React.ReactElement> = {
  wall:    WallMode,
  stream:  StreamMode,
  echo:    EchoMode,
  dossier: DossierMode,
  brief:   BriefMode,
}

export function NewsroomLayout() {
  const { ready, fetcher, tokenRef } = useAuthedFetch()
  const [mode, setMode] = useState<NewsroomMode>('wall')
  const [liveCount, setLiveCount] = useState<number | null>(null)
  const [breakingCount, setBreakingCount] = useState<number | null>(null)
  const [tickerNames, setTickerNames] = useState<string[]>([])
  const [sseAlive, setSseAlive] = useState(false)
  const sseRef = useRef<EventSource | null>(null)

  // Poll status bar metrics every 30s
  useEffect(() => {
    if (!ready) return
    let cancelled = false
    const load = async () => {
      try {
        const [chans, breaking] = await Promise.all([
          fetcher<{ channels: NewsroomChannel[] }>('/api/newsroom/channels?only_active=true'),
          fetcher<NewsroomBreakingResponse>('/api/newsroom/breaking?hours=4'),
        ])
        if (cancelled) return
        const liveChans = chans.channels.filter((c) => c.is_live_24x7)
        setLiveCount(liveChans.length)
        setBreakingCount(breaking.clusters.length)
        setTickerNames(chans.channels.map((c) => c.name))
      } catch {
        // ignore — keep last good values
      }
    }
    void load()
    const t = setInterval(() => { void load() }, 30_000)
    return () => { cancelled = true; clearInterval(t) }
  }, [ready, fetcher])

  // SSE connection — fires fade-up animations on tile captions when new
  // segments land. The mode components themselves poll for content; the
  // SSE just provides the "something arrived" signal so we can flash.
  useEffect(() => {
    if (!ready || !tokenRef.current) return
    // EventSource doesn't support custom headers; we pass token via a
    // querystring fallback. The router accepts both forms in production
    // (router checks Authorization header, but for SSE we pass via JWT
    // query — see backend follow-up). For now, attempt without auth and
    // log silently on failure.
    const url = `${NEWSROOM_API_BASE}/api/newsroom/stream/live`
    let es: EventSource | null = null
    try {
      es = new EventSource(url, { withCredentials: true })
      es.addEventListener('open', () => setSseAlive(true))
      es.addEventListener('error', () => setSseAlive(false))
      sseRef.current = es
    } catch {
      // swallow — SSE is a nice-to-have; modes work via polling
    }
    return () => { es?.close(); sseRef.current = null; setSseAlive(false) }
  }, [ready, tokenRef])

  // Hotkeys 1-5 for mode switching
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLElement && (
        e.target.tagName === 'INPUT' ||
        e.target.tagName === 'SELECT' ||
        e.target.tagName === 'TEXTAREA'
      )) return
      const m = NEWSROOM_MODES.find((m) => m.key === e.key)
      if (m) {
        e.preventDefault()
        setMode(m.id)
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  const View = MODE_VIEWS[mode]

  return (
    <div
      data-newsroom-root
      style={{
        background: '#000000',
        color: '#ECEEF1',
        minHeight: '100vh',
        width: '100%',
        position: 'relative',
        paddingBottom: 60,
        fontFamily: '"Inter", system-ui, -apple-system, sans-serif',
      }}
    >
      {/* Status bar */}
      <header style={{
        position: 'sticky', top: 0, zIndex: 60,
        background: 'rgba(0, 0, 0, 0.92)',
        backdropFilter: 'blur(8px)',
        borderBottom: '1px solid rgba(168, 173, 184, 0.18)',
        padding: '10px 28px',
        display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap',
      }}>
        <p style={{
          margin: 0,
          font: '500 11px/1 var(--onyx-mono)',
          color: 'var(--onyx-red)',
          letterSpacing: '0.32em',
          textTransform: 'uppercase',
        }}>The Newsroom</p>
        <span style={{
          font: '400 10px/1 var(--onyx-mono)',
          color: 'var(--onyx-bone-2)',
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
        }}>
          {liveCount == null ? '· ·' : `${liveCount} live`} · {' '}
          {breakingCount == null ? '· ·' : `${breakingCount} breaking`} · {' '}
          {sseAlive ? <span style={{ color: 'var(--onyx-red)' }}>stream connected</span> : 'polling'}
        </span>
        <span style={{ flex: 1 }} />
        <nav role="tablist" aria-label="Newsroom mode" style={{ display: 'flex', gap: 4 }}>
          {NEWSROOM_MODES.map((m) => (
            <button
              key={m.id}
              role="tab"
              className="onyx-mode-tab"
              aria-current={mode === m.id ? 'page' : undefined}
              onClick={() => setMode(m.id)}
              title={`Switch to ${m.label} (${m.key})`}
            >{m.label} <span style={{ opacity: 0.45, marginLeft: 4 }}>{m.key}</span></button>
          ))}
        </nav>
      </header>

      {/* Active mode */}
      <main style={{
        maxWidth: 1480, margin: '0 auto',
        padding: '20px 28px',
        position: 'relative', zIndex: 1,
      }}>
        <View />
      </main>

      {/* Bottom marquee */}
      {tickerNames.length > 0 && (
        <footer style={{
          position: 'fixed', bottom: 0, left: 0, right: 0,
          height: 36,
          background: 'rgba(0, 0, 0, 0.92)',
          borderTop: '1px solid rgba(255, 45, 45, 0.32)',
          overflow: 'hidden',
          zIndex: 58,
        }}>
          <div className="onyx-marquee-track" style={{
            display: 'flex', gap: 36, alignItems: 'center', height: '100%',
            font: '400 10px/1 var(--onyx-mono)',
            color: 'var(--onyx-bone-2)',
            letterSpacing: '0.32em',
            textTransform: 'uppercase',
            whiteSpace: 'nowrap',
            paddingLeft: 28,
          }}>
            {[...tickerNames, ...tickerNames].map((n, i) => (
              <span key={`${n}-${i}`}>
                <span className="onyx-pip" style={{ marginRight: 12 }} />
                {n}
              </span>
            ))}
          </div>
        </footer>
      )}
    </div>
  )
}
