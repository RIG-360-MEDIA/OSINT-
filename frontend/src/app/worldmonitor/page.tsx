'use client'

export default function WorldMonitorPage() {
  return (
    <div
      style={{
        position: 'fixed',
        top: 'var(--topbar-h)',
        left: 0,
        right: 0,
        bottom: 0,
        background: 'var(--rig-paper)',
      }}
    >
      <iframe
        title="World Monitor"
        src="/world-monitor-app/"
        loading="eager"
        style={{
          width: '100%',
          height: '100%',
          border: 'none',
          display: 'block',
        }}
      />
    </div>
  )
}
