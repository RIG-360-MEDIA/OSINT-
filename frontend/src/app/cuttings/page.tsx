'use client'

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'

import Navigation from '@/components/Navigation'
import { Dateline } from '@/components/Dateline'
import { createClient } from '@/lib/supabase/client'

import { EditionModal, type Clipping } from './EditionModal'
import { Newsstand, type PaperSummary } from './Newsstand'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface PapersResponse {
  papers: PaperSummary[]
}

interface FeedResponse {
  clippings: Clipping[]
  has_more: boolean
  next_cursor: string | null
}

// Defect F3: HTTP status numbers leak directly to the masthead UI ("HTTP 502")
// which means nothing to a reader. Map the common cases to copy that matches
// the rest of the desk-memo language in this view.
function describeFetchFailure(status: number): string {
  if (status === 401 || status === 403) return 'Sign-in expired. Reload the page to sort the morning post again.'
  if (status === 404) return 'The newsstand has no edition filed for this date.'
  if (status >= 500) return 'The press room is having a moment. Try again in a few seconds.'
  return 'The newsstand is refusing to load right now.'
}

function CuttingsPageInner() {
  const router = useRouter()
  const searchParams = useSearchParams()

  const [token, setToken] = useState<string | null>(null)
  const [papers, setPapers] = useState<PaperSummary[]>([])
  const [papersLoading, setPapersLoading] = useState(true)
  const [papersError, setPapersError] = useState<string | null>(null)

  const [openPaper, setOpenPaper] = useState<PaperSummary | null>(null)
  const [editionClippings, setEditionClippings] = useState<Clipping[]>([])
  const [editionLoading, setEditionLoading] = useState(false)
  const [editionError, setEditionError] = useState<string | null>(null)

  const [langFilter, setLangFilter] = useState<string>('all')

  // ── Get Supabase token ──────────────────────────────────────────────
  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getSession().then(({ data }) => {
      setToken(data.session?.access_token ?? null)
    })
    const { data: sub } = supabase.auth.onAuthStateChange((_e, session) => {
      setToken(session?.access_token ?? null)
    })
    return () => sub.subscription.unsubscribe()
  }, [])

  // ── Fetch newsstand once token is in hand ───────────────────────────
  const loadPapers = useCallback(async () => {
    if (!token) return
    setPapersLoading(true)
    setPapersError(null)
    try {
      const r = await fetch(`${API_BASE}/api/clippings/papers?days=7`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!r.ok) throw new Error(describeFetchFailure(r.status))
      const data: PapersResponse = await r.json()
      setPapers(data.papers ?? [])
    } catch (err: unknown) {
      setPapersError(
        err instanceof Error ? err.message : 'Could not load newsstand',
      )
    } finally {
      setPapersLoading(false)
    }
  }, [token])

  useEffect(() => {
    if (token) loadPapers()
  }, [token, loadPapers])

  // ── Fetch clippings for the selected paper ──────────────────────────
  const openEdition = useCallback(
    async (paper: PaperSummary) => {
      setOpenPaper(paper)
      setEditionLoading(true)
      setEditionError(null)
      setEditionClippings([])
      try {
        if (!token) throw new Error('Not authenticated')
        const params = new URLSearchParams({
          newspaper: paper.name,
          days: '7',
          limit: '100',
        })
        const r = await fetch(
          `${API_BASE}/api/clippings/feed?${params.toString()}`,
          { headers: { Authorization: `Bearer ${token}` } },
        )
        if (!r.ok) throw new Error(describeFetchFailure(r.status))
        const data: FeedResponse = await r.json()
        setEditionClippings(data.clippings ?? [])
      } catch (err: unknown) {
        setEditionError(
          err instanceof Error ? err.message : 'Could not load edition',
        )
      } finally {
        setEditionLoading(false)
      }
    },
    [token],
  )

  // ── Deep-link sync: ?paper=<id> opens that masthead's modal ─────────
  // URL is the single source of truth. Open/close handlers only mutate the
  // URL; this effect mirrors URL state into local state. Mutating both at
  // once caused a close/reopen race because the effect re-fired with a
  // stale `queryPaperId` after `setOpenPaper(null)` flipped `openPaper`.
  const queryPaperId = searchParams.get('paper')
  useEffect(() => {
    if (!queryPaperId) {
      setOpenPaper(null)
      setEditionClippings([])
      setEditionError(null)
      return
    }
    if (openPaper?.newspaper_id === queryPaperId) return
    const target = papers.find(p => p.newspaper_id === queryPaperId)
    if (target) openEdition(target)
  }, [queryPaperId, papers, openPaper, openEdition])

  const handlePaperClick = useCallback(
    (paper: PaperSummary) => {
      const params = new URLSearchParams(searchParams.toString())
      params.set('paper', paper.newspaper_id)
      router.push(`/cuttings?${params.toString()}`, { scroll: false })
    },
    [router, searchParams],
  )

  const handleClose = useCallback(() => {
    const params = new URLSearchParams(searchParams.toString())
    params.delete('paper')
    const qs = params.toString()
    router.replace(qs ? `/cuttings?${qs}` : '/cuttings', { scroll: false })
  }, [router, searchParams])

  return (
    <div style={{ minHeight: '100vh', background: 'var(--rig-paper)' }}>
      <Navigation />
      <main style={{ maxWidth: '1280px', margin: '0 auto', padding: '40px 24px 80px' }}>
        <Dateline
          issueNumber={1}
          extra={[
            `${papers.length} ${papers.length === 1 ? 'MASTHEAD' : 'MASTHEADS'}`,
            `${papers.reduce((n, p) => n + p.clip_count, 0)} CUTTINGS`,
          ]}
        />
        <header style={{ margin: '24px 0 36px' }}>
          <h1
            style={{
              fontFamily: 'var(--font-serif)',
              fontSize: '40px',
              fontStyle: 'italic',
              fontWeight: 700,
              margin: 0,
              lineHeight: 1.05,
            }}
          >
            Newspaper
          </h1>
          <p
            style={{
              fontFamily: 'var(--font-serif)',
              fontSize: '15px',
              color: 'var(--rig-ink-soft)',
              marginTop: '8px',
              maxWidth: '640px',
            }}
          >
            The morning papers, sorted into a rack. Pull a masthead to read its
            cuttings; flip the full edition with one click.
          </p>
        </header>

        {papersLoading ? (
          <LoadingState />
        ) : papersError ? (
          <DeskMemo
            kicker="DESK MEMO"
            headline="The newsstand is refusing to load."
            body={papersError}
          />
        ) : (
          <>
            <TopClippings
              token={token}
              papers={papers}
              onClippingClick={handlePaperClick}
            />
            <Newsstand
              papers={papers}
              langFilter={langFilter}
              onLangFilterChange={setLangFilter}
              onPaperClick={handlePaperClick}
            />
          </>
        )}
      </main>

      {openPaper ? (
        <EditionModal
          paper={openPaper}
          clippings={editionClippings}
          loading={editionLoading}
          error={editionError}
          token={token}
          onClose={handleClose}
        />
      ) : null}
    </div>
  )
}

