'use client'

import { useEffect, useState } from 'react'
import type { Pillar } from './types'
import { WiresMomentCard, scoreStory } from './WiresMomentCard'
import type { ScoredStory, WireStory } from './WiresMomentCard'
import { WiresDeskSummary } from './WiresDeskSummary'

/**
 * Top of the Wires — bi-pane "story of the moment" + live desk summary.
 *
 * Owns the cross-pillar fetch + criticality scoring, then hands the
 * scored story pool to both subcomponents. Polling cadence is 60s, which
 * matches the shelves below; the brief-anchor poll inside the summary is
 * a slower 5min loop because the brief itself only refreshes daily.
 */

interface HighlightsBandProps {
  apiBase: string
  token: string | null
  paused: boolean
}

interface FeedSpec {
  pillar: Pillar
  url: string
  itemsKey: 'articles' | 'clippings' | 'posts' | 'clips' | 'documents'
}

const POLL_INTERVAL_MS = 60_000
// No hard cap — rotate through up to 30 freshest stories so the moment
// card keeps cycling new content rather than looping the same five.
const TOP_N = 30
const PER_PILLAR_TAKE = 8

export function HighlightsBand({
  apiBase,
  token,
  paused,
}: HighlightsBandProps): React.ReactElement {
  const [scored, setScored] = useState<ScoredStory[]>([])
  const [counts, setCounts] = useState<Record<Pillar, number>>({
    articles: 0, newspaper: 0, social: 0, clips: 0, documents: 0,
  })
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!token) return
    let cancelled = false

    // Per-pillar sort behaviour (backend defaults):
    //   - articles:  default sort=relevance (score DESC) — pass
    //                sort=recency or freshest items get buried under older
    //                high-scoring ones.
    //   - clips, newspaper: ORDER BY relevance_score DESC, collected_at
    //                DESC — same problem; backend has no sort param yet,
    //                so we just pull max limit and client-side sort wins.
    //   - social, documents: already collected_at DESC, no fix needed.
    const feeds: FeedSpec[] = [
      { pillar: 'articles', url: `${apiBase}/api/coverage/feed?sort=recency&limit=50`, itemsKey: 'articles' },
      { pillar: 'newspaper', url: `${apiBase}/api/clippings/feed?days=14&limit=50`, itemsKey: 'clippings' },
      { pillar: 'social', url: `${apiBase}/api/signals/feed?days=2&limit=50`, itemsKey: 'posts' },
      { pillar: 'clips', url: `${apiBase}/api/clips/feed?days=14&limit=50`, itemsKey: 'clips' },
      { pillar: 'documents', url: `${apiBase}/api/documents/feed?days=14&limit=50`, itemsKey: 'documents' },
    ]

    const tick = async (): Promise<void> => {
      if (paused) return
      try {
        const responses = await Promise.allSettled(
          feeds.map((f) =>
            fetch(f.url, { headers: { Authorization: `Bearer ${token}` } }).then(
              async (res) => {
                if (!res.ok) throw new Error(`${f.pillar} HTTP ${res.status}`)
                return { feed: f, json: (await res.json()) as Record<string, unknown> }
              },
            ),
          ),
        )

        if (cancelled) return

        const collected: WireStory[] = []
        const pillarTotals: Record<Pillar, number> = {
          articles: 0, newspaper: 0, social: 0, clips: 0, documents: 0,
        }

        for (const r of responses) {
          if (r.status !== 'fulfilled') continue
          const { feed, json } = r.value
          const arr = (json[feed.itemsKey] as unknown[]) ?? []
          pillarTotals[feed.pillar] = arr.length
          for (const raw of arr.slice(0, PER_PILLAR_TAKE)) {
            const w = toWireStory(raw, feed.pillar)
            if (w) collected.push(w)
          }
        }

        // Score every collected story against the same pool so cohort
        // detection (pillar diversity in the time window) is consistent.
        const allScored = collected.map((s) => scoreStory(s, collected))

        // Sort by RECENCY first (newest leads — the user explicitly wants
        // "latest first"), criticality is shown via the per-card pill.
        // Score-led sorting was burying today's items under yesterday's
        // T1 articles; recency-first matches what the live shelves do.
        allScored.sort((a, b) => {
          const ta = a.timestamp ? Date.parse(a.timestamp) : 0
          const tb = b.timestamp ? Date.parse(b.timestamp) : 0
          if (tb !== ta) return tb - ta
          return b.score - a.score
        })

        if (cancelled) return
        setScored(allScored.slice(0, TOP_N))
        setCounts(pillarTotals)
        setError(null)
        setLoading(false)
      } catch (err: unknown) {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Network error')
        setLoading(false)
      }
    }

    void tick()
    const id = setInterval(() => void tick(), POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [apiBase, token, paused])

  return (
    <section style={{ padding: '36px 0 28px' }}>
      <header
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: '16px',
          marginBottom: '20px',
        }}
      >
        <span className="rig-kicker rig-kicker-gold">Top of the Wires · live desk</span>
        <span style={{ flex: 1, height: '1px', background: 'var(--rig-rule-hair)' }} />
        <span
          className="rig-byline"
          style={{ fontSize: '10px', color: 'var(--rig-ink-3)' }}
        >
          {scored.length > 0
            ? `ranked by criticality · refreshes every 60s`
            : 'live'}
        </span>
      </header>

      {error ? (
        <p
          className="rig-prose"
          style={{ fontStyle: 'italic', color: 'var(--rig-oxblood)' }}
        >
          Couldn&apos;t load the wires — {error}
        </p>
      ) : loading ? (
        <p
          className="rig-prose"
          style={{ fontStyle: 'italic', color: 'var(--rig-ink-3)' }}
        >
          Reading the wires…
        </p>
      ) : (
        <div
          style={{
            display: 'grid',
            // 2/3 + 1/3 split on wide; stacks on narrow.
            gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)',
            gap: '20px',
            alignItems: 'stretch',
          }}
        >
          <WiresMomentCard stories={scored} />
          <WiresDeskSummary
            apiBase={apiBase}
            token={token}
            paused={paused}
            topStories={scored}
            pillarCounts={counts}
          />
        </div>
      )}
    </section>
  )
}

