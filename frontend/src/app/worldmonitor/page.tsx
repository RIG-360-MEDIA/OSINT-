'use client'

// WM is a vanilla-TS SPA whose HTML references absolute paths (/assets/...,
// /api/...). Path-prefix proxying through a Next.js rewrite breaks asset
// loading. Pointing the iframe directly at the WM container origin works
// because WM doesn't share auth state with rig (Clerk vs. Supabase), so
// the cross-origin loss is purely theoretical for cookie flow.
const WM_URL = process.env.NEXT_PUBLIC_WM_URL || 'http://localhost:3001'

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
        src={WM_URL}
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
