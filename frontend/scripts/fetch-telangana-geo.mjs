#!/usr/bin/env node
/**
 * Build helper — download GADM 4.1 India L2 districts, filter to Telangana,
 * simplify (Douglas–Peucker), project (equirectangular) into the editorial
 * map's SVG viewBox, and emit a TypeScript module.
 *
 * Usage:  node frontend/scripts/fetch-telangana-geo.mjs
 *
 * Re-run only when the underlying GADM dataset is updated. The output file
 * (`frontend/src/app/brief/cm/editorial/telangana-geo.ts`) is committed to
 * the repo so the editorial brief renders without any runtime fetch.
 */
import https from 'node:https'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const URL = 'https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_IND_2.json'
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

function fetchBuf(url, depth = 0) {
  return new Promise((resolve, reject) => {
    if (depth > 5) return reject(new Error('too many redirects'))
    https
      .get(url, (res) => {
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

function perpDist(p, a, b) {
  const dx = b[0] - a[0]
  const dy = b[1] - a[1]
  if (dx === 0 && dy === 0) return Math.hypot(p[0] - a[0], p[1] - a[1])
  const t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
  const x = a[0] + t * dx
  const y = a[1] + t * dy
  return Math.hypot(p[0] - x, p[1] - y)
}

function dp(points, tol) {
  if (points.length < 3) return points
  let maxDist = 0
  let maxIdx = 0
  const a = points[0]
  const b = points[points.length - 1]
  for (let i = 1; i < points.length - 1; i++) {
    const d = perpDist(points[i], a, b)
    if (d > maxDist) {
      maxDist = d
      maxIdx = i
    }
  }
  if (maxDist > tol) {
    const left = dp(points.slice(0, maxIdx + 1), tol)
    const right = dp(points.slice(maxIdx), tol)
    return left.slice(0, -1).concat(right)
  }
  return [a, b]
}

const SVG_W = 700
const SVG_H = 800
const PAD = 24
const TOL = 0.0035

function idify(s) {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')
}

;(async () => {
  console.log('Downloading GADM 4.1 IND L2...')
  const buf = await fetchBuf(URL)
  console.log('Downloaded', (buf.length / 1024 / 1024).toFixed(1), 'MB')
  const j = JSON.parse(buf.toString())

  const tg = j.features.filter((f) =>
    /telang/i.test(String(f.properties.NAME_1 || '')),
  )
  console.log('Telangana features:', tg.length)
  if (tg.length === 0) throw new Error('no Telangana features found')

  let minLon = Infinity
  let maxLon = -Infinity
  let minLat = Infinity
  let maxLat = -Infinity
  function visit(c) {
    if (typeof c[0] === 'number') {
      if (c[0] < minLon) minLon = c[0]
      if (c[0] > maxLon) maxLon = c[0]
      if (c[1] < minLat) minLat = c[1]
      if (c[1] > maxLat) maxLat = c[1]
    } else for (const v of c) visit(v)
  }
  for (const f of tg) visit(f.geometry.coordinates)

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
    if (g.type === 'Polygon') {
      for (const r of g.coordinates) parts.push(ringToPath(r))
    } else if (g.type === 'MultiPolygon') {
      for (const p of g.coordinates) for (const r of p) parts.push(ringToPath(r))
    }
    return parts.join(' ')
  }
  function centroidSvg(g) {
    let xs = 0
    let ys = 0
    let n = 0
    function w(c) {
      if (typeof c[0] === 'number') {
        const [x, y] = project(c)
        xs += x
        ys += y
        n++
      } else for (const v of c) w(v)
    }
    w(g.coordinates)
    return [xs / n, ys / n]
  }

  const districts = tg
    .map((f) => {
      const name = f.properties.NAME_2
      const [cx, cy] = centroidSvg(f.geometry)
      return {
        id: idify(name),
        name: name.toUpperCase(),
        d: geomToPath(f.geometry),
        cx: +cx.toFixed(1),
        cy: +cy.toFixed(1),
      }
    })
    .sort((a, b) => a.name.localeCompare(b.name))

  const ts = `/* Auto-generated from GADM 4.1 India L2 districts (post-2014).
 * Filtered to Telangana, simplified at ${TOL}° tolerance,
 * projected equirectangular into ${SVG_W} × ${SVG_H} SVG viewBox.
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
})().catch((e) => {
  console.error('FAIL', e.message)
  process.exit(1)
})
