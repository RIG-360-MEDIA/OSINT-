/**
 * OnyxTopBar — sleek, professional top navigation for the /coverage hub.
 *
 * Inspirations: 21st.dev (clean glassy nav), smoothie.video (sliding active
 * indicator + tight typography), astrodither (intelligence-dossier feel),
 * particles.casberry.in (subtle glow accents).
 *
 * Composition (left to right):
 *   - Custom radar glyph + 'Robin' wordmark in Space Grotesk
 *   - Vertical hairline
 *   - Mono nav links with a sliding cyan indicator that tracks the active
 *     route and animates between positions
 *   - Live status pill (pulsing green dot)
 *   - Live UTC clock with tabular numerals
 *   - User avatar circle (initial)
 *   - Minimal text sign-out
 *
 * Background: 55%-opacity black + backdrop-filter blur, so the page's
 * particle field bleeds through faintly. Bottom hairline is a red
 * horizontal gradient that fades at both edges.
 */

'use client'

import Link from 'next/link'
import { useRouter, usePathname } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { createClient } from '@/lib/supabase/client'

interface NavLink {
  path: string
  label: string
}

const NAV_LINKS: ReadonlyArray<NavLink> = [
  { path: '/brief',    label: 'The Brief' },
  { path: '/coverage', label: 'Coverage' },
]

interface IndicatorStyle {
  left: number
  width: number
  opacity: number
}

const formatHMS = (d: Date): string => {
  const h = String(d.getUTCHours()).padStart(2, '0')
  const m = String(d.getUTCMinutes()).padStart(2, '0')
  const s = String(d.getUTCSeconds()).padStart(2, '0')
  return `${h}:${m}:${s}`
}