/* ── Per-pillar shape extractors → WireStory ───────────────────────────── */

interface RawArticle {
  article_id?: string
  id?: string
  title?: string
  lead_text_translated?: string | null
  lead_text_original?: string | null
  source_name?: string | null
  topic_category?: string | null
  published_at?: string | null
  collected_at?: string | null
  relevance_tier?: number | null
  matched_entity_names?: string[] | null
}
interface RawClipping {
  clipping_id?: string
  headline?: string | null
  headline_translated?: string | null
  article_text?: string | null
  article_text_translated?: string | null
  newspaper_name?: string | null
  topic_category?: string | null
  edition_date?: string | null
  collected_at?: string | null
  entities_extracted?: string[] | null
}
interface RawPost {
  post_id?: string
  platform?: string
  post_text?: string | null
  post_text_translated?: string | null
  monitor_name?: string | null
  topic_category?: string | null
  posted_at?: string | null
  collected_at?: string | null
  sentiment_score?: number | null
  matched_entities?: unknown
}
interface RawClip {
  clip_id?: string
  video_id?: string
  video_title?: string | null
  channel_name?: string | null
  matched_entity?: string | null
  transcript_translated?: string | null
  transcript_segment?: string | null
  video_published_at?: string | null
  collected_at?: string | null
}
interface RawDoc {
  doc_id?: string
  id?: string
  title?: string | null
  summary?: string | null
  intel_json?: { what_it_does?: string } | null
  source_name?: string | null
  source_geography?: string | null
  document_type?: string | null
  published_at?: string | null
  collected_at?: string | null
  urgency?: string | null
}

/** Social posts store matched entities as a JSONB shape that varies —
 * sometimes a dict keyed by entity, sometimes an array of names. Coerce
 * to a string[] of names; return [] for anything we can't parse. */
