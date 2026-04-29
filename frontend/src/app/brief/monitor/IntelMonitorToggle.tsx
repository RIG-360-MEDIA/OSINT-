'use client'

import type { ReactElement } from 'react'

export type BriefView = 'intel' | 'monitor' | 'cm'

interface IntelMonitorToggleProps {
  view: BriefView
  onChange: (next: BriefView) => void
}

interface Segment {
  view: BriefView
  label: string
  Glyph: (props: { active: boolean }) => ReactElement
}

const SEGMENTS: Segment[] = [
  { view: 'intel',   label: 'Intelligence', Glyph: GlyphBook    },
  { view: 'monitor', label: 'Monitoring',   Glyph: GlyphPulse   },
  { view: 'cm',      label: 'CM Room',      Glyph: GlyphCompass },
]

export function IntelMonitorToggle({ view, onChange }: IntelMonitorToggleProps) {
  return (
    <div
      role="tablist"
      aria-label="Brief view"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        background: 'transparent',
        border: '1px solid var(--rig-rule)',
        overflow: 'hidden',
      }}
    >
      {SEGMENTS.map(({ view: v, label, Glyph }, i) => {
        const active = view === v
        return (
          <button
            key={v}
            type="button"
            role="tab"
            aria-selected={active}
            aria-label={`Switch to ${label}`}
            title={`Switch to ${label}`}
            onClick={() => {
              if (!active) onChange(v)
            }}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              padding: '6px 12px',
              background: active ? 'var(--rig-ink)' : 'transparent',
              color: active ? 'var(--rig-paper)' : 'var(--rig-ink-2)',
              border: 'none',
              borderLeft: i === 0 ? 'none' : '1px solid var(--rig-rule)',
              fontFamily: 'var(--font-mono)',
              fontSize: '10px',
              letterSpacing: '0.24em',
              textTransform: 'uppercase',
              cursor: active ? 'default' : 'pointer',
              transition: 'background 0.18s, color 0.18s',
            }}
            onMouseEnter={(e) => {
              if (!active) e.currentTarget.style.color = 'var(--rig-ink)'
            }}
            onMouseLeave={(e) => {
              if (!active) e.currentTarget.style.color = 'var(--rig-ink-2)'
            }}
          >
            <Glyph active={active} />
            <span>{label}</span>
          </button>
        )
      })}
    </div>
  )
}

function GlyphBook({ active }: { active: boolean }) {
  return (
    <svg
      width="12" height="12" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="1.4"
      style={{ opacity: active ? 1 : 0.55 }}
      aria-hidden="true"
    >
      <path d="M4 4 h7 a3 3 0 0 1 3 3 v13 a3 3 0 0 0 -3 -3 H4 z" strokeLinejoin="round" />
      <path d="M20 4 h-3 a3 3 0 0 0 -3 3 v13 a3 3 0 0 1 3 -3 h3 z" strokeLinejoin="round" />
    </svg>
  )
}

function GlyphPulse({ active }: { active: boolean }) {
  return (
    <svg
      width="12" height="12" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="1.4"
      style={{ opacity: active ? 1 : 0.55 }}
      aria-hidden="true"
    >
      <path d="M2 12 H7 L9 6 L13 18 L15 12 H22" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function GlyphCompass({ active }: { active: boolean }) {
  return (
    <svg
      width="12" height="12" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="1.4"
      style={{ opacity: active ? 1 : 0.55 }}
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" />
      <path
        d="M12 3 L13.5 11 L21 12 L13.5 13 L12 21 L10.5 13 L3 12 L10.5 11 Z"
        fill="currentColor"
        stroke="none"
        opacity="0.85"
      />
    </svg>
  )
}