function LoadingState() {
  return (
    <div
      style={{
        textAlign: 'center',
        padding: '80px 20px',
        fontFamily: 'var(--font-serif)',
        fontStyle: 'italic',
        color: 'var(--rig-ink-soft)',
      }}
    >
      Sorting the morning papers…
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
        margin: '40px auto',
        maxWidth: '480px',
        padding: '28px 32px',
        background: 'var(--rig-paper-2)',
        border: '1px solid color-mix(in srgb, var(--rig-ink) 18%, transparent)',
        borderRadius: '4px',
        textAlign: 'center',
      }}
    >
      <div
        style={{
          fontFamily: 'var(--font-sans-condensed)',
          fontSize: '10px',
          letterSpacing: '0.22em',
          color: 'var(--rig-ink-soft)',
          textTransform: 'uppercase',
          marginBottom: '12px',
        }}
      >
        {kicker}
      </div>
      <div
        style={{
          fontFamily: 'var(--font-serif)',
          fontSize: '20px',
          fontStyle: 'italic',
          marginBottom: '8px',
        }}
      >
        {headline}
      </div>
      <div
        style={{
          fontFamily: 'var(--font-serif)',
          fontSize: '14px',
          color: 'var(--rig-ink-soft)',
          lineHeight: 1.5,
        }}
      >
        {body}
      </div>
    </div>
  )
}

// ── Top clippings strip ─────────────────────────────────────────────────────
//
// Above-the-fold feed that surfaces the most recent clippings across every
// masthead, so the reader can browse in-context without first picking a
// paper. Click on a card opens the same EditionModal as clicking the
// masthead would, scoped to that clipping's newspaper.

interface TopClippingsProps {
  token: string | null
  papers: PaperSummary[]
  onClippingClick: (paper: PaperSummary) => void
}

function TopClippings({ token, papers, onClippingClick }: TopClippingsProps) {
  const [clippings, setClippings] = useState<Clipping[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!token) return
    let cancelled = false
    setLoading(true)
    setError(null)
    const params = new URLSearchParams({ days: '2', limit: '24' })
    fetch(`${API_BASE}/api/clippings/feed?${params.toString()}`, {
      headers: { Authorization: `Bearer ${token}` },
      credentials: 'include',
    })
      .then(async r => {
        if (!r.ok) throw new Error(describeFetchFailure(r.status))
        return r.json() as Promise<FeedResponse>
      })
      .then(data => {
        if (!cancelled) setClippings(data.clippings ?? [])
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load top clippings')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [token])

  // Map newspaper_name -> PaperSummary so a clipping click can resolve its
  // owning masthead and reuse the existing modal flow.
  const paperByName = useMemo<Map<string, PaperSummary>>(() => {
    const m = new Map<string, PaperSummary>()
    for (const p of papers) m.set(p.name, p)
    return m
  }, [papers])

  if (!loading && !error && clippings.length === 0) return null

  return (
    <section style={{ margin: '0 0 56px' }}>
      <SectionKicker
        label="Top Clippings"
        sub={`Latest 48 hours · ${clippings.length} pieces`}
      />
      {loading ? (
        <div
          style={{
            textAlign: 'center',
            padding: '40px 20px',
            fontFamily: 'var(--font-serif)',
            fontStyle: 'italic',
            color: 'var(--rig-ink-3)',
          }}
        >
          Pulling the freshest cuttings…
        </div>
      ) : error ? (
        <DeskMemo
          kicker="DESK MEMO"
          headline="Top clippings are unavailable right now."
          body={error}
        />
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: '20px',
          }}
        >
          {clippings.map(c => {
            const owner = paperByName.get(c.newspaper_name)
            return (
              <ClippingCard
                key={c.clipping_id}
                clipping={c}
                onClick={owner ? () => onClippingClick(owner) : undefined}
              />
            )
          })}
        </div>
      )}
    </section>
  )
}

