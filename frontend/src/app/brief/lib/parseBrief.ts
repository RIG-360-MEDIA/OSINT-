/**
 * Brief markdown parser — extracted from page.tsx so it can be unit-tested.
 *
 * The current page.tsx inlines this logic (around line 31). This module is a
 * one-to-one extraction so tests in `__tests__/parseBrief.test.ts` can run
 * against it. Refactor target: page.tsx should import from here (tracked as
 * D-BRIEF-9 in docs/qa/brief-defects.md).
 */

export const SECTION_NAMES = [
  'SITUATION STATUS',
  'KEY DEVELOPMENTS',
  'ENTITIES TODAY',
  'SIGNALS TO WATCH',
  'FINANCIAL PULSE',
  'SOURCE COVERAGE',
] as const

export type SectionName = typeof SECTION_NAMES[number]

export interface BriefMeta {
  briefDate: string
  articlesUsed: number
  generatedAt: string
}

export interface SourceCounts {
  articles: number
  govt_docs: number
  social_posts: number
  newspaper_clippings: number
  video_clips: number
}

export interface GovtDocItem {
  doc_id?: string
  title?: string
  source_name?: string
  source_geography?: string
  document_type?: string
  published_at?: string | null
  collected_at?: string | null
  page_number?: number | null
  section_heading?: string | null
  snippet?: string | null
  intel_json?: Record<string, unknown> | null
  relevance_tier?: number | null
  score_final?: number | null
}

export interface SocialPostItem {
  post_id?: string
  platform?: string
  author?: string
  text_snippet?: string
  url?: string | null
  sentiment?: number | null
  topic?: string | null
  posted_at?: string | null
  matched_entities?: unknown
  distance?: number
}

export interface NewspaperClipItem {
  clip_id?: string
  newspaper?: string
  language?: string
  edition_date?: string | null
  page_number?: number | null
  headline?: string
  text_snippet?: string
  topic_category?: string | null
  geo_primary?: string | null
  sentiment?: string | null
  distance?: number
}

export interface VideoClipItem {
  video_id?: string
  title?: string
  channel?: string
  start_seconds?: number
  embed_url?: string | null
  text_snippet?: string
  matched_entity?: string | null
  published_at?: string | null
  distance?: number
}

export interface EvidenceBundle {
  govt_docs: GovtDocItem[]
  social_posts: SocialPostItem[]
  newspaper_clippings: NewspaperClipItem[]
  video_clips: VideoClipItem[]
}

export interface ParsedBrief {
  date: string
  generatedFor: string
  sections: Record<string, string>
  meta: BriefMeta
  /** Per-pillar counts shown in the sticky pulse band. Optional because
   * older briefs (pre multi-pillar upgrade) didn't persist these. */
  sourceCounts?: SourceCounts
  /** Structured per-pillar evidence — drives the new evidence-led steps
   * (Primary Sources, Print Press, Public Pulse, On The Wires). */
  evidence?: EvidenceBundle
}

/**
 * Strip the LLM's inline citation glyphs from rendered prose.
 *
 * The brief generator (backend/nlp/brief_generator.py) inserts circled
 * unicode digits (①–⑳, dingbat ❶–❿, double-circle ⓵, etc.) wrapped in
 * parentheses to mark which source any sentence came from — e.g.
 * `bus services across the state, leaving commuters stranded (⑧).`
 *
 * Senior readers find these characters jarring: they read like footnote
 * markers but lead nowhere because the live sources panel renders them
 * separately. This cleanup removes the glyphs, collapses the now-empty
 * parens (`( )` → ``), and tidies any double spaces / spaced punctuation
 * left behind.
 */
function stripCitationGlyphs(text: string): string {
  if (!text) return text
  // Unicode ranges for circled digits + dingbat circled digits.
  const CIRCLED = /[①-⓿❶-➓]/g
  return text
    .replace(CIRCLED, '')
    // (   ) ← any parens left holding only whitespace
    .replace(/\(\s*\)/g, '')
    // [   ] ← square-bracket variant
    .replace(/\[\s*\]/g, '')
    // double spaces left where citations sat
    .replace(/[ \t]{2,}/g, ' ')
    // hanging space before a comma / period / semicolon
    .replace(/\s+([,.;:])/g, '$1')
    .trim()
}

export function parseBrief(content: string, meta: BriefMeta): ParsedBrief {
  const cleaned = stripCitationGlyphs(content)
  const dateMatch = cleaned.match(/^## (.+)$/m)
  const metaMatch = cleaned.match(/\*Generated for: (.+?)\*/)
  const sections: Record<string, string> = {}
  for (const part of cleaned.split(/\n---\n/)) {
    const m = part.trim().match(/^## ([A-Z ]+)\n\n([\s\S]*)/)
    if (m) {
      const name = m[1].trim()
      if ((SECTION_NAMES as readonly string[]).includes(name)) {
        sections[name] = m[2].trim()
      }
    }
  }
  return {
    date: dateMatch?.[1] ?? '',
    generatedFor: metaMatch?.[1] ?? '',
    sections,
    meta,
  }
}
