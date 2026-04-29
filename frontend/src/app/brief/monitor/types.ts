/**
 * Monitor view types — discriminated union per pillar so each card can
 * render with the same visual identity its dedicated room uses (Coverage,
 * Cuttings, Signal Room, Clip Room, Document Room).
 *
 * Why a discriminated union rather than a flat shape: the article card
 * needs a thumbnail, the newspaper card needs the original-language
 * headline, the clip card needs a video embed URL, the social card needs
 * platform / sentiment, and the doc card needs urgency + intel snippet.
 * Forcing them through one flat shape made every shelf look the same.
 * With this union each card asks for exactly what it needs.
 */

export type Pillar = 'articles' | 'newspaper' | 'social' | 'clips' | 'documents'

interface BaseItem {
  id: string
  pillar: Pillar
  /** ISO timestamp used for "X min ago" rendering and for sorting. */
  timestamp: string | null
}

/* ── Articles (mirrors Coverage Room's `Clipping`) ─────────────────────── */

export interface ArticleMonitorItem extends BaseItem {
  pillar: 'articles'
  title: string
  source_name: string | null
  source_domain: string | null
  thumbnail_url: string | null
  relevance_tier: number | null
  topic_category: string | null
  geo_primary: string | null
  /** External URL to the original article. */
  external_url: string | null
}

/* ── Newspaper clippings (mirrors Cuttings room) ───────────────────────── */

export interface NewspaperMonitorItem extends BaseItem {
  pillar: 'newspaper'
  headline: string
  headline_translated: string | null
  newspaper_name: string | null
  newspaper_language: string | null
  edition_date: string | null
  page_number: number | null
  topic_category: string | null
  /** Optional preview image URL for the clipping. */
  clipping_image_url: string | null
}

/* ── Social posts (mirrors Signal Room's `PostRow`) ────────────────────── */

export interface SocialMonitorItem extends BaseItem {
  pillar: 'social'
  platform: string
  author: string | null
  monitor_name: string | null
  post_text: string
  post_text_translated: string | null
  post_language: string | null
  sentiment_score: number | null
  upvotes: number | null
  comment_count: number | null
  post_url: string | null
}

/* ── Video clips (mirrors Clip Room's `StoryCard`) ─────────────────────── */

export interface ClipMonitorItem extends BaseItem {
  pillar: 'clips'
  video_id: string
  video_title: string
  channel_name: string | null
  clip_start_seconds: number | null
  embed_url: string | null
  video_url: string | null
  transcript_segment: string | null
  transcript_translated: string | null
  matched_entity: string | null
  thumbnail_url: string | null
}

/* ── Govt documents (mirrors Document Room's `DocumentRow`) ────────────── */

export interface DocumentMonitorItem extends BaseItem {
  pillar: 'documents'
  title: string
  source_name: string | null
  source_geography: string | null
  document_type: string | null
  urgency: string | null
  intel_snippet: string | null
  url: string | null
}

export type MonitorItem =
  | ArticleMonitorItem
  | NewspaperMonitorItem
  | SocialMonitorItem
  | ClipMonitorItem
  | DocumentMonitorItem

/* ── Highlights (cross-pillar hero band) ───────────────────────────────── */

export interface HighlightItem {
  pillar: Pillar
  id: string
  headline: string
  source: string | null
  timestamp: string | null
  score: number | null
  extra: {
    tier?: number
    sentiment?: number | null
  }
}

export const PILLAR_LABEL: Record<Pillar, string> = {
  articles: 'Articles',
  newspaper: 'Newspapers',
  social: 'Social',
  clips: 'Clips',
  documents: 'Govt Docs',
}

export const PILLAR_KICKER: Record<Pillar, string> = {
  articles: 'Articles · tier 1+2 · live',
  newspaper: 'Newspapers · today · live',
  social: 'Social · Reddit + Telegram · live',
  clips: 'Clips · YouTube · live',
  documents: 'Govt Docs · by relevance · live',
}
