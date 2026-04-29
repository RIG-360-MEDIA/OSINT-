'use client'

import { useEffect, useRef, useState } from 'react'

import { ClippingImage } from './ClippingImage'
import type { PaperSummary } from './Newsstand'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface Clipping {
  clipping_id: string
  newspaper_name: string
  newspaper_language: string
  edition_date: string | null
  page_number: number | null
  headline: string
  headline_translated: string | null
  text_preview: string | null
  translated_preview: string | null
  has_image: boolean
  relevance_score: number | null
  relevance_explanation: string | null
  collected_at: string
}

interface EditionModalProps {
  paper: PaperSummary
  clippings: Clipping[]
  loading: boolean
  error: string | null
  token: string | null
  onClose: () => void
}

export function EditionModal({
  paper, clippings, loading, error, token, onClose,
}: EditionModalProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const [showFullPdf, setShowFullPdf] = useState(false)
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null)
  const [pdfLoading, setPdfLoading] = useState(false)
  const [pdfError, setPdfError] = useState<string | null>(null)

  // ── Lock scroll on the body while modal is open. Pattern from coverage/page.tsx
  useEffect(() => {
    const scrollY = window.scrollY
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth
    document.body.style.position = 'fixed'
    document.body.style.top = `-${scrollY}px`
    document.body.style.left = '0'
    document.body.style.right = '0'
    document.body.style.overflow = 'hidden'
    document.body.style.paddingRight = `${scrollbarWidth}px`
    return () => {
      document.body.style.position = ''
      document.body.style.top = ''
      document.body.style.left = ''
      document.body.style.right = ''
      document.body.style.overflow = ''
      document.body.style.paddingRight = ''
      window.scrollTo(0, scrollY)
    }
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // ── Fetch PDF as blob (so Authorization header can be applied).
  useEffect(() => {
    if (!showFullPdf || pdfBlobUrl || !token) return
    let cancelled = false
    let blobUrl: string | null = null
    setPdfLoading(true)
    setPdfError(null)
    ;(async () => {
      try {
        const dateStr = paper.edition_date ?? new Date().toISOString().slice(0, 10)
        const r = await fetch(
          `${API_BASE}/api/newspapers/${paper.newspaper_id}/pdf?date=${dateStr}`,
          { headers: { Authorization: `Bearer ${token}` } },
        )
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const blob = await r.blob()
        blobUrl = URL.createObjectURL(blob)
        if (!cancelled) setPdfBlobUrl(blobUrl)
      } catch (err: unknown) {
        if (!cancelled) {
          setPdfError(
            err instanceof Error
              ? err.message
              : 'Could not load full edition',
          )
        }
      } finally {
        if (!cancelled) setPdfLoading(false)
      }
    })()
    return () => {
      cancelled = true
      if (blobUrl) URL.revokeObjectURL(blobUrl)
    }
  }, [showFullPdf, paper.edition_date, paper.newspaper_id, token, pdfBlobUrl])

  useEffect(() => {
    return () => {
      if (pdfBlobUrl) URL.revokeObjectURL(pdfBlobUrl)
    }
  }, [pdfBlobUrl])

  const editionLabel = paper.edition_date
    ? new Date(paper.edition_date).toLocaleDateString('en-IN', {
        day: '2-digit', month: 'short', year: 'numeric',
      }).toUpperCase()
    : ''

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="edition-modal-title"
      data-testid="edition-modal"
      onClick={e => {
        if (e.target === e.currentTarget) onClose()
      }}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'color-mix(in srgb, var(--rig-ink) 60%, transparent)',
        backdropFilter: 'blur(6px)',
        WebkitBackdropFilter: 'blur(6px)',
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '32px',
      }}
    >
      <div
        ref={panelRef}
        style={{
          width: '100%',
          maxWidth: '1100px',
          maxHeight: '85vh',
          background: 'var(--rig-paper)',
          border: '1px solid color-mix(in srgb, var(--rig-ink) 18%, transparent)',
          boxShadow: '0 24px 64px rgba(0,0,0,0.32)',
          borderRadius: '4px',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          position: 'relative',
        }}
      >
        {/* ── Dateline header ─────────────────────────────────────────────── */}
        <div
          style={{
            padding: '20px 28px',
            borderBottom: '1px solid color-mix(in srgb, var(--rig-ink) 14%, transparent)',
            display: 'flex',
            alignItems: 'baseline',
            justifyContent: 'space-between',
            gap: '20px',
            background:
              'linear-gradient(180deg, var(--rig-paper) 0%, var(--rig-paper-2) 100%)',
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div
              id="edition-modal-title"
              style={{
                fontFamily: 'var(--font-serif)',
                fontWeight: 700,
                fontStyle: 'italic',
                fontSize: '26px',
                lineHeight: 1.1,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                backgroundImage:
                  'linear-gradient(180deg, #1a1a1a 0%, #2d2d2d 38%, #6b6b6b 50%, #2d2d2d 62%, #0d0d0d 100%)',
                WebkitBackgroundClip: 'text',
                backgroundClip: 'text',
                color: 'transparent',
                textShadow:
                  '0 1px 0 rgba(255,255,255,0.55), 0 -1px 0 rgba(0,0,0,0.35)',
              }}
            >
              {paper.name}
            </div>
            <div
              style={{
                fontFamily: 'var(--font-sans-condensed)',
                fontSize: '11px',
                letterSpacing: '0.18em',
                color: 'var(--rig-ink-soft)',
                marginTop: '4px',
                textTransform: 'uppercase',
              }}
            >
              {editionLabel} · {clippings.length}{' '}
              {clippings.length === 1 ? 'cutting' : 'cuttings'}
            </div>
          </div>
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <button
              type="button"
              onClick={() => setShowFullPdf(s => !s)}
              data-testid="full-edition-button"
              style={{
                fontFamily: 'var(--font-sans-condensed)',
                fontSize: '11px',
                letterSpacing: '0.16em',
                textTransform: 'uppercase',
                padding: '8px 14px',
                background: showFullPdf ? 'var(--rig-ink)' : 'transparent',
                color: showFullPdf ? 'var(--rig-paper)' : 'var(--rig-ink)',
                border: '1px solid var(--rig-ink)',
                borderRadius: '2px',
                cursor: 'pointer',
              }}
            >
              {showFullPdf ? '× Hide edition' : 'Full edition ↗'}
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close edition"
              style={{
                fontFamily: 'var(--font-serif)',
                fontSize: '22px',
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                color: 'var(--rig-ink-soft)',
                padding: '0 6px',
              }}
            >
              ×
            </button>
          </div>
        </div>

        {/* ── Body: clippings grid + optional PDF pane ───────────────────── */}
        <div
          style={{
            flex: 1,
            position: 'relative',
            overflow: 'hidden',
            display: 'flex',
          }}
        >
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '24px 28px',
            }}
          >
            {loading ? (
              <div
                style={{
                  textAlign: 'center',
                  padding: '60px 20px',
                  fontFamily: 'var(--font-serif)',
                  fontStyle: 'italic',
                  color: 'var(--rig-ink-soft)',
                }}
              >
                Sorting cuttings from {paper.name}…
              </div>
            ) : error ? (
              <div
                style={{
                  textAlign: 'center',
                  padding: '60px 20px',
                  fontFamily: 'var(--font-serif)',
                  fontStyle: 'italic',
                  color: 'var(--rig-ink-soft)',
                }}
              >
                {error}
              </div>
            ) : clippings.length === 0 ? (
              <div
                style={{
                  textAlign: 'center',
                  padding: '60px 28px',
                  fontFamily: 'var(--font-serif)',
                  color: 'var(--rig-ink-soft)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '14px',
                  alignItems: 'center',
                }}
              >
                <div
                  style={{
                    fontFamily: 'var(--font-sans-condensed)',
                    fontSize: '11px',
                    letterSpacing: '0.2em',
                    textTransform: 'uppercase',
                  }}
                >
                  Desk memo
                </div>
                <div style={{ fontStyle: 'italic', fontSize: '20px' }}>
                  No cuttings filed for {paper.name} today.
                </div>
                <div style={{ maxWidth: '420px', lineHeight: 1.5, fontSize: '14px' }}>
                  Today&apos;s edition was scanned but nothing crossed your tracking
                  list. Open the full broadcast to read it cover to cover.
                </div>
              </div>
            ) : (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(420px, 1fr))',
                  gap: '20px',
                }}
              >
                {clippings.map(c => (
                  <ClippingCard key={c.clipping_id} clip={c} token={token} />
                ))}
              </div>
            )}
          </div>

          {showFullPdf ? (
            <div
              data-testid="full-edition-pane"
              style={{
                position: 'absolute',
                inset: 0,
                left: '33%',
                background: 'var(--rig-ink)',
                borderLeft: '1px solid color-mix(in srgb, var(--rig-ink) 30%, transparent)',
                boxShadow: '-12px 0 24px rgba(0,0,0,0.22)',
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              {pdfLoading ? (
                <div
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'var(--rig-paper)',
                    fontFamily: 'var(--font-serif)',
                    fontStyle: 'italic',
                  }}
                >
                  Pulling today&apos;s edition…
                </div>
              ) : pdfError ? (
                <div
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'var(--rig-paper)',
                    fontFamily: 'var(--font-serif)',
                    fontStyle: 'italic',
                    padding: '40px',
                    textAlign: 'center',
                  }}
                >
                  Could not load full edition: {pdfError}
                </div>
              ) : pdfBlobUrl ? (
                <iframe
                  data-testid="full-edition-iframe"
                  src={pdfBlobUrl}
                  title={`${paper.name} ${editionLabel}`}
                  style={{ flex: 1, width: '100%', border: 'none' }}
                />
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

// ── Bilingual clipping card ────────────────────────────────────────────────

interface ClippingCardProps {
  clip: Clipping
  token: string | null
}

function ClippingCard({ clip, token }: ClippingCardProps) {
  const isNonEnglish = clip.newspaper_language !== 'en'
  const summary =
    (isNonEnglish ? clip.translated_preview : clip.text_preview) ||
    clip.text_preview ||
    ''

  return (
    <article
      data-testid="clipping-card"
      data-language={clip.newspaper_language}
      style={{
        display: 'grid',
        gridTemplateColumns: '180px 1fr',
        gap: '16px',
        padding: '14px',
        background: 'var(--rig-paper-2)',
        border: '1px solid color-mix(in srgb, var(--rig-ink) 12%, transparent)',
        borderRadius: '3px',
      }}
    >
      <div
        style={{
          width: '180px',
          height: '220px',
          overflow: 'hidden',
          background: 'var(--rig-paper)',
          borderRight: '1px solid color-mix(in srgb, var(--rig-ink) 14%, transparent)',
        }}
      >
        <ClippingImage
          clippingId={clip.clipping_id}
          token={token}
          hasImage={clip.has_image}
          newspaperName={clip.newspaper_name}
        />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', minWidth: 0 }}>
        {isNonEnglish && clip.headline ? (
          <div
            data-testid="original-headline"
            style={{
              fontFamily: 'var(--font-serif)',
              fontSize: '13px',
              color: 'var(--rig-ink-soft)',
              lineHeight: 1.35,
            }}
          >
            {clip.headline}
          </div>
        ) : null}

        <div
          data-testid="primary-headline"
          style={{
            fontFamily: 'var(--font-serif)',
            fontSize: '17px',
            fontWeight: 700,
            lineHeight: 1.25,
            color: 'var(--rig-ink)',
          }}
        >
          {isNonEnglish
            ? clip.headline_translated || clip.headline
            : clip.headline}
        </div>

        {summary ? (
          <div
            style={{
              fontFamily: 'var(--font-serif)',
              fontSize: '13px',
              color: 'var(--rig-ink-soft)',
              lineHeight: 1.5,
              display: '-webkit-box',
              WebkitLineClamp: 3,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
          >
            {summary}
          </div>
        ) : null}

        {clip.relevance_explanation ? (
          <div
            data-testid="relation-block"
            style={{
              marginTop: '4px',
              padding: '8px 10px',
              background: 'color-mix(in srgb, var(--rig-gold) 12%, transparent)',
              borderLeft: '2px solid var(--rig-gold)',
              fontFamily: 'var(--font-sans-condensed)',
              fontSize: '11px',
              color: 'var(--rig-ink)',
              lineHeight: 1.5,
            }}
          >
            <span style={{ letterSpacing: '0.18em', fontWeight: 600 }}>WHY: </span>
            {clip.relevance_explanation}
          </div>
        ) : null}
      </div>
    </article>
  )
}
