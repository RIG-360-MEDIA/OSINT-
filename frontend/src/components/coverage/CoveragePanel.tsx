/**
 * CoveragePanel — single panel in the Coverage hub grid.
 *
 * Layout (top → bottom):
 *   1. Thumbnail (procedural SVG, 55% of panel height)
 *      - bottom 15% strip overlays the latest headline + relative timestamp
 *   2. Single 1px red hairline divider
 *   3. Section name in Space Grotesk display
 *   4. Mono metadata row: count · new · last update
 *   5. Italic Instrument Serif summary paragraph (LLM-generated daily)
 *   6. ENTER → indicator bottom-right
 *
 * Interaction:
 *   - Cursor-tracking cyan halo (CSS var --mx, --my updated on mousemove)
 *   - Border glows cyan, scanline sweeps once per hover entry
 *   - Click navigates via Next router to the destination route
 *
 * The scanline element is in the DOM permanently; CSS animates it on
 * :hover so we get a fresh sweep every time the cursor enters.
 */

'use client'

import { useRouter } from 'next/navigation'
import { useCallback, useRef, type MouseEvent } from 'react'
import { CoverageThumb, type CoverageSlug } from './thumbnails'

export interface CoveragePanelData {
  slug: CoverageSlug
  /** Display name, e.g. "Articles" */
  name: string
  /** Destination route on click, e.g. "/coverage/articles" */
  href: string
  /** Total indexed count for this stream */
  totalCount: number
  /** Items added in the last 24h */
  newCount: number
  /** Most recent item — title + timestamp ISO string */
  latest: {
    title: string
    collectedAt: string  // ISO 8601
  } | null
  /** LLM-generated daily summary (2-3 lines) */
  summary: string
  /** Loading state */
  loading?: boolean
}

interface Props {
  data: CoveragePanelData
}

const formatTimeAgo = (iso: string): string => {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

const formatCount = (n: number): string => {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

export function CoveragePanel({ data }: Props) {
  const router = useRouter()
  const ref = useRef<HTMLDivElement>(null)

  const onMouseMove = useCallback((e: MouseEvent<HTMLDivElement>) => {
    const el = ref.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * 100
    const y = ((e.clientY - rect.top) / rect.height) * 100
    el.style.setProperty('--mx', `${x}%`)
    el.style.setProperty('--my', `${y}%`)
  }, [])

  const onClick = useCallback(() => {
    router.push(data.href)
  }, [router, data.href])

  const onKeyDown = useCallback((e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      router.push(data.href)
    }
  }, [router, data.href])

  return (
    <div
      ref={ref}
      className="onyx-panel onyx-fade-up"
      role="link"
      tabIndex={0}
      onMouseMove={onMouseMove}
      onClick={onClick}
      onKeyDown={onKeyDown}
      aria-label={`${data.name} — ${formatCount(data.totalCount)} indexed`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: 0,
      }}
    >
      {/* Scanline (CSS animates on parent :hover) */}
      <span className="onyx-scanline" />

      {/* ── 1. Thumbnail with latest-headline overlay ────────────────── */}
      <div
        style={{
          position: 'relative',
          aspectRatio: '5 / 3',
          flexShrink: 0,
          borderBottom: '1px solid var(--onyx-rule-dim)',
          overflow: 'hidden',
        }}
      >
        <CoverageThumb slug={data.slug} />

        {/* Latest-headline strip (bottom 22% of thumbnail) */}
        {data.latest && (
          <div
            style={{
              position: 'absolute',
              left: 0, right: 0, bottom: 0,
              padding: '10px 14px 12px',
              background: 'linear-gradient(to top, rgba(0,0,0,0.95) 0%, rgba(0,0,0,0.7) 70%, transparent 100%)',
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
              zIndex: 2,
            }}
          >
            <div
              className="onyx-mono"
              style={{
                fontSize: '9px',
                letterSpacing: '0.22em',
                textTransform: 'uppercase',
                color: 'var(--onyx-cyan)',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <span className="onyx-live-dot" style={{ display: 'inline-block' }} />
              LATEST · {formatTimeAgo(data.latest.collectedAt)}
            </div>
            <div
              style={{
                fontFamily: 'var(--onyx-display)',
                fontSize: '12px',
                fontWeight: 400,
                color: 'var(--onyx-bone)',
                letterSpacing: '0.005em',
                lineHeight: 1.35,
                overflow: 'hidden',
                display: '-webkit-box',
                WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical',
              }}
            >
              {data.latest.title}
            </div>
          </div>
        )}
      </div>

      {/* ── 2. Red hairline divider ─────────────────────────────────── */}
      <hr className="onyx-hairline" style={{ margin: 0 }} />

      {/* ── 3. Body ──────────────────────────────────────────────────── */}
      <div
        style={{
          padding: '20px 22px 22px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
          flex: 1,
          minHeight: 0,
          position: 'relative',
          zIndex: 2,
        }}
      >
        {/* Section name */}
        <div
          className="onyx-display onyx-display-tight"
          style={{
            fontSize: '28px',
            fontWeight: 500,
            lineHeight: 1,
          }}
        >
          {data.name}
        </div>

        {/* Mono metadata row */}
        <div
          className="onyx-mono"
          style={{
            fontSize: '10px',
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            flexWrap: 'wrap',
          }}
        >
          <span style={{ color: 'var(--onyx-bone-2)' }}>
            {formatCount(data.totalCount)} indexed
          </span>
          <span style={{ opacity: 0.4 }}>·</span>
          <span style={{ color: data.newCount > 0 ? 'var(--onyx-cyan)' : 'var(--onyx-dim)' }}>
            {data.newCount} new
          </span>
        </div>

        {/* Italic summary */}
        <p
          className="onyx-italic"
          style={{
            fontSize: '15px',
            lineHeight: 1.55,
            color: 'var(--onyx-bone-2)',
            margin: 0,
            flex: 1,
            display: '-webkit-box',
            WebkitLineClamp: 4,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {data.loading ? '…' : data.summary}
        </p>

        {/* ENTER → */}
        <div
          className="onyx-mono"
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            alignItems: 'center',
            gap: '6px',
            fontSize: '10px',
            letterSpacing: '0.32em',
            textTransform: 'uppercase',
            color: 'var(--onyx-dim)',
            transition: 'color 0.4s ease, transform 0.4s ease',
            marginTop: '4px',
          }}
        >
          <span className="onyx-panel-enter-label">ENTER</span>
          <span className="onyx-panel-enter-arrow">→</span>
        </div>
      </div>

    </div>
  )
}
