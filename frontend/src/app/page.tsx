import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'

// Frontend reset: brief / coverage / landing have been removed. Logged-in users
// land on /onboarding until the new app pages (Brief, Map, Analytics) are built.
// Logged-out users see a minimal placeholder pointing them to /login.

export default async function Home() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) {
    return (
      <main
        style={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'var(--font-serif, serif)',
          padding: '24px',
          textAlign: 'center',
        }}
      >
        <h1 style={{ fontSize: '40px', fontStyle: 'italic', margin: 0 }}>
          Robin <span style={{ color: 'var(--rig-gold, #b08d4f)' }}>Surveillance</span>
        </h1>
        <p style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: '13px', letterSpacing: '0.16em', textTransform: 'uppercase', marginTop: '24px', opacity: 0.6 }}>
          New app rebuild in progress
        </p>
        <a
          href="/login"
          style={{
            marginTop: '32px',
            padding: '12px 24px',
            border: '1px solid currentColor',
            textDecoration: 'none',
            color: 'inherit',
            fontFamily: 'var(--font-mono, monospace)',
            fontSize: '12px',
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
          }}
        >
          Sign in
        </a>
      </main>
    )
  }

  // Authenticated → go to onboarding (only surviving primary destination).
  // Super-admins fall through to /admin per their access policy.
  const session = await supabase.auth.getSession()
  const token = session.data.session?.access_token

  try {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
    const res = await fetch(`${apiUrl}/api/me/access`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: 'no-store',
    })
    if (res.ok) {
      const access = (await res.json()) as {
        role: 'user' | 'super_admin'
      }
      if (access.role === 'super_admin') {
        redirect('/admin')
      }
    }
  } catch {
    /* fall through */
  }

  redirect('/onboarding')
}
