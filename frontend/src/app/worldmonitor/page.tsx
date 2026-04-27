'use client'

import { useEffect, useState } from 'react'
import Navigation from '@/components/Navigation'

const WM_URL = process.env.NEXT_PUBLIC_WM_URL || 'http://localhost:3001'

export default function WorldMonitorPage() {
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
      <Navigation />
      <iframe
        title="World Monitor"
        src={WM_URL}
        loading="eager"
        style={{
          position: 'fixed',
          top: navH,
          left: 0,
          width: '100vw',
          height: `calc(100dvh - ${navH}px)`,
          border: 'none',
          display: 'block',
          background: 'var(--rig-paper)',
        }}
      />
    </>
  )
}
