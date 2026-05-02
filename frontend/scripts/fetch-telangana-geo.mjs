#!/usr/bin/env node
/**
 * Build helper — fetch the geoBoundaries (gbOpen) ADM2 GeoJSON for India,
 * filter to the 33 current Telangana districts, simplify (Douglas–Peucker),
 * project (equirectangular) into the editorial map's SVG viewBox, and emit
 * a TypeScript module.
 *
 * Why geoBoundaries (2021) and not GADM:
 *   GADM 4.1 still uses the 10 historical (state-creation-era) districts.
 *   geoBoundaries 2021 has the post-2019 33-district reorganisation that
 *   matches what people expect to see when they look at a map of Telangana
 *   today.
 *
 * Why bbox + exclude-list:
 *   The geoBoundaries GeoJSON has no state-level metadata on each feature,
 *   so we filter spatially. A tight Telangana bbox catches 36 features —
 *   33 actual districts plus three neighbours from Chhattisgarh that
 *   happen to fall inside the bounding box (Bijapur, Dakshin Bastar
 *   Dantewada, Narayanpur). We drop those by name. Source also has typos
 *   ("Hydrabad" for Hyderabad) and pre-rename labels ("Warangal (U)" for
 *   Hanumakonda) — DISPLAY_NAMES below corrects those for the UI without
 *   touching the underlying geometry.
 *
 * Usage:  node frontend/scripts/fetch-telangana-geo.mjs
 *
 * Re-run only when the underlying dataset is updated. The output file
 * (`frontend/src/app/brief/cm/editorial/telangana-geo.ts`) is committed
 * so the editorial brief renders without any runtime fetch.
 */
import https from 'node:https'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const SOURCE_URL =
  'https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/IND/ADM2/geoBoundaries-IND-ADM2_simplified.geojson'

const OUT_DIR = path.resolve(
  __dirname,
  '..',
  'src',
  'app',
  'brief',
  'cm',
  'editorial',
)
const OUT = path.join(OUT_DIR, 'telangana-geo.ts')

/** Telangana state bounding box (with a small margin). */
const BBOX = { minLon: 77.2, maxLon: 81.85, minLat: 15.8, maxLat: 19.96 }

/** Three Chhattisgarh districts whose bbox overlaps Telangana — drop by name. */
const EXCLUDE_NAMES = new Set([
  'bijapur',
  'dakshin bastar dantewada',
  'narayanpur',
])

/**
 * Source-name → { id, name } overrides. Anything not listed here uses
 * the default idify(shapeName) and shapeName.toUpperCase().
 *
 * Why the overrides exist:
 *   - geoBoundaries source has typos and pre-rename labels.
 *   - We standardise IDs so volatility data in data.ts stays clean.
 */
const NAME_FIXES = {
  Hydrabad: { id: 'hyderabad', name: 'HYDERABAD' },
  Mahabubnagar: { id: 'mahbubnagar', name: 'MAHBUBNAGAR' },
  'Komaram Bheem': { id: 'komaram-bheem', name: 'KUMRAM BHEEM' },
  'Yadadri Bhongiri': { id: 'yadadri', name: 'YADADRI' },
  'Rajanna Sircilla': { id: 'rajanna-sircilla', name: 'RAJANNA SIRCILLA' },
  'Warangal (U)': { id: 'hanumakonda', name: 'HANUMAKONDA' },
  'Warangal (R)': { id: 'warangal', name: 'WARANGAL' },
  Bhadradri: { id: 'bhadradri', name: 'BHADRADRI' },
  Jogulamba: { id: 'jogulamba', name: 'JOGULAMBA' },
  Jayashankar: { id: 'jayashankar', name: 'JAYASHANKAR' },
}

/* --- helpers --- */

function fetchBuf(url, depth = 0) {
  return new Promise((resolve, reject) => {
    if (depth > 5) return reject(new Error('too many redirects'))
    https
      .get(url, { headers: { 'User-Agent': 'rig-surveillance-build' } }, (res) => {
        if ([301, 302, 307, 308].includes(res.statusCode)) {
          return fetchBuf(res.headers.location, depth + 1).then(resolve, reject)
        }
        const chunks = []
        res.on('data', (c) => chunks.push(c))
        res.on('end', () => resolve(Buffer.concat(chunks)))
      })
      .on('error', reject)
  })
}

function bboxFromGeom(g) {
  let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity
  function v(c) {
    if (typeof c[0] === 'number') {
      if (c[0] < xMin) xMin = c[0]
      if (c[0] > xMax) xMax = c[0]
      if (c[1] < yMin) yMin = c[1]
      if (c[1] > yMax) yMax = c[1]
    } else for (const x of c) v(x)
  }
  v(g.coordinates)
  return { xMin, xMax, yMin, yMax }
}

function perpDist(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1]
  if (dx === 0 && dy === 0) return Math.hypot(p[0] - a[0], p[1] - a[1])
  const t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
  const x = a[0] + t * dx, y = a[1] + t * dy
  return Math.hypot(p[0] - x, p[1] - y)
}

function dp(points, tol) {
  if (points.length < 3) return points
  let maxDist = 0, maxIdx = 0
  const a = points[0], b = points[points.length - 1]
  for (let i = 1; i < points.length - 1; i++) {
    const d = perpDist(points[i], a, b)
    if (d > maxDist) { maxDist = d; maxIdx = i }
  }
  if (maxDist > tol) {
    const left = dp(points.slice(0, maxIdx + 1), tol)
    const right = dp(points.slice(maxIdx), tol)
    return left.slice(0, -1).concat(right)
  }
  return [a, b]
}

