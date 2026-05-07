'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { createClient } from '@/lib/supabase/client'
import { VideoBackground } from '@/components/ui/video-background'
import styles from '@/components/auth/auth.module.css'

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

function CompassGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="11" stroke="currentColor" strokeWidth="0.6" opacity="0.55" />
      <path
        d="M12 1 L13.2 10.8 L22 12 L13.2 13.2 L12 23 L10.8 13.2 L2 12 L10.8 10.8 Z"
        fill="currentColor"
        opacity="0.9"
      />
      <circle cx="12" cy="12" r="1.4" fill="currentColor" />
    </svg>
  )
}

function Wordmark() {
  return (
    <Link href="/" className={styles.brand} aria-label="Robin OSINT">
      <span className={styles.brandOrnament} aria-hidden="true">
        <CompassGlyph />
      </span>
      <span className={styles.brandRig}>Robin</span>
      <span className={styles.brandSurveillance}>OSINT</span>
      <span className={styles.brandTerminal}>.</span>
    </Link>
  )
}

const FEATURES: { num: string; text: string }[] = [
  { num: 'I', text: 'The morning brief, filed by 06:00 IST' },
  { num: 'II', text: 'Coverage rooms across 17 languages' },
  { num: 'III', text: 'An analyst you can audit, line by line' },
  { num: 'IV', text: 'Signals weighted against their history' },
]

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
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
      // Use /api/me/access (role-aware) instead of onboarding/status so
      // super_admins land on /admin instead of being trapped at /onboarding.
      const res = await fetch(`${API}/api/me/access`, {
        headers: { Authorization: `Bearer ${token}` },
        credentials: 'include',
      })
      if (!res.ok) {
        // D-07: on backend error, prefer /onboarding (a public route) over
        // /brief — middleware would bounce a profile-less user back to
        // /onboarding anyway, so going there directly avoids a visible
        // redirect flash.
        router.push('/onboarding')
        return
      }
      const access = (await res.json()) as {
        role: 'user' | 'super_admin'
        has_profile: boolean
        has_entities: boolean
      }
      if (access.role === 'super_admin') {
        router.push('/admin')
        return
      }
      router.push(access.has_profile && access.has_entities ? '/brief' : '/onboarding')
    } catch {
      router.push('/onboarding')
    }
  }

  return (
    <main className={styles.shell}>
      <section className={styles.left}>
        <div className={styles.videoLayer}>
          <VideoBackground src="/landing/hero.mp4" poster="/landing/hero-poster.jpg" />
        </div>
        <div className={styles.leftVignette} />
        <div className={styles.grain} />
        <div className={styles.watermarkMask} />

        <div className={styles.leftInner}>
          <Wordmark />

          <div className={styles.copy}>
            <div className={styles.copyEyebrow}>
              <span className={styles.rule} />
              <span>Returning Reader</span>
            </div>
            <h1 className={styles.copyTitle}>
              Credentials,
              <br />
              <em>please.</em>
            </h1>
            <p className={styles.copyDeck}>
              The room remembers you. Sign in and the brief you missed will be waiting — filed,
              annotated, ordered by consequence.
            </p>

            <div className={styles.list}>
              {FEATURES.map((f) => (
                <div key={f.num} className={styles.listItem}>
                  <span className={styles.listNum}>{f.num}.</span>
                  <span className={styles.listText}>{f.text}</span>
                </div>
              ))}
            </div>
          </div>

          <div className={styles.leftFooter}>Scientia · Potentia · Est</div>
        </div>
      </section>

      <section className={styles.right}>
        <div className={styles.rightInner}>
          <div className={styles.mobileBrand}>
            <Wordmark />
          </div>

          <div className={styles.formKicker}>Access · Vol. I</div>
          <h2 className={styles.formTitle}>
            Sign <em>in</em>
          </h2>
          <p className={styles.formSub}>Welcome back to the desk of record.</p>

          <div className={styles.fields}>
            <div className={styles.field}>
              <label className={styles.fieldLabel} htmlFor="email">
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
                className={styles.input}
                placeholder="you@example.com"
                autoComplete="email"
              />
            </div>

            <div className={styles.field}>
              <label className={styles.fieldLabel} htmlFor="password">
                Passphrase
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
                  className={styles.input}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  style={{ paddingRight: '64px' }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Hide passphrase' : 'Show passphrase'}
                  aria-pressed={showPassword}
                  tabIndex={0}
                  style={{
                    position: 'absolute',
                    top: '50%',
                    right: '10px',
                    transform: 'translateY(-50%)',
                    background: 'transparent',
                    border: 'none',
                    padding: '4px 6px',
                    cursor: 'pointer',
                    fontFamily: 'var(--font-sans-condensed, var(--font-mono))',
                    fontSize: '10px',
                    letterSpacing: '0.22em',
                    textTransform: 'uppercase',
                    color: 'var(--rig-ink-3)',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.color = 'var(--rig-ink)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.color = 'var(--rig-ink-3)'
                  }}
                >
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </div>
            </div>

            {error && <div className={styles.error}>{error}</div>}

            <button
              onClick={handleLogin}
              disabled={loading}
              className={styles.submit}
              type="button"
            >
              {loading ? 'Signing in…' : 'Enter the room'}
              <span className={styles.arrow}>→</span>
            </button>

            <p className={styles.altLine}>
              No credentials yet?
              <Link href="/signup" className={styles.altLink}>
                Request press access
              </Link>
            </p>
          </div>
        </div>
      </section>
    </main>
  )
}
