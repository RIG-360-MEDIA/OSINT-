/**
 * /coverage — the new Coverage Hub.
 *
 * Replaces the previous articles-list page (which moved to /coverage/articles).
 * Five equal panels in a 3-on-top, 2-on-bottom editorial grid. Each panel is
 * a portal into its full archive; clicking routes to the existing pillar
 * pages (untouched, scheduled for migration one-by-one later).
 *
 * Theme: opt-in `data-theme="onyx"` on the page wrapper — does not affect
 * the rest of the site, which stays parchment until each page is migrated.
 */

'use client'

import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'
import { OnyxTopBar } from '@/components/coverage/OnyxTopBar'
import { CoveragePanel, type CoveragePanelData } from '@/components/coverage/CoveragePanel'
import { LiveTicker } from '@/components/coverage/LiveTicker'
import { ParticleField } from '@/components/coverage/ParticleField'
import { GrainOverlay } from '@/components/coverage/GrainOverlay'
import type { CoverageSlug } from '@/components/coverage/thumbnails'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

/** Static panel definitions — name + destination. Data merged in at runtime. */
const PANELS: ReadonlyArray<Pick<CoveragePanelData, 'slug' | 'name' | 'href'>> = [
  { slug: 'articles',  name: 'Articles',  href: '/coverage/articles' },
  { slug: 'newspaper', name: 'Newspaper', href: '/cuttings' },
  { slug: 'tv',        name: 'TV',        href: '/clips' },
  { slug: 'social',    name: 'Social',    href: '/signals' },
  { slug: 'govt',      name: 'Govt Docs', href: '/documents' },
]

interface PanelsApiResponse {
  panels: Array<{
    slug: CoverageSlug
    total_count: number
    new_count: number
    latest: { title: string; collected_at: string } | null
    summary: string
  }>
}

/** Fallback summaries shown until backend responds (or if Groq is down) */
const FALLBACK_SUMMARY: Record<CoverageSlug, string> = {
  articles:  'A continuous stream of regional and national reporting, scraped from RSS feeds and direct sources, ranked by per-user relevance.',
  newspaper: 'Daily editions filed from print and e-paper sources, archived as searchable text and original layout.',
  tv:        'Broadcast clips and long-form interviews — transcripts and key moments indexed alongside their video.',
  social:    'Reddit and Telegram signals, translated when needed, clustered by topic and weighted by community velocity.',
  govt:      'Official orders, circulars, and gazettes from central, state, and district authorities — parsed, chunked, and citable.',
}

const buildInitialPanels = (): CoveragePanelData[] =>
  PANELS.map((p) => ({
    ...p,
    totalCount: 0,
    newCount: 0,
    latest: null,
    summary: FALLBACK_SUMMARY[p.slug],
    loading: true,
  }))

export default function CoveragePage() {
  const [panels, setPanels] = useState<CoveragePanelData[]>(() => buildInitialPanels())

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      try {
        const supabase = createClient()
        const { data: { session } } = await supabase.auth.getSession()
        const token = session?.access_token
        if (!token) {
          if (!cancelled) setPanels((prev) => prev.map((p) => ({ ...p, loading: false })))
          return
        }
        const res = await fetch(`${API_BASE}/api/coverage/panels`, {
          headers: { Authorization: `Bearer ${token}` },
          cache: 'no-store',
        })
        if (!res.ok) {
          // Backend not ready or auth missing — keep fallback
          if (!cancelled) {
            setPanels((prev) => prev.map((p) => ({ ...p, loading: false })))
          }
          return
        }
        const json = (await res.json()) as PanelsApiResponse
        if (cancelled) return
        const bySlug = new Map(json.panels.map((p) => [p.slug, p]))
        setPanels((prev) =>
          prev.map((p) => {
            const live = bySlug.get(p.slug)
            if (!live) return { ...p, loading: false }
            return {
              ...p,
              totalCount: live.total_count,
              newCount: live.new_count,
              latest: live.latest
                ? { title: live.latest.title, collectedAt: live.latest.collected_at }
                : null,
              summary: live.summary || FALLBACK_SUMMARY[p.slug],
              loading: false,
            }
          })
        )
      } catch {
        if (!cancelled) {
          setPanels((prev) => prev.map((p) => ({ ...p, loading: false })))
        }
      }
    }

    load()
    // Refresh every 5 minutes — counts and latest tick over time
    const id = setInterval(load, 5 * 60 * 1000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  return (
    <>
      <OnyxTopBar />
    <div
      data-theme="onyx"
      style={{
        position: 'relative',
        minHeight: '100vh',
        paddingTop: 'var(--topbar-h)',
        background: 'var(--onyx-bg)',
        color: 'var(--onyx-bone)',
        fontFamily: 'var(--onyx-display)',
        overflow: 'hidden',
      }}
    >
      <ParticleField />
      <GrainOverlay />

      {/* ── Header ───────────────────────────────────────────────────── */}
      <div
        style={{
          position: 'relative',
          zIndex: 10,
          padding: '64px 48px 0',
          maxWidth: '1480px',
          margin: '0 auto',
        }}
      >
        <h1
          className="onyx-display onyx-display-tight onyx-fade-up"
          style={{
            fontSize: 'clamp(28px, 3vw, 36px)',
            fontWeight: 500,
            lineHeight: 1,
            margin: 0,
            color: 'var(--onyx-bone)',
          }}
        >
          Coverage
        </h1>
        <div
          className="onyx-mono onyx-fade-up"
          style={{
            fontSize: '10px',
            letterSpacing: '0.32em',
            textTransform: 'uppercase',
            color: 'var(--onyx-dim)',
            marginTop: '12px',
            animationDelay: '120ms',
          }}
        >
          five intelligence streams · live archive
        </div>
        <hr className="onyx-hairline" style={{ marginTop: '20px' }} />
        <LiveTicker />
      </div>

      {/* ── Five-panel grid ──────────────────────────────────────────── */}
      <div
        style={{
          position: 'relative',
          zIndex: 10,
          padding: '0 48px 96px',
          maxWidth: '1480px',
          margin: '0 auto',
        }}
      >
        <div
          className="coverage-grid"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: '24px',
          }}
        >
          {panels.slice(0, 3).map((p, i) => (
            <div
              key={p.slug}
              style={{ animationDelay: `${i * 80 + 200}ms` }}
            >
              <CoveragePanel data={p} />
            </div>
          ))}
        </div>
        <div
          className="coverage-grid coverage-grid-bottom"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(2, 1fr)',
            gap: '24px',
            marginTop: '24px',
            maxWidth: '66%',
            marginLeft: 'auto',
            marginRight: 'auto',
          }}
        >
          {panels.slice(3, 5).map((p, i) => (
            <div
              key={p.slug}
              style={{ animationDelay: `${(i + 3) * 80 + 200}ms` }}
            >
              <CoveragePanel data={p} />
            </div>
          ))}
        </div>
      </div>

      {/* Responsive collapse — single column on mobile */}
      <style>{`
        @media (max-width: 980px) {
          .coverage-grid {
            grid-template-columns: 1fr !important;
          }
          .coverage-grid-bottom {
            max-width: 100% !important;
          }
        }
        @media (max-width: 1280px) and (min-width: 981px) {
          .coverage-grid:not(.coverage-grid-bottom) {
            grid-template-columns: repeat(2, 1fr) !important;
          }
        }
      `}</style>
    </div>
    </>
  )
}
