'use client'

import Navigation from '@/components/Navigation'

const WM_URL = process.env.NEXT_PUBLIC_WM_URL || 'http://localhost:3001'

export default function WorldMonitorPage() {
  return (
    <>
      <Navigation />
      <iframe
        title="World Monitor"
        src={WM_URL}
        loading="eager"
        style={{
          position: 'fixed',
          top: 'var(--topbar-h)',
          left: 0,
          width: '100vw',
          height: 'calc(100vh - var(--topbar-h))',
          border: 'none',
          display: 'block',
          background: 'var(--rig-paper)',
        }}
      />
    </>
  )
}
