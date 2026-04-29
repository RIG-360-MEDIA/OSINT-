'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import Navigation from '@/components/Navigation'
import { Dateline } from '@/components/Dateline'

import { DeskMemo } from './components/DeskMemo'
import { DocumentDialog } from './components/DocumentDialog'
import { DocumentRow } from './components/DocumentRow'
import { ErrorBanner } from './components/ErrorBanner'
import { FilterPill } from './components/FilterPill'
import { FilterRow } from './components/FilterRow'
import { LoadingState } from './components/LoadingState'
import {
  API_BASE,
  DOC_TYPES,
  GEO_FILTERS,
  WINDOWS,
} from './lib/constants'
import type {
  DocumentItem,
  FeedResponse,
  GeoCount,
  GeoFilter,
  WindowDays,
} from './lib/types'

export default function DocumentsPage() {
  const router = useRouter()
  const [token, setToken] = useState<string | null>(null)
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [total, setTotal] = useState(0)
  const [geoCounts, setGeoCounts] = useState<GeoCount[]>([])
  const [hasMore, setHasMore] = useState(false)
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [appending, setAppending] = useState(false)

  const [geoFilter, setGeoFilter] = useState<GeoFilter>('all')
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [windowDays, setWindowDays] = useState<WindowDays>(30)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')

  const [openDoc, setOpenDoc] = useState<DocumentItem | null>(null)
  const [error, setError] = useState<string | null>(null)

  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const fetchAbort = useRef<AbortController | null>(null)

  useEffect(() => {
    const supabase = createClient()
    void (async () => {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        router.push('/login')
        return
      }
      setToken(session.access_token)
    })()

    // D-13: keep the in-memory token in sync with Supabase. When the access
    // token rotates (~1h cadence) the previous behaviour was a silent 401 on
    // the next fetch; now we receive TOKEN_REFRESHED, swap in the new token,
    // and the existing fetchFeed effect re-runs because `token` is in its
    // dep list. SIGNED_OUT bounces the user to /login.
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (event, session) => {
        if (event === 'SIGNED_OUT' || !session) {
          router.push('/login')
          return
        }
        setToken(session.access_token)
      },
    )
    return () => subscription.unsubscribe()
  }, [router])

  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => setSearch(searchInput), 350)
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current)
    }
  }, [searchInput])

  const fetchFeed = useCallback(
    async (cursor: string | null, append: boolean) => {
      if (!token) return

      // D-5: cancel any in-flight request before starting a new one so a
      // slow stale response can't clobber the fresh result on rapid
      // filter clicks.
      if (fetchAbort.current) fetchAbort.current.abort()
      const abort = new AbortController()
      fetchAbort.current = abort

      if (append) setAppending(true)
      else {
        setLoading(true)
        setError(null)
      }
      try {
        const params = new URLSearchParams()
        params.set('limit', '20')
        params.set('days', String(windowDays))
        if (geoFilter !== 'all') params.set('geography', geoFilter)
        if (typeFilter !== 'all') params.set('doc_type', typeFilter)
        if (search) params.set('search', search)
        if (cursor) params.set('cursor', cursor)

        const res = await fetch(
          `${API_BASE}/api/documents/feed?${params.toString()}`,
          {
            headers: { Authorization: `Bearer ${token}` },
            signal: abort.signal,
          },
        )
        if (!res.ok) {
          const message =
            res.status === 401 ? 'Your session expired. Please sign in again.'
              : res.status >= 500 ? 'The archive is temporarily unavailable. Try again in a moment.'
              : `Couldn't load the archive (HTTP ${res.status}).`
          setError(message)
          if (!append) setDocuments([])
          return
        }
        const data = (await res.json()) as FeedResponse
        setDocuments(prev => (append ? [...prev, ...data.documents] : data.documents))
        setHasMore(data.has_more)
        setNextCursor(data.next_cursor)
        setTotal(data.total)
        setGeoCounts(data.geography_counts)
        setError(null)
      } catch (err) {
        if ((err as Error)?.name === 'AbortError') return
        setError('Network error. Check your connection and try again.')
        if (!append) setDocuments([])
      } finally {
        if (fetchAbort.current === abort) fetchAbort.current = null
        setLoading(false)
        setAppending(false)
      }
    },
    [token, geoFilter, typeFilter, windowDays, search],
  )

  useEffect(() => {
    if (!token) return
    void fetchFeed(null, false)
  }, [token, geoFilter, typeFilter, windowDays, search, fetchFeed])

  useEffect(() => {
    return () => {
      if (fetchAbort.current) fetchAbort.current.abort()
    }
  }, [])

  return (
    <div style={{ minHeight: '100vh', background: 'var(--rig-paper)' }}>
      <Navigation />

      <div style={{ paddingTop: 'var(--topbar-h)' }}>
        <Dateline
          issueNumber={total}
          extra={geoCounts.length > 0 ? [`${geoCounts.length} DESKS`] : undefined}
        />

        <main style={{ maxWidth: '1200px', margin: '0 auto', padding: '48px 32px 80px' }}>
          {/* Section head */}
          <header style={{ marginBottom: '28px' }}>
            <div className="rig-kicker" style={{ marginBottom: '10px' }}>
              Govt Docs
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
              Papers of record,{' '}
              <em style={{ fontWeight: 500, color: 'var(--rig-gold)' }}>
                filed by the State and filed by us.
              </em>
            </h1>
          </header>

          {/* Filters */}
          <div
            style={{
              position: 'sticky',
              top: 'var(--topbar-h)',
              zIndex: 50,
              background: 'var(--rig-paper-2)',
              borderTop: '1px solid var(--rig-rule)',
              borderBottom: '1px solid var(--rig-rule)',
              padding: '14px 0',
              marginBottom: '32px',
            }}
          >
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
                padding: '0 24px',
              }}
            >
              <FilterRow label="Desk">
                {GEO_FILTERS.map(({ value, label }) => (
                  <FilterPill
                    key={value}
                    label={label}
                    active={geoFilter === value}
                    onClick={() => setGeoFilter(value)}
                  />
                ))}
              </FilterRow>

              <FilterRow label="Document">
                {DOC_TYPES.map(({ value, label }) => (
                  <FilterPill
                    key={value}
                    label={label}
                    active={typeFilter === value}
                    onClick={() => setTypeFilter(value)}
                  />
                ))}
              </FilterRow>

              <FilterRow label="Window">
                {WINDOWS.map(({ value, label }) => (
                  <FilterPill
                    key={value}
                    label={label}
                    active={windowDays === value}
                    onClick={() => setWindowDays(value)}
                  />
                ))}
              </FilterRow>

              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  borderTop: '1px solid var(--rig-rule-hair)',
                  paddingTop: '10px',
                }}
              >
                <span
                  aria-hidden="true"
                  style={{
                    fontFamily: 'var(--font-serif)',
                    fontStyle: 'italic',
                    fontSize: '16px',
                    color: 'var(--rig-ink-3)',
                  }}
                >
                  ⌕
                </span>
                <input
                  type="text"
                  value={searchInput}
                  onChange={e => setSearchInput(e.target.value)}
                  placeholder="Search the archive…"
                  className="rig-input"
                  style={{ flex: 1, maxWidth: '520px' }}
                />
              </div>
            </div>
          </div>

          {/* Results */}
          {error && (
            <ErrorBanner
              message={error}
              onRetry={() => {
                setError(null)
                void fetchFeed(null, false)
              }}
            />
          )}

          {loading && !error && <LoadingState />}

          {!loading && !error && documents.length === 0 && (
            <DeskMemo
              kicker="Desk memo"
              headline="No papers match these terms."
              body="The overnight sweep runs at 06:30 UTC. Loosen the filters, or wait for the next run."
            />
          )}

          {!loading && documents.length > 0 && (
            <>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'baseline',
                  justifyContent: 'space-between',
                  paddingBottom: '14px',
                  marginBottom: '8px',
                  borderBottom: '1px solid var(--rig-rule)',
                }}
              >
                <span className="rig-kicker">The stacks — sorted by weight</span>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '10px',
                    letterSpacing: '0.2em',
                    textTransform: 'uppercase',
                    color: 'var(--rig-ink-3)',
                  }}
                >
                  {documents.length} of {total.toLocaleString()}
                </span>
              </div>

              {documents.map((doc, i) => (
                <DocumentRow
                  key={doc.doc_id}
                  doc={doc}
                  index={i + 1}
                  onOpen={() => setOpenDoc(doc)}
                />
              ))}

              {hasMore && (
                <div style={{ display: 'flex', justifyContent: 'center', marginTop: '32px' }}>
                  <button
                    onClick={() => fetchFeed(nextCursor, true)}
                    disabled={appending}
                    className="rig-btn-ghost"
                  >
                    {appending ? 'Pulling more…' : 'Pull more papers'}
                  </button>
                </div>
              )}
            </>
          )}
        </main>
      </div>

      {openDoc && token && (
        <DocumentDialog
          doc={openDoc}
          token={token}
          onClose={() => setOpenDoc(null)}
          onInvestigate={() => {
            const q = encodeURIComponent(
              `What are the implications of this document: ${openDoc.title}`,
            )
            router.push(`/analyst?q=${q}`)
          }}
          onSummaryUpdated={summary => {
            setDocuments(prev =>
              prev.map(d => (d.doc_id === openDoc.doc_id ? { ...d, summary } : d)),
            )
            setOpenDoc(prev => (prev ? { ...prev, summary } : prev))
          }}
        />
      )}
    </div>
  )
}
