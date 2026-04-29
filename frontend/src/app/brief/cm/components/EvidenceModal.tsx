'use client'

import { ReactNode, useEffect } from 'react'

interface EvidenceModalProps {
  open: boolean
  onClose: () => void
  title: string
  kicker?: string
  children: ReactNode
}

/** Center-modal dialog used by every CM section's drill-down. */
export function EvidenceModal({ open, onClose, title, kicker, children }: EvidenceModalProps) {
  useEffect(() => {
    if (!open) return undefined
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', handler)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 80,
        background: 'rgba(10, 7, 6, 0.62)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--rig-paper)',
          maxWidth: 920,
          width: '100%',
          maxHeight: '88vh',
          overflowY: 'auto',
          padding: '32px',
          border: '1px solid var(--rig-ink-4)',
          boxShadow: '0 18px 48px rgba(0,0,0,0.32)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginBottom: 14 }}>
          {kicker && (
            <span className="rig-byline" style={{ color: 'var(--rig-gold)' }}>
              {kicker}
            </span>
          )}
          <h3 className="rig-headline" style={{ fontSize: 24, margin: 0 }}>
            <em>{title}</em>
          </h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rig-byline"
            style={{
              marginLeft: 'auto',
              background: 'transparent',
              border: '1px solid var(--rig-ink-4)',
              padding: '4px 10px',
              cursor: 'pointer',
              color: 'var(--rig-ink-2)',
            }}
          >
            esc · close
          </button>
        </div>
        <hr className="rig-rule-hair" style={{ marginBottom: 18 }} />
        {children}
      </div>
    </div>
  )
}

export default EvidenceModal
