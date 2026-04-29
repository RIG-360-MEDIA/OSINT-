import type {
  ArticleMonitorItem,
  ClipMonitorItem,
  DocumentMonitorItem,
  MonitorItem,
  NewspaperMonitorItem,
  SocialMonitorItem,
} from './types'

/* ── Raw backend feed shapes ────────────────────────────────────────────── */
//
// Each pillar has its own /feed endpoint in the existing pillar router.
// The shapes below are the subset the cards consume; extra fields are
// ignored. Optional / nullable everywhere so a missing field never throws.

interface RawArticleFeed {
  articles?: Array<{
    article_id?: string
    id?: string
    title?: string
    source_name?: string | null
    source_domain?: string | null
    thumbnail_url?: string | null
    published_at?: string | null
    collected_at?: string | null
    relevance_tier?: number | null
    topic_category?: string | null
    geo_primary?: string | null
    url?: string | null
  }>
}

interface RawClippingFeed {
  clippings?: Array<{
    clipping_id: string
    headline?: string | null
    headline_translated?: string | null
    newspaper_name?: string | null
    newspaper_language?: string | null
    edition_date?: string | null
    page_number?: number | null
    topic_category?: string | null
    collected_at?: string | null
    image_url?: string | null
    clipping_image_url?: string | null
  }>
}

interface RawSignalsFeed {
  posts?: Array<{
    post_id: string
    platform?: string
    monitor_name?: string | null
    author_username?: string | null
    post_text?: string | null
    post_text_translated?: string | null
    post_language?: string | null
    posted_at?: string | null
    collected_at?: string
    sentiment_score?: number | null
    upvotes?: number | null
    comment_count?: number | null
    post_url?: string | null
  }>
}

interface RawClipsFeed {
  clips?: Array<{
    clip_id: string
    video_id?: string
    video_title?: string
    channel_name?: string | null
    clip_start_seconds?: number | null
    embed_url?: string | null
    video_url?: string | null
    transcript_segment?: string | null
    transcript_translated?: string | null
    matched_entity?: string | null
    video_published_at?: string | null
    collected_at?: string | null
  }>
}

interface RawDocumentsFeed {
  documents?: Array<{
    id?: string
    doc_id?: string
    title?: string
    source_name?: string | null
    source_geography?: string | null
    document_type?: string | null
    urgency?: string | null
    summary?: string | null
    intel_json?: { what_it_does?: string } | null
    published_at?: string | null
    collected_at?: string | null
    url?: string | null
  }>
}

/* ── Helpers ───────────────────────────────────────────────────────────── */

export function timeAgo(iso: string | null): string {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  if (!Number.isFinite(then)) return ''
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return new Date(iso).toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'short',
  })
}

/* ── Per-pillar normalizers ─────────────────────────────────────────────── */

export function normalizeArticles(raw: unknown): MonitorItem[] {
  const data = raw as RawArticleFeed
  return (data.articles ?? [])
    .map((a): ArticleMonitorItem | null => {
      const id = a.article_id ?? a.id
      if (!id) return null
      return {
        id,
        pillar: 'articles',
        // Use collected_at as primary timestamp — that's the "we saw it"
        // moment, which is what the Coverage page surfaces. published_at
        // can be hours older for syndicated / republished content (e.g.
        // an article published at 04:07 UTC and collected at 06:08 UTC
        // would show "2H AGO" by published_at but "1M AGO" by collected_at).
        // Coverage uses collected_at; Monitor must match.
        timestamp: a.collected_at ?? a.published_at ?? null,
        title: a.title ?? '',
        source_name: a.source_name ?? null,
        source_domain: a.source_domain ?? null,
        thumbnail_url: a.thumbnail_url ?? null,
        relevance_tier: a.relevance_tier ?? null,
        topic_category: a.topic_category ?? null,
        geo_primary: a.geo_primary ?? null,
        external_url: a.url ?? null,
      }
    })
    .filter((x): x is ArticleMonitorItem => x !== null)
}

export function normalizeNewspapers(raw: unknown): MonitorItem[] {
  const data = raw as RawClippingFeed
  return (data.clippings ?? []).map((c): NewspaperMonitorItem => ({
    id: c.clipping_id,
    pillar: 'newspaper',
    // collected_at primary so newly-scanned clippings sort fresh; the
    // edition_date is preserved separately as a metadata field.
    timestamp: c.collected_at ?? c.edition_date ?? null,
    headline: c.headline ?? c.headline_translated ?? '',
    headline_translated: c.headline_translated ?? null,
    newspaper_name: c.newspaper_name ?? null,
    newspaper_language: c.newspaper_language ?? null,
    edition_date: c.edition_date ?? null,
    page_number: c.page_number ?? null,
    topic_category: c.topic_category ?? null,
    clipping_image_url: c.clipping_image_url ?? c.image_url ?? null,
  }))
}

export function normalizeSocial(raw: unknown): MonitorItem[] {
  const data = raw as RawSignalsFeed
  return (data.posts ?? [])
    .filter((p) => p.platform !== 'twitter')
    .map((p): SocialMonitorItem => ({
      id: p.post_id,
      pillar: 'social',
      timestamp: p.posted_at ?? p.collected_at ?? null,
      platform: p.platform ?? 'unknown',
      author: p.author_username ?? null,
      monitor_name: p.monitor_name ?? null,
      post_text: p.post_text ?? '',
      post_text_translated: p.post_text_translated ?? null,
      post_language: p.post_language ?? null,
      sentiment_score: p.sentiment_score ?? null,
      upvotes: p.upvotes ?? null,
      comment_count: p.comment_count ?? null,
      post_url: p.post_url ?? null,
    }))
}

export function normalizeClips(raw: unknown): MonitorItem[] {
  const data = raw as RawClipsFeed
  return (data.clips ?? []).map((c): ClipMonitorItem => ({
    id: c.clip_id,
    pillar: 'clips',
    // collected_at first (when WE indexed it) — matches Clip Room display.
    timestamp: c.collected_at ?? c.video_published_at ?? null,
    video_id: c.video_id ?? c.clip_id,
    video_title: c.video_title ?? '',
    channel_name: c.channel_name ?? null,
    clip_start_seconds: c.clip_start_seconds ?? null,
    embed_url: c.embed_url ?? null,
    video_url: c.video_url ?? null,
    transcript_segment: c.transcript_segment ?? null,
    transcript_translated: c.transcript_translated ?? null,
    matched_entity: c.matched_entity ?? null,
    thumbnail_url: c.video_id
      ? `https://i.ytimg.com/vi/${c.video_id}/hqdefault.jpg`
      : null,
  }))
}

export function normalizeDocuments(raw: unknown): MonitorItem[] {
  const data = raw as RawDocumentsFeed
  return (data.documents ?? [])
    .map((d): DocumentMonitorItem | null => {
      const id = d.doc_id ?? d.id
      if (!id) return null
      const intel = d.intel_json ?? null
      const intelSnippet =
        (intel && typeof intel.what_it_does === 'string'
          ? intel.what_it_does
          : null) ??
        d.summary ??
        null
      return {
        id,
        pillar: 'documents',
        // collected_at primary so freshly-ingested docs lead.
        timestamp: d.collected_at ?? d.published_at ?? null,
        title: d.title ?? '',
        source_name: d.source_name ?? null,
        source_geography: d.source_geography ?? null,
        document_type: d.document_type ?? null,
        urgency: d.urgency ?? null,
        intel_snippet: intelSnippet,
        url: d.url ?? null,
      }
    })
    .filter((x): x is DocumentMonitorItem => x !== null)
}
