import { useCallback, useEffect, useRef, useState } from 'react'

import {
  API_BASE,
  GEO_KICKER,
  URGENCY_TONE,
  formatShortDate,
} from '../lib/constants'
import type { DocumentItem } from '../lib/types'

import { TagChip } from './TagChip'

interface DocumentDialogProps {
  doc: DocumentItem
  token: string
  onClose: () => void
  onInvestigate: () => void
  onSummaryUpdated: (summary: string) => void
}

export function DocumentDialog({
  doc,
  token,
  onClose,
  onInvestigate,
  onSummaryUpdated,
}: DocumentDialogProps) {
  const [summary, setSummary] = useState<string | null>(doc.summary)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summaryError, setSummaryError] = useState<string | null>(null)

  const dialogRef = useRef<HTMLElement | null>(null)
  const previouslyFocused = useRef<HTMLElement | null>(null)

  // D-10 + Q10: Esc closes the modal; focus is moved into the dialog on
  // mount and restored to the row that opened it on unmount; Tab is
  // trapped inside the dialog so keyboard users cannot wander into the
  // background page.
  useEffect(() => {
    previouslyFocused.current = document.activeElement as HTMLElement | null
    dialogRef.current?.focus()

    const FOCUSABLE_SELECTOR =
      'a[href], button:not([disabled]), textarea:not([disabled]), ' +
      'input:not([disabled]):not([type="hidden"]), select:not([disabled]), ' +
      '[tabindex]:not([tabindex="-1"])'

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key !== 'Tab') return
      const root = dialogRef.current
      if (!root) return
      const focusable = Array.from(
        root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter(el => !el.hasAttribute('aria-hidden'))
      if (focusable.length === 0) {
        // No focusable content yet — keep focus on the dialog itself.
        e.preventDefault()
        root.focus()
        return
      }
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement as HTMLElement | null
      if (e.shiftKey && (active === first || active === root)) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && active === last) {
        e.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      previouslyFocused.current?.focus?.()
    }
  }, [onClose])

  const generateSummary = useCallback(async () => {
    setSummaryLoading(true)
    setSummaryError(null)
    try {
      const res = await fetch(`${API_BASE}/api/documents/${doc.doc_id}/summary`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        setSummaryError('Summary generation failed.')
        return
      }
      const data = (await res.json()) as { summary: string }
      setSummary(data.summary)
      onSummaryUpdated(data.summary)
    } catch {
      setSummaryError('Summary generation failed.')
    } finally {
      setSummaryLoading(false)
    }
  }, [doc.doc_id, token, onSummaryUpdated])

  const urgencyTone = doc.urgency ? URGENCY_TONE[doc.urgency] : null

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'color-mix(in srgb, var(--rig-ink) 45%, transparent)',
        backdropFilter: 'blur(3px)',
        zIndex: 300,
      }}
    >
      <aside
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={doc.title}
        tabIndex={-1}
        onClick={e => e.stopPropagation()}
        className="anim-slide-right"
        style={{
          position: 'fixed',
          top: 'var(--topbar-h)',
          right: 0,
          width: '580px',
          maxWidth: '100vw',
          height: 'calc(100vh - var(--topbar-h))',
          background: 'var(--rig-paper)',
          borderLeft: '1px solid var(--rig-rule)',
          boxShadow: '-8px 0 32px color-mix(in srgb, var(--rig-ink) 10%, transparent)',
          overflowY: 'auto',
          outline: 'none',
        }}
      >
        {/* Head */}
        <div
          style={{
            position: 'sticky',
            top: 0,
            background: 'var(--rig-paper-2)',
            borderBottom: '1px solid var(--rig-rule-hair)',
            padding: '18px 28px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            zIndex: 2,
          }}
        >
          <span className="rig-kicker">On the desk</span>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{
              background: 'none',
              border: '1px solid var(--rig-rule)',
              cursor: 'pointer',
              width: '28px',
              height: '28px',
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              fontSize: '16px',
              color: 'var(--rig-ink-2)',
              lineHeight: 1,
            }}
          >
            ×
          </button>
        </div>

        <div style={{ padding: '28px 32px 48px' }}>
          {/* Kickers */}
          <div
            className="rig-byline"
            style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', marginBottom: '14px' }}
          >
            <span style={{ color: 'var(--rig-copper)' }}>
              {GEO_KICKER[doc.source_geography] ?? doc.source_geography}
            </span>
            <span aria-hidden="true" style={{ opacity: 0.4 }}>·</span>
            <span>{doc.document_type.replace(/_/g, ' ')}</span>
            {doc.urgency && (
              <>
                <span aria-hidden="true" style={{ opacity: 0.4 }}>·</span>
                <span
                  className="rig-chip"
                  data-tone={urgencyTone === 'default' ? undefined : urgencyTone ?? undefined}
                >
                  <span className="dot" />
                  {doc.urgency} urgency
                </span>
              </>
            )}
          </div>

          {/* Title */}
          <h2
            className="rig-headline"
            style={{
              fontSize: '26px',
              lineHeight: 1.25,
              color: 'var(--rig-ink)',
              margin: 0,
              marginBottom: '10px',
            }}
          >
            {doc.title}
          </h2>

          {/* Source line */}
          <div
            className="rig-byline"
            style={{ marginBottom: '24px' }}
          >
            <span style={{ textTransform: 'none', letterSpacing: 'normal', fontSize: '13px' }}>
              {doc.source_name}
            </span>
            <span aria-hidden="true" style={{ margin: '0 8px', opacity: 0.4 }}>·</span>
            <span>Filed {formatShortDate(doc.collected_at)}</span>
          </div>

          {/* Why This Matters */}
          {doc.why_it_matters && (
            <div
              style={{
                borderLeft: '2px solid var(--rig-gold)',
                background: 'color-mix(in srgb, var(--rig-gold) 7%, transparent)',
                padding: '14px 18px',
                marginBottom: '20px',
              }}
            >
              <div
                className="rig-kicker"
                style={{ color: 'var(--rig-copper)', marginBottom: '6px' }}
              >
                Why this matters to you
              </div>
              <p
                style={{
                  margin: 0,
                  fontFamily: 'var(--font-serif)',
                  fontStyle: 'italic',
                  fontSize: '15px',
                  lineHeight: 1.55,
                  color: 'var(--rig-ink)',
                }}
              >
                {doc.why_it_matters}
              </p>
            </div>
          )}

          {/* Suggested action */}
          {doc.suggested_action && (
            <div
              style={{
                marginBottom: '20px',
                paddingBottom: '18px',
                borderBottom: '1px solid var(--rig-rule-hair)',
              }}
            >
              <div className="rig-kicker" style={{ marginBottom: '4px' }}>
                Suggested action
              </div>
              <div
                style={{
                  fontFamily: 'var(--font-serif)',
                  fontSize: '14px',
                  color: 'var(--rig-ink-2)',
                  lineHeight: 1.5,
                }}
              >
                {doc.suggested_action}
              </div>
            </div>
          )}

          {/* Summary */}
          {!summary && !summaryLoading && !summaryError && (
            <button
              onClick={generateSummary}
              className="rig-btn-ghost"
              style={{ marginBottom: '20px' }}
            >
              ✦ Commission a summary
            </button>
          )}

          {summaryLoading && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                marginBottom: '20px',
                padding: '10px 0',
              }}
            >
              <span
                className="rig-headline"
                style={{
                  fontStyle: 'italic',
                  fontSize: '16px',
                  color: 'var(--rig-ink-2)',
                }}
              >
                Reading and condensing…
              </span>
            </div>
          )}

          {summaryError && !summaryLoading && (
            <div style={{ marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span
                style={{
                  fontFamily: 'var(--font-serif)',
                  fontStyle: 'italic',
                  fontSize: '14px',
                  color: 'var(--rig-oxblood)',
                }}
              >
                {summaryError}
              </span>
              <button onClick={generateSummary} className="rig-btn-ghost">
                Retry
              </button>
            </div>
          )}

          {summary && (
            <div
              style={{
                marginBottom: '24px',
                padding: '16px 18px',
                background: 'var(--rig-paper-2)',
                border: '1px solid var(--rig-rule-hair)',
              }}
            >
              <div className="rig-kicker" style={{ marginBottom: '8px' }}>
                Summary
              </div>
              <p
                style={{
                  margin: 0,
                  fontFamily: 'var(--font-serif)',
                  fontSize: '15px',
                  lineHeight: 1.7,
                  color: 'var(--rig-ink)',
                }}
              >
                {summary}
              </p>
            </div>
          )}

          {/* Preview fallback */}
          {doc.summary_preview && !summary && (
            <p
              style={{
                fontFamily: 'var(--font-serif)',
                fontSize: '15px',
                lineHeight: 1.7,
                color: 'var(--rig-ink-2)',
                marginBottom: '24px',
              }}
            >
              {doc.summary_preview}
              {doc.summary_preview.length >= 400 ? '…' : ''}
            </p>
          )}

          {/* Meta row */}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '6px',
              paddingTop: '16px',
              marginTop: '8px',
              borderTop: '1px solid var(--rig-rule-hair)',
              marginBottom: '22px',
            }}
          >
            {doc.topic_category && <TagChip label={doc.topic_category} />}
            {doc.geo_primary && <TagChip label={doc.geo_primary} />}
            {doc.page_count && <TagChip label={`${doc.page_count} pages`} />}
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            <a
              href={doc.document_url}
              target="_blank"
              rel="noopener noreferrer"
              className="rig-btn-primary"
              style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}
            >
              Read the document ↗
            </a>
            <button onClick={onInvestigate} className="rig-btn-ghost">
              Take to Analyst →
            </button>
          </div>
        </div>
      </aside>
    </div>
  )
}
