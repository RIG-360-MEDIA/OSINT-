'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import { ThemeToggle } from './theme/ThemeToggle'

interface NavLink {
  path: string
  label: string
  slug: string  // page slug — currently unused while nav is empty during reset
}

// FRONTEND RESET (2026-05-19) — brief / coverage / clips / cuttings / documents /
// analyst / signals / threads / worldmonitor / landing / admin / onboarding
// routes were all removed. Surviving routes are /, /landing, /login, /signup.
// New app pages will be added back here as they ship via the
// docs/new-chat-prompts/ sessions.
const BASE_NAV_LINKS: ReadonlyArray<NavLink> = []

export default function Navigation() {
  const pathname = usePathname()
  const router = useRouter()
  const [userInitial, setUserInitial] = useState<string>('')

  // Nav is empty during the frontend reset — no pages to link to.
  const navLinks: ReadonlyArray<NavLink> = useMemo(() => BASE_NAV_LINKS, [])

  useEffect(() => {
    const supabase = createClient()
    const fetchSession = async () => {
      try {
        const { data: { session } } = await supabase.auth.getSession()
        if (!session) return
        const email = session.user?.email ?? ''
        setUserInitial(email.charAt(0).toUpperCase())
      } catch {
        /* non-critical */
      }
    }
    fetchSession()
  }, [pathname])

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
        background: 'var(--rig-paper-2)',
        borderBottom: '1px solid var(--rig-rule)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 24px',
        gap: '14px',
        zIndex: 200,
        backdropFilter: 'blur(6px)',
      }}
    >
      {/* ── Wordmark ────────────────────────────────────────────── */}
      <Link
        href="/"
        aria-label="Robin OSINT"
        style={{
          display: 'inline-flex',
          alignItems: 'baseline',
          textDecoration: 'none',
          userSelect: 'none',
          flexShrink: 0,
          marginRight: '8px',
        }}
      >
        <span style={{ display: 'inline-block', width: '14px', height: '14px', marginRight: '10px', color: 'var(--rig-gold)', position: 'relative', top: '1px' }}>
          <CompassGlyph />
        </span>
        <span
          style={{
            fontFamily: 'var(--font-serif)',
            fontStyle: 'italic',
            fontSize: '26px',
            lineHeight: 1,
            letterSpacing: '0.002em',
          }}
        >
          <span style={{ fontWeight: 600, color: 'var(--rig-ink)' }}>Robin</span>
          <span style={{ fontWeight: 500, color: 'var(--rig-gold)' }}> Surveillance</span>
          <span style={{ color: 'var(--rig-gold)' }}>.</span>
        </span>
      </Link>

      {/* ── Nav (spreads across available width; all items fit, no scroll) ── */}
      <nav
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '36px',
          flex: 1,
          minWidth: 0,
          justifyContent: 'flex-start',
          marginRight: '12px',
          flexWrap: 'nowrap',
        }}
      >
        {navLinks.map(({ path, label }) => (
          <NavItem
            key={path}
            label={label}
            href={path}
            isActive={pathname === path || pathname.startsWith(`${path}/`)}
          />
        ))}
      </nav>

      {/* ── Controls ───────────────────────────────────────────── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          flexShrink: 0,
          paddingLeft: '12px',
          borderLeft: '1px solid var(--rig-rule)',
        }}
      >
        <ThemeToggle />

        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '36px',
            height: '36px',
            border: '1px solid var(--rig-rule)',
            color: 'var(--rig-ink-2)',
            fontFamily: 'var(--font-serif)',
            fontStyle: 'italic',
            fontSize: '17px',
            borderRadius: '50%',
            marginLeft: '6px',
            flexShrink: 0,
          }}
          aria-hidden="true"
        >
          {userInitial || '·'}
        </div>

        <button
          onClick={handleSignOut}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: '10px 14px',
            fontFamily: 'var(--font-mono)',
            fontSize: '12px',
            letterSpacing: '0.24em',
            textTransform: 'uppercase',
            color: 'var(--rig-ink-3)',
            transition: 'color 0.2s',
            whiteSpace: 'nowrap',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--rig-oxblood)' }}
          onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--rig-ink-3)' }}
        >
          Sign out
        </button>
      </div>
    </header>
  )
}

/* ── Sub-components ──────────────────────────────────────────────────────── */

function NavItem({ href, label, isActive }: { href: string; label: string; isActive: boolean }) {
  const [hover, setHover] = useState(false)
  return (
    <Link
      href={href}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        position: 'relative',
        padding: '12px 10px',
        textDecoration: 'none',
        fontFamily: 'var(--font-mono)',
        fontSize: '11.5px',
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        color: isActive ? 'var(--rig-ink)' : hover ? 'var(--rig-ink-2)' : 'var(--rig-ink-3)',
        transition: 'color 0.2s',
        whiteSpace: 'nowrap',
        flexShrink: 1,
        minWidth: 0,
      }}
    >
      {label}
      {isActive && (
        <span
          style={{
            position: 'absolute',
            bottom: '-1px',
            left: '10px',
            right: '10px',
            height: '1px',
            background: 'var(--rig-gold)',
          }}
        />
      )}
    </Link>
  )
}

function CompassGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="11" stroke="currentColor" strokeWidth="0.7" opacity="0.55" />
      <path
        d="M12 1 L13.2 10.8 L22 12 L13.2 13.2 L12 23 L10.8 13.2 L2 12 L10.8 10.8 Z"
        fill="currentColor"
        opacity="0.9"
      />
      <circle cx="12" cy="12" r="1.4" fill="currentColor" />
    </svg>
  )
}
