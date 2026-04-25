'use client'

import { useCallback, useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'
import Navigation from '@/components/Navigation'
import { Dateline } from '@/components/Dateline'
import { formatTimeAgo } from '@/lib/domainColor'

/* ── Types ─────────────────────────────────────────────────────── */

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

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

function newspaperInitials(name: string): string {
  return name
    .split(/\s+/)
    .map(w => w[0])
    .join('')
    .slice(0, 3)
    .toUpperCase()
}

function normalizeHeadline(h: string): string {
  return (h || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
}

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
    if (groups.find(g => g.key === key)) continue
    const distinctPapers = new Set(bucket.map(b => b.newspaper_name)).size
    groups.push({
      key,
      divergence: bucket.length > 1 && distinctPapers > 1,
      clippings: bucket,
    })
  }
  return groups
}

/* ── Clipping image ────────────────────────────────────────────── */

interface ClippingImageProps {
  clippingId: string
  token: string | null
  hasImage: boolean
  newspaperName: string
}

function ClippingImage({ clippingId, token, hasImage, newspaperName }: ClippingImageProps) {
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
        const r = await fetch(`${API_BASE}/api/clippings/${clippingId}/image`, {
          headers: { Authorization: `Bearer ${token}` },
        })
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
    return () => { cancelled = true }
  }, [clippingId, token, hasImage])

  if (imgB64) {
    return (
      <img
        src={`data:image/png;base64,${imgB64}`}
        alt={`${newspaperName} clipping`}
        style={{
          width: '100%',
          maxHeight: '240px',
          objectFit: 'cover',
          border: '1px solid var(--rig-ink)',
          display: 'block',
          filter: 'sepia(0.06) contrast(1.02)',
        }}
      />
    )
  }

  return (
    <div
      style={{
        width: '100%',
        height: '200px',
        background: 'var(--rig-paper-2)',
        border: '1px solid var(--rig-ink-2)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexDirection: 'column',
        gap: '8px',
      }}
    >
      <span
        style={{
          fontFamily: 'var(--font-serif)',
          fontWeight: 500,
          fontStyle: 'italic',
          fontSize: '46px',
          letterSpacing: '0.02em',
          color: 'var(--rig-ink)',
          lineHeight: 1,
        }}
      >
        {newspaperInitials(newspaperName)}
      </span>
      <span
        className="rig-kicker"
        style={{ opacity: 0.6, fontSize: '9px' }}
      >
        {failed ? 'Image unavailable' : 'No scan filed'}
      </span>
    </div>
  )
}

/* ── Clipping card ─────────────────────────────────────────────── */

interface ClippingCardProps {
  clipping: Clipping
  token: string | null
}

