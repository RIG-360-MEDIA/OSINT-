'use client'

import { useState } from 'react'
import { useTelanganaSignals } from './hooks/useTelanganaSignals'
import { TELANGANA, TELUGU_LIVE_CHANNELS } from './config/telangana'

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
  return (
    <div
      style={{
        position: 'sticky',
        top: 'var(--topbar-h, 64px)',
        zIndex: 10,
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
  const [activeIdx, setActiveIdx] = useState(0)
  const ch = TELUGU_LIVE_CHANNELS[activeIdx]
  return (
    <DrawerShell title="Live channels" onClose={onClose}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, height: '100%' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {TELUGU_LIVE_CHANNELS.map((c, i) => (
            <button
              key={c.id}
              onClick={() => setActiveIdx(i)}
              style={{
                padding: '6px 12px',
                background: i === activeIdx ? 'var(--rig-ink)' : 'transparent',
                color: i === activeIdx ? 'var(--rig-paper)' : 'var(--rig-ink-2)',
                border: '1px solid var(--rig-rule)',
                fontFamily: 'var(--font-mono)',
                fontSize: 10.5,
                letterSpacing: '0.16em',
                textTransform: 'uppercase',
                cursor: 'pointer',
              }}
            >
              {c.label}
            </button>
          ))}
        </div>
        <div style={{ flex: 1, minHeight: 360, background: '#000' }}>
          <iframe
            key={ch.id}
            src={`https://www.youtube.com/embed/live_stream?channel=${ch.id}&autoplay=0`}
            title={ch.label}
            allow="autoplay; encrypted-media; picture-in-picture"
            style={{ width: '100%', height: '100%', border: 'none' }}
          />
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
    { k: 'ACLED events', v: 'wiring up — backend proxy pending' },
    { k: 'News headlines', v: 'wiring up — backend proxy pending' },
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
      </table>
    </DrawerShell>
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
  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.35)',
        zIndex: 100,
        display: 'flex',
        justifyContent: 'flex-end',
      }}
    >
      <aside
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 'min(720px, 92vw)',
          height: '100%',
          background: 'var(--rig-paper)',
          borderLeft: '1px solid var(--rig-rule)',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <header
          style={{
            padding: '20px 24px',
            borderBottom: '1px solid var(--rig-rule)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline',
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
        <div style={{ flex: 1, overflow: 'auto', padding: '24px' }}>{children}</div>
      </aside>
    </div>
  )
}