export function OnyxTopBar() {
  const router = useRouter()
  const pathname = usePathname()
  const [userInitial, setUserInitial] = useState<string>('')
  const [now, setNow] = useState<Date | null>(null)
  const navRef = useRef<HTMLElement | null>(null)
  const [indicator, setIndicator] = useState<IndicatorStyle>({
    left: 0, width: 0, opacity: 0,
  })

  // ── User initial for avatar ───────────────────────────────────────────
  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getSession().then(({ data: { session } }) => {
      const email = session?.user?.email ?? ''
      if (email) setUserInitial(email.charAt(0).toUpperCase())
    }).catch(() => {})
  }, [pathname])

  // ── 1Hz UTC clock ─────────────────────────────────────────────────────
  useEffect(() => {
    setNow(new Date())
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  // ── Sliding indicator follows the active route ───────────────────────
  useEffect(() => {
    const updateIndicator = (): void => {
      const nav = navRef.current
      if (!nav) return
      const links = nav.querySelectorAll<HTMLAnchorElement>('a[data-nav-link]')
      let active: HTMLAnchorElement | null = null
      links.forEach((link) => {
        const path = link.getAttribute('href') ?? ''
        if (pathname === path || pathname.startsWith(`${path}/`)) {
          active = link
        }
      })
      if (active) {
        const navRect = nav.getBoundingClientRect()
        const a = active as HTMLAnchorElement
        const linkRect = a.getBoundingClientRect()
        setIndicator({
          left: linkRect.left - navRect.left,
          width: linkRect.width,
          opacity: 1,
        })
      } else {
        setIndicator((s) => ({ ...s, opacity: 0 }))
      }
    }
    updateIndicator()
    window.addEventListener('resize', updateIndicator)
    return () => window.removeEventListener('resize', updateIndicator)
  }, [pathname])

  const handleSignOut = async (): Promise<void> => {
    const supabase = createClient()
    await supabase.auth.signOut()
    router.push('/login')
  }

  return (
    <header
      data-theme="onyx"
      className="onyx-fade-up"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        height: 'var(--topbar-h)',
        background: 'rgba(0, 0, 0, 0.55)',
        backdropFilter: 'blur(24px) saturate(1.4)',
        WebkitBackdropFilter: 'blur(24px) saturate(1.4)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 32px',
        gap: '28px',
        zIndex: 200,
      }}
    >
      {/* Bottom gradient hairline (red, fades at edges) */}
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          left: 0, right: 0, bottom: 0,
          height: '1px',
          background: 'linear-gradient(90deg, transparent 0%, var(--onyx-red) 18%, var(--onyx-red) 82%, transparent 100%)',
          opacity: 0.42,
          pointerEvents: 'none',
        }}
      />

      {/* ── Wordmark with custom radar glyph ──────────────────────────── */}
      <Link
        href="/brief"
        aria-label="Robin"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '14px',
          textDecoration: 'none',
          flexShrink: 0,
        }}
      >
        <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true" style={{ color: 'var(--onyx-cyan)', display: 'block', filter: 'drop-shadow(0 0 6px rgba(0, 194, 255, 0.45))' }}>
          <circle cx="11" cy="11" r="9.5" fill="none" stroke="currentColor" strokeWidth="0.6" opacity="0.32" />
          <circle cx="11" cy="11" r="5.5" fill="none" stroke="currentColor" strokeWidth="0.9" opacity="0.62" />
          <circle cx="11" cy="11" r="2" fill="currentColor" />
          <line x1="11" y1="0.5" x2="11" y2="3.5" stroke="currentColor" strokeWidth="1" />
          <line x1="21.5" y1="11" x2="18.5" y2="11" stroke="currentColor" strokeWidth="1" />
        </svg>
        <span style={{
          fontFamily: 'var(--onyx-display)',
          fontWeight: 500,
          fontSize: '17px',
          lineHeight: 1,
          letterSpacing: '-0.012em',
          color: 'var(--onyx-bone)',
        }}>
          Robin
        </span>
      </Link>

      {/* Vertical hairline divider */}
      <div style={{ width: '1px', height: '22px', background: 'var(--onyx-rule-hair)', flexShrink: 0 }} aria-hidden="true" />

      {/* ── Nav with sliding cyan indicator ───────────────────────────── */}
      <nav
        ref={navRef as React.RefObject<HTMLElement>}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '32px',
          flex: 1,
          position: 'relative',
          height: '100%',
        }}
      >
        {NAV_LINKS.map(({ path, label }) => {
          const isActive = pathname === path || pathname.startsWith(`${path}/`)
          return (
            <Link
              key={path}
              href={path}
              data-nav-link
              style={{
                fontFamily: 'var(--onyx-mono)',
                fontSize: '11px',
                fontWeight: 500,
                letterSpacing: '0.28em',
                textTransform: 'uppercase',
                color: isActive ? 'var(--onyx-bone)' : 'var(--onyx-dim)',
                textDecoration: 'none',
                padding: '0 2px',
                lineHeight: 'var(--topbar-h)',
                transition: 'color 0.4s ease',
                whiteSpace: 'nowrap',
              }}
              onMouseEnter={(e) => {
                if (!isActive) (e.currentTarget as HTMLAnchorElement).style.color = 'var(--onyx-bone-2)'
              }}
              onMouseLeave={(e) => {
                if (!isActive) (e.currentTarget as HTMLAnchorElement).style.color = 'var(--onyx-dim)'
              }}
            >
              {label}
            </Link>
          )
        })}
        {/* Sliding indicator — animates left + width on route change */}
        <div
          aria-hidden="true"
          style={{
            position: 'absolute',
            bottom: '14px',
            left: indicator.left,
            width: indicator.width,
            height: '2px',
            background: 'var(--onyx-cyan)',
            boxShadow: '0 0 14px var(--onyx-cyan-glow)',
            opacity: indicator.opacity,
            transition: 'left 0.55s cubic-bezier(0.16, 1, 0.3, 1), width 0.55s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.3s ease',
            pointerEvents: 'none',
          }}
        />
      </nav>

      {/* ── Right rail ────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '18px', flexShrink: 0 }}>
        {/* Live status pill */}
        <div className="onyx-topbar-rail-mid" style={{
          display: 'inline-flex', alignItems: 'center', gap: '8px',
          padding: '5px 11px',
          border: '1px solid var(--onyx-rule-hair)',
          fontFamily: 'var(--onyx-mono)',
          fontSize: '9.5px',
          fontWeight: 500,
          letterSpacing: '0.28em',
          textTransform: 'uppercase',
          color: 'var(--onyx-bone-2)',
        }}>
          <span className="onyx-live-dot" style={{ display: 'inline-block' }} />
          Live
        </div>

        {/* UTC clock */}
        <span className="onyx-topbar-rail-mid" style={{
          fontFamily: 'var(--onyx-mono)',
          fontSize: '11.5px',
          letterSpacing: '0.14em',
          color: 'var(--onyx-bone-2)',
          fontVariantNumeric: 'tabular-nums',
        }}>
          {now ? formatHMS(now) : '--:--:--'}{' '}
          <span style={{ color: 'var(--onyx-dim)', marginLeft: '4px', fontSize: '9.5px', letterSpacing: '0.32em' }}>UTC</span>
        </span>

        {/* User avatar */}
        {userInitial && (
          <div
            aria-label="Account"
            style={{
              width: '32px', height: '32px',
              border: '1px solid var(--onyx-rule-hair)',
              borderRadius: '50%',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              fontFamily: 'var(--onyx-display)',
              fontSize: '13px',
              fontWeight: 500,
              color: 'var(--onyx-bone-2)',
              flexShrink: 0,
            }}
          >
            {userInitial}
          </div>
        )}

        {/* Sign out — minimal text */}
        <button
          type="button"
          onClick={handleSignOut}
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--onyx-dim)',
            fontFamily: 'var(--onyx-mono)',
            fontSize: '10px',
            fontWeight: 500,
            letterSpacing: '0.32em',
            textTransform: 'uppercase',
            cursor: 'pointer',
            padding: '4px 0',
            transition: 'color 0.3s ease',
          }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--onyx-red)' }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--onyx-dim)' }}
        >
          Sign Out
        </button>
      </div>

      {/* Responsive: hide status pill + clock on narrow viewports */}
      <style>{`
        @media (max-width: 980px) {
          .onyx-topbar-rail-mid { display: none !important; }
        }
      `}</style>
    </header>
  )
}
