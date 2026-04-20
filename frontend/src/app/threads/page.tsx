'use client'

import dynamic from 'next/dynamic'
import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import Navigation from '@/components/Navigation'
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

const MOMENTUM_COLOR: Record<string, string> = {
  escalating: '#EF4444',
  stable: '#94A3B8',
  fading: '#CBD5E1',
}

const MOMENTUM_BG: Record<string, string> = {
  escalating: '#FEF2F2',
  stable: '#F8FAFC',
  fading: '#F8FAFC',
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

  return (
    <div style={{ minHeight: '100vh', backgroundColor: 'var(--color-bg, #F1F5F9)' }}>
      <Navigation />

      <div style={{ paddingTop: '56px', height: '100vh', display: 'flex', flexDirection: 'column' }}>

        {/* ── Page header ─────────────────────────────────────────── */}
        <div style={{
          display:        'flex',
          alignItems:     'center',
          justifyContent: 'space-between',
          padding:        '14px 28px 10px',
          borderBottom:   '1px solid #E2E8F0',
          backgroundColor: '#FFFFFF',
          flexShrink:     0,
        }}>
          <div style={{
            fontFamily:    "'DM Sans', system-ui, sans-serif",
            fontSize:      '11px',
            fontWeight:    600,
            textTransform: 'uppercase',
            letterSpacing: '0.15em',
            color:         '#A1A1AA',
          }}>
            STORY THREADS
          </div>
          <div style={{
            fontFamily: "'DM Mono', ui-monospace, monospace",
            fontSize:   '11px',
            color:      '#A1A1AA',
          }}>
            {loading
              ? 'Loading threads…'
              : escalatingCount > 0
              ? `${threadCount} threads · ${escalatingCount} escalating`
              : `${threadCount} threads`}
          </div>
        </div>

        {/* ── Force graph (60% of remaining height) ───────────────── */}
        <div style={{
          flex:            '0 0 58%',
          position:        'relative',
          backgroundColor: '#FFFFFF',
          borderBottom:    '1px solid #E2E8F0',
          overflow:        'hidden',
          marginRight:     detailPanel ? '320px' : 0,
          transition:      'margin-right 0.25s ease',
        }}>
          {loading ? (
            <div style={{
              width: '100%', height: '100%', display: 'flex',
              alignItems: 'center', justifyContent: 'center',
            }}>
              <div style={{
                fontFamily: "'DM Mono', ui-monospace, monospace",
                fontSize: '11px', color: '#A1A1AA', letterSpacing: '0.1em',
              }}>
                Loading threads…
              </div>
            </div>
          ) : (
            <ThreadGraph
              nodes={nodes}
              edges={edges}
              onNodeClick={handleNodeClick}
              selectedNodeId={selectedNodeId}
            />
          )}
        </div>

        {/* ── Thread list (remaining height, scrollable) ───────────── */}
        <div style={{
          flex:            1,
          overflowY:       'auto',
          marginRight:     detailPanel ? '320px' : 0,
          transition:      'margin-right 0.25s ease',
        }}>
          <div style={{
            padding:        '10px 28px 4px',
            fontFamily:     "'DM Sans', system-ui, sans-serif",
            fontSize:       '10px',
            fontWeight:     600,
            textTransform:  'uppercase',
            letterSpacing:  '0.12em',
            color:          '#A1A1AA',
            borderBottom:   '1px solid #F1F5F9',
          }}>
            ALL THREADS
          </div>

          {nodes.length === 0 && !loading && (
            <div style={{ padding: '24px 28px', fontFamily: "'DM Sans', system-ui", fontSize: '14px', color: '#94A3B8' }}>
              No threads yet — articles are being processed.
            </div>
          )}

          {nodes.map(node => (
            <div
              key={node.thread_id}
              onClick={() => handleRowClick(node.thread_id)}
              style={{
                display:         'flex',
                alignItems:      'center',
                gap:             '12px',
                padding:         '10px 28px',
                cursor:          'pointer',
                borderBottom:    '1px solid #F1F5F9',
                backgroundColor: selectedNodeId === node.thread_id ? '#F8FAFC' : 'transparent',
                transition:      'background 0.12s',
              }}
              onMouseEnter={e => { if (selectedNodeId !== node.thread_id) (e.currentTarget as HTMLDivElement).style.backgroundColor = '#FAFAFA' }}
              onMouseLeave={e => { if (selectedNodeId !== node.thread_id) (e.currentTarget as HTMLDivElement).style.backgroundColor = 'transparent' }}
            >
              {/* Momentum dot */}
              <div style={{
                width:           '8px',
                height:          '8px',
                borderRadius:    '50%',
                backgroundColor: node.momentum === 'fading' ? 'transparent' : MOMENTUM_COLOR[node.momentum] ?? '#CBD5E1',
                border:          node.momentum === 'fading' ? '1.5px solid #CBD5E1' : 'none',
                flexShrink:      0,
              }} />

              {/* Title */}
              <div style={{
                flex:        1,
                fontFamily:  "'DM Sans', system-ui, sans-serif",
                fontSize:    '13px',
                color:       '#18181B',
                overflow:    'hidden',
                textOverflow:'ellipsis',
                whiteSpace:  'nowrap',
              }}>
                {node.title}
              </div>

              {/* Article count */}
              <div style={{
                fontFamily:  "'DM Mono', ui-monospace, monospace",
                fontSize:    '11px',
                color:       '#94A3B8',
                flexShrink:  0,
              }}>
                {node.article_count} art
              </div>

              {/* Last updated */}
              <div style={{
                fontFamily:  "'DM Mono', ui-monospace, monospace",
                fontSize:    '10px',
                color:       '#CBD5E1',
                flexShrink:  0,
                minWidth:    '52px',
                textAlign:   'right',
              }}>
                {formatTimeAgo(node.last_updated_at)}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Thread detail panel ──────────────────────────────────── */}
      {detailPanel && (
        <div
          className="anim-slide-right"
          style={{
            position:        'fixed',
            top:             '56px',
            right:           0,
            width:           '320px',
            height:          'calc(100vh - 56px)',
            backgroundColor: '#FFFFFF',
            borderLeft:      '1px solid #E2E8F0',
            boxShadow:       '-4px 0 16px rgba(15,23,42,0.06)',
            zIndex:          100,
            display:         'flex',
            flexDirection:   'column',
            overflowY:       'auto',
          }}
        >
          {/* Close */}
          <div style={{
            display:        'flex',
            alignItems:     'center',
            justifyContent: 'space-between',
            padding:        '14px 16px 10px',
            borderBottom:   '1px solid #F1F5F9',
            flexShrink:     0,
          }}>
            {/* Momentum badge */}
            <span style={{
              padding:         '3px 10px',
              borderRadius:    '9999px',
              backgroundColor: MOMENTUM_BG[detailPanel.momentum] ?? '#F8FAFC',
              border:          `1px solid ${MOMENTUM_COLOR[detailPanel.momentum] ?? '#CBD5E1'}`,
              fontFamily:      "'DM Mono', ui-monospace, monospace",
              fontSize:        '10px',
              fontWeight:      700,
              color:           MOMENTUM_COLOR[detailPanel.momentum] ?? '#94A3B8',
              letterSpacing:   '0.08em',
              textTransform:   'uppercase',
            }}>
              {detailPanel.momentum}
            </span>
            <button
              onClick={() => { setDetailPanel(null); setSelectedNodeId(null) }}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                fontFamily: "'DM Sans', system-ui", fontSize: '18px',
                color: '#94A3B8', lineHeight: 1, padding: '2px 6px',
              }}
            >
              ×
            </button>
          </div>

          <div style={{ padding: '14px 16px', flex: 1, display: 'flex', flexDirection: 'column', gap: '14px', overflowY: 'auto' }}>

            {/* Title */}
            <div style={{
              fontFamily:  "'Playfair Display', Georgia, serif",
              fontSize:    '18px',
              fontWeight:  700,
              lineHeight:  1.35,
              color:       '#18181B',
            }}>
              {detailPanel.title}
            </div>

            {/* Meta */}
            <div style={{
              fontFamily: "'DM Mono', ui-monospace, monospace",
              fontSize:   '10px',
              color:      '#A1A1AA',
            }}>
              {detailPanel.article_count} articles · first seen {formatTimeAgo(detailPanel.first_seen_at)}
            </div>

            {/* Entities */}
            {detailPanel.primary_entities.length > 0 && (
              <div>
                <div style={{
                  fontFamily: "'DM Sans', system-ui", fontSize: '9px',
                  fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.12em',
                  color: '#A1A1AA', marginBottom: '6px',
                }}>
                  KEY ENTITIES
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                  {detailPanel.primary_entities.map(entity => (
                    <span
                      key={entity}
                      style={{
                        padding:         '2px 8px',
                        backgroundColor: '#EFF6FF',
                        border:          '1px solid #DBEAFE',
                        borderRadius:    '3px',
                        fontFamily:      "'DM Sans', system-ui",
                        fontSize:        '11px',
                        color:           '#3B82F6',
                      }}
                    >
                      {entity}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Articles */}
            <div>
              <div style={{
                fontFamily: "'DM Sans', system-ui", fontSize: '9px',
                fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.12em',
                color: '#A1A1AA', marginBottom: '8px',
              }}>
                ARTICLES IN THIS THREAD
              </div>
              <div style={{ maxHeight: '38vh', overflowY: 'auto' }}>
                {detailLoading && (
                  <div style={{ fontFamily: "'DM Mono'", fontSize: '11px', color: '#A1A1AA', padding: '8px 0' }}>
                    Loading articles…
                  </div>
                )}
                {detailPanel.articles.map((article, i) => (
                  <div key={article.article_id}>
                    <div style={{ padding: '8px 0' }}>
                      <div style={{
                        fontFamily:  "'DM Sans', system-ui",
                        fontSize:    '11px',
                        color:       '#94A3B8',
                        marginBottom:'3px',
                      }}>
                        {article.source_name} · {formatTimeAgo(article.collected_at)}
                      </div>
                      <div style={{
                        fontFamily:    "'DM Sans', system-ui",
                        fontSize:      '13px',
                        color:         '#18181B',
                        lineHeight:    1.4,
                        display:       '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                        overflow:      'hidden',
                      }}>
                        {article.title}
                      </div>
                      {article.topic_category && (
                        <span style={{
                          display: 'inline-block', marginTop: '4px',
                          padding: '1px 6px',
                          backgroundColor: '#F1F5F9', borderRadius: '3px',
                          fontFamily: "'DM Sans', system-ui", fontSize: '9px',
                          color: '#64748B', textTransform: 'uppercase', letterSpacing: '0.06em',
                        }}>
                          {article.topic_category}
                        </span>
                      )}
                    </div>
                    {i < detailPanel.articles.length - 1 && (
                      <div style={{ height: '1px', backgroundColor: '#F1F5F9' }} />
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Investigate button */}
            <button
              onClick={() => void handleInvestigate()}
              disabled={investigateLoading}
              style={{
                width:           '100%',
                height:          '44px',
                backgroundColor: investigateLoading ? '#CBD5E1' : '#18181B',
                color:           '#FFFFFF',
                border:          'none',
                borderRadius:    '6px',
                fontFamily:      "'DM Sans', system-ui, sans-serif",
                fontSize:        '14px',
                fontWeight:      600,
                cursor:          investigateLoading ? 'not-allowed' : 'pointer',
                transition:      'background 0.15s',
                marginTop:       'auto',
                flexShrink:      0,
              }}
              onMouseEnter={e => { if (!investigateLoading) (e.currentTarget as HTMLButtonElement).style.backgroundColor = '#27272A' }}
              onMouseLeave={e => { if (!investigateLoading) (e.currentTarget as HTMLButtonElement).style.backgroundColor = '#18181B' }}
            >
              {investigateLoading ? 'Opening Analyst…' : 'Investigate this thread →'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