function ClippingCard({ clipping, token }: ClippingCardProps) {
  const headlineDisplay = clipping.headline_translated || clipping.headline
  const bodyDisplay = clipping.translated_preview || clipping.text_preview || ''
  const timeAgo = formatTimeAgo(clipping.collected_at)

  return (
    <article
      style={{
        display: 'grid',
        gridTemplateColumns: '260px 1fr',
        gap: '28px',
        paddingTop: '32px',
        paddingBottom: '32px',
        borderBottom: '1px solid var(--rig-rule-hair)',
      }}
    >
      <div>
        <ClippingImage
          clippingId={clipping.clipping_id}
          token={token}
          hasImage={clipping.has_image}
          newspaperName={clipping.newspaper_name}
        />
        <div
          className="rig-kicker"
          style={{
            marginTop: '10px',
            opacity: 0.75,
            fontSize: '9px',
            textAlign: 'center',
          }}
        >
          {clipping.newspaper_language !== 'en'
            ? `${clipping.newspaper_language.toUpperCase()} · filed`
            : 'Filed'}
          {' '}
          {timeAgo}
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {/* Masthead line */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            borderBottom: '1px solid var(--rig-rule)',
            paddingBottom: '8px',
          }}
          className="rig-byline"
        >
          <span
            style={{
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              fontWeight: 500,
              fontSize: '18px',
              color: 'var(--rig-ink)',
              textTransform: 'none',
              letterSpacing: 'normal',
            }}
          >
            {clipping.newspaper_name}
          </span>
          <span aria-hidden="true" style={{ opacity: 0.5 }}>·</span>
          <span>
            {clipping.page_number ? `Page ${clipping.page_number}` : 'Page —'}
          </span>
          {clipping.edition_date && (
            <>
              <span aria-hidden="true" style={{ opacity: 0.5 }}>·</span>
              <span>{clipping.edition_date}</span>
            </>
          )}
          <span
            style={{
              marginLeft: 'auto',
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              color: 'var(--rig-gold)',
              fontSize: '16px',
            }}
          >
            {clipping.relevance_score.toFixed(2)}
          </span>
        </div>

        {/* Headline */}
        <h2
          className="rig-headline"
          style={{
            margin: 0,
            fontSize: '24px',
            lineHeight: 1.2,
            color: 'var(--rig-ink)',
            letterSpacing: '-0.005em',
          }}
        >
          {headlineDisplay}
        </h2>

        {/* Original headline (if translated) */}
        {clipping.headline_translated &&
          clipping.headline_translated !== clipping.headline && (
            <div
              style={{
                fontFamily: 'var(--font-serif)',
                fontStyle: 'italic',
                fontSize: '14px',
                color: 'var(--rig-ink-3)',
                lineHeight: 1.35,
                marginTop: '-6px',
              }}
            >
              {clipping.headline}
            </div>
          )}

        {/* Preview text */}
        <p
          style={{
            margin: 0,
            fontFamily: 'var(--font-serif)',
            fontSize: '15px',
            lineHeight: 1.55,
            color: 'var(--rig-ink-2)',
          }}
        >
          {bodyDisplay}
          {bodyDisplay.length >= 280 ? '…' : ''}
        </p>

        {/* Why this matters */}
        {clipping.relevance_explanation && (
          <div
            style={{
              borderLeft: '2px solid var(--rig-gold)',
              background: 'color-mix(in srgb, var(--rig-gold) 6%, transparent)',
              padding: '10px 14px',
              marginTop: '4px',
            }}
          >
            <div
              className="rig-kicker"
              style={{ marginBottom: '4px', color: 'var(--rig-copper)' }}
            >
              Why this matters
            </div>
            <div
              style={{
                fontFamily: 'var(--font-serif)',
                fontStyle: 'italic',
                fontSize: '14px',
                color: 'var(--rig-ink)',
                lineHeight: 1.45,
              }}
            >
              {clipping.relevance_explanation}
            </div>
          </div>
        )}
      </div>
    </article>
  )
}

/* ── Divergence strip ─────────────────────────────────────────── */

function DivergenceStrip({ clippings }: { clippings: Clipping[] }) {
  const papers = Array.from(new Set(clippings.map(c => c.newspaper_name)))
  const subtitle =
    papers.length === 2
      ? `${papers[0]} and ${papers[1]} file the same story in different words.`
      : `${papers.slice(0, -1).join(', ')} and ${papers.slice(-1)[0]} file the same story in different words.`

  return (
    <div
      style={{
        borderLeft: '2px solid var(--rig-oxblood)',
        background: 'color-mix(in srgb, var(--rig-oxblood) 6%, transparent)',
        padding: '12px 16px',
        marginTop: '24px',
        marginBottom: '-8px',
      }}
    >
      <div
        className="rig-kicker"
        style={{ color: 'var(--rig-oxblood)', marginBottom: '4px' }}
      >
        Narrative divergence
      </div>
      <div
        style={{
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontSize: '15px',
          color: 'var(--rig-ink-2)',
          lineHeight: 1.45,
        }}
      >
        {subtitle}
      </div>
    </div>
  )
}

