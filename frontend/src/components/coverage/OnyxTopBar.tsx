/**
 * OnyxTopBar — onyx-themed top navigation matching the /coverage hub.
 *
 * Replaces the parchment Navigation component on dark pages so the bar
 * doesn't cream-clash with the black canvas. Same affordances: wordmark
 * back to /brief, Brief and Coverage links, sign-out on the right.
 *
 * Active link gets a thin cyan underline + bone text. Inactive links sit
 * in dim gray. All labels are JetBrains Mono uppercase with wide tracking
 * to read as terminal chrome rather than parchment serif.
 */

'use client'

import Link from 'next/link'
import { useRouter, usePathname } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'

interface NavLink {
  path: string
  label: string
}

const NAV_LINKS: ReadonlyArray<NavLink> = [
  { path: '/brief',    label: 'The Brief' },
  { path: '/coverage', label: 'Coverage' },
]

export function OnyxTopBar() {
  const router = useRouter()
  const pathname = usePathname()

  const handleSignOut = async () => {
    const supabase = createClient()
    await supabase.auth.signOut()
    router.push('/login')
  }

  return (
    <header
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        height: 'var(--topbar-h)',
        background: 'var(--onyx-bg)',
        borderBottom: '1px solid var(--onyx-rule-hair)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 32px',
        gap: '28px',
        zIndex: 200,
        backdropFilter: 'blur(8px)',
      }}
      data-theme="onyx"
    >
      {/* ── Wordmark ──────────────────────────────────────────── */}
      <Link
        href="/brief"
        aria-label="Robin"
        style={{
          display: 'inline-flex',
          alignItems: 'baseline',
          gap: '10px',
          textDecoration: 'none',
          flexShrink: 0,
        }}
      >
        <span
          style={{
            display: 'inline-block',
            width: '6px',
            height: '6px',
            background: 'var(--onyx-cyan)',
            boxShadow: '0 0 8px var(--onyx-cyan-glow)',
          }}
        />
        <span
          style={{
            fontFamily: 'var(--onyx-italic)',
            fontStyle: 'italic',
            fontSize: '24px',
            lineHeight: 1,
            color: 'var(--onyx-bone)',
            letterSpacing: '0.005em',
          }}
        >
          Robin
        </span>
      </Link>

      {/* ── Nav links ─────────────────────────────────────────── */}
      <nav
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '32px',
          marginLeft: '24px',
          flex: 1,
        }}
      >
        {NAV_LINKS.map(({ path, label }) => {
          const isActive =
            pathname === path || pathname.startsWith(`${path}/`)
          return (
            <Link
              key={path}
              href={path}
              style={{
                fontFamily: 'var(--onyx-mono)',
                fontSize: '11px',
                fontWeight: 500,
                letterSpacing: '0.32em',
                textTransform: 'uppercase',
                color: isActive ? 'var(--onyx-bone)' : 'var(--onyx-dim)',
                textDecoration: 'none',
                paddingBottom: '6px',
                borderBottom: isActive
                  ? '1px solid var(--onyx-cyan)'
                  : '1px solid transparent',
                transition: 'color 0.35s ease, border-color 0.35s ease',
              }}
              onMouseEnter={(e) => {
                if (!isActive)
                  (e.currentTarget as HTMLAnchorElement).style.color =
                    'var(--onyx-bone-2)'
              }}
              onMouseLeave={(e) => {
                if (!isActive)
                  (e.currentTarget as HTMLAnchorElement).style.color =
                    'var(--onyx-dim)'
              }}
            >
              {label}
            </Link>
          )
        })}
      </nav>

      {/* ── Sign out ──────────────────────────────────────────── */}
      <button
        type="button"
        onClick={handleSignOut}
        style={{
          background: 'transparent',
          border: '1px solid var(--onyx-rule-hair)',
          color: 'var(--onyx-dim)',
          fontFamily: 'var(--onyx-mono)',
          fontSize: '10px',
          fontWeight: 500,
          letterSpacing: '0.32em',
          textTransform: 'uppercase',
          padding: '9px 18px',
          cursor: 'pointer',
          transition: 'border-color 0.3s ease, color 0.3s ease',
          flexShrink: 0,
        }}
        onMouseEnter={(e) => {
          ;(e.currentTarget as HTMLButtonElement).style.borderColor =
            'var(--onyx-red)'
          ;(e.currentTarget as HTMLButtonElement).style.color =
            'var(--onyx-bone)'
        }}
        onMouseLeave={(e) => {
          ;(e.currentTarget as HTMLButtonElement).style.borderColor =
            'var(--onyx-rule-hair)'
          ;(e.currentTarget as HTMLButtonElement).style.color =
            'var(--onyx-dim)'
        }}
      >
        Sign Out
      </button>
    </header>
  )
}
