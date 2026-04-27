'use client'

import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'
import { useTelanganaSignals } from './hooks/useTelanganaSignals'
import { TELANGANA, TELUGU_LIVE_CHANNELS } from './config/telangana'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface ResolvedChannel {
  channel_id: string
  label: string
  video_id: string | null
  live: boolean
}

interface Props {
  onSwitchToGlobal: () => void
}

export function TelanganaBriefing({ onSwitchToGlobal }: Props) {
  const s = useTelanganaSignals()
  const [drawer, setDrawer] = useState<null | 'live' | 'data'>(null)

  return (
    <main
      style={{
        minHeight: 'calc(100dvh - var(--topbar-h, 64px))',
        background: 'var(--rig-paper)',
        color: 'var(--rig-ink)',
        paddingTop: '64px',
      }}
    >
      {/* ── Scope row ─────────────────────────────────────────────────── */}
      <ScopeRow active="telangana" onPickGlobal={onSwitchToGlobal} />

      {/* ── Hero: dateline → number → sentence → doors ─────────────────── */}
      <section
        style={{
          maxWidth: 760,
          margin: '0 auto',
          padding: '64px 32px 96px',
          textAlign: 'center',
        }}
      >
        <Dateline />

        <h1
          style={{
            fontFamily: 'var(--font-serif)',
            fontStyle: 'italic',
            fontWeight: 500,
            fontSize: 44,
            lineHeight: 1.1,
            margin: '32px 0 8px',
            color: 'var(--rig-ink)',
          }}
        >
          {TELANGANA.name} Today
        </h1>

        <StabilityNumber score={s.stability.score} label={s.stability.label} loading={s.loading} />

        <p
          style={{
            fontFamily: 'var(--font-serif)',
            fontSize: 19,
            lineHeight: 1.65,
            color: 'var(--rig-ink-2)',
            margin: '40px 0 0',
            maxWidth: 580,
            marginLeft: 'auto',
            marginRight: 'auto',
          }}
        >
          {s.error ? (
            <span style={{ color: 'var(--rig-oxblood)' }}>Briefing unavailable: {s.error}</span>
          ) : (
            s.summary
          )}
        </p>

        <DoorRow
          onLive={() => setDrawer('live')}
          onData={() => setDrawer('data')}
          onMap={onSwitchToGlobal}
        />
      </section>

      {/* ── Slim status footer ─────────────────────────────────────────── */}
      <footer
        style={{
          borderTop: '1px solid var(--rig-rule)',
          padding: '14px 32px',
          fontFamily: 'var(--font-mono)',
          fontSize: 10.5,
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
          color: 'var(--rig-ink-3)',
          display: 'flex',
          justifyContent: 'space-between',
          maxWidth: 1280,
          margin: '0 auto',
        }}
      >
        <span>
          Hyderabad · {s.weather.tempC ?? '—'}°C · AQI {s.air.aqi ?? '—'} · {s.air.label}
        </span>
        <span>
          {s.loadedAt
            ? `Last update ${s.loadedAt.toLocaleTimeString(TELANGANA.locale, { hour: '2-digit', minute: '2-digit' })}`
            : 'Loading…'}
        </span>
      </footer>

      {/* ── Drawers ────────────────────────────────────────────────────── */}
      {drawer === 'live' && <LiveChannelsDrawer onClose={() => setDrawer(null)} />}
      {drawer === 'data' && <DataDrawer onClose={() => setDrawer(null)} signals={s} />}
    </main>
  )
}

/* ─── pieces ─────────────────────────────────────────────────────────── */

function Dateline() {
  const now = new Date()
  const dayDate = now.toLocaleDateString('en-IN', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
  const time = now.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: TELANGANA.tz,
  })
  return (
    <div
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        letterSpacing: '0.24em',
        textTransform: 'uppercase',
        color: 'var(--rig-ink-3)',
      }}
    >
      {dayDate} · {time} IST
    </div>
  )
}

