'use client'

import dynamic from 'next/dynamic'
import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import Navigation from '@/components/Navigation'
import { Dateline } from '@/components/Dateline'
import type { ThreadNode, ThreadEdge } from '@/components/ThreadGraph'

const ThreadGraph = dynamic(() => import('@/components/ThreadGraph'), { ssr: false })

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface ThreadDetail {
  thread_id: string
  title: string
  primary_entities: string[]
  article_count: number
  momentum: string
  first_seen_at: string
  last_updated_at: string
  articles: ThreadArticle[]
}

interface ThreadArticle {
  article_id: string
  title: string
  url: string
  topic_category: string | null
  geo_primary: string | null
  collected_at: string | null
  source_name: string
  source_domain: string
  score_final: number | null
  relevance_tier: string | null
}

function formatTimeAgo(iso: string | null | undefined): string {
  if (!iso) return 'unknown'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

type Momentum = 'escalating' | 'stable' | 'fading'

const MOMENTUM_LABEL: Record<string, string> = {
  escalating: 'Escalating',
  stable: 'Holding',
  fading: 'Fading',
}

const MOMENTUM_TONE: Record<string, 'alert' | 'gold' | 'default'> = {
  escalating: 'alert',
  stable: 'gold',
  fading: 'default',
}

export default function ThreadsPage() {
  const router = useRouter()

  const getToken = useCallback(async (): Promise<string | null> => {
    const supabase = createClient()
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) { router.push('/login'); return null }
    return session.access_token
  }, [router])

  const [nodes, setNodes] = useState<ThreadNode[]>([])
  const [edges, setEdges] = useState<ThreadEdge[]>([])
  const [threadCount, setThreadCount] = useState(0)
  const [escalatingCount, setEscalatingCount] = useState(0)
  const [loading, setLoading] = useState(true)

  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [detailPanel, setDetailPanel] = useState<ThreadDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [investigateLoading, setInvestigateLoading] = useState(false)
  const [view, setView] = useState<'atlas' | 'ledger'>('atlas')
  const [momentumFilter, setMomentumFilter] = useState<'all' | Momentum>('all')

  useEffect(() => {
    const load = async () => {
      const token = await getToken()
      if (!token) return
      try {
        const res = await fetch(`${API_BASE}/api/threads?limit=50`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!res.ok) return
        const data = await res.json()
        setNodes(data.nodes ?? [])
        setEdges(data.edges ?? [])
        setThreadCount(data.thread_count ?? 0)
        setEscalatingCount(data.escalating_count ?? 0)
      } catch {
        // non-critical
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [getToken])

  const openDetail = async (threadId: string) => {
    const token = await getToken()
    if (!token) return
    setDetailLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/threads/${threadId}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) setDetailPanel(await res.json())
    } catch {
      // non-critical
    } finally {
      setDetailLoading(false)
    }
  }

  const handleNodeClick = (node: ThreadNode) => {
    setSelectedNodeId(node.thread_id)
    void openDetail(node.thread_id)
  }

  const handleRowClick = (threadId: string) => {
    setSelectedNodeId(threadId)
    void openDetail(threadId)
  }

  const handleInvestigate = async () => {
    if (!detailPanel) return
    const token = await getToken()
    if (!token) return
    setInvestigateLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/threads/${detailPanel.thread_id}/investigate`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        router.push(
          `/analyst?session=${data.session_id}&question=${encodeURIComponent(data.question)}`,
        )
      }
    } catch {
      // non-critical
    } finally {
      setInvestigateLoading(false)
    }
  }

  const visibleNodes = momentumFilter === 'all'
    ? nodes
    : nodes.filter(n => n.momentum === momentumFilter)

  return (
    <div style={{ minHeight: '100vh', background: 'var(--rig-paper)' }}>
      <Navigation />

      <div
        style={{
          paddingTop: 'var(--topbar-h)',
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <Dateline
          issueNumber={threadCount}
          extra={escalatingCount > 0 ? [`${escalatingCount} ESCALATING`] : undefined}
        />

        {/* ── Section head ──────────────────────────────────────── */}
        <div
          style={{
            padding: '40px 48px 24px',
            borderBottom: '1px solid var(--rig-rule-hair)',
            marginRight: detailPanel ? '480px' : 0,
            transition: 'margin-right 0.25s ease',
          }}
        >
          <div className="rig-kicker" style={{ marginBottom: '10px' }}>
            The Situation Room
          </div>
          <h1
            className="rig-headline"
            style={{
              fontSize: '34px',
              margin: 0,
              marginBottom: '14px',
              letterSpacing: '-0.01em',
            }}
          >
            Narrative arcs in motion,{' '}
            <em style={{ fontWeight: 500, color: 'var(--rig-gold)' }}>
              filed as they cohere.
            </em>
          </h1>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '32px',
              marginTop: '18px',
            }}
          >
            <StatBadge value={loading ? '—' : threadCount} label="Open files" tone="default" />
            <StatBadge
              value={loading ? '—' : escalatingCount}
              label="Escalating"
              tone={escalatingCount > 0 ? 'alert' : 'default'}
            />
            <StatBadge
              value={loading ? '—' : nodes.filter(n => n.momentum === 'stable').length}
              label="Holding"
              tone="gold"
            />
          </div>
        </div>

        {/* ── Control strip ─────────────────────────────────────── */}
        <div
          style={{
            position: 'sticky',
            top: 'var(--topbar-h)',
            zIndex: 50,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '14px 48px',
            background: 'var(--rig-paper-2)',
            borderBottom: '1px solid var(--rig-rule)',
            marginRight: detailPanel ? '480px' : 0,
            transition: 'margin-right 0.25s ease',
            flexWrap: 'wrap',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <ViewToggle label="Atlas" active={view === 'atlas'} onClick={() => setView('atlas')} />
            <Divider />
            <ViewToggle label="Ledger" active={view === 'ledger'} onClick={() => setView('ledger')} />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span className="rig-kicker" style={{ marginRight: '10px', opacity: 0.7 }}>
              Momentum
            </span>
            <FilterPill label="All" active={momentumFilter === 'all'} onClick={() => setMomentumFilter('all')} />
            <FilterPill label="Escalating" active={momentumFilter === 'escalating'} onClick={() => setMomentumFilter('escalating')} tone="alert" />
            <FilterPill label="Holding" active={momentumFilter === 'stable'} onClick={() => setMomentumFilter('stable')} />
            <FilterPill label="Fading" active={momentumFilter === 'fading'} onClick={() => setMomentumFilter('fading')} />
          </div>
        </div>

        {/* ── Atlas (graph) ─────────────────────────────────────── */}
        {view === 'atlas' && (
          <div
            style={{
              height: '58vh',
              minHeight: '420px',
              position: 'relative',
              background: 'var(--rig-paper)',
              borderBottom: '1px solid var(--rig-rule-hair)',
              overflow: 'hidden',
              marginRight: detailPanel ? '480px' : 0,
              transition: 'margin-right 0.25s ease',
            }}
          >
            {loading ? (
              <GraphLoading />
            ) : nodes.length === 0 ? (
              <DeskMemo
                kicker="Desk memo"
                headline="No threads have cohered yet."
                body="As articles arrive and cluster, their shared arcs will appear here."
              />
            ) : (
              <ThreadGraph
                nodes={visibleNodes}
                edges={edges}
                onNodeClick={handleNodeClick}
                selectedNodeId={selectedNodeId}
              />
            )}
          </div>
        )}

        {/* ── Ledger (list) ─────────────────────────────────────── */}
        {(view === 'ledger' || view === 'atlas') && (
          <div
            style={{
              marginRight: detailPanel ? '480px' : 0,
              transition: 'margin-right 0.25s ease',
              padding: '32px 48px 64px',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'baseline',
                justifyContent: 'space-between',
                paddingBottom: '14px',
                marginBottom: '18px',
                borderBottom: '1px solid var(--rig-rule)',
              }}
            >
              <div className="rig-kicker">
                {view === 'atlas' ? 'The Ledger — below' : 'All open files'}
              </div>
              <div
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '10px',
                  letterSpacing: '0.2em',
                  textTransform: 'uppercase',
                  color: 'var(--rig-ink-3)',
                }}
              >
                {visibleNodes.length} of {threadCount}
              </div>
            </div>

            {loading && <LedgerSkeleton />}

            {!loading && visibleNodes.length === 0 && (
              <DeskMemo
                kicker="Desk memo"
                headline="No threads match this filter."
                body="Try widening the momentum filter or return to the Atlas."
              />
            )}

            {!loading && visibleNodes.map((node, idx) => (
              <ThreadRow
                key={node.thread_id}
                node={node}
                selected={selectedNodeId === node.thread_id}
                index={idx + 1}
                onClick={() => handleRowClick(node.thread_id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* ── Detail panel (slide-in) ─────────────────────────────── */}
      {detailPanel && (
        <ThreadDetailPanel
          detail={detailPanel}
          detailLoading={detailLoading}
          investigateLoading={investigateLoading}
          onClose={() => { setDetailPanel(null); setSelectedNodeId(null) }}
          onInvestigate={() => void handleInvestigate()}
        />
      )}
    </div>
  )
}

/* ── Subcomponents ─────────────────────────────────────────────── */

interface StatBadgeProps {
  value: number | string
  label: string
  tone: 'default' | 'gold' | 'alert'
}

function StatBadge({ value, label, tone }: StatBadgeProps) {
  const color =
    tone === 'alert' ? 'var(--rig-oxblood)' :
    tone === 'gold' ? 'var(--rig-gold)' :
    'var(--rig-ink)'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <span
        style={{
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontWeight: 500,
          fontSize: '28px',
          lineHeight: 1,
          color,
        }}
      >
        {value}
      </span>
      <span className="rig-kicker" style={{ opacity: 0.75 }}>{label}</span>
    </div>
  )
}

interface ViewToggleProps {
  label: string
  active: boolean
  onClick: () => void
}

function ViewToggle({ label, active, onClick }: ViewToggleProps) {
  return (
    <button
      onClick={onClick}
      style={{
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        padding: '6px 12px',
        fontFamily: 'var(--font-mono)',
        fontSize: '10px',
        letterSpacing: '0.24em',
        textTransform: 'uppercase',
        color: active ? 'var(--rig-ink)' : 'var(--rig-ink-3)',
        borderBottom: active ? '1px solid var(--rig-gold)' : '1px solid transparent',
        transition: 'color 0.15s, border-color 0.15s',
      }}
    >
      {label}
    </button>
  )
}

function Divider() {
  return (
    <span
      aria-hidden="true"
      style={{
        width: '1px',
        height: '14px',
        background: 'var(--rig-rule)',
        margin: '0 8px',
      }}
    />
  )
}

interface FilterPillProps {
  label: string
  active: boolean
  onClick: () => void
  tone?: 'alert'
}

function FilterPill({ label, active, onClick, tone }: FilterPillProps) {
  const activeColor = tone === 'alert' ? 'var(--rig-oxblood)' : 'var(--rig-ink)'
  return (
    <button
      onClick={onClick}
      style={{
        background: 'none',
        border: '1px solid',
        borderColor: active ? activeColor : 'var(--rig-rule)',
        cursor: 'pointer',
        padding: '5px 11px',
        fontFamily: 'var(--font-mono)',
        fontSize: '10px',
        letterSpacing: '0.2em',
        textTransform: 'uppercase',
        color: active ? activeColor : 'var(--rig-ink-3)',
        backgroundColor: active ? 'color-mix(in srgb, var(--rig-paper-2) 60%, transparent)' : 'transparent',
        transition: 'all 0.15s',
      }}
    >
      {label}
    </button>
  )
}

interface ThreadRowProps {
  node: ThreadNode
  selected: boolean
  index: number
  onClick: () => void
}

function ThreadRow({ node, selected, index, onClick }: ThreadRowProps) {
  const [hover, setHover] = useState(false)
  const isEscalating = node.momentum === 'escalating'
  const isFading = node.momentum === 'fading'

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'grid',
        gridTemplateColumns: '44px 12px 1fr auto auto',
        alignItems: 'baseline',
        gap: '16px',
        padding: '18px 0',
        cursor: 'pointer',
        borderBottom: '1px solid var(--rig-rule-hair)',
        background: selected
          ? 'color-mix(in srgb, var(--rig-gold) 10%, transparent)'
          : hover
          ? 'color-mix(in srgb, var(--rig-paper-2) 60%, transparent)'
          : 'transparent',
        borderLeft: isEscalating ? '2px solid var(--rig-oxblood)' : '2px solid transparent',
        paddingLeft: '14px',
        marginLeft: '-14px',
        transition: 'background 0.15s',
        opacity: isFading ? 0.72 : 1,
      }}
    >
      <span
        style={{
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontWeight: 400,
          fontSize: '22px',
          color: 'var(--rig-ink-3)',
          lineHeight: 1,
        }}
      >
        {String(index).padStart(2, '0')}
      </span>

      <span
        aria-hidden="true"
        style={{
          width: '8px',
          height: '8px',
          borderRadius: '50%',
          backgroundColor: isEscalating
            ? 'var(--rig-oxblood)'
            : isFading
            ? 'transparent'
            : 'var(--rig-gold)',
          border: isFading ? '1.5px solid var(--rig-ink-3)' : 'none',
          alignSelf: 'center',
        }}
      />

      <div style={{ minWidth: 0 }}>
        <div
          className="rig-headline"
          style={{
            fontSize: '18px',
            lineHeight: 1.3,
            color: 'var(--rig-ink)',
            overflow: 'hidden',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
          }}
        >
          {node.title}
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            marginTop: '6px',
          }}
          className="rig-byline"
        >
          <span>{MOMENTUM_LABEL[node.momentum] ?? node.momentum}</span>
          <span aria-hidden="true" style={{ opacity: 0.4 }}>·</span>
          <span>Last filed {formatTimeAgo(node.last_updated_at)}</span>
        </div>
      </div>

      <span
        style={{
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontWeight: 500,
          fontSize: '22px',
          color: 'var(--rig-gold)',
          lineHeight: 1,
        }}
      >
        {node.article_count}
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontStyle: 'normal',
            fontSize: '9px',
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            color: 'var(--rig-ink-3)',
            marginLeft: '6px',
          }}
        >
          dispatches
        </span>
      </span>

      <span
        aria-hidden="true"
        style={{
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          color: hover || selected ? 'var(--rig-gold)' : 'var(--rig-ink-3)',
          fontSize: '18px',
          transition: 'color 0.15s',
        }}
      >
        →
      </span>
    </div>
  )
}

function LedgerSkeleton() {
  return (
    <div>
      {[1, 2, 3, 4].map(i => (
        <div
          key={i}
          style={{
            padding: '18px 0',
            borderBottom: '1px solid var(--rig-rule-hair)',
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
            opacity: 0.5,
          }}
        >
          <div style={{ height: '18px', width: '40%', background: 'var(--rig-paper-2)' }} />
          <div style={{ height: '12px', width: '20%', background: 'var(--rig-paper-2)', marginLeft: 'auto' }} />
        </div>
      ))}
    </div>
  )
}

function GraphLoading() {
  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexDirection: 'column',
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
        Plotting the arcs…
      </span>
      <span
        style={{
          width: '160px',
          height: '1px',
          background:
            'linear-gradient(90deg, transparent, var(--rig-gold), transparent)',
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
        padding: '48px 32px',
        textAlign: 'center',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '10px',
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
          maxWidth: '420px',
          lineHeight: 1.55,
        }}
      >
        {body}
      </span>
    </div>
  )
}

interface ThreadDetailPanelProps {
  detail: ThreadDetail
  detailLoading: boolean
  investigateLoading: boolean
  onClose: () => void
  onInvestigate: () => void
}

function ThreadDetailPanel({
  detail,
  detailLoading,
  investigateLoading,
  onClose,
  onInvestigate,
}: ThreadDetailPanelProps) {
  const tone = MOMENTUM_TONE[detail.momentum] ?? 'default'

  return (
    <aside
      className="anim-slide-right"
      style={{
        position: 'fixed',
        top: 'var(--topbar-h)',
        right: 0,
        width: '480px',
        height: 'calc(100vh - var(--topbar-h))',
        background: 'var(--rig-paper)',
        borderLeft: '1px solid var(--rig-rule)',
        boxShadow: '-8px 0 32px color-mix(in srgb, var(--rig-ink) 8%, transparent)',
        zIndex: 100,
        display: 'flex',
        flexDirection: 'column',
        overflowY: 'auto',
      }}
    >
      {/* Panel head */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '20px 28px 14px',
          borderBottom: '1px solid var(--rig-rule-hair)',
          flexShrink: 0,
          background: 'var(--rig-paper-2)',
        }}
      >
        <span className="rig-kicker">The file on this thread</span>
        <button
          onClick={onClose}
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
          aria-label="Close"
        >
          ×
        </button>
      </div>

      <div
        style={{
          padding: '24px 28px 8px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
        }}
      >
        <span className="rig-chip" data-tone={tone === 'default' ? undefined : tone} style={{ alignSelf: 'flex-start' }}>
          <span className="dot" />
          {MOMENTUM_LABEL[detail.momentum] ?? detail.momentum}
        </span>

        <h2
          className="rig-headline"
          style={{
            fontSize: '26px',
            margin: 0,
            lineHeight: 1.25,
            color: 'var(--rig-ink)',
          }}
        >
          {detail.title}
        </h2>

        <div
          className="rig-byline"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
          }}
        >
          <span>{detail.article_count} dispatches</span>
          <span aria-hidden="true" style={{ opacity: 0.4 }}>·</span>
          <span>First seen {formatTimeAgo(detail.first_seen_at)}</span>
          <span aria-hidden="true" style={{ opacity: 0.4 }}>·</span>
          <span>Updated {formatTimeAgo(detail.last_updated_at)}</span>
        </div>
      </div>

      {detail.primary_entities.length > 0 && (
        <div style={{ padding: '14px 28px 0' }}>
          <div
            className="rig-kicker"
            style={{ marginBottom: '10px', opacity: 0.75 }}
          >
            Figures in the frame
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {detail.primary_entities.map(entity => (
              <span
                key={entity}
                style={{
                  padding: '4px 10px',
                  background: 'transparent',
                  border: '1px solid var(--rig-rule)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '10px',
                  letterSpacing: '0.12em',
                  textTransform: 'uppercase',
                  color: 'var(--rig-ink-2)',
                }}
              >
                {entity}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Dispatches */}
      <div style={{ padding: '22px 28px 0', flex: 1 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            justifyContent: 'space-between',
            borderBottom: '1px solid var(--rig-rule)',
            paddingBottom: '8px',
            marginBottom: '4px',
          }}
        >
          <span className="rig-kicker">Dispatches, in order</span>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '9px',
              letterSpacing: '0.2em',
              textTransform: 'uppercase',
              color: 'var(--rig-ink-3)',
            }}
          >
            {detail.articles.length} items
          </span>
        </div>

        {detailLoading && (
          <div
            style={{
              padding: '18px 0',
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              color: 'var(--rig-ink-3)',
              fontSize: '15px',
            }}
          >
            Gathering dispatches…
          </div>
        )}

        {detail.articles.map((article, i) => (
          <div
            key={article.article_id}
            style={{
              padding: '14px 0',
              borderBottom:
                i < detail.articles.length - 1
                  ? '1px solid var(--rig-rule-hair)'
                  : 'none',
              display: 'grid',
              gridTemplateColumns: '28px 1fr',
              gap: '12px',
              alignItems: 'baseline',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--font-serif)',
                fontStyle: 'italic',
                color: 'var(--rig-ink-3)',
                fontSize: '14px',
              }}
            >
              {String(i + 1).padStart(2, '0')}
            </span>
            <div>
              <div className="rig-byline" style={{ marginBottom: '4px' }}>
                {article.source_name} · {formatTimeAgo(article.collected_at)}
              </div>
              <div
                style={{
                  fontFamily: 'var(--font-serif)',
                  fontWeight: 500,
                  fontSize: '15px',
                  color: 'var(--rig-ink)',
                  lineHeight: 1.35,
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                }}
              >
                {article.title}
              </div>
              {article.topic_category && (
                <span
                  style={{
                    display: 'inline-block',
                    marginTop: '6px',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '9px',
                    letterSpacing: '0.18em',
                    textTransform: 'uppercase',
                    color: 'var(--rig-copper)',
                  }}
                >
                  {article.topic_category}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Investigate CTA */}
      <div
        style={{
          padding: '20px 28px 28px',
          borderTop: '1px solid var(--rig-rule-hair)',
          background: 'var(--rig-paper-2)',
          marginTop: 'auto',
          flexShrink: 0,
        }}
      >
        <button
          onClick={onInvestigate}
          disabled={investigateLoading}
          className="rig-btn-primary"
          style={{
            width: '100%',
            opacity: investigateLoading ? 0.6 : 1,
            cursor: investigateLoading ? 'not-allowed' : 'pointer',
          }}
        >
          {investigateLoading ? 'Opening the Analyst…' : 'Take this to the Analyst  →'}
        </button>
        <div
          style={{
            marginTop: '10px',
            fontFamily: 'var(--font-serif)',
            fontStyle: 'italic',
            fontSize: '12px',
            color: 'var(--rig-ink-3)',
            textAlign: 'center',
          }}
        >
          Ask questions of this thread in the reading room.
        </div>
      </div>
    </aside>
  )
}
