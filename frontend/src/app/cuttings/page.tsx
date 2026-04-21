'use client'

import { useCallback, useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'
import Navigation from '@/components/Navigation'
import { formatTimeAgo } from '@/lib/domainColor'

// ─── Types ──────────────────────────────────────────────────────────────

interface Clipping {
  clipping_id: string
  newspaper_name: string
  newspaper_language: string
  edition_date: string | null
  page_number: number | null
  headline: string
  headline_translated: string | null
  text_preview: string
  translated_preview: string | null
  has_image: boolean
  relevance_score: number
  relevance_explanation: string | null
  collected_at: string
}

interface NewspaperSummary {
  name: string
  language: string
  count: number
}

interface FeedResponse {
  clippings: Clipping[]
  has_more: boolean
  next_cursor: string | null
  newspapers: NewspaperSummary[]
}

type LangFilter = 'all' | 'en' | 'te'

// ─── Constants ──────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const CLIPPING_RED = '#8B1A1A'
const ACCENT_AMBER = '#F59E0B'
const ACCENT_PALE = '#FFFBEB'
const TEXT_PRIMARY = '#18181B'
const TEXT_SECONDARY = '#52525B'
const TEXT_TERTIARY = '#A1A1AA'
const BORDER = '#E2E8F0'
const DIVERGENCE_ROSE = '#F43F5E'

function newspaperInitials(name: string): string {
  return name
    .split(/\s+/)
    .map((w) => w[0])
    .join('')
    .slice(0, 3)
    .toUpperCase()
}

function normalizeHeadline(h: string): string {
  return (h || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
}

// Group clippings: adjacent entries with matching edition_date + similar
// normalized headline from different papers form a divergence group.
interface ClippingGroup {
  key: string
  divergence: boolean
  clippings: Clipping[]
}

function groupForDivergence(clippings: Clipping[]): ClippingGroup[] {
  const buckets = new Map<string, Clipping[]>()
  for (const c of clippings) {
    const key = `${c.edition_date ?? 'x'}::${normalizeHeadline(
      c.headline_translated || c.headline,
    ).slice(0, 40)}`
    const arr = buckets.get(key) ?? []
    arr.push(c)
    buckets.set(key, arr)
  }
  const groups: ClippingGroup[] = []
  for (const c of clippings) {
    const key = `${c.edition_date ?? 'x'}::${normalizeHeadline(
      c.headline_translated || c.headline,
    ).slice(0, 40)}`
    const bucket = buckets.get(key)
    if (!bucket) continue
    if (groups.find((g) => g.key === key)) continue
    const distinctPapers = new Set(bucket.map((b) => b.newspaper_name)).size
    groups.push({
      key,
      divergence: bucket.length > 1 && distinctPapers > 1,
      clippings: bucket,
    })
  }
  return groups
}

// ─── Clipping image (lazy fetch) ────────────────────────────────────────

interface ClippingImageProps {
  clippingId: string
  token: string | null
  hasImage: boolean
  newspaperName: string
}

function ClippingImage({
  clippingId,
  token,
  hasImage,
  newspaperName,
}: ClippingImageProps) {
  const [imgB64, setImgB64] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    if (!hasImage || !token) {
      setFailed(true)
      return
    }
    const run = async () => {
      try {
        const r = await fetch(
          `${API_BASE}/api/clippings/${clippingId}/image`,
          { headers: { Authorization: `Bearer ${token}` } },
        )
        if (!r.ok) {
          if (!cancelled) setFailed(true)
          return
        }
        const data = (await r.json()) as { image_b64: string | null }
        if (!cancelled) {
          if (data.image_b64) setImgB64(data.image_b64)
          else setFailed(true)
        }
      } catch {
        if (!cancelled) setFailed(true)
      }
    }
    run()
    return () => {
      cancelled = true
    }
  }, [clippingId, token, hasImage])

  if (imgB64) {
    return (
      <img
        src={`data:image/png;base64,${imgB64}`}
        alt={`${newspaperName} clipping`}
        style={{
          width: '100%',
          maxHeight: '200px',
          objectFit: 'cover',
          border: `2px solid ${CLIPPING_RED}`,
          borderRadius: '2px',
          display: 'block',
        }}
      />
    )
  }

  // Fallback tile — newspaper initials on amber gradient
  return (
    <div
      style={{
        width: '100%',
        height: '180px',
        background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
        border: `2px solid ${CLIPPING_RED}`,
        borderRadius: '2px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#FFFFFF',
        fontFamily: "'Playfair Display', serif",
        fontWeight: 700,
        fontSize: '42px',
        letterSpacing: '0.02em',
      }}
    >
      {newspaperInitials(newspaperName)}
      {failed ? null : null}
    </div>
  )
}

