/**
 * THE NEWSROOM API contracts.
 *
 * Mirror of backend/routers/newsroom_router.py response shapes. Update
 * this file together with the router to keep the contract on one
 * canonical surface — the brief verifies "Response shape matches a
 * TypeScript interface defined in frontend/src/types/newsroom.ts."
 */

export type NewsroomLanguage = 'te' | 'hi' | 'en' | 'kn' | 'ta' | string

export interface NewsroomChannel {
  id: string
  name: string
  yt_handle: string
  language: NewsroomLanguage
  beat: string
  is_live_24x7: boolean
  active: boolean
  created_at: string
}

export interface NewsroomSegmentSummary {
  segment_id: string
  text_native: string | null
  text_en: string | null
  confidence: number | null
  is_quote: boolean
  is_editorial: boolean
  framing: 'adversarial' | 'aligned' | 'neutral' | null
  sentiment?: number | null
  start_sec: number
  end_sec: number
  created_at: string
  is_live?: boolean
  speaker_label?: string | null
  speaker_entity_id?: string | null
}

export interface NewsroomDigestStory {
  headline: string
  blurb?: string
}

export interface NewsroomWallTile {
  channel_id: string
  channel_name: string
  language: NewsroomLanguage
  beat: string
  is_live_24x7?: boolean
  yt_handle?: string | null
  current_live_video_id?: string | null
  current_live_title?: string | null
  last_live_at?: string | null
  last_live_check_at?: string | null
  segments: NewsroomSegmentSummary[]
  digest_summary?: string
  digest_phrases?: string[]
  digest_stories?: NewsroomDigestStory[]
  digest_generated_at?: string | null
}

export interface NewsroomWallResponse {
  tiles: NewsroomWallTile[]
}

export interface NewsroomStreamItem extends NewsroomSegmentSummary {
  channel_id: string
  channel_name: string
  language: NewsroomLanguage
}

export interface NewsroomStreamResponse {
  items: NewsroomStreamItem[]
  next_cursor: string | null
}

export interface NewsroomEchoItem extends NewsroomSegmentSummary {
  channel_id: string
  channel_name: string
  language: NewsroomLanguage
  was_phonetic: boolean
}

export interface NewsroomEchoResponse {
  entity_id: string
  hours: number
  total_mentions: number
  cross_channel_count: number
  items: NewsroomEchoItem[]
}

export interface NewsroomDossierResponse {
  entity_id: string
  days: number
  this_period: number
  prev_period: number
  delta_pct: number | null
  sentiment_avg: number | null
  top_quotes: Array<{
    segment_id: string
    text_native: string | null
    text_en: string | null
    framing: string | null
    sentiment: number | null
    created_at: string
    channel_name: string
  }>
  top_channels: Array<{ channel_name: string; n: number }>
}

export interface NewsroomBreakingCluster {
  id: string
  headline: string
  headline_en: string | null
  first_seen_at: string
  last_seen_at: string
  channel_count: number
  segment_count: number
  severity: number
  created_at: string
}

export interface NewsroomBreakingResponse {
  clusters: NewsroomBreakingCluster[]
}

export interface NewsroomBriefStory {
  headline: string
  summary: string
  source_segment_ids: string[]
}

export interface NewsroomBriefResponse {
  id: string
  for_date: string
  generated_at: string
  stories: NewsroomBriefStory[]
  story_count: number
  source_channel_count: number
  source_segment_count: number
}

export interface NewsroomSegmentDetail extends NewsroomSegmentSummary {
  broadcast_id: string
  l1_text: string | null
  l2_text: string | null
  l3_text: string | null
  yt_video_id: string
  title: string | null
  channel_name: string
  language: NewsroomLanguage
}

export interface NewsroomSseEvent {
  segment_id: string
  broadcast_id: string
  is_live: boolean
  created_at: string
}

export type NewsroomMode = 'wall' | 'stream' | 'echo' | 'dossier' | 'brief'

export const NEWSROOM_MODES: { id: NewsroomMode; label: string; key: string }[] = [
  { id: 'wall',    label: 'Wall',    key: '1' },
  { id: 'stream',  label: 'Stream',  key: '2' },
  { id: 'echo',    label: 'Echo',    key: '3' },
  { id: 'dossier', label: 'Dossier', key: '4' },
  { id: 'brief',   label: 'Brief',   key: '5' },
]