function StabilityNumber({
  score,
  label,
  loading,
}: {
  score: number
  label: string
  loading: boolean
}) {
  // Color the number subtly based on label; gold default, oxblood when strained
  const color =
    label === 'Critical' ? 'var(--rig-oxblood)' : label === 'Strained' ? 'var(--rig-copper)' : 'var(--rig-ink)'

  return (
    <div style={{ marginTop: 24 }}>
      <div
        style={{
          fontFamily: 'var(--font-serif)',
          fontWeight: 500,
          fontSize: 96,
          lineHeight: 1,
          letterSpacing: '-0.02em',
          color,
          opacity: loading ? 0.35 : 1,
          transition: 'opacity .3s',
        }}
      >
        {loading ? '—' : score}
        <span style={{ fontSize: 32, color: 'var(--rig-ink-3)', marginLeft: 4 }}>/100</span>
      </div>
      <div
        aria-hidden
        style={{
          width: 96,
          height: 1,
          background: 'var(--rig-rule)',
          margin: '12px auto',
        }}
      />
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11.5,
          letterSpacing: '0.32em',
          textTransform: 'uppercase',
          color: 'var(--rig-ink-3)',
        }}
      >
        {label.toLowerCase()}
      </div>
    </div>
  )
}

function DoorRow({
  onLive,
  onData,
  onMap,
}: {
  onLive: () => void
  onData: () => void
  onMap: () => void
}) {
  return (
    <div
      style={{
        marginTop: 64,
        display: 'flex',
        justifyContent: 'center',
        gap: 48,
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        letterSpacing: '0.24em',
        textTransform: 'uppercase',
      }}
    >
      <Door label="Live channels" onClick={onLive} />
      <Door label="Map" onClick={onMap} />
      <Door label="Browse data" onClick={onData} />
    </div>
  )
}

function Door({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        color: 'var(--rig-ink-2)',
        padding: '4px 0',
        fontFamily: 'inherit',
        fontSize: 'inherit',
        letterSpacing: 'inherit',
        textTransform: 'inherit',
        borderBottom: '1px solid transparent',
        transition: 'color .2s, border-color .2s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.color = 'var(--rig-ink)'
        e.currentTarget.style.borderBottomColor = 'var(--rig-gold)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.color = 'var(--rig-ink-2)'
        e.currentTarget.style.borderBottomColor = 'transparent'
      }}
    >
      {label} →
    </button>
  )
}

function ScopeRow({
  active,
  onPickGlobal,
}: {
  active: 'telangana' | 'global'
  onPickGlobal: () => void
}) {
  // Non-sticky on purpose: a sticky bar at this size kept clipping the H1
  // headline as it scrolled past. Scope toggle isn't a primary action, so
  // scrolling back to the top to switch scope is acceptable.
  return (
    <div
      style={{
        background: 'var(--rig-paper-2)',
        borderBottom: '1px solid var(--rig-rule)',
        padding: '10px 32px',
        display: 'flex',
        gap: 24,
        alignItems: 'center',
        fontFamily: 'var(--font-mono)',
        fontSize: 10.5,
        letterSpacing: '0.22em',
        textTransform: 'uppercase',
      }}
    >
      <span style={{ color: 'var(--rig-ink-3)' }}>Scope:</span>
      <ScopeChip active={active === 'telangana'} label="Telangana" />
      <ScopeChip active={active === 'global'} label="Global" onClick={onPickGlobal} />
    </div>
  )
}

function ScopeChip({
  active,
  label,
  onClick,
}: {
  active: boolean
  label: string
  onClick?: () => void
}) {
  return (
    <button
      onClick={onClick}
      disabled={active && !onClick}
      style={{
        background: 'none',
        border: 'none',
        cursor: onClick ? 'pointer' : 'default',
        padding: 0,
        fontFamily: 'inherit',
        fontSize: 'inherit',
        letterSpacing: 'inherit',
        textTransform: 'inherit',
        color: active ? 'var(--rig-ink)' : 'var(--rig-ink-3)',
        borderBottom: active ? '1px solid var(--rig-gold)' : '1px solid transparent',
        paddingBottom: 2,
      }}
    >
      {label}
    </button>
  )
}

/* ─── drawers ────────────────────────────────────────────────────────── */

