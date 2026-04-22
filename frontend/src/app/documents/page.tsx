'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import Navigation from '@/components/Navigation'

// ── Types ──────────────────────────────────────────────────────────────────────

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

const URGENCY_BADGE: Record<string, { bg: string; text: string }> = {
  HIGH:   { bg: '#FEE2E2', text: '#DC2626' },
  MEDIUM: { bg: '#FEF3C7', text: '#D97706' },
  LOW:    { bg: '#F1F5F9', text: '#64748B' },
}

const TIER_LEFT_BORDER: Record<number, string> = {
  1: '#3B82F6',
  2: '#10B981',
  3: '#94A3B8',
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

interface DocTypeOption {
  value: string
  label: string
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const GEO_FILTERS: Array<{ value: GeoFilter; label: string }> = [
  { value: 'all',           label: 'All' },
  { value: 'LOCAL',         label: 'Local' },
  { value: 'CENTRAL',       label: 'Central' },
  { value: 'NEIGHBOURING',  label: 'Neighbouring' },
  { value: 'INTERNATIONAL', label: 'International' },
]

const DOC_TYPES: DocTypeOption[] = [
  { value: 'all',              label: 'All Types' },
  { value: 'government_order', label: 'GO.Ms' },
  { value: 'court_order',      label: 'HC Orders' },
  { value: 'audit_report',     label: 'CAG Reports' },
  { value: 'press_release',    label: 'PIB Releases' },
  { value: 'ministry_order',   label: 'Ministry Orders' },
]

const GEO_BADGE: Record<string, { bg: string; text: string; border: string }> = {
  LOCAL:         { bg: '#EFF6FF', text: '#2563EB', border: '#DBEAFE' },
  CENTRAL:       { bg: '#FFFBEB', text: '#D97706', border: 'rgba(245,158,11,0.25)' },
  NEIGHBOURING:  { bg: '#ECFDF5', text: '#059669', border: '#D1FAE5' },
  INTERNATIONAL: { bg: '#FEF2F2', text: '#DC2626', border: '#FECACA' },
}

// ── Page ───────────────────────────────────────────────────────────────────────

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

  const [geoFilter, setGeoFilter]   = useState<GeoFilter>('all')
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')

  const [openDoc, setOpenDoc] = useState<DocumentItem | null>(null)

  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ── Auth boot ────────────────────────────────────────────────────────────
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

  // ── Search debounce ─────────────────────────────────────────────────────
  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => setSearch(searchInput), 350)
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current)
    }
  }, [searchInput])

  // ── Feed fetch ───────────────────────────────────────────────────────────
  const fetchFeed = useCallback(
    async (cursor: string | null, append: boolean) => {
      if (!token) return
      if (append) setAppending(true)
      else setLoading(true)

      try {
        const params = new URLSearchParams()
        params.set('limit', '20')
        if (geoFilter !== 'all') params.set('geography', geoFilter)
        if (typeFilter !== 'all') params.set('doc_type', typeFilter)
        if (search) params.set('search', search)
        if (cursor) params.set('cursor', cursor)

        const res = await fetch(
          `${API_BASE}/api/documents/feed?${params.toString()}`,
          { headers: { Authorization: `Bearer ${token}` } },
        )
        if (!res.ok) {
          if (!append) setDocuments([])
          return
        }
        const data = (await res.json()) as FeedResponse
        setDocuments(prev =>
          append ? [...prev, ...data.documents] : data.documents,
        )
        setHasMore(data.has_more)
        setNextCursor(data.next_cursor)
        setTotal(data.total)
        setGeoCounts(data.geography_counts)
      } finally {
        setLoading(false)
        setAppending(false)
      }
    },
    [token, geoFilter, typeFilter, search],
  )

  useEffect(() => {
    if (!token) return
    void fetchFeed(null, false)
  }, [token, geoFilter, typeFilter, search, fetchFeed])

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <>
      <Navigation />

      <main
        style={{
          paddingTop:      '56px',
          minHeight:       '100vh',
          backgroundColor: '#F1F5F9',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding:    '28px 32px 16px',
            maxWidth:   '1400px',
            margin:     '0 auto',
            display:    'flex',
            alignItems: 'flex-end',
            justifyContent: 'space-between',
            gap:        '16px',
            flexWrap:   'wrap',
          }}
        >
          <div>
            <div
              style={{
                fontFamily:    "'DM Sans', system-ui",
                fontSize:      '11px',
                fontWeight:    600,
                color:         '#94A3B8',
                textTransform: 'uppercase',
                letterSpacing: '0.15em',
              }}
            >
              Document Room
            </div>
            <h1
              style={{
                fontFamily:    "'Playfair Display', serif",
                fontSize:      '28px',
                fontWeight:    700,
                color:         '#18181B',
                letterSpacing: '-0.02em',
                margin:        '4px 0 0',
              }}
            >
              Government Intelligence
            </h1>
          </div>
          <div
            style={{
              fontFamily:    "'DM Mono', monospace",
              fontSize:      '12px',
              color:         '#64748B',
              letterSpacing: '0.04em',
            }}
          >
            {total.toLocaleString()} documents · {geoCounts.length} geographies
          </div>
        </div>

        {/* Filters */}
        <div
          style={{
            position:        'sticky',
            top:             '56px',
            zIndex:          50,
            backgroundColor: 'rgba(241,245,249,0.92)',
            backdropFilter:  'blur(8px)',
            padding:         '12px 32px',
            borderBottom:    '1px solid #E2E8F0',
          }}
        >
          <div
            style={{
              maxWidth: '1400px',
              margin:   '0 auto',
              display:  'flex',
              flexDirection: 'column',
              gap:      '10px',
            }}
          >
            {/* Geography filter row */}
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', alignItems: 'center' }}>
              <FilterLabel>Geography</FilterLabel>
              {GEO_FILTERS.map(({ value, label }) => (
                <FilterPill
                  key={value}
                  active={geoFilter === value}
                  onClick={() => setGeoFilter(value)}
                >
                  {label}
                </FilterPill>
              ))}
            </div>

            {/* Document type filter row */}
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', alignItems: 'center' }}>
              <FilterLabel>Type</FilterLabel>
              {DOC_TYPES.map(({ value, label }) => (
                <FilterPill
                  key={value}
                  active={typeFilter === value}
                  onClick={() => setTypeFilter(value)}
                >
                  {label}
                </FilterPill>
              ))}
            </div>

            {/* Search */}
            <input
              type="text"
              value={searchInput}
              onChange={e => setSearchInput(e.target.value)}
              placeholder="Search documents..."
              style={{
                width:           '100%',
                maxWidth:        '480px',
                padding:         '8px 12px',
                borderRadius:    '8px',
                border:          '1px solid #E2E8F0',
                backgroundColor: '#FFFFFF',
                fontFamily:      "'DM Sans', system-ui",
                fontSize:        '14px',
                color:           '#18181B',
                outline:         'none',
              }}
            />
          </div>
        </div>

        {/* Card grid */}
        <div
          style={{
            maxWidth: '1400px',
            margin:   '0 auto',
            padding:  '20px 32px 48px',
          }}
        >
          {loading && (
            <div
              style={{
                display:             'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
                gap:                 '16px',
              }}
            >
              {Array.from({ length: 6 }).map((_, i) => (
                <div
                  key={i}
                  className="skeleton"
                  style={{
                    height:       '220px',
                    borderRadius: '10px',
                  }}
                />
              ))}
            </div>
          )}

          {!loading && documents.length === 0 && (
            <div
              style={{
                padding:        '64px 16px',
                textAlign:      'center',
                fontFamily:     "'DM Sans', system-ui",
              }}
            >
              <div style={{ fontSize: '32px', marginBottom: '12px' }}>📄</div>
              <div style={{ fontSize: '14px', color: '#64748B' }}>
                No documents match your filters yet.
              </div>
              <div style={{ fontSize: '12px', color: '#94A3B8', marginTop: '6px' }}>
                The first govt collection runs daily at 06:30 UTC.
              </div>
            </div>
          )}

          {!loading && documents.length > 0 && (
            <>
              {total > 0 && (
                <div style={{ display: 'flex', marginBottom: '12px' }}>
                  <span
                    style={{
                      fontFamily:      "'DM Mono', monospace",
                      fontSize:        '11px',
                      color:           '#94A3B8',
                      padding:         '4px 10px',
                      backgroundColor: '#F1F5F9',
                      border:          '1px solid #E2E8F0',
                      borderRadius:    '9999px',
                    }}
                  >
                    Sorted by: Relevance ↓
                  </span>
                </div>
              )}
              <div
                style={{
                  display:             'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
                  gap:                 '16px',
                }}
              >
                {documents.map(doc => (
                  <DocumentCard
                    key={doc.doc_id}
                    doc={doc}
                    onOpen={() => setOpenDoc(doc)}
                  />
                ))}
              </div>

              {hasMore && (
                <div style={{ display: 'flex', justifyContent: 'center', marginTop: '24px' }}>
                  <button
                    onClick={() => fetchFeed(nextCursor, true)}
                    disabled={appending}
                    style={{
                      padding:         '10px 20px',
                      borderRadius:    '9999px',
                      border:          '1px solid #E2E8F0',
                      backgroundColor: '#FFFFFF',
                      fontFamily:      "'DM Sans', system-ui",
                      fontSize:        '13px',
                      fontWeight:      500,
                      color:           '#475569',
                      cursor:          appending ? 'default' : 'pointer',
                      opacity:         appending ? 0.6 : 1,
                    }}
                  >
                    {appending ? 'Loading…' : 'Load more'}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </main>

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
              prev.map(d =>
                d.doc_id === openDoc.doc_id ? { ...d, summary } : d,
              ),
            )
            setOpenDoc(prev => (prev ? { ...prev, summary } : prev))
          }}
        />
      )}
    </>
  )
}

