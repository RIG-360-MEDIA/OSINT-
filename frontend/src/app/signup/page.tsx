'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { createClient } from '@/lib/supabase/client'
import { VideoBackground } from '@/components/ui/video-background'
import styles from '@/components/auth/auth.module.css'

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

const STEPS: { num: string; text: string }[] = [
  { num: 'I', text: 'Tell us who you are' },
  { num: 'II', text: 'Define what you monitor' },
  { num: 'III', text: 'Set your geography' },
  { num: 'IV', text: 'Specify your signals' },
  { num: 'V', text: 'Describe your risk horizon' },
]

export default function SignupPage() {
  const router = useRouter()
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSignup = async () => {
    if (!email || !password) {
      setError('Please enter your email and password.')
      return
    }
    if (password.length < 6) {
      setError('Password must be at least 6 characters.')
      return
    }
    setLoading(true)
    setError('')

    const supabase = createClient()
    const { error: authError } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { display_name: displayName } },
    })

    if (authError) {
      setError(
        authError.message.toLowerCase().includes('already registered')
          ? 'This email is already registered.'
          : authError.message,
      )
      setLoading(false)
      return
    }

    router.push('/onboarding')
  }

  const alreadyRegistered = error.includes('already registered')

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
              <span>Press Credentials</span>
            </div>
            <h1 className={styles.copyTitle}>
              Build your
              <br />
              <em>dossier.</em>
            </h1>
            <p className={styles.copyDeck}>
              Five questions. Two minutes. A morning paper of one, tuned to the entities, regions,
              and signals that move your work.
            </p>

            <div className={styles.list}>
              {STEPS.map((step) => (
                <div key={step.num} className={styles.listItem}>
                  <span className={styles.listNum}>{step.num}.</span>
                  <span className={styles.listText}>{step.text}</span>
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

          <div className={styles.formKicker}>Intake · Vol. I</div>
          <h2 className={styles.formTitle}>
            Create <em>account</em>
          </h2>
          <p className={styles.formSub}>A reading room of one, filed by morning.</p>

          <div className={styles.fields}>
            <div className={styles.field}>
              <label className={styles.fieldLabel} htmlFor="displayName">
                Your name · optional
              </label>
              <input
                id="displayName"
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className={styles.input}
                placeholder="Jane Smith"
                autoComplete="name"
              />
            </div>

            <div className={styles.field}>
              <label className={styles.fieldLabel} htmlFor="email">
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={styles.input}
                placeholder="you@example.com"
                autoComplete="email"
              />
            </div>

            <div className={styles.field}>
              <label className={styles.fieldLabel} htmlFor="password">
                Passphrase
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSignup()}
                className={styles.input}
                placeholder="Minimum six characters"
                autoComplete="new-password"
              />
            </div>

            {error && (
              <div className={styles.error}>
                {error}
                {alreadyRegistered && (
                  <>
                    {' '}
                    <Link href="/login">Sign in instead.</Link>
                  </>
                )}
              </div>
            )}

            <button
              onClick={handleSignup}
              disabled={loading}
              className={styles.submit}
              type="button"
            >
              {loading ? 'Issuing credentials…' : 'Request credentials'}
              <span className={styles.arrow}>→</span>
            </button>

            <p className={styles.altLine}>
              Already on the masthead?
              <Link href="/login" className={styles.altLink}>
                Sign in
              </Link>
            </p>
          </div>
        </div>
      </section>
    </main>
  )
}
