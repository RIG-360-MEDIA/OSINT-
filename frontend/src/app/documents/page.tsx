'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import Navigation from '@/components/Navigation'
import { Dateline } from '@/components/Dateline'

/* ── Types ─────────────────────────────────────────────────────── */

interface DocumentItem {
  doc_id: string
  title: string
  document_url: string
  source_name: string
  source_geography: 'LOCAL' | 'CENTRAL' | 'NEIGHBOURING' | 'INTERNATIONAL' | string
  document_type: string
  topic_category: string | null
  geo_primary: string | null
  summary_preview: string | null
  summary: string | null
  page_count: number | null
  published_at: string | null
  collected_at: string
  score_final: number | null
  relevance_tier: number | null
  urgency: 'HIGH' | 'MEDIUM' | 'LOW' | null
  why_it_matters: string | null
  suggested_action: string | null
}

interface GeoCount {
  geography: string
  count: number
}

interface FeedResponse {
  documents: DocumentItem[]
  has_more: boolean
  next_cursor: string | null
  total: number
  geography_counts: GeoCount[]
}

type GeoFilter = 'all' | 'LOCAL' | 'CENTRAL' | 'NEIGHBOURING' | 'INTERNATIONAL'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const GEO_FILTERS: Array<{ value: GeoFilter; label: string }> = [
  { value: 'all',           label: 'All' },
  { value: 'LOCAL',         label: 'Local' },
  { value: 'CENTRAL',       label: 'Central' },
  { value: 'NEIGHBOURING',  label: 'Neighbouring' },
  { value: 'INTERNATIONAL', label: 'International' },
]

// D-6: covers the document_type values emitted by all 47 adapters.
// Update this list whenever a new adapter introduces a new type — or
// switch to a `/api/documents/facets` endpoint when the type universe
// stabilises.
const DOC_TYPES: Array<{ value: string; label: string }> = [
  { value: 'all',                    label: 'All types' },
  { value: 'government_order',       label: 'GO.Ms' },
  { value: 'court_order',            label: 'HC Orders' },
  { value: 'judgment',               label: 'Judgments' },
  { value: 'nclt_order',             label: 'NCLT Orders' },
  { value: 'nclat_order',            label: 'NCLAT Orders' },
  { value: 'ngt_order',              label: 'NGT Orders' },
  { value: 'audit_report',           label: 'CAG Reports' },
  { value: 'press_release',          label: 'PIB Releases' },
  { value: 'ministry_order',         label: 'Ministry Orders' },
  { value: 'mof_notification',       label: 'MoF Notifications' },
  { value: 'mha_notification',       label: 'MHA Notifications' },
  { value: 'mea_release',            label: 'MEA Press' },
  { value: 'mod_release',            label: 'MoD Press' },
  { value: 'niti_report',            label: 'NITI Reports' },
  { value: 'gem_circular',           label: 'GeM Circulars' },
  { value: 'regulator_circular',     label: 'Regulator Circulars' },
  { value: 'tariff_order',           label: 'Tariff Orders' },
  { value: 'gazette',                label: 'Gazettes' },
  { value: 'gazette_notification',   label: 'Gazette Notifications' },
  { value: 'tender',                 label: 'Tenders' },
  { value: 'clearance',              label: 'Clearances' },
  { value: 'notification',           label: 'Notifications' },
  { value: 'parliamentary_question', label: 'LS/RS Questions' },
  { value: 'bill',                   label: 'Bills' },
  { value: 'committee_report',       label: 'Committee Reports' },
  { value: 'patent_grant',           label: 'Patents' },
  { value: 'trademark',              label: 'Trademarks' },
  { value: 'world_bank_doc',         label: 'World Bank' },
  { value: 'document',               label: 'Other' },
]

type WindowDays = 7 | 30 | 90 | 365

const WINDOWS: Array<{ value: WindowDays; label: string }> = [
  { value: 7,   label: '7 days' },
  { value: 30,  label: '30 days' },
  { value: 90,  label: '90 days' },
  { value: 365, label: '1 year' },
]

const URGENCY_TONE: Record<string, 'alert' | 'gold' | 'default'> = {
  HIGH: 'alert',
  MEDIUM: 'gold',
  LOW: 'default',
}