// ─── Clipping card ──────────────────────────────────────────────────────

interface ClippingCardProps {
  clipping: Clipping
  token: string | null
}

function ClippingCard({ clipping, token }: ClippingCardProps) {
  const headlineDisplay =
    clipping.headline_translated || clipping.headline
  const bodyDisplay =
    clipping.translated_preview || clipping.text_preview || ''
  const timeAgo = formatTimeAgo(clipping.collected_at)

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '220px 1fr',
        gap: '18px',
        padding: '18px',
        backgroundColor: '#FFFFFF',
        border: `1px solid ${BORDER}`,
        borderRadius: '6px',
        marginBottom: '12px',
      }}
    >
      {/* Left: clipping image */}
      <div>
        <ClippingImage
          clippingId={clipping.clipping_id}
          token={token}
          hasImage={clipping.has_image}
          newspaperName={clipping.newspaper_name}
        />
      </div>

      {/* Right: metadata + text */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {/* Source line */}
        <div
          style={{
            fontFamily: "'DM Mono', ui-monospace, monospace",
            fontSize: '11px',
            color: TEXT_TERTIARY,
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
          }}
        >
          {clipping.newspaper_name}
          {clipping.page_number ? ` · Page ${clipping.page_number}` : ''}
          {clipping.edition_date ? ` · ${clipping.edition_date}` : ''}
          {timeAgo ? ` · ${timeAgo}` : ''}
        </div>

        {/* Headline */}
        <div
          style={{
            fontFamily: "'Playfair Display', serif",
            fontSize: '17px',
            fontWeight: 700,
            lineHeight: 1.25,
            color: TEXT_PRIMARY,
          }}
        >
          {headlineDisplay}
        </div>

        {/* Original (if translated is shown and different) */}
        {clipping.headline_translated &&
          clipping.headline_translated !== clipping.headline && (
            <div
              style={{
                fontFamily: "'Playfair Display', serif",
                fontStyle: 'italic',
                fontSize: '13px',
                color: TEXT_TERTIARY,
                lineHeight: 1.35,
              }}
            >
              {clipping.headline}
            </div>
          )}

        {/* Preview text */}
        <div
          style={{
            fontFamily: "'DM Sans', system-ui, sans-serif",
            fontSize: '13px',
            lineHeight: 1.5,
            color: TEXT_SECONDARY,
          }}
        >
          {bodyDisplay}
          {bodyDisplay.length >= 280 ? '…' : ''}
        </div>

        {/* WHY THIS MATTERS */}
        {clipping.relevance_explanation && (
          <div
            style={{
              backgroundColor: ACCENT_PALE,
              borderLeft: `4px solid ${ACCENT_AMBER}`,
              padding: '8px 12px',
              borderRadius: '3px',
            }}
          >
            <div
              style={{
                fontFamily: "'DM Mono', ui-monospace, monospace",
                fontSize: '10px',
                color: '#B45309',
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                marginBottom: '4px',
              }}
            >
              Why this matters
            </div>
            <div
              style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: '12px',
                color: TEXT_PRIMARY,
                lineHeight: 1.45,
              }}
            >
              {clipping.relevance_explanation}
            </div>
          </div>
        )}

        {/* Score chip */}
        <div
          style={{
            fontFamily: "'DM Mono', ui-monospace, monospace",
            fontSize: '11px',
            color: '#2563EB',
            marginTop: 'auto',
          }}
        >
          score {clipping.relevance_score.toFixed(2)}
          {clipping.newspaper_language !== 'en'
            ? ` · ${clipping.newspaper_language.toUpperCase()}`
            : ''}
        </div>
      </div>
    </div>
  )
}