// ── Filter primitives ──────────────────────────────────────────────────────────

function FilterLabel({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        fontFamily:    "'DM Sans', system-ui",
        fontSize:      '10px',
        fontWeight:    600,
        color:         '#94A3B8',
        textTransform: 'uppercase',
        letterSpacing: '0.12em',
        marginRight:   '4px',
      }}
    >
      {children}
    </span>
  )
}

function FilterPill({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      style={{
        padding:         '5px 12px',
        borderRadius:    '9999px',
        border:          active
          ? '1px solid rgba(245,158,11,0.4)'
          : '1px solid #E2E8F0',
        backgroundColor: active
          ? 'rgba(245,158,11,0.12)'
          : '#FFFFFF',
        fontFamily:      "'DM Sans', system-ui",
        fontSize:        '12px',
        fontWeight:      active ? 600 : 500,
        color:           active ? '#B45309' : '#475569',
        cursor:          'pointer',
        transition:      'all 0.15s',
      }}
    >
      {children}
    </button>
  )
}

// ── Card ───────────────────────────────────────────────────────────────────────

function DocumentCard({
  doc,
  onOpen,
}: {
  doc: DocumentItem
  onOpen: () => void
}) {
  const geo = GEO_BADGE[doc.source_geography] ?? GEO_BADGE.CENTRAL
  const tierLeft = doc.relevance_tier != null ? TIER_LEFT_BORDER[doc.relevance_tier] : undefined
  const urgency = doc.urgency ? URGENCY_BADGE[doc.urgency] : null

  return (
    <div
      onClick={onOpen}
      className="card-lift"
      style={{
        backgroundColor: '#FFFFFF',
        borderRadius:    '10px',
        border:          '1px solid #E2E8F0',
        borderLeft:      tierLeft ? `3px solid ${tierLeft}` : '1px solid #E2E8F0',
        boxShadow:       '0 1px 3px rgba(15,23,42,0.05)',
        cursor:          'pointer',
        overflow:        'hidden',
        display:         'flex',
        flexDirection:   'column',
        padding:         '16px',
        gap:             '12px',
      }}
    >
      {/* Top badges */}
      <div
        style={{
          display:        'flex',
          gap:            '6px',
          flexWrap:       'wrap',
          alignItems:     'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          <span
            style={{
              padding:         '2px 8px',
              borderRadius:    '9999px',
              backgroundColor: geo.bg,
              border:          `1px solid ${geo.border}`,
              fontFamily:      "'DM Sans', system-ui",
              fontSize:        '10px',
              fontWeight:      700,
              color:           geo.text,
              letterSpacing:   '0.08em',
            }}
          >
            {doc.source_geography}
          </span>
          <span
            style={{
              padding:         '2px 8px',
              borderRadius:    '9999px',
              backgroundColor: '#F8FAFC',
              border:          '1px solid #E2E8F0',
              fontFamily:      "'DM Sans', system-ui",
              fontSize:        '10px',
              fontWeight:      600,
              color:           '#475569',
              letterSpacing:   '0.06em',
              textTransform:   'uppercase',
            }}
          >
            {doc.document_type.replace(/_/g, ' ')}
          </span>
        </div>
        {urgency && (
          <span
            style={{
              padding:         '2px 8px',
              borderRadius:    '9999px',
              backgroundColor: urgency.bg,
              border:          `1px solid ${urgency.text}`,
              fontFamily:      "'DM Sans', system-ui",
              fontSize:        '10px',
              fontWeight:      700,
              color:           urgency.text,
              letterSpacing:   '0.08em',
            }}
          >
            {doc.urgency}
          </span>
        )}
      </div>

      {/* Title */}
      <h3
        style={{
          fontFamily:    "'Playfair Display', serif",
          fontSize:      '17px',
          fontWeight:    700,
          color:         '#18181B',
          lineHeight:    1.3,
          letterSpacing: '-0.01em',
          margin:        0,
        }}
      >
        {doc.title}
      </h3>

      {/* Why it matters (if present) */}
      {doc.why_it_matters && (
        <div
          style={{
            fontFamily:    "'DM Sans', system-ui",
            fontSize:      '12px',
            fontStyle:     'italic',
            color:         '#B45309',
            lineHeight:    1.4,
            whiteSpace:    'nowrap',
            overflow:      'hidden',
            textOverflow:  'ellipsis',
          }}
        >
          {doc.why_it_matters}
        </div>
      )}

      {/* Source */}
      <div
        style={{
          fontFamily: "'DM Sans', system-ui",
          fontSize:   '12px',
          color:      '#64748B',
        }}
      >
        {doc.source_name}
      </div>

      <div style={{ height: '1px', backgroundColor: '#F1F5F9' }} />

      {/* Preview (only if no why_it_matters) */}
      {!doc.why_it_matters && (
        <p
          style={{
            fontFamily: "'DM Sans', system-ui",
            fontSize:   '13px',
            color:      '#475569',
            lineHeight: 1.55,
            margin:     0,
            display:    '-webkit-box',
            WebkitLineClamp: 4,
            WebkitBoxOrient: 'vertical',
            overflow:   'hidden',
          }}
        >
          {doc.summary || doc.summary_preview || 'No preview available.'}
        </p>
      )}

      {/* Footer chips */}
      <div
        style={{
          display:        'flex',
          alignItems:     'center',
          justifyContent: 'space-between',
          marginTop:      'auto',
          gap:            '8px',
          flexWrap:       'wrap',
        }}
      >
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
          {doc.topic_category && <FooterChip>{doc.topic_category}</FooterChip>}
          {doc.geo_primary && <FooterChip>{doc.geo_primary}</FooterChip>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {doc.score_final != null && (
            <span
              style={{
                fontFamily: "'DM Mono', monospace",
                fontSize:   '11px',
                color:      '#3B82F6',
              }}
            >
              {doc.score_final.toFixed(2)}
            </span>
          )}
          <span
            style={{
              fontFamily: "'DM Mono', monospace",
              fontSize:   '11px',
              color:      '#94A3B8',
            }}
          >
            {formatShortDate(doc.collected_at)}
          </span>
        </div>
      </div>
    </div>
  )
}

function FooterChip({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        padding:         '2px 7px',
        borderRadius:    '9999px',
        backgroundColor: '#F1F5F9',
        border:          '1px solid #E2E8F0',
        fontFamily:      "'DM Sans', system-ui",
        fontSize:        '10px',
        color:           '#475569',
        letterSpacing:   '0.02em',
      }}
    >
      {children}
    </span>
  )
}

function formatShortDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
  } catch {
    return ''
  }
}