/* ── Page ─────────────────────────────────────────────────────── */

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
        if (!r.ok) throw new Error(`Feed request failed: ${r.status}`)
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
      const { data: { session } } = await supabase.auth.getSession()
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
    <div style={{ minHeight: '100vh', background: 'var(--rig-paper)' }}>
      <Navigation />

      <div style={{ paddingTop: 'var(--topbar-h)' }}>
        <Dateline
          issueNumber={totalCount}
          extra={paperCount > 0 ? [`${paperCount} MASTHEADS`] : undefined}
        />

        <main style={{ maxWidth: '980px', margin: '0 auto', padding: '48px 32px 80px' }}>
          {/* Section head */}
          <header style={{ marginBottom: '32px' }}>
            <div className="rig-kicker" style={{ marginBottom: '10px' }}>
              The Cutting Room
            </div>
            <h1
              className="rig-headline"
              style={{
                fontSize: '34px',
                margin: 0,
                letterSpacing: '-0.01em',
                lineHeight: 1.15,
              }}
            >
              The morning papers,{' '}
              <em style={{ fontWeight: 500, color: 'var(--rig-gold)' }}>
                scissored and filed.
              </em>
            </h1>
          </header>

          {/* Filters */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '14px',
              marginBottom: '32px',
              paddingBottom: '22px',
              borderBottom: '1px solid var(--rig-rule)',
            }}
          >
            <div>
              <div className="rig-kicker" style={{ marginBottom: '8px', opacity: 0.7 }}>
                Masthead
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                <FilterPill
                  label="All"
                  active={paperFilter === 'all'}
                  onClick={() => setPaperFilter('all')}
                />
                {(feed?.newspapers ?? []).map(p => (
                  <FilterPill
                    key={p.name}
                    label={`${p.name} · ${p.count}`}
                    active={paperFilter === p.name}
                    onClick={() => setPaperFilter(p.name)}
                  />
                ))}
              </div>
            </div>

            <div>
              <div className="rig-kicker" style={{ marginBottom: '8px', opacity: 0.7 }}>
                Language
              </div>
              <div style={{ display: 'flex', gap: '6px' }}>
                <FilterPill label="All" active={langFilter === 'all'} onClick={() => setLangFilter('all')} />
                <FilterPill label="English" active={langFilter === 'en'} onClick={() => setLangFilter('en')} />
                <FilterPill label="Telugu" active={langFilter === 'te'} onClick={() => setLangFilter('te')} />
              </div>
            </div>
          </div>

          {/* States */}
          {loading && <LoadingState />}

          {!loading && error && (
            <DeskMemo
              kicker="Desk memo"
              headline="The scanner went quiet."
              body={error}
            />
          )}

          {!loading && !error && totalCount === 0 && (
            <DeskMemo
              kicker="Desk memo"
              headline="No clippings filed today."
              body="The morning run starts at 07:30 UTC. Fresh scans will appear here as the papers hit the desk."
            />
          )}

          {!loading && !error && groups.map(g => (
            <div key={g.key}>
              {g.divergence && <DivergenceStrip clippings={g.clippings} />}
              {g.clippings.map(c => (
                <ClippingCard key={c.clipping_id} clipping={c} token={token} />
              ))}
            </div>
          ))}
        </main>
      </div>
    </div>
  )
}

/* ── Subcomponents ─────────────────────────────────────────────── */

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
        cursor: 'pointer',
        fontFamily: 'var(--font-mono)',
        fontSize: '10px',
        letterSpacing: '0.2em',
        textTransform: 'uppercase',
        border: '1px solid',
        borderColor: active ? 'var(--rig-ink)' : 'var(--rig-rule)',
        background: active
          ? 'color-mix(in srgb, var(--rig-paper-2) 60%, transparent)'
          : 'transparent',
        color: active ? 'var(--rig-ink)' : 'var(--rig-ink-3)',
        transition: 'all 0.15s',
      }}
    >
      {label}
    </button>
  )
}

function LoadingState() {
  return (
    <div
      style={{
        padding: '72px 0',
        textAlign: 'center',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '14px',
      }}
    >
      <span
        className="rig-headline"
        style={{
          fontStyle: 'italic',
          fontSize: '20px',
          color: 'var(--rig-ink-2)',
        }}
      >
        Sorting the morning papers…
      </span>
      <span
        style={{
          width: '160px',
          height: '1px',
          background: 'linear-gradient(90deg, transparent, var(--rig-gold), transparent)',
        }}
      />
    </div>
  )
}

interface DeskMemoProps {
  kicker: string
  headline: string
  body: string
}

function DeskMemo({ kicker, headline, body }: DeskMemoProps) {
  return (
    <div
      style={{
        padding: '56px 32px',
        textAlign: 'center',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '12px',
        border: '1px solid var(--rig-rule)',
        background: 'var(--rig-paper-2)',
      }}
    >
      <span className="rig-kicker">{kicker}</span>
      <span
        className="rig-headline"
        style={{ fontStyle: 'italic', fontSize: '22px', color: 'var(--rig-ink-2)' }}
      >
        {headline}
      </span>
      <span
        style={{
          fontFamily: 'var(--font-sans)',
          fontSize: '14px',
          color: 'var(--rig-ink-3)',
          maxWidth: '440px',
          lineHeight: 1.55,
        }}
      >
        {body}
      </span>
    </div>
  )
}
