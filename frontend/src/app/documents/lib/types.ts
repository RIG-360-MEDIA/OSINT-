export interface DocumentItem {
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

export interface GeoCount {
  geography: string
  count: number
}

export interface FeedResponse {
  documents: DocumentItem[]
  has_more: boolean
  next_cursor: string | null
  total: number
  geography_counts: GeoCount[]
}

export type GeoFilter = 'all' | 'LOCAL' | 'CENTRAL' | 'NEIGHBOURING' | 'INTERNATIONAL'

export type WindowDays = 7 | 30 | 90 | 365
