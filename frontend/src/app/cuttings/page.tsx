'use client'

import { Suspense, useCallback, useEffect, useState } from 'react'
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
          <Newsstand
            papers={papers}
            langFilter={langFilter}
            onLangFilterChange={setLangFilter}
            onPaperClick={handlePaperClick}
          />
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

export default function CuttingsPage() {
  return (
    <Suspense fallback={<LoadingState />}>
      <CuttingsPageInner />
    </Suspense>
  )
}
