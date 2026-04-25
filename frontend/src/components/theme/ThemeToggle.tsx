'use client'

import { useTheme } from './ThemeProvider'

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const label = theme === 'parchment' ? 'Night desk' : 'Parchment'

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={`Switch to ${label}`}
      title={`Switch to ${label}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '8px',
        padding: '6px 10px',
        background: 'transparent',
        border: '1px solid var(--rig-rule)',
        color: 'var(--rig-ink-2)',
        fontFamily: 'var(--font-mono)',
        fontSize: '10px',
        letterSpacing: '0.24em',
        textTransform: 'uppercase',
        cursor: 'pointer',
        transition: 'border-color 0.2s, color 0.2s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = 'var(--rig-gold)'
        e.currentTarget.style.color = 'var(--rig-ink)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--rig-rule)'
        e.currentTarget.style.color = 'var(--rig-ink-2)'
      }}
    >
      <GlyphSun active={theme === 'parchment'} />
      <span aria-hidden="true" style={{ opacity: 0.4 }}>/</span>
      <GlyphMoon active={theme === 'night'} />
    </button>
  )
}

function GlyphSun({ active }: { active: boolean }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      style={{ opacity: active ? 1 : 0.35, transition: 'opacity 0.2s' }}
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2 L12 5 M12 19 L12 22 M2 12 L5 12 M19 12 L22 12 M4.2 4.2 L6.3 6.3 M17.7 17.7 L19.8 19.8 M4.2 19.8 L6.3 17.7 M17.7 6.3 L19.8 4.2" strokeLinecap="round" />
    </svg>
  )
}

function GlyphMoon({ active }: { active: boolean }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      style={{ opacity: active ? 1 : 0.35, transition: 'opacity 0.2s' }}
      aria-hidden="true"
    >
      <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4 a6.5 6.5 0 0 0 10.5 10.5z" strokeLinejoin="round" />
    </svg>
  )
}
