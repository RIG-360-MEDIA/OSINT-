'use client'

import { useEffect, useState } from 'react'

interface Props {
  onSwitchToTelangana: () => void
}

const WM_URL = process.env.NEXT_PUBLIC_WM_URL || 'http://localhost:3001'

export function GlobalView({ onSwitchToTelangana }: Props) {
  const [navH, setNavH] = useState(86)

  useEffect(() => {
    const measure = () => {
      const header = document.querySelector('header')
      if (header) setNavH(header.getBoundingClientRect().height)
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [])

  return (
    <>
      {/* Tiny scope row so the user can return to the regional briefing */}
      <div
        style={{
          position: 'fixed',
          top: navH,
          left: 0,
          right: 0,
          zIndex: 50,
          background: 'var(--rig-paper-2)',
          borderBottom: '1px solid var(--rig-rule)',
          padding: '8px 24px',
          display: 'flex',
          gap: 24,
          fontFamily: 'var(--font-mono)',
          fontSize: 10.5,
          letterSpacing: '0.22em',
          textTransform: 'uppercase',
        }}
      >
        <span style={{ color: 'var(--rig-ink-3)' }}>Scope:</span>
        <button
          onClick={onSwitchToTelangana}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--rig-ink-3)',
            padding: 0,
            fontFamily: 'inherit',
            fontSize: 'inherit',
            letterSpacing: 'inherit',
            textTransform: 'inherit',
            cursor: 'pointer',
          }}
        >
          Telangana
        </button>
        <span
          style={{
            color: 'var(--rig-ink)',
            borderBottom: '1px solid var(--rig-gold)',
            paddingBottom: 2,
          }}
        >
          Global
        </span>
      </div>

      <iframe
        title="World Monitor"
        src={WM_URL}
        loading="eager"
        style={{
          position: 'fixed',
          top: navH + 36, // nav + scope row
          left: 0,
          width: '100vw',
          height: `calc(100dvh - ${navH + 36}px)`,
          border: 'none',
          display: 'block',
          background: 'var(--rig-paper)',
        }}
      />
    </>
  )
}