// ── Document dialog ────────────────────────────────────────────────────────────

function DocumentDialog({
  doc,
  token,
  onClose,
  onInvestigate,
  onSummaryUpdated,
}: {
  doc: DocumentItem
  token: string
  onClose: () => void
  onInvestigate: () => void
  onSummaryUpdated: (summary: string) => void
}) {
  const [summary, setSummary] = useState<string | null>(doc.summary)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summaryError, setSummaryError] = useState<string | null>(null)

  const generateSummary = useCallback(async () => {
    setSummaryLoading(true)
    setSummaryError(null)
    try {
      const res = await fetch(
        `${API_BASE}/api/documents/${doc.doc_id}/summary`,
        {
          method:  'POST',
          headers: { Authorization: `Bearer ${token}` },
        },
      )
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

  const geo = GEO_BADGE[doc.source_geography] ?? GEO_BADGE.CENTRAL

  return (
    <div
      onClick={onClose}
      style={{
        position:        'fixed',
        inset:           0,
        backgroundColor: 'rgba(15,23,42,0.5)',
        backdropFilter:  'blur(4px)',
        zIndex:          300,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="anim-slide-right"
        style={{
          position:        'fixed',
          top:             '56px',
          right:           0,
          width:           '560px',
          maxWidth:        '100vw',
          height:          'calc(100vh - 56px)',
          backgroundColor: '#FFFFFF',
          overflowY:       'auto',
          boxShadow:       '-8px 0 40px rgba(15,23,42,0.15)',
        }}
      >
        <button
          onClick={onClose}
          style={{
            position:        'absolute',
            top:             '14px',
            right:           '14px',
            width:           '28px',
            height:          '28px',
            borderRadius:    '50%',
            backgroundColor: '#F1F5F9',
            border:          '1px solid #E2E8F0',
            display:         'flex',
            alignItems:      'center',
            justifyContent:  'center',
            cursor:          'pointer',
            fontSize:        '16px',
            color:           '#64748B',
            zIndex:          1,
          }}
        >
          ×
        </button>

        <div style={{ padding: '32px 28px 48px' }}>
          {/* Geography + type */}
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '14px' }}>
            <span
              style={{
                padding:         '3px 10px',
                borderRadius:    '9999px',
                backgroundColor: geo.bg,
                border:          `1px solid ${geo.border}`,
                fontFamily:      "'DM Sans', system-ui",
                fontSize:        '10px',
                fontWeight:      700,
                color:           geo.text,
                letterSpacing:   '0.08em',
              }}
            >
              {doc.source_geography}
            </span>
            <span
              style={{
                padding:         '3px 10px',
                borderRadius:    '9999px',
                backgroundColor: '#F8FAFC',
                border:          '1px solid #E2E8F0',
                fontFamily:      "'DM Sans', system-ui",
                fontSize:        '10px',
                fontWeight:      600,
                color:           '#475569',
                letterSpacing:   '0.06em',
                textTransform:   'uppercase',
              }}
            >
              {doc.document_type.replace(/_/g, ' ')}
            </span>
          </div>

          {/* Title */}
          <h2
            style={{
              fontFamily:    "'Playfair Display', serif",
              fontSize:      '22px',
              fontWeight:    700,
              lineHeight:    1.3,
              color:         '#18181B',
              letterSpacing: '-0.02em',
              marginBottom:  '8px',
              marginTop:     0,
            }}
          >
            {doc.title}
          </h2>

          {/* Source line */}
          <div
            style={{
              fontFamily:   "'DM Sans', system-ui",
              fontSize:     '13px',
              color:        '#475569',
              marginBottom: '20px',
            }}
          >
            {doc.source_name}
            <span style={{ color: '#94A3B8' }}>
              {' · '}
              {formatShortDate(doc.collected_at)}
            </span>
          </div>

          {/* Why This Matters To You */}
          {doc.why_it_matters && (
            <div
              style={{
                marginBottom:    '14px',
                padding:         '14px 16px',
                borderRadius:    '8px',
                backgroundColor: '#FFFBEB',
                borderLeft:      '3px solid #F59E0B',
              }}
            >
              <div
                style={{
                  display:        'flex',
                  alignItems:     'center',
                  justifyContent: 'space-between',
                  gap:            '8px',
                  marginBottom:   '8px',
                }}
              >
                <div
                  style={{
                    fontFamily:    "'DM Sans', system-ui",
                    fontSize:      '10px',
                    fontWeight:    700,
                    color:         '#B45309',
                    textTransform: 'uppercase',
                    letterSpacing: '0.1em',
                  }}
                >
                  Why This Matters To You
                </div>
                {doc.urgency && (() => {
                  const u = URGENCY_BADGE[doc.urgency]
                  return (
                    <span
                      style={{
                        padding:         '2px 8px',
                        borderRadius:    '9999px',
                        backgroundColor: u.bg,
                        border:          `1px solid ${u.text}`,
                        fontFamily:      "'DM Sans', system-ui",
                        fontSize:        '10px',
                        fontWeight:      700,
                        color:           u.text,
                        letterSpacing:   '0.08em',
                      }}
                    >
                      {doc.urgency}
                    </span>
                  )
                })()}
              </div>
              <p
                style={{
                  fontFamily: "'DM Sans', system-ui",
                  fontSize:   '14px',
                  lineHeight: 1.6,
                  color:      '#78350F',
                  margin:     0,
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
                fontFamily:   "'DM Sans', system-ui",
                fontSize:     '13px',
                fontStyle:    'italic',
                color:        '#475569',
                marginBottom: '20px',
              }}
            >
              Suggested action: {doc.suggested_action}
            </div>
          )}

          {/* Summary section */}
          {!summary && !summaryLoading && !summaryError && (
            <button
              onClick={generateSummary}
              style={{
                marginBottom:    '20px',
                padding:         '8px 14px',
                borderRadius:    '8px',
                border:          '1px solid rgba(245,158,11,0.3)',
                backgroundColor: 'rgba(245,158,11,0.08)',
                fontFamily:      "'DM Sans', system-ui",
                fontSize:        '13px',
                fontWeight:      600,
                color:           '#B45309',
                cursor:          'pointer',
              }}
            >
              ✦ Generate Summary
            </button>
          )}
          {summaryLoading && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px', padding: '12px 0' }}>
              <div
                style={{
                  width:        '16px',
                  height:       '16px',
                  borderRadius: '50%',
                  border:       '2px solid #E2E8F0',
                  borderTopColor: '#F59E0B',
                  animation:    'spin 0.8s linear infinite',
                }}
              />
              <span style={{ fontFamily: "'DM Sans', system-ui", fontSize: '13px', color: '#64748B' }}>
                Generating summary…
              </span>
            </div>
          )}
          {summaryError && !summaryLoading && (
            <div style={{ marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{ fontFamily: "'DM Sans', system-ui", fontSize: '13px', color: '#E11D48' }}>
                {summaryError}
              </span>
              <button
                onClick={generateSummary}
                style={{
                  background:     'none',
                  border:         'none',
                  cursor:         'pointer',
                  fontFamily:     "'DM Sans', system-ui",
                  fontSize:       '13px',
                  color:          '#64748B',
                  textDecoration: 'underline',
                }}
              >
                Retry
              </button>
            </div>
          )}
          {summary && (
            <div
              style={{
                marginBottom:    '20px',
                padding:         '16px',
                borderRadius:    '8px',
                backgroundColor: '#F8FAFC',
                border:          '1px solid #E2E8F0',
              }}
            >
              <div
                style={{
                  fontFamily:    "'DM Sans', system-ui",
                  fontSize:      '10px',
                  fontWeight:    700,
                  color:         '#94A3B8',
                  textTransform: 'uppercase',
                  letterSpacing: '0.1em',
                  marginBottom:  '8px',
                }}
              >
                Summary
              </div>
              <p
                style={{
                  fontFamily: "'DM Sans', system-ui",
                  fontSize:   '14px',
                  lineHeight: 1.7,
                  color:      '#334155',
                  margin:     0,
                }}
              >
                {summary}
              </p>
            </div>
          )}

          {/* Preview */}
          {doc.summary_preview && !summary && (
            <p
              style={{
                fontFamily:   "'DM Sans', system-ui",
                fontSize:     '14px',
                lineHeight:   1.7,
                color:        '#334155',
                marginBottom: '24px',
              }}
            >
              {doc.summary_preview}
              {doc.summary_preview.length >= 400 ? '…' : ''}
            </p>
          )}

          {/* Meta footer */}
          <div
            style={{
              display:    'flex',
              gap:        '6px',
              flexWrap:   'wrap',
              padding:    '14px 0',
              borderTop:  '1px solid #F1F5F9',
              borderBottom: '1px solid #F1F5F9',
              marginBottom: '20px',
            }}
          >
            {doc.topic_category && <FooterChip>{doc.topic_category}</FooterChip>}
            {doc.geo_primary && <FooterChip>{doc.geo_primary}</FooterChip>}
            {doc.page_count && <FooterChip>{doc.page_count} pages</FooterChip>}
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <a
              href={doc.document_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                padding:         '10px 18px',
                borderRadius:    '8px',
                backgroundColor: '#18181B',
                color:           '#F8FAFC',
                fontFamily:      "'DM Sans', system-ui",
                fontSize:        '13px',
                fontWeight:      600,
                textDecoration:  'none',
              }}
            >
              Read Document ↗
            </a>
            <button
              onClick={onInvestigate}
              style={{
                padding:         '10px 18px',
                borderRadius:    '8px',
                backgroundColor: '#FFFFFF',
                border:          '1px solid #E2E8F0',
                fontFamily:      "'DM Sans', system-ui",
                fontSize:        '13px',
                fontWeight:      600,
                color:           '#475569',
                cursor:          'pointer',
              }}
            >
              Investigate →
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