const SVG_W = 700
const SVG_H = 640
const PAD = 8
/** Tolerance — sub-districts are small, want smooth curves at this zoom. */
const TOL = 0.0012

const idify = (s) =>
  s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')

function resolveDisplay(shapeName) {
  if (NAME_FIXES[shapeName]) return NAME_FIXES[shapeName]
  return { id: idify(shapeName), name: shapeName.toUpperCase() }
}

;(async () => {
  console.log('Downloading geoBoundaries IND ADM2 (2021)...')
  const buf = await fetchBuf(SOURCE_URL)
  console.log('Downloaded', (buf.length / 1024 / 1024).toFixed(2), 'MB')
  const j = JSON.parse(buf.toString())
  console.log('Total ADM2 features:', j.features.length)

  // Keep features whose bbox is entirely inside Telangana, dropping known neighbours.
  const tg = j.features.filter((f) => {
    const b = bboxFromGeom(f.geometry)
    if (
      !(
        b.xMin >= BBOX.minLon &&
        b.xMax <= BBOX.maxLon &&
        b.yMin >= BBOX.minLat &&
        b.yMax <= BBOX.maxLat
      )
    ) {
      return false
    }
    const n = String(f.properties.shapeName || '').toLowerCase()
    return !EXCLUDE_NAMES.has(n)
  })

  console.log('Telangana features:', tg.length)
  if (tg.length !== 33) {
    console.warn(
      'WARNING: expected 33 districts, got',
      tg.length,
      '— bbox or exclude-list may need tuning.',
    )
  }

  // Bounds across all selected features (NOT the editorial bbox — actual data).
  let minLon = Infinity, maxLon = -Infinity, minLat = Infinity, maxLat = -Infinity
  for (const f of tg) {
    const b = bboxFromGeom(f.geometry)
    if (b.xMin < minLon) minLon = b.xMin
    if (b.xMax > maxLon) maxLon = b.xMax
    if (b.yMin < minLat) minLat = b.yMin
    if (b.yMax > maxLat) maxLat = b.yMax
  }

  const lonR = maxLon - minLon
  const latR = maxLat - minLat
  const s = Math.min((SVG_W - PAD * 2) / lonR, (SVG_H - PAD * 2) / latR)
  const ox = PAD + ((SVG_W - PAD * 2) - s * lonR) / 2
  const oy = PAD + ((SVG_H - PAD * 2) - s * latR) / 2
  const project = ([lon, lat]) => [
    ox + (lon - minLon) * s,
    oy + (maxLat - lat) * s,
  ]

  function ringToPath(ring) {
    const simp = dp(ring, TOL)
    const pts = simp.map(project)
    return (
      'M ' +
      pts.map((p) => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' L ') +
      ' Z'
    )
  }
  function geomToPath(g) {
    const parts = []
    if (g.type === 'Polygon') for (const r of g.coordinates) parts.push(ringToPath(r))
    else if (g.type === 'MultiPolygon')
      for (const p of g.coordinates) for (const r of p) parts.push(ringToPath(r))
    return parts.join(' ')
  }
  function centroidSvg(g) {
    let xs = 0, ys = 0, n = 0
    function w(c) {
      if (typeof c[0] === 'number') {
        const [x, y] = project(c); xs += x; ys += y; n++
      } else for (const v of c) w(v)
    }
    w(g.coordinates)
    return [xs / n, ys / n]
  }

  const districts = tg
    .map((f) => {
      const { id, name } = resolveDisplay(f.properties.shapeName)
      const [cx, cy] = centroidSvg(f.geometry)
      return {
        id,
        name,
        d: geomToPath(f.geometry),
        cx: +cx.toFixed(1),
        cy: +cy.toFixed(1),
      }
    })
    .sort((a, b) => a.name.localeCompare(b.name))

  // Sanity-check: IDs must be unique.
  const ids = new Set()
  for (const d of districts) {
    if (ids.has(d.id)) console.warn('DUP ID:', d.id)
    ids.add(d.id)
  }

  const ts = `/* Auto-generated from geoBoundaries gbOpen IND ADM2 (2021).
 * Filtered to the 33 current Telangana districts, simplified at ${TOL}°
 * tolerance, projected equirectangular into ${SVG_W} × ${SVG_H} SVG viewBox.
 * Bounds: lon ${minLon.toFixed(3)}–${maxLon.toFixed(3)}, lat ${minLat.toFixed(3)}–${maxLat.toFixed(3)}.
 *
 * To regenerate: node frontend/scripts/fetch-telangana-geo.mjs
 */

export const TELANGANA_VIEWBOX = { width: ${SVG_W}, height: ${SVG_H} } as const

export interface DistrictGeo {
  id: string
  name: string
  /** SVG path data for fill / stroke. */
  d: string
  /** Centroid in SVG coords for label placement. */
  cx: number
  cy: number
}

export const TELANGANA_DISTRICTS: ReadonlyArray<DistrictGeo> = ${JSON.stringify(districts, null, 2)}
`

  fs.mkdirSync(OUT_DIR, { recursive: true })
  fs.writeFileSync(OUT, ts)
  const stat = fs.statSync(OUT)
  console.log('Wrote', OUT, '(' + (stat.size / 1024).toFixed(1) + ' KB)')
  console.log('District IDs:', districts.map((d) => d.id).join(', '))
})().catch((e) => {
  console.error('FAIL', e.message)
  process.exit(1)
})
