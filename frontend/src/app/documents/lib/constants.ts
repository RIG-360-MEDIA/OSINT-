import type { GeoFilter, WindowDays } from './types'

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export const GEO_FILTERS: Array<{ value: GeoFilter; label: string }> = [
  { value: 'all',           label: 'All' },
  { value: 'LOCAL',         label: 'Local' },
  { value: 'CENTRAL',       label: 'Central' },
  { value: 'NEIGHBOURING',  label: 'Neighbouring' },
  { value: 'INTERNATIONAL', label: 'International' },
]

// D-6: covers the document_type values emitted by all 53 adapters.
// Update this list whenever a new adapter introduces a new type — or
// switch to a `/api/documents/facets` endpoint when the type universe
// stabilises.
export const DOC_TYPES: Array<{ value: string; label: string }> = [
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

export const WINDOWS: Array<{ value: WindowDays; label: string }> = [
  { value: 7,   label: '7 days' },
  { value: 30,  label: '30 days' },
  { value: 90,  label: '90 days' },
  { value: 365, label: '1 year' },
]

export const URGENCY_TONE: Record<string, 'alert' | 'gold' | 'default'> = {
  HIGH: 'alert',
  MEDIUM: 'gold',
  LOW: 'default',
}

export const GEO_KICKER: Record<string, string> = {
  LOCAL: 'Local desk',
  CENTRAL: 'Central desk',
  NEIGHBOURING: 'Neighbouring',
  INTERNATIONAL: 'Foreign desk',
}

export function formatShortDate(iso: string): string {
  try {
    const d = new Date(iso)
    // D-11: pin locale so SSR (Node default) and CSR (browser default) agree.
    // The previous `undefined` locale produced a hydration mismatch on every
    // non-en-US client. The display format is intentionally numeric+short
    // month, locale-stable across regions.
    return d
      .toLocaleDateString('en-US', { day: 'numeric', month: 'short' })
      .toUpperCase()
  } catch {
    return ''
  }
}