function LiveChannelsDrawer({ onClose }: { onClose: () => void }) {
  const [channels, setChannels] = useState<ResolvedChannel[]>(
    // Optimistic skeleton from config; real video IDs populate from backend
    TELUGU_LIVE_CHANNELS.map((c) => ({
      channel_id: c.id,
      label: c.label,
      video_id: null,
      live: false,
    })),
  )
  const [activeIdx, setActiveIdx] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const ctrl = new AbortController()
    ;(async () => {
      try {
        const supabase = createClient()
        const { data: { session } } = await supabase.auth.getSession()
        if (!session) {
          setError('Not signed in')
          setLoading(false)
          return
        }
        const r = await fetch(`${API_BASE}/api/worldmonitor/telangana/live-channels`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
          signal: ctrl.signal,
        })
        if (!r.ok) {
          setError(`Backend ${r.status}`)
          setLoading(false)
          return
        }
        const j = await r.json()
        if (Array.isArray(j.channels)) {
          setChannels(j.channels)
          // Default to first channel that's actually live
          const firstLive = j.channels.findIndex((c: ResolvedChannel) => c.live)
          if (firstLive >= 0) setActiveIdx(firstLive)
        }
      } catch (e) {
        if ((e as Error).name !== 'AbortError') setError((e as Error).message)
      } finally {
        setLoading(false)
      }
    })()
    return () => ctrl.abort()
  }, [])

  const ch = channels[activeIdx]
  const liveCount = channels.filter((c) => c.live).length

  return (
    <DrawerShell title="Live channels" onClose={onClose}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, height: '100%' }}>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            color: 'var(--rig-ink-3)',
          }}
        >
          {loading
            ? 'Resolving live streams…'
            : error
              ? `Error: ${error}`
              : `${liveCount} of ${channels.length} channels live`}
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {channels.map((c, i) => (
            <button
              key={c.channel_id}
              onClick={() => setActiveIdx(i)}
              disabled={!c.live && !loading}
              title={c.live ? '' : 'Not currently live'}
              style={{
                padding: '6px 12px',
                background: i === activeIdx ? 'var(--rig-ink)' : 'transparent',
                color: i === activeIdx
                  ? 'var(--rig-paper)'
                  : c.live
                    ? 'var(--rig-ink-2)'
                    : 'var(--rig-ink-3)',
                border: '1px solid var(--rig-rule)',
                fontFamily: 'var(--font-mono)',
                fontSize: 10.5,
                letterSpacing: '0.16em',
                textTransform: 'uppercase',
                cursor: c.live ? 'pointer' : 'not-allowed',
                opacity: c.live ? 1 : 0.55,
              }}
            >
              {c.label}
              {c.live && <span style={{ color: 'var(--rig-oxblood)', marginLeft: 6 }}>●</span>}
            </button>
          ))}
        </div>

        <div style={{ flex: 1, minHeight: 360, background: '#000', position: 'relative' }}>
          {ch?.video_id ? (
            <iframe
              key={ch.video_id}
              src={`https://www.youtube.com/embed/${ch.video_id}?autoplay=1&rel=0`}
              title={ch.label}
              allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
              allowFullScreen
              style={{ width: '100%', height: '100%', border: 'none' }}
            />
          ) : (
            <div
              style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#888',
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                letterSpacing: '0.18em',
                textTransform: 'uppercase',
                gap: 12,
              }}
            >
              <div>{loading ? 'Loading…' : ch ? `${ch.label} not currently live` : 'No channel selected'}</div>
              {ch && !loading && (
                <a
                  href={`https://www.youtube.com/channel/${ch.channel_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: 'var(--rig-gold)', textDecoration: 'none' }}
                >
                  Open channel on YouTube →
                </a>
              )}
            </div>
          )}
        </div>
      </div>
    </DrawerShell>
  )
}

function DataDrawer({
  onClose,
  signals,
}: {
  onClose: () => void
  signals: ReturnType<typeof useTelanganaSignals>
}) {
  const rows: { k: string; v: string }[] = [
    { k: 'Stability index', v: `${signals.stability.score} / 100 (${signals.stability.label})` },
    { k: 'Hyderabad temp', v: signals.weather.tempC !== null ? `${signals.weather.tempC}°C` : '—' },
    { k: 'Today high / low', v: `${signals.weather.maxC ?? '—'}° / ${signals.weather.minC ?? '—'}°` },
    { k: 'Conditions', v: signals.weather.label },
    { k: 'AQI (US scale)', v: signals.air.aqi !== null ? `${signals.air.aqi} — ${signals.air.label}` : '—' },
    { k: 'PM2.5', v: signals.air.pm25 !== null ? `${signals.air.pm25.toFixed(1)} µg/m³` : '—' },
    { k: 'ACLED events (7d)', v: signals.source === 'fallback' ? 'backend offline' : `${signals.events.length} recorded` },
    { k: 'News headlines', v: signals.source === 'fallback' ? 'backend offline' : `${signals.news.length} fresh` },
    { k: 'Source', v: signals.source === 'backend' ? (signals.cached ? 'rig backend (cached)' : 'rig backend') : 'public APIs (fallback)' },
  ]
  return (
    <DrawerShell title="Browse data" onClose={onClose}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-serif)' }}>
        <tbody>
          {rows.map((r) => (
            <tr key={r.k} style={{ borderBottom: '1px solid var(--rig-rule)' }}>
              <td
                style={{
                  padding: '12px 0',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10.5,
                  letterSpacing: '0.18em',
                  textTransform: 'uppercase',
                  color: 'var(--rig-ink-3)',
                  width: '40%',
                }}
              >
                {r.k}
              </td>
              <td style={{ padding: '12px 0', fontSize: 16, color: 'var(--rig-ink)' }}>{r.v}</td>
            </tr>
          ))}
        </tbody>

        {signals.news.length > 0 && (
          <SectionList title="Today's headlines" items={signals.news.slice(0, 12).map((n) => ({
            primary: n.title,
            secondary: n.source_label,
            link: n.link,
          }))} />
        )}

        {signals.events.length > 0 && (
          <SectionList title="ACLED · past 7 days" items={signals.events.slice(0, 20).map((e) => ({
            primary: `${e.event_type}${e.sub_event_type ? ' · ' + e.sub_event_type : ''} — ${e.location || '—'}`,
            secondary: `${e.event_date}${e.fatalities ? ' · ' + e.fatalities + ' fatalities' : ''}`,
          }))} />
        )}
      </table>
    </DrawerShell>
  )
}

function SectionList({
  title,
  items,
}: {
  title: string
  items: { primary: string; secondary?: string; link?: string }[]
}) {
  return (
    <>
      <h3
        style={{
          margin: '32px 0 8px',
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontSize: 18,
          fontWeight: 500,
          color: 'var(--rig-ink)',
        }}
      >
        {title}
      </h3>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {items.map((it, i) => (
          <li key={i} style={{ padding: '12px 0', borderBottom: '1px solid var(--rig-rule)' }}>
            {it.link ? (
              <a
                href={it.link}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  fontFamily: 'var(--font-serif)',
                  fontSize: 16,
                  color: 'var(--rig-ink)',
                  textDecoration: 'none',
                  borderBottom: '1px solid transparent',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.borderBottomColor = 'var(--rig-gold)' }}
                onMouseLeave={(e) => { e.currentTarget.style.borderBottomColor = 'transparent' }}
              >
                {it.primary}
              </a>
            ) : (
              <span style={{ fontFamily: 'var(--font-serif)', fontSize: 16, color: 'var(--rig-ink)' }}>{it.primary}</span>
            )}
            {it.secondary && (
              <div
                style={{
                  marginTop: 4,
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10.5,
                  letterSpacing: '0.16em',
                  textTransform: 'uppercase',
                  color: 'var(--rig-ink-3)',
                }}
              >
                {it.secondary}
              </div>
            )}
          </li>
        ))}
      </ul>
    </>
  )
}

function DrawerShell({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: React.ReactNode
}) {
  // Drawer sits flush below the rig nav (fixed at top). The scope row is
  // not sticky, so we don't need to clear it.
  const [topOffset, setTopOffset] = useState(64)

  useEffect(() => {
    const measure = () => {
      const header = document.querySelector('header')
      const navH = header?.getBoundingClientRect().height ?? 64
      setTopOffset(navH)
    }
    measure()
    window.addEventListener('resize', measure)

    // Lock the page scroll while the drawer is open so the wheel doesn't
    // bleed through to the briefing underneath.
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    // Esc closes
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)

    return () => {
      window.removeEventListener('resize', measure)
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [onClose])

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      style={{
        position: 'fixed',
        top: topOffset,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0,0,0,0.35)',
        zIndex: 90, // below the rig nav (200) so the nav stays usable
        display: 'flex',
        justifyContent: 'flex-end',
      }}
    >
      <aside
        onClick={(e) => e.stopPropagation()}
        onWheel={(e) => e.stopPropagation()}
        style={{
          width: 'min(720px, 92vw)',
          height: '100%',
          background: 'var(--rig-paper)',
          borderLeft: '1px solid var(--rig-rule)',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '-4px 0 20px rgba(0,0,0,0.08)',
        }}
      >
        <header
          style={{
            padding: '20px 24px',
            borderBottom: '1px solid var(--rig-rule)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline',
            flexShrink: 0,
          }}
        >
          <h2
            style={{
              margin: 0,
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              fontWeight: 500,
              fontSize: 22,
            }}
          >
            {title}
          </h2>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              letterSpacing: '0.24em',
              textTransform: 'uppercase',
              color: 'var(--rig-ink-3)',
            }}
          >
            Close ×
          </button>
        </header>
        <div style={{ flex: 1, overflow: 'auto', padding: '24px', overscrollBehavior: 'contain' }}>
          {children}
        </div>
      </aside>
    </div>
  )
}