// ─── Divergence strip ───────────────────────────────────────────────────

function DivergenceStrip({ clippings }: { clippings: Clipping[] }) {
  const papers = Array.from(
    new Set(clippings.map((c) => c.newspaper_name)),
  )
  const subtitle =
    papers.length === 2
      ? `${papers[0]} and ${papers[1]} cover this story with different framing`
      : `${papers.slice(0, -1).join(', ')} and ${papers.slice(-1)[0]} cover this story with different framing`
  return (
    <div
      style={{
        backgroundColor: 'rgba(244,63,94,0.06)',
        border: `1px solid rgba(244,63,94,0.2)`,
        borderRadius: '6px',
        padding: '10px 14px',
        marginBottom: '8px',
      }}
    >
      <div
        style={{
          fontFamily: "'DM Mono', ui-monospace, monospace",
          fontSize: '10px',
          color: DIVERGENCE_ROSE,
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          fontWeight: 500,
        }}
      >
        Narrative divergence detected
      </div>
      <div
        style={{
          fontFamily: "'DM Sans', system-ui, sans-serif",
          fontSize: '12px',
          color: TEXT_SECONDARY,
          marginTop: '3px',
        }}
      >
        {subtitle}
      </div>
    </div>
  )
}

// ─── Page ──────────────────────────────────────────────────────────────

