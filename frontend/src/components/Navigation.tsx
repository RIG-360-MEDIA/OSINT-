'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import { ThemeToggle } from './theme/ThemeToggle'

interface NavCounts {
  brief_ready: boolean
  article_count: number
  thread_count: number
  escalating_count: number
  clip_count: number
  doc_count: number
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const NAV_LINKS = [
  { path: '/brief',     label: 'The Brief' },
  { path: '/coverage',  label: 'Coverage' },
  { path: '/threads',   label: 'Threads' },
  { path: '/clips',     label: 'Clippings' },
  { path: '/cuttings',  label: 'Cutting Room' },
  { path: '/signals',   label: 'Signals' },
  { path: '/documents', label: 'Archive' },
  { path: '/analyst',   label: 'Analyst' },
  { path: '/worldmonitor', label: 'Globe' },
]

export default function Navigation() {
  const pathname = usePathname()
  const router = useRouter()
  const [counts, setCounts] = useState<NavCounts>({
    brief_ready: false,
    article_count: 0,
    thread_count: 0,
    escalating_count: 0,
    clip_count: 0,
    doc_count: 0,
  })
  const [userInitial, setUserInitial] = useState<string>('')

  useEffect(() => {
    const supabase = createClient()
    const fetchAll = async () => {
      try {
        const { data: { session } } = await supabase.auth.getSession()
        if (!session) return
        const token = session.access_token

        const email = session.user?.email ?? ''
        setUserInitial(email.charAt(0).toUpperCase())

        const [briefRes, feedRes, threadsRes, clipsRes, docsRes] = await Promise.all([
          fetch(`${API_BASE}/api/brief/today`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API_BASE}/api/coverage/feed?limit=1`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API_BASE}/api/threads?limit=50`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API_BASE}/api/clips/feed?limit=1`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API_BASE}/api/documents/feed?limit=1`, { headers: { Authorization: `Bearer ${token}` } }),
        ])

        let articleCount = 0
        if (feedRes.ok) {
          const data = await feedRes.json()
          articleCount = data?.totals?.total ?? 0
        }

        let threadCount = 0
        let escalatingCount = 0
        if (threadsRes.ok) {
          const t = await threadsRes.json()
          threadCount = t?.thread_count ?? 0
          escalatingCount = t?.escalating_count ?? 0
        }

        let clipCount = 0
        if (clipsRes.ok) {
          const c = await clipsRes.json()
          clipCount = c?.total ?? 0
        }

        let docCount = 0
        if (docsRes.ok) {
          const d = await docsRes.json()
          docCount = d?.total ?? 0
        }

        setCounts({
          brief_ready: briefRes.status === 200,
          article_count: articleCount,
          thread_count: threadCount,
          escalating_count: escalatingCount,
          clip_count: clipCount,
          doc_count: docCount,
        })
      } catch {
        /* non-critical */
      }
    }
    fetchAll()
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
        href="/brief"
        aria-label="Rig Surveillance"
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
            fontSize: '24px',
            lineHeight: 1,
            letterSpacing: '0.002em',
          }}
        >
          <span style={{ fontWeight: 600, color: 'var(--rig-ink)' }}>Rig</span>
          <span style={{ fontWeight: 500, color: 'var(--rig-gold)' }}> Surveillance</span>
          <span style={{ color: 'var(--rig-gold)' }}>.</span>
        </span>
      </Link>

      {/* ── Nav (horizontally scrollable on overflow) ──────────── */}
      <nav
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0px',
          flex: 1,
          minWidth: 0,
          justifyContent: 'flex-start',
          marginRight: '8px',
          overflowX: 'auto',
          overflowY: 'hidden',
          scrollbarWidth: 'none',
          msOverflowStyle: 'none' as 'none',
        }}
        // Hide horizontal scrollbar but keep scroll functionality
        // (extra style block via className would also work; inline kept terse).
      >
        {NAV_LINKS.map(({ path, label }) => (
          <NavItem
            key={path}
            label={label}
            href={path}
            isActive={pathname === path}
          />
        ))}
      </nav>

      {/* ── Ticker + controls ──────────────────────────────────── */}
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
        {/* Low-priority counters: hidden on viewports < 1400 px so the
            high-signal chips (escalating, brief ready) always fit. */}
        {counts.doc_count > 0 && (
          <span className="rig-chip-mq-wide">
            <Chip tone="default" label={`${counts.doc_count} docs`} />
          </span>
        )}
        {counts.clip_count > 0 && (
          <span className="rig-chip-mq-wide">
            <Chip tone="copper" label={`${counts.clip_count} clips`} />
          </span>
        )}
        {counts.article_count > 0 && (
          <span className="rig-chip-mq-mid">
            <Chip tone="default" label={counts.article_count.toLocaleString()} />
          </span>
        )}
        {counts.brief_ready && (
          <span className="pulse-gold" style={{ display: 'inline-flex' }}>
            <Chip tone="gold" label="Brief ready" />
          </span>
        )}

        <span
          aria-hidden="true"
          style={{
            width: '1px',
            height: '18px',
            background: 'var(--rig-rule)',
            margin: '0 6px',
          }}
        />

        <ThemeToggle />

        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '32px',
            height: '32px',
            border: '1px solid var(--rig-rule)',
            color: 'var(--rig-ink-2)',
            fontFamily: 'var(--font-serif)',
            fontStyle: 'italic',
            fontSize: '15px',
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
            padding: '8px 12px',
            fontFamily: 'var(--font-mono)',
            fontSize: '10.5px',
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
        padding: '10px 8px',
        textDecoration: 'none',
        fontFamily: 'var(--font-mono)',
        fontSize: '10px',
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        color: isActive ? 'var(--rig-ink)' : hover ? 'var(--rig-ink-2)' : 'var(--rig-ink-3)',
        transition: 'color 0.2s',
        whiteSpace: 'nowrap',
        flexShrink: 0,
      }}
    >
      {label}
      {isActive && (
        <span
          style={{
            position: 'absolute',
            bottom: '-1px',
            left: '8px',
            right: '8px',
            height: '1px',
            background: 'var(--rig-gold)',
          }}
        />
      )}
    </Link>
  )
}

function Chip({ label, tone }: { label: string; tone: 'default' | 'gold' | 'copper' | 'alert' }) {
  return (
    <span
      className="rig-chip"
      data-tone={tone === 'default' ? undefined : tone}
    >
      <span className="dot" />
      {label}
    </span>
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
