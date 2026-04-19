'use client'

import { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'

interface NavCounts {
  brief_ready: boolean
  article_count: number
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface NavItem {
  path: string
  label: string
  subtitle: string
  disabled?: boolean
}

export default function Navigation() {
  const pathname = usePathname()
  const router = useRouter()
  const [counts, setCounts] = useState<NavCounts>({
    brief_ready: false,
    article_count: 0,
  })

  useEffect(() => {
    const supabase = createClient()

    const fetchCounts = async () => {
      try {
        const { data: { session } } = await supabase.auth.getSession()
        if (!session) return
        const token = session.access_token

        const briefRes = await fetch(
          `${API_BASE}/api/brief/today`,
          { headers: { Authorization: `Bearer ${token}` } }
        )
        const briefReady = briefRes.status === 200

        const feedRes = await fetch(
          `${API_BASE}/api/coverage/feed?limit=1`,
          { headers: { Authorization: `Bearer ${token}` } }
        )
        let articleCount = 0
        if (feedRes.ok) {
          const data = await feedRes.json()
          articleCount = data?.totals?.total ?? 0
        }

        setCounts({
          brief_ready: briefReady,
          article_count: articleCount,
        })
      } catch {
        // Silent — nav counts are non-critical
      }
    }
    fetchCounts()
  }, [pathname])

  const handleSignOut = async () => {
    const supabase = createClient()
    await supabase.auth.signOut()
    router.push('/login')
  }

  const navItems: NavItem[] = [
    {
      path: '/brief',
      label: 'Daily Brief',
      subtitle: counts.brief_ready
        ? "Today's brief ready"
        : 'No brief yet today',
    },
    {
      path: '/coverage',
      label: 'Coverage Room',
      subtitle:
        counts.article_count > 0
          ? `${counts.article_count.toLocaleString()} articles ranked`
          : 'Loading...',
    },
    {
      path: '/analyst',
      label: 'Analyst',
      subtitle: 'Coming soon',
      disabled: true,
    },
    {
      path: '/threads',
      label: 'Story Threads',
      subtitle: 'Coming soon',
      disabled: true,
    },
    {
      path: '/collections',
      label: 'Collections',
      subtitle: 'Coming soon',
      disabled: true,
    },
  ]

  return (
    <nav
      style={{
        position: 'fixed',
        left: 0,
        top: 0,
        width: '200px',
        height: '100vh',
        backgroundColor: '#EFEBE4',
        borderRight: '1px solid #DDD8D0',
        display: 'flex',
        flexDirection: 'column',
        zIndex: 100,
        overflowY: 'auto',
      }}
    >
      <div
        style={{
          padding: '24px 20px 20px',
          borderBottom: '1px solid #DDD8D0',
        }}
      >
        <div
          style={{
            fontFamily: "'Playfair Display', Georgia, serif",
            fontSize: '13px',
            fontWeight: 700,
            color: '#8B1A1A',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            lineHeight: 1.2,
          }}
        >
          RIG
        </div>
        <div
          style={{
            fontFamily: "'Playfair Display', Georgia, serif",
            fontSize: '13px',
            fontWeight: 700,
            color: '#8B1A1A',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            lineHeight: 1.2,
          }}
        >
          SURVEILLANCE
        </div>
      </div>

      <div style={{ flex: 1, padding: '8px 0' }}>
        {navItems.map((item) => {
          const isActive = pathname === item.path
          return (
            <div
              key={item.path}
              onClick={() => {
                if (!item.disabled) router.push(item.path)
              }}
              style={{
                padding: '10px 20px',
                borderLeft: isActive
                  ? '2px solid #8B1A1A'
                  : '2px solid transparent',
                cursor: item.disabled ? 'default' : 'pointer',
                opacity: item.disabled ? 0.4 : 1,
              }}
            >
              <div
                style={{
                  fontFamily: "'DM Sans', system-ui, sans-serif",
                  fontSize: '14px',
                  fontWeight: isActive ? 600 : 400,
                  color: isActive ? '#8B1A1A' : '#1A1614',
                }}
              >
                {item.label}
              </div>
              <div
                style={{
                  fontFamily: "'DM Sans', system-ui, sans-serif",
                  fontSize: '11px',
                  color: '#9C928A',
                  marginTop: '2px',
                }}
              >
                {item.subtitle}
              </div>
            </div>
          )
        })}
      </div>

      <div
        style={{
          padding: '16px 20px',
          borderTop: '1px solid #DDD8D0',
        }}
      >
        <button
          onClick={handleSignOut}
          style={{
            background: 'none',
            border: 'none',
            fontFamily: "'DM Sans', system-ui, sans-serif",
            fontSize: '12px',
            color: '#9C928A',
            cursor: 'pointer',
            padding: 0,
          }}
        >
          Sign out
        </button>
      </div>
    </nav>
  )
}