const GEO_KICKER: Record<string, string> = {
  LOCAL: 'Local desk',
  CENTRAL: 'Central desk',
  NEIGHBOURING: 'Neighbouring',
  INTERNATIONAL: 'Foreign desk',
}

function formatShortDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' }).toUpperCase()
  } catch {
    return ''
  }
}

/* ── Page ──────────────────────────────────────────────────────── */

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
          // D-4: surface the failure. Preserve the previous list on
          // append-failure (so a flaky load-more doesn't blank the page).
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
        // AbortError means we cancelled this fetch on purpose — ignore.
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
              The Archive
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

/* ── Subcomponents ─────────────────────────────────────────────── */

interface FilterRowProps {
  label: string
  children: React.ReactNode
}

function FilterRow({ label, children }: FilterRowProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
      <span
        className="rig-kicker"
        style={{ opacity: 0.7, minWidth: '78px' }}
      >
        {label}
      </span>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
        {children}
      </div>
    </div>
  )
}

interface FilterPillProps {
  label: string
  active: boolean
  onClick: () => void
}

function FilterPill({ label, active, onClick }: FilterPillProps) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      aria-pressed={active}
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
          ? 'color-mix(in srgb, var(--rig-paper) 70%, transparent)'
          : 'transparent',
        color: active ? 'var(--rig-ink)' : 'var(--rig-ink-3)',
        transition: 'all 0.15s',
      }}
    >
      {label}
    </button>
  )
}

interface DocumentRowProps {
  doc: DocumentItem
  index: number
  onOpen: () => void
}

function DocumentRow({ doc, index, onOpen }: DocumentRowProps) {
  const [hover, setHover] = useState(false)
  const urgencyTone = doc.urgency ? URGENCY_TONE[doc.urgency] : null
  const urgencyColor =
    urgencyTone === 'alert' ? 'var(--rig-oxblood)' :
    urgencyTone === 'gold' ? 'var(--rig-gold)' :
    'transparent'

  return (
    <article
      onClick={onOpen}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'grid',
        gridTemplateColumns: '48px 1fr auto',
        gap: '20px',
        padding: '22px 14px 22px',
        cursor: 'pointer',
        borderBottom: '1px solid var(--rig-rule-hair)',
        borderLeft: `2px solid ${urgencyColor}`,
        marginLeft: '-14px',
        background: hover
          ? 'color-mix(in srgb, var(--rig-paper-2) 55%, transparent)'
          : 'transparent',
        transition: 'background 0.15s',
      }}
    >
      {/* Numeral */}
      <span
        style={{
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontWeight: 400,
          fontSize: '26px',
          color: 'var(--rig-ink-3)',
          lineHeight: 1,
          paddingTop: '4px',
        }}
      >
        {String(index).padStart(2, '0')}
      </span>

      {/* Body */}
      <div style={{ minWidth: 0 }}>
        {/* Kicker line */}
        <div
          className="rig-byline"
          style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px', flexWrap: 'wrap' }}
        >
          <span style={{ color: 'var(--rig-copper)' }}>
            {GEO_KICKER[doc.source_geography] ?? doc.source_geography}
          </span>
          <span aria-hidden="true" style={{ opacity: 0.4 }}>·</span>
          <span>{doc.document_type.replace(/_/g, ' ')}</span>
          <span aria-hidden="true" style={{ opacity: 0.4 }}>·</span>
          <span>{doc.source_name}</span>
          {doc.urgency && (
            <>
              <span aria-hidden="true" style={{ opacity: 0.4 }}>·</span>
              <span style={{ color: urgencyColor !== 'transparent' ? urgencyColor : undefined }}>
                {doc.urgency} urgency
              </span>
            </>
          )}
        </div>

        {/* Title */}
        <h2
          className="rig-headline"
          style={{
            margin: 0,
            fontSize: '19px',
            lineHeight: 1.3,
            color: 'var(--rig-ink)',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {doc.title}
        </h2>

        {/* Why it matters or preview */}
        {doc.why_it_matters ? (
          <p
            style={{
              margin: '8px 0 0',
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              fontSize: '14px',
              color: 'var(--rig-copper)',
              lineHeight: 1.45,
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
          >
            {doc.why_it_matters}
          </p>
        ) : (
          <p
            style={{
              margin: '8px 0 0',
              fontFamily: 'var(--font-serif)',
              fontSize: '14px',
              color: 'var(--rig-ink-2)',
              lineHeight: 1.5,
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
          >
            {doc.summary || doc.summary_preview || ''}
          </p>
        )}

        {/* Footer tags */}
        {(doc.topic_category || doc.geo_primary) && (
          <div
            style={{
              display: 'flex',
              gap: '6px',
              flexWrap: 'wrap',
              marginTop: '10px',
            }}
          >
            {doc.topic_category && <TagChip label={doc.topic_category} />}
            {doc.geo_primary && <TagChip label={doc.geo_primary} />}
          </div>
        )}
      </div>

      {/* Right rail */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-end',
          justifyContent: 'space-between',
          gap: '10px',
          minWidth: '80px',
        }}
      >
        {doc.score_final != null && (
          <span
            style={{
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              fontWeight: 500,
              fontSize: '22px',
              lineHeight: 1,
              color: 'var(--rig-gold)',
            }}
          >
            {doc.score_final.toFixed(2)}
          </span>
        )}
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '9px',
            letterSpacing: '0.2em',
            textTransform: 'uppercase',
            color: 'var(--rig-ink-3)',
          }}
        >
          {formatShortDate(doc.collected_at)}
        </span>
        <span
          aria-hidden="true"
          style={{
            fontFamily: 'var(--font-serif)',
            fontStyle: 'italic',
            color: hover ? 'var(--rig-gold)' : 'var(--rig-ink-3)',
            fontSize: '16px',
            transition: 'color 0.15s',
          }}
        >
          →
        </span>
      </div>
    </article>
  )
}

function TagChip({ label }: { label: string }) {
  return (
    <span
      style={{
        padding: '2px 8px',
        fontFamily: 'var(--font-mono)',
        fontSize: '9px',
        letterSpacing: '0.16em',
        textTransform: 'uppercase',
        border: '1px solid var(--rig-rule)',
        color: 'var(--rig-ink-3)',
      }}
    >
      {label}
    </span>
  )
}

function LoadingState() {
  return (
    <div
      style={{
        padding: '64px 0',
        textAlign: 'center',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '12px',
      }}
    >
      <span
        className="rig-headline"
        style={{ fontStyle: 'italic', fontSize: '20px', color: 'var(--rig-ink-2)' }}
      >
        Opening the filing cabinet…
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
          maxWidth: '460px',
          lineHeight: 1.55,
        }}
      >
        {body}
      </span>
    </div>
  )
}

