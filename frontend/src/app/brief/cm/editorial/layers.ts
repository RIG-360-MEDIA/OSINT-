/**
 * Atlas layer registry.
 *
 * Each layer is one way of looking at the same Telangana districts —
 * a different signal mapped to a different colour palette. The map
 * reads the active layer's `valueFor(districtId)` and renders the
 * polygon fill from `colorFor(value)`.
 *
 * Hardcoded for v1. Wiring to live data is later: replace the value
 * tables (or `valueFor` lookups) with a server fetch.
 */

import { DISTRICTS } from './data'
import { TELANGANA_DISTRICTS } from './telangana-geo'

export interface LayerOverlay {
  /** Where the marker sits — district id (we'll resolve to centroid). */
  districtId: string
  /** Marker label (rendered next to the dot). */
  label: string
  /** Marker tone — wax-red / ink-blue / sepia. */
  tone: 'red' | 'blue' | 'sepia'
  /** Display value when tooltip / focus. */
  value: string
}

export interface LayerDef {
  id: string
  label: string
  category: 'signal' | 'safety' | 'economy' | 'infra' | 'composite'
  description: string
  /** Returns 0..1 normalised intensity for a given district. */
  valueFor: (districtId: string) => number
  /** Returns a hex/rgba fill given the intensity. */
  colorFor: (value: number) => string
  /** Plain-language scale labels for the legend, low → high. */
  scale: ReadonlyArray<string>
  /** Optional pinned markers on top of the choropleth. */
  overlays?: ReadonlyArray<LayerOverlay>
}

/* ------------------------------------------------------------------ */
/* Palettes                                                             */
/* ------------------------------------------------------------------ */

const SEPIA = ['#f5f0e6', '#ebd9b6', '#dabf8a', '#c9a373', '#a07a45', '#7a5224', '#5a3613']

const WAX_RED = [
  '#fbf0ee', // pale
  '#f3d7d2',
  '#e3a89e',
  '#d3786a',
  '#c14e3e',
  '#9c2b1f',
  '#5a160e',
]

const INK_BLUE = [
  '#eef2f5',
  '#cdd9e3',
  '#9bb1c5',
  '#6589a8',
  '#3f6589',
  '#1d3557',
  '#0f1f36',
]

/** Picks a swatch from a palette by 0..1 intensity. */
function ramp(palette: ReadonlyArray<string>, v: number): string {
  if (v <= 0) return palette[0]
  if (v >= 1) return palette[palette.length - 1]
  const idx = Math.min(palette.length - 1, Math.floor(v * palette.length))
  return palette[idx]
}

/* ------------------------------------------------------------------ */
/* Hardcoded value tables                                              */
/* ------------------------------------------------------------------ */

/** District volatility from data.ts (0..1). News hotspot uses this. */
const VOLATILITY: Record<string, number> = Object.fromEntries(
  DISTRICTS.map((d) => [d.id, d.volatility]),
)

/** Generate a deterministic perturbation for non-news layers — keeps demo
 * values plausible while ensuring each layer paints a different picture. */
function offset(districtId: string, seed: number): number {
  let h = seed
  for (let i = 0; i < districtId.length; i++) {
    h = (h * 31 + districtId.charCodeAt(i)) >>> 0
  }
  return ((h % 1000) / 1000 - 0.5) * 0.4
}

function clamp01(n: number): number {
  return Math.max(0, Math.min(1, n))
}

/* SENTIMENT — somewhat correlated with hotspot but more polarised on the
 * political districts. Higher = more negative sentiment. */
function sentimentFor(id: string): number {
  const base = VOLATILITY[id] ?? 0.3
  return clamp01(base * 0.85 + offset(id, 11) + 0.05)
}

/* ACLED EVENTS — sparse, only the high-volatility districts carry events. */
const ACLED_COUNTS: Record<string, number> = {
  hyderabad: 7,
  khammam: 4,
  karimnagar: 3,
  warangal: 2,
  rangareddy: 3,
  hanumakonda: 2,
  medchal: 1,
  nalgonda: 1,
  medak: 1,
  sangareddy: 1,
}

function acledFor(id: string): number {
  const c = ACLED_COUNTS[id] ?? 0
  return clamp01(c / 7)
}

/* MANDI VOLATILITY — agricultural districts higher. */
const MANDI_HIGH = new Set([
  'khammam', 'warangal', 'mahabubabad', 'nalgonda', 'karimnagar',
  'jagtial', 'peddapalli', 'siddipet', 'mahbubnagar', 'medak',
  'nizamabad', 'kamareddy', 'sangareddy', 'bhadradri',
])