export default function CuttingRoomPage() {
  const [token, setToken] = useState<string | null>(null)
  const [feed, setFeed] = useState<FeedResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [paperFilter, setPaperFilter] = useState<string>('all')
  const [langFilter, setLangFilter] = useState<LangFilter>('all')

  const fetchFeed = useCallback(
    async (authToken: string) => {
      setLoading(true)
      setError(null)
      try {
        const params = new URLSearchParams({
          newspaper: paperFilter,
          language: langFilter,
          days: '7',
          limit: '20',
        })
        const r = await fetch(
          `${API_BASE}/api/clippings/feed?${params.toString()}`,
          { headers: { Authorization: `Bearer ${authToken}` } },
        )
        if (!r.ok) {
          throw new Error(`Feed request failed: ${r.status}`)
        }
        const data = (await r.json()) as FeedResponse
        setFeed(data)
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : 'Unexpected error')
      } finally {
        setLoading(false)
      }
    },
    [paperFilter, langFilter],
  )

  useEffect(() => {
    const init = async () => {
      const supabase = createClient()
      const {
        data: { session },
      } = await supabase.auth.getSession()
      const t = session?.access_token ?? null
      setToken(t)
      if (t) void fetchFeed(t)
      else setLoading(false)
    }
    void init()
  }, [fetchFeed])

  const groups = feed ? groupForDivergence(feed.clippings) : []
  const totalCount = feed?.clippings.length ?? 0
  const paperCount = feed?.newspapers.length ?? 0

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#F8FAFC' }}>
      <Navigation />

      <main
        style={{
          paddingTop: '76px',
          paddingLeft: '24px',
          paddingRight: '24px',
          paddingBottom: '48px',
          maxWidth: '1080px',
          margin: '0 auto',
        }}
      >
        {/* Header */}
        <header
          style={{
            display: 'flex',
            alignItems: 'baseline',
            justifyContent: 'space-between',
            marginBottom: '20px',
          }}
        >
          <h1
            style={{
              fontFamily: "'Playfair Display', serif",
              fontSize: '32px',
              fontWeight: 700,
              color: TEXT_PRIMARY,
              letterSpacing: '-0.02em',
              margin: 0,
            }}
          >
            CUTTING ROOM
          </h1>
          <div
            style={{
              fontFamily: "'DM Mono', ui-monospace, monospace",
              fontSize: '11px',
              color: TEXT_TERTIARY,
              letterSpacing: '0.04em',
            }}
          >
            {totalCount} clipping{totalCount === 1 ? '' : 's'} · {paperCount} paper{paperCount === 1 ? '' : 's'}
          </div>
        </header>

        {/* Newspaper filter pills */}
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '10px' }}>
          <FilterPill
            label="All"
            active={paperFilter === 'all'}
            onClick={() => setPaperFilter('all')}
          />
          {(feed?.newspapers ?? []).map((p) => (
            <FilterPill
              key={p.name}
              label={`${p.name} (${p.count})`}
              active={paperFilter === p.name}
              onClick={() => setPaperFilter(p.name)}
            />
          ))}
        </div>

        {/* Language toggle */}
        <div style={{ display: 'flex', gap: '6px', marginBottom: '22px' }}>
          <FilterPill
            label="All"
            active={langFilter === 'all'}
            onClick={() => setLangFilter('all')}
          />
          <FilterPill
            label="English"
            active={langFilter === 'en'}
            onClick={() => setLangFilter('en')}
          />
          <FilterPill
            label="Telugu"
            active={langFilter === 'te'}
            onClick={() => setLangFilter('te')}
          />
        </div>

        {/* Body */}
        {loading && (
          <div
            style={{
              fontFamily: "'DM Sans', system-ui, sans-serif",
              fontSize: '14px',
              color: TEXT_TERTIARY,
              padding: '40px 0',
              textAlign: 'center',
            }}
          >
            Loading clippings…
          </div>
        )}

        {error && !loading && (
          <div
            style={{
              fontFamily: "'DM Sans', system-ui, sans-serif",
              fontSize: '13px',
              color: DIVERGENCE_ROSE,
              padding: '16px',
              backgroundColor: 'rgba(244,63,94,0.06)',
              borderRadius: '6px',
              border: `1px solid rgba(244,63,94,0.2)`,
            }}
          >
            {error}
          </div>
        )}

        {!loading && !error && totalCount === 0 && (
          <div
            style={{
              fontFamily: "'DM Sans', system-ui, sans-serif",
              fontSize: '14px',
              color: TEXT_TERTIARY,
              padding: '48px 0',
              textAlign: 'center',
              border: `1px dashed ${BORDER}`,
              borderRadius: '6px',
            }}
          >
            No clippings yet. The morning scrape runs at 07:30 UTC.
          </div>
        )}

        {!loading && !error && groups.map((g) => (
          <div key={g.key}>
            {g.divergence && <DivergenceStrip clippings={g.clippings} />}
            {g.clippings.map((c) => (
              <ClippingCard
                key={c.clipping_id}
                clipping={c}
                token={token}
              />
            ))}
          </div>
        ))}
      </main>
    </div>
  )
}

// ─── Filter pill ────────────────────────────────────────────────────────

interface FilterPillProps {
  label: string
  active: boolean
  onClick: () => void
}

function FilterPill({ label, active, onClick }: FilterPillProps) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '5px 12px',
        borderRadius: '9999px',
        border: `1px solid ${active ? ACCENT_AMBER : BORDER}`,
        backgroundColor: active ? ACCENT_PALE : '#FFFFFF',
        color: active ? '#B45309' : TEXT_SECONDARY,
        fontFamily: "'DM Sans', system-ui, sans-serif",
        fontSize: '12px',
        fontWeight: active ? 600 : 500,
        cursor: 'pointer',
        letterSpacing: '0.01em',
      }}
    >
      {label}
    </button>
  )
}