function extractMatchedEntities(raw: unknown): string[] {
  if (!raw) return []
  if (Array.isArray(raw)) return raw.map((x) => String(x)).slice(0, 8)
  if (typeof raw === 'object') return Object.keys(raw as Record<string, unknown>).slice(0, 8)
  if (typeof raw === 'string') {
    try {
      const parsed: unknown = JSON.parse(raw)
      if (Array.isArray(parsed)) return parsed.map((x) => String(x)).slice(0, 8)
      if (typeof parsed === 'object' && parsed !== null) {
        return Object.keys(parsed as Record<string, unknown>).slice(0, 8)
      }
    } catch {
      /* fall through */
    }
  }
  return []
}

function toWireStory(raw: unknown, pillar: Pillar): WireStory | null {
  if (typeof raw !== 'object' || raw === null) return null
  switch (pillar) {
    case 'articles': {
      const a = raw as RawArticle
      const id = a.article_id ?? a.id
      if (!id) return null
      const snippet = (a.lead_text_translated ?? a.lead_text_original ?? '').slice(0, 320)
      const entities = Array.isArray(a.matched_entity_names) ? a.matched_entity_names : []
      return {
        id, pillar,
        headline: a.title ?? '',
        source: a.source_name ?? null,
        // collected_at first — Coverage page uses the same, so the same
        // article shows the same "X min ago" on both surfaces.
        timestamp: a.collected_at ?? a.published_at ?? null,
        topic: a.topic_category ?? null,
        href: `/coverage?article=${id}`,
        tier: a.relevance_tier ?? null,
        sentiment: null,
        snippet: snippet || null,
        entities,
      }
    }
    case 'newspaper': {
      const c = raw as RawClipping
      if (!c.clipping_id) return null
      const snippet = (c.article_text_translated ?? c.article_text ?? '').slice(0, 320)
      const entities = Array.isArray(c.entities_extracted) ? c.entities_extracted : []
      return {
        id: c.clipping_id, pillar,
        headline: c.headline_translated || c.headline || '',
        source: c.newspaper_name ?? null,
        timestamp: c.collected_at ?? c.edition_date ?? null,
        topic: c.topic_category ?? null,
        href: '/cuttings',
        tier: null,
        sentiment: null,
        snippet: snippet || null,
        entities,
      }
    }
    case 'social': {
      const p = raw as RawPost
      if (!p.post_id) return null
      // Use the FULL post text as the snippet (longer than headline);
      // headline is a tighter excerpt for the title slot.
      const full = p.post_text_translated ?? p.post_text ?? ''
      const headline = full.slice(0, 140)
      const snippet = full.length > 140 ? full.slice(0, 360) : null
      const entityNames = extractMatchedEntities(p.matched_entities)
      return {
        id: p.post_id, pillar,
        headline,
        source: p.platform ? p.platform.toUpperCase() : (p.monitor_name ?? null),
        timestamp: p.posted_at ?? p.collected_at ?? null,
        topic: p.topic_category ?? null,
        href: '/signals',
        tier: null,
        sentiment: p.sentiment_score ?? null,
        snippet,
        entities: entityNames,
      }
    }
    case 'clips': {
      const c = raw as RawClip
      if (!c.clip_id) return null
      const snippet = (c.transcript_translated ?? c.transcript_segment ?? '').slice(0, 320)
      return {
        id: c.clip_id, pillar,
        headline: c.video_title ?? '',
        source: c.channel_name ?? null,
        timestamp: c.collected_at ?? c.video_published_at ?? null,
        topic: c.matched_entity ?? null,
        href: '/clips',
        tier: null,
        sentiment: null,
        snippet: snippet || null,
        entities: c.matched_entity ? [c.matched_entity] : [],
      }
    }
    case 'documents': {
      const d = raw as RawDoc
      const id = d.doc_id ?? d.id
      if (!id) return null
      const intelWhat =
        d.intel_json && typeof d.intel_json.what_it_does === 'string'
          ? d.intel_json.what_it_does
          : null
      const snippet = (intelWhat ?? d.summary ?? '').slice(0, 320)
      return {
        id, pillar,
        headline: d.title ?? '',
        source: d.source_name ?? d.source_geography ?? null,
        timestamp: d.collected_at ?? d.published_at ?? null,
        topic: d.document_type ?? null,
        href: '/documents',
        tier: null,
        sentiment: null,
        snippet: snippet || null,
        entities: [],
      }
    }
    default:
      return null
  }
}