function mandiFor(id: string): number {
  const base = MANDI_HIGH.has(id) ? 0.55 : 0.18
  return clamp01(base + offset(id, 23))
}

/* WELFARE COVERAGE — relatively uniform; rural districts slightly higher. */
function welfareFor(id: string): number {
  const base = id === 'hyderabad' ? 0.55 : 0.78
  return clamp01(base + offset(id, 41))
}

/* POWER STRESS — Khammam stressed, others largely OK. */
const POWER_STATE: Record<string, number> = {
  khammam: 0.85,
  mahabubabad: 0.65,
  bhadradri: 0.55,
  hyderabad: 0.42,
  rangareddy: 0.4,
  nalgonda: 0.5,
}

function powerFor(id: string): number {
  return POWER_STATE[id] ?? 0.18
}

/* STABILITY (composite) — invert volatility, blend with conflict / news. */
function stabilityFor(id: string): number {
  const vol = VOLATILITY[id] ?? 0.3
  const acled = ACLED_COUNTS[id] ?? 0
  const composite = 1 - (vol * 0.6 + (acled / 7) * 0.4)
  return clamp01(composite)
}

/* ------------------------------------------------------------------ */
/* Layer definitions                                                   */
/* ------------------------------------------------------------------ */

export const LAYERS: ReadonlyArray<LayerDef> = [
  {
    id: 'news-hotspot',
    label: 'News Hotspot',
    category: 'signal',
    description:
      'Tier-1 / tier-2 article volume × composite severity, last 24h',
    valueFor: (id) => VOLATILITY[id] ?? 0.3,
    colorFor: (v) => ramp(SEPIA, v),
    scale: ['Quiet', 'Moderate', 'High', 'Volatile'],
  },
  {
    id: 'sentiment',
    label: 'Sentiment',
    category: 'signal',
    description: 'Negative-leaning sentiment intensity per district',
    valueFor: (id) => sentimentFor(id),
    colorFor: (v) => ramp(WAX_RED, v),
    scale: ['Calm', 'Cautious', 'Tense', 'Hot'],
  },
  {
    id: 'acled',
    label: 'ACLED Events',
    category: 'safety',
    description: 'Protests, riots and strategic developments — last 7 days',
    valueFor: (id) => acledFor(id),
    colorFor: (v) => ramp(SEPIA, v * 0.7),
    scale: ['0', '1–2', '3–5', '6+'],
    overlays: Object.entries(ACLED_COUNTS).map(([districtId, count]) => ({
      districtId,
      label: `${count}`,
      tone: 'red' as const,
      value: `${count} events`,
    })),
  },
  {
    id: 'mandi',
    label: 'Mandi Volatility',
    category: 'economy',
    description: 'Commodity price deviation vs 30-day average',
    valueFor: (id) => mandiFor(id),
    colorFor: (v) => ramp(SEPIA, v),
    scale: ['Stable', 'Drifting', 'Volatile'],
  },
  {
    id: 'welfare',
    label: 'Welfare Coverage',
    category: 'composite',
    description:
      'Composite of Rythu Bandhu, Aasara and 2BHK delivery percentage',
    valueFor: (id) => welfareFor(id),
    colorFor: (v) => ramp(INK_BLUE, v),
    scale: ['<60%', '60–80%', '80–95%', '>95%'],
  },
  {
    id: 'power',
    label: 'Power Stress',
    category: 'infra',
    description: 'Demand vs supply — load-shedding risk',
    valueFor: (id) => powerFor(id),
    colorFor: (v) => ramp(WAX_RED, v),
    scale: ['Normal', 'Stressed', 'Shedding'],
    overlays: Object.entries(POWER_STATE)
      .filter(([, v]) => v >= 0.55)
      .map(([districtId, v]) => ({
        districtId,
        label: v >= 0.8 ? '⚡' : '!',
        tone: 'red' as const,
        value: `Stress index ${Math.round(v * 100)}`,
      })),
  },
  {
    id: 'stability',
    label: 'Stability Index',
    category: 'composite',
    description:
      'Composite — inverse of volatility blended with conflict and news anomaly',
    valueFor: (id) => stabilityFor(id),
    colorFor: (v) => ramp(INK_BLUE, v),
    scale: ['Stressed', 'Monitor', 'Calm', 'Stable'],
  },
]

export const DEFAULT_LAYER_ID = 'news-hotspot'

export function getLayer(id: string): LayerDef {
  return LAYERS.find((l) => l.id === id) ?? LAYERS[0]
}

export function findCentroid(districtId: string): { cx: number; cy: number } | null {
  const d = TELANGANA_DISTRICTS.find((x) => x.id === districtId)
  return d ? { cx: d.cx, cy: d.cy } : null
}