interface ClippingCardProps {
  clipping: Clipping
  onClick?: () => void
}

function ClippingCard({ clipping, onClick }: ClippingCardProps) {
  const headline = clipping.headline_translated || clipping.headline
  const preview = clipping.translated_preview || clipping.text_preview || ''
  const dateLabel = clipping.edition_date
    ? new Date(clipping.edition_date).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
      })
    : '—'

  const interactive = typeof onClick === 'function'
  const handleKey = (e: React.KeyboardEvent<HTMLElement>) => {
    if (!interactive) return
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onClick?.()
    }
  }

  return (
    <article
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : -1}
      onClick={onClick}
      onKeyDown={handleKey}
      style={{
        cursor: interactive ? 'pointer' : 'default',
        background: 'var(--rig-card, var(--rig-paper-2))',
        border: '1px solid var(--rig-card-border, var(--rig-rule))',
        borderRadius: '4px',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        transition: 'transform 120ms ease, box-shadow 120ms ease, border-color 120ms ease',
      }}
      onMouseEnter={e => {
        if (!interactive) return
        e.currentTarget.style.transform = 'translateY(-2px)'
        e.currentTarget.style.boxShadow = '0 4px 14px color-mix(in srgb, var(--rig-ink) 12%, transparent)'
        e.currentTarget.style.borderColor = 'var(--rig-gold)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.transform = ''
        e.currentTarget.style.boxShadow = ''
        e.currentTarget.style.borderColor = 'var(--rig-card-border, var(--rig-rule))'
      }}
    >
      {clipping.has_image ? (
        <div
          style={{
            width: '100%',
            aspectRatio: '4 / 3',
            background: 'var(--rig-paper-3)',
            position: 'relative',
            overflow: 'hidden',
          }}
        >
          {/* Cookie-authenticated same-origin image fetch — no extra header
              required because the Supabase auth cookie is sent automatically. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={`${API_BASE}/api/clippings/${clipping.clipping_id}/image`}
            alt=""
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            loading="lazy"
            onError={e => {
              ;(e.currentTarget as HTMLImageElement).style.display = 'none'
            }}
          />
        </div>
      ) : null}

      <div style={{ padding: '14px 16px 16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <div
          style={{
            fontFamily: 'var(--font-sans-condensed, var(--font-mono))',
            fontSize: '10px',
            letterSpacing: '0.22em',
            textTransform: 'uppercase',
            color: 'var(--rig-ink-3)',
            display: 'flex',
            justifyContent: 'space-between',
            gap: '8px',
          }}
        >
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {clipping.newspaper_name}
          </span>
          <span>{dateLabel}</span>
        </div>
        <h3
          style={{
            fontFamily: 'var(--font-serif)',
            fontSize: '17px',
            fontWeight: 700,
            lineHeight: 1.25,
            margin: 0,
            display: '-webkit-box',
            WebkitLineClamp: 3,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {headline}
        </h3>
        {preview ? (
          <p
            style={{
              fontFamily: 'var(--font-serif)',
              fontSize: '13px',
              color: 'var(--rig-ink-2)',
              lineHeight: 1.45,
              margin: 0,
              display: '-webkit-box',
              WebkitLineClamp: 3,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
          >
            {preview}
          </p>
        ) : null}
      </div>
    </article>
  )
}

interface SectionKickerProps {
  label: string
  sub?: string
}

function SectionKicker({ label, sub }: SectionKickerProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'baseline',
        justifyContent: 'space-between',
        gap: '12px',
        margin: '0 0 16px',
        paddingBottom: '8px',
        borderBottom: '1px solid var(--rig-rule)',
      }}
    >
      <div
        style={{
          fontFamily: 'var(--font-serif)',
          fontSize: '22px',
          fontStyle: 'italic',
          fontWeight: 700,
          letterSpacing: '0.01em',
        }}
      >
        {label}
      </div>
      {sub ? (
        <div
          style={{
            fontFamily: 'var(--font-sans-condensed, var(--font-mono))',
            fontSize: '10px',
            letterSpacing: '0.22em',
            textTransform: 'uppercase',
            color: 'var(--rig-ink-3)',
          }}
        >
          {sub}
        </div>
      ) : null}
    </div>
  )
}


export default function CuttingsPage() {
  return (
    <Suspense fallback={<LoadingState />}>
      <CuttingsPageInner />
    </Suspense>
  )
}
