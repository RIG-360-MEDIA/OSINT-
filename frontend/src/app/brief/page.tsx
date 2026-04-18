'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import type { User } from '@supabase/supabase-js'

export default function BriefPage() {
  const router = useRouter()
  const [user, setUser] = useState<User | null>(null)

  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getUser().then(({ data }) => {
      if (!data.user) {
        router.push('/login')
      } else {
        setUser(data.user)
      }
    })
  }, [router])

  if (!user) return null

  return (
    <div style={{
      minHeight: '100vh',
      backgroundColor: '#F7F4EF',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      flexDirection: 'column',
      gap: '16px',
      padding: '24px',
      textAlign: 'center',
    }}>
      <h1 style={{
        fontFamily: "'Playfair Display', Georgia, serif",
        fontSize: '32px',
        fontWeight: 700,
        color: '#1A1614',
      }}>
        Your intelligence feed is live.
      </h1>
      <p style={{
        fontFamily: "'DM Sans', system-ui, sans-serif",
        fontSize: '17px',
        color: '#5C5249',
        maxWidth: '480px',
        lineHeight: '1.6',
      }}>
        Your first brief arrives at 06:00 IST. Articles are being ranked for you now.
      </p>
      <p style={{
        fontFamily: "'DM Mono', ui-monospace, monospace",
        fontSize: '12px',
        color: '#9C928A',
        marginTop: '8px',
      }}>
        Signed in as {user.email}
      </p>
    </div>
  )
}
