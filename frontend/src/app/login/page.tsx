'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { createClient } from '@/lib/supabase/client'

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 0',
  border: 'none',
  borderBottom: '1.5px solid #DDD8D0',
  background: 'transparent',
  fontFamily: "'DM Sans', system-ui, sans-serif",
  fontSize: '15px',
  color: '#1A1614',
  outline: 'none',
  transition: 'border-color 0.15s',
}

const labelStyle: React.CSSProperties = {
  fontFamily: "'DM Sans', system-ui, sans-serif",
  fontSize: '12px',
  fontWeight: 500,
  color: '#5C5249',
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  display: 'block',
  marginBottom: '6px',
}

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleLogin = async () => {
    if (!email || !password) {
      setError('Please enter your email and password.')
      return
    }
    setLoading(true)
    setError('')

    const supabase = createClient()
    const { data, error: authError } = await supabase.auth.signInWithPassword({ email, password })

    if (authError) {
      setError(authError.message)
      setLoading(false)
      return
    }

    const token = data.session?.access_token
    try {
      const res = await fetch(`${API}/api/onboarding/status`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      const status = await res.json()
      router.push(status.has_profile ? '/brief' : '/onboarding')
    } catch {
      router.push('/onboarding')
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      backgroundColor: '#F7F4EF',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '24px',
    }}>
      <div style={{ width: '100%', maxWidth: '400px' }}>
        <div style={{ textAlign: 'center', marginBottom: '48px' }}>
          <h1 style={{
            fontFamily: "'Playfair Display', Georgia, serif",
            fontSize: '24px',
            fontWeight: 700,
            color: '#8B1A1A',
            letterSpacing: '0.05em',
          }}>
            RIG SURVEILLANCE
          </h1>
          <p style={{
            fontFamily: "'DM Sans', system-ui, sans-serif",
            fontSize: '13px',
            color: '#9C928A',
            marginTop: '6px',
          }}>
            Personal Intelligence Platform
          </p>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div>
            <label style={labelStyle}>Email</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              style={inputStyle}
              onFocus={e => (e.target.style.borderBottom = '1.5px solid #8B1A1A')}
              onBlur={e => (e.target.style.borderBottom = '1.5px solid #DDD8D0')}
            />
          </div>

          <div>
            <label style={labelStyle}>Password</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleLogin()}
              style={inputStyle}
              onFocus={e => (e.target.style.borderBottom = '1.5px solid #8B1A1A')}
              onBlur={e => (e.target.style.borderBottom = '1.5px solid #DDD8D0')}
            />
          </div>

          {error && (
            <p style={{
              fontFamily: "'DM Sans', system-ui, sans-serif",
              fontSize: '13px',
              color: '#8B1A1A',
            }}>
              {error}
            </p>
          )}

          <button
            onClick={handleLogin}
            disabled={loading}
            style={{
              marginTop: '8px',
              padding: '12px 24px',
              backgroundColor: loading ? '#9C928A' : '#8B1A1A',
              color: 'white',
              border: 'none',
              borderRadius: '2px',
              fontFamily: "'DM Sans', system-ui, sans-serif",
              fontSize: '14px',
              fontWeight: 500,
              cursor: loading ? 'not-allowed' : 'pointer',
              letterSpacing: '0.03em',
              transition: 'background-color 0.15s',
            }}
          >
            {loading ? 'Signing in...' : 'Sign in'}
          </button>

          <p style={{
            textAlign: 'center',
            fontFamily: "'DM Sans', system-ui, sans-serif",
            fontSize: '13px',
            color: '#9C928A',
          }}>
            No account?{' '}
            <Link href="/signup" style={{ color: '#8B1A1A', textDecoration: 'none' }}>
              Create one
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
