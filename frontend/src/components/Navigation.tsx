'use client'

import { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'

interface NavCounts {
  brief_ready: boolean
  article_count: number
  thread_count: number
  escalating_count: number
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const NAV_LINKS = [
  { path: '/brief',    label: 'Daily Brief' },
  { path: '/coverage', label: 'Coverage Room' },
  { path: '/threads',  label: 'Story Threads' },
  { path: '/analyst',  label: 'Analyst' },
]

export default function Navigation() {
  const pathname = usePathname()
  const router   = useRouter()
  const [counts, setCounts] = useState<NavCounts>({ brief_ready: false, article_count: 0, thread_count: 0, escalating_count: 0 })
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    const supabase = createClient()
    const fetchCounts = async () => {
      try {
        const { data: { session } } = await supabase.auth.getSession()
        if (!session) return
        const token = session.access_token

        const [briefRes, feedRes, threadsRes] = await Promise.all([
          fetch(`${API_BASE}/api/brief/today`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API_BASE}/api/coverage/feed?limit=1`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API_BASE}/api/threads?limit=50`, { headers: { Authorization: `Bearer ${token}` } }),
        ])

        let articleCount = 0
        if (feedRes.ok) {
          const data = await feedRes.json()
          articleCount = data?.totals?.total ?? 0
        }

        let threadCount = 0
        let escalatingCount = 0
        if (threadsRes.ok) {
          const tData = await threadsRes.json()
          threadCount = tData?.thread_count ?? 0
          escalatingCount = tData?.escalating_count ?? 0
        }

        setCounts({
          brief_ready: briefRes.status === 200,
          article_count: articleCount,
          thread_count: threadCount,
          escalating_count: escalatingCount,
        })
      } catch {
        // non-critical
      }
    }
    fetchCounts()
  }, [pathname])

  const handleSignOut = async () => {
    const supabase = createClient()
    await supabase.auth.signOut()
    router.push('/login')
  }

  return (
    <header style={{
      position:        'fixed',
      top:             0,
      left:            0,
      right:           0,
      height:          '56px',
      backgroundColor: '#18181B',
      borderBottom:    '1px solid rgba(255,255,255,0.07)',
      display:         'flex',
      alignItems:      'center',
      padding:         '0 20px',
      zIndex:          200,
      gap:             '0',
    }}>

      {/* ── Logo ─────────────────────────────────────────────── */}
      <div
        onClick={() => router.push('/brief')}
        style={{
          display:    'flex',
          alignItems: 'center',
          gap:        '10px',
          cursor:     'pointer',
          flexShrink: 0,
          marginRight: '32px',
        }}
      >
        <div style={{
          width:           '30px',
          height:          '30px',
          borderRadius:    '8px',
          background:      'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
          display:         'flex',
          alignItems:      'center',
          justifyContent:  'center',
          boxShadow:       '0 2px 8px rgba(245,158,11,0.4)',
          flexShrink:      0,
        }}>
          <span style={{
            fontFamily:  "'DM Sans', system-ui, sans-serif",
            fontSize:    '13px',
            fontWeight:  700,
            color:       '#18181B',
            letterSpacing: '-0.02em',
          }}>R</span>
        </div>
        <div style={{ lineHeight: 1 }}>
          <div style={{
            fontFamily:    "'DM Sans', system-ui, sans-serif",
            fontSize:      '13px',
            fontWeight:    600,
            color:         '#F8FAFC',
            letterSpacing: '-0.01em',
          }}>RIG Surveillance</div>
          <div style={{
            fontFamily: "'DM Sans', system-ui, sans-serif",
            fontSize:   '10px',
            color:      'rgba(255,255,255,0.3)',
            marginTop:  '1px',
          }}>Intelligence Platform</div>
        </div>
      </div>

      {/* ── Nav links ────────────────────────────────────────── */}
      <nav style={{
        display:    'flex',
        alignItems: 'center',
        gap:        '2px',
        flex:       1,
      }}>
        {NAV_LINKS.map(({ path, label }) => {
          const isActive = pathname === path
          return (
            <NavLink
              key={path}
              label={label}
              isActive={isActive}
              onClick={() => router.push(path)}
            />
          )
        })}
      </nav>

      {/* ── Right side: stats + badges + sign out ────────────── */}
      <div style={{
        display:    'flex',
        alignItems: 'center',
        gap:        '10px',
        flexShrink: 0,
      }}>
        {/* Article count chip */}
        {counts.article_count > 0 && (
          <div style={{
            display:         'flex',
            alignItems:      'center',
            gap:             '5px',
            padding:         '4px 10px',
            borderRadius:    '9999px',
            border:          '1px solid rgba(59,130,246,0.25)',
            backgroundColor: 'rgba(59,130,246,0.1)',
          }}>
            <span style={{
              width:           '5px',
              height:          '5px',
              borderRadius:    '50%',
              backgroundColor: '#3B82F6',
              flexShrink:      0,
            }} />
            <span style={{
              fontFamily:  "'DM Mono', ui-monospace, monospace",
              fontSize:    '11px',
              color:       '#93C5FD',
              fontWeight:  500,
              letterSpacing: '0.02em',
            }}>
              {counts.article_count.toLocaleString()}
            </span>
          </div>
        )}

        {/* Story Threads escalating badge */}
        {counts.escalating_count > 0 && (
          <div style={{
            display:         'flex',
            alignItems:      'center',
            gap:             '5px',
            padding:         '4px 10px',
            borderRadius:    '9999px',
            border:          '1px solid rgba(239,68,68,0.3)',
            backgroundColor: 'rgba(239,68,68,0.1)',
          }}>
            <span style={{
              width:           '5px',
              height:          '5px',
              borderRadius:    '50%',
              backgroundColor: '#EF4444',
              flexShrink:      0,
            }} />
            <span style={{
              fontFamily:    "'DM Mono', ui-monospace, monospace",
              fontSize:      '11px',
              color:         '#FCA5A5',
              fontWeight:    500,
              letterSpacing: '0.02em',
            }}>
              {counts.escalating_count} escalating
            </span>
          </div>
        )}

        {/* Brief ready badge */}
        {counts.brief_ready && (
          <div
            className="pulse-amber"
            style={{
              display:         'flex',
              alignItems:      'center',
              gap:             '5px',
              padding:         '4px 10px',
              borderRadius:    '9999px',
              border:          '1px solid rgba(245,158,11,0.3)',
              backgroundColor: 'rgba(245,158,11,0.12)',
            }}
          >
            <span style={{
              width:           '5px',
              height:          '5px',
              borderRadius:    '50%',
              backgroundColor: '#F59E0B',
              flexShrink:      0,
            }} />
            <span style={{
              fontFamily: "'DM Sans', system-ui, sans-serif",
              fontSize:   '11px',
              fontWeight: 600,
              color:      '#FCD34D',
              letterSpacing: '0.02em',
            }}>
              Brief Ready
            </span>
          </div>
        )}

        {/* Divider */}
        <div style={{
          width:           '1px',
          height:          '20px',
          backgroundColor: 'rgba(255,255,255,0.1)',
        }} />

        {/* Sign out */}
        <button
          onClick={handleSignOut}
          style={{
            background:  'none',
            border:      'none',
            cursor:      'pointer',
            padding:     '6px 10px',
            borderRadius: '6px',
            fontFamily:  "'DM Sans', system-ui, sans-serif",
            fontSize:    '12px',
            color:       'rgba(255,255,255,0.35)',
            transition:  'color 0.15s, background 0.15s',
          }}
          onMouseEnter={e => {
            const el = e.currentTarget
            el.style.color = 'rgba(255,255,255,0.7)'
            el.style.background = 'rgba(255,255,255,0.06)'
          }}
          onMouseLeave={e => {
            const el = e.currentTarget
            el.style.color = 'rgba(255,255,255,0.35)'
            el.style.background = 'none'
          }}
        >
          Sign out
        </button>
      </div>
    </header>
  )
}

