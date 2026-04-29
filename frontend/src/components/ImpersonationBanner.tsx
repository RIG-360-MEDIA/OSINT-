'use client'

/**
 * Top-of-page banner shown whenever the current request is being made under
 * an active impersonation session. The "Exit" button calls
 * /api/admin/impersonate/end which closes the session and clears the cookie,
 * then reloads.
 */
import { useEffect, useState } from 'react'
import { useAccess } from '@/lib/access'
import { createClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

export function ImpersonationBanner() {
  const { access } = useAccess()
  const [busy, setBusy] = useState(false)

  // Hide unless we know we're impersonating.
  if (!access?.is_impersonating) return null

  const exit = async () => {
    setBusy(true)
    try {
      const supabase = createClient()
      const { data } = await supabase.auth.getSession()
      if (!data.session) return
      await fetch(`${API_BASE}/api/admin/impersonate/end`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${data.session.access_token}` },
        credentials: 'include',
      })
    } finally {
      // Even on error, force reload so the banner state resets.
      window.location.reload()
    }
  }

  return (
    <div
      role="alert"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 1000,
        background: '#7c2d12',
        color: '#fef3c7',
        padding: '8px 16px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 16,
        fontSize: 13,
        fontWeight: 500,
        borderBottom: '1px solid rgba(255,255,255,0.2)',
      }}
    >
      <span>
        Viewing as <strong>{access.target_email}</strong> · admin{' '}
        <span style={{ opacity: 0.85 }}>{access.real_email}</span>
      </span>
      <button
        type="button"
        onClick={exit}
        disabled={busy}
        style={{
          background: 'transparent',
          border: '1px solid #fef3c7',
          color: '#fef3c7',
          padding: '2px 12px',
          borderRadius: 3,
          fontSize: 12,
          cursor: busy ? 'wait' : 'pointer',
        }}
      >
        {busy ? 'Exiting…' : 'Exit'}
      </button>
    </div>
  )
}