/* ── Error banner ──────────────────────────────────────────────── */

interface ErrorBannerProps {
  message: string
  onRetry: () => void
}

function ErrorBanner({ message, onRetry }: ErrorBannerProps) {
  return (
    <div
      role="alert"
      style={{
        padding: '20px 24px',
        margin: '0 0 24px',
        border: '1px solid var(--rig-alert, #b1442d)',
        background: 'rgba(177, 68, 45, 0.06)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '16px',
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        <span className="rig-kicker" style={{ color: 'var(--rig-alert, #b1442d)' }}>
          Stop press
        </span>
        <span
          style={{
            fontFamily: 'var(--font-serif)',
            fontSize: '17px',
            color: 'var(--rig-ink-1)',
            lineHeight: 1.45,
          }}
        >
          {message}
        </span>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="rig-button"
        style={{
          fontSize: '12px',
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
          padding: '8px 16px',
          border: '1px solid var(--rig-rule)',
          background: 'var(--rig-paper)',
          color: 'var(--rig-ink-1)',
          cursor: 'pointer',
          whiteSpace: 'nowrap',
        }}
      >
        Try again
      </button>
    </div>
  )
}

/* ── Document dialog ───────────────────────────────────────────── */

interface DocumentDialogProps {
  doc: DocumentItem
  token: string
  onClose: () => void
  onInvestigate: () => void
  onSummaryUpdated: (summary: string) => void
}

function DocumentDialog({
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

  // D-10: Esc closes the modal; focus is moved into the dialog on mount and
  // restored to the row that opened it on unmount.
  useEffect(() => {
    previouslyFocused.current = document.activeElement as HTMLElement | null
    dialogRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
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