/* ── NavLink sub-component ─────────────────────────────────────────────────── */
function NavLink({
  label,
  isActive,
  onClick,
}: {
  label: string
  isActive: boolean
  onClick: () => void
}) {
  const [hovered, setHovered] = useState(false)

  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position:        'relative',
        background:      'none',
        border:          'none',
        cursor:          'pointer',
        padding:         '6px 14px',
        borderRadius:    '6px',
        fontFamily:      "'DM Sans', system-ui, sans-serif",
        fontSize:        '14px',
        fontWeight:      isActive ? 600 : 400,
        color:           isActive ? '#F8FAFC' : hovered ? '#CBD5E1' : 'rgba(255,255,255,0.5)',
        transition:      'color 0.15s, background 0.15s',
        backgroundColor: hovered && !isActive ? 'rgba(255,255,255,0.05)' : 'transparent',
        letterSpacing:   '-0.01em',
      }}
    >
      {label}
      {/* Active underline */}
      {isActive && (
        <span style={{
          position:        'absolute',
          bottom:          '-2px',
          left:            '14px',
          right:           '14px',
          height:          '2px',
          borderRadius:    '2px 2px 0 0',
          background:      'linear-gradient(90deg, #F59E0B, #FBBF24)',
          boxShadow:       '0 0 8px rgba(245,158,11,0.6)',
          animation:       'nav-underline 0.22s ease both',
        }} />
      )}
      {/* Hover underline */}
      {hovered && !isActive && (
        <span style={{
          position:        'absolute',
          bottom:          '-2px',
          left:            '14px',
          right:           '14px',
          height:          '1px',
          borderRadius:    '1px',
          backgroundColor: 'rgba(255,255,255,0.2)',
          animation:       'nav-underline 0.18s ease both',
        }} />
      )}
    </button>
  )
}
