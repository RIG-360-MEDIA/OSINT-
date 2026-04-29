/**
 * Unit tests for the brief markdown parser.
 *
 * The parser is brittle today (D-BRIEF-13): it requires uppercase-only section
 * headers, exactly two newlines after each header, and exact `\n---\n`
 * separators. These tests document both the working contract and the cases
 * that currently *should* work but don't. The latter are marked .fails().
 */
import { describe, expect, it } from 'vitest'

import {
  type BriefMeta,
  parseBrief,
  SECTION_NAMES,
} from '../lib/parseBrief'

const META: BriefMeta = {
  briefDate: '2026-04-26',
  articlesUsed: 30,
  generatedAt: '2026-04-26T07:00:00Z',
}

function buildBrief(sections: Partial<Record<string, string>>): string {
  const ordered = [
    'SITUATION STATUS',
    'KEY DEVELOPMENTS',
    'ENTITIES TODAY',
    'SIGNALS TO WATCH',
    'FINANCIAL PULSE',
    'SOURCE COVERAGE',
  ]
  const blocks = [
    '# DAILY INTELLIGENCE BRIEF\n## Sunday, 26 April 2026\n*Generated for: Senior analyst, Hyderabad*',
    ...ordered.map(name => `## ${name}\n\n${sections[name] ?? `${name} body`}`),
  ]
  return blocks.join('\n---\n')
}

// ── Happy path ──────────────────────────────────────────────────────────────

describe('parseBrief — golden path', () => {
  it('extracts the date headline', () => {
    const md = buildBrief({})
    const parsed = parseBrief(md, META)
    expect(parsed.date).toBe('Sunday, 26 April 2026')
  })

  it('extracts the generated-for line', () => {
    const md = buildBrief({})
    const parsed = parseBrief(md, META)
    expect(parsed.generatedFor).toBe('Senior analyst, Hyderabad')
  })

  it('returns all six section bodies keyed by canonical name', () => {
    const md = buildBrief({
      'SITUATION STATUS': 'Calm seas today.',
      'KEY DEVELOPMENTS': '① First.\n② Second.',
      'ENTITIES TODAY': 'CM\nMet leaders.',
      'SIGNALS TO WATCH': '⚑ Watch the rupee.',
      'FINANCIAL PULSE': 'Markets up 1%.',
      'SOURCE COVERAGE': 'Hindu — politics.',
    })
    const parsed = parseBrief(md, META)
    for (const name of SECTION_NAMES) {
      expect(parsed.sections[name]).toBeDefined()
      expect(parsed.sections[name].length).toBeGreaterThan(0)
    }
  })

  it('returns the meta object unchanged', () => {
    expect(parseBrief(buildBrief({}), META).meta).toEqual(META)
  })
})

// ── Edge: extra whitespace around section bodies ────────────────────────────

describe('parseBrief — whitespace tolerance', () => {
  it('trims trailing whitespace on section bodies', () => {
    const md = buildBrief({ 'SITUATION STATUS': 'Body with trailing space.   ' })
    const parsed = parseBrief(md, META)
    expect(parsed.sections['SITUATION STATUS']).toBe('Body with trailing space.')
  })
})

// ── Edge: section dropped (LLM produced only 5 sections) ────────────────────

describe('parseBrief — missing sections', () => {
  it('still parses surviving sections when one block is missing', () => {
    const md = [
      '# DAILY INTELLIGENCE BRIEF\n## Sunday, 26 April 2026\n*Generated for: X*',
      '## SITUATION STATUS\n\nA',
      '## KEY DEVELOPMENTS\n\nB',
      '## ENTITIES TODAY\n\nC',
      '## SIGNALS TO WATCH\n\nD',
      '## SOURCE COVERAGE\n\nF',
    ].join('\n---\n')
    const parsed = parseBrief(md, META)
    expect(parsed.sections['SITUATION STATUS']).toBe('A')
    expect(parsed.sections['SOURCE COVERAGE']).toBe('F')
    expect(parsed.sections['FINANCIAL PULSE']).toBeUndefined()
  })
})

// ── Edge: non-ASCII entity content (Telugu / Hindi) ─────────────────────────

describe('parseBrief — i18n content', () => {
  it('preserves non-ASCII entity names in section bodies', () => {
    const md = buildBrief({
      'ENTITIES TODAY': 'తెలంగాణ సీఎం\nDelivered budget.\n\nनरेन्द्र मोदी\nVisited Telangana.',
    })
    const parsed = parseBrief(md, META)
    expect(parsed.sections['ENTITIES TODAY']).toContain('తెలంగాణ సీఎం')
    expect(parsed.sections['ENTITIES TODAY']).toContain('नरेन्द्र मोदी')
  })
})

// ── Defect-tracking failures (D-BRIEF-13) ──────────────────────────────────-

describe('parseBrief — D-BRIEF-13 brittleness (currently fails)', () => {
  it.fails('accepts mixed-case section headers (LLM drift)', () => {
    const md = [
      '# DAILY INTELLIGENCE BRIEF\n## Sunday\n*Generated for: X*',
      '## Situation Status\n\nbody',
      '## Key Developments\n\nbody',
      '## Entities Today\n\nbody',
      '## Signals to Watch\n\nbody',
      '## Financial Pulse\n\nbody',
      '## Source Coverage\n\nbody',
    ].join('\n---\n')
    const parsed = parseBrief(md, META)
    expect(parsed.sections['SITUATION STATUS']).toBeDefined()
  })

  it.fails('accepts trailing colon on header (LLM drift)', () => {
    const md = [
      '# DAILY INTELLIGENCE BRIEF\n## Sunday\n*Generated for: X*',
      '## SITUATION STATUS:\n\nbody',
    ].join('\n---\n')
    const parsed = parseBrief(md, META)
    expect(parsed.sections['SITUATION STATUS']).toBe('body')
  })

  it.fails('accepts a single newline after header (LLM drift)', () => {
    const md = [
      '# DAILY INTELLIGENCE BRIEF\n## Sunday\n*Generated for: X*',
      '## SITUATION STATUS\nbody-single-newline',
    ].join('\n---\n')
    const parsed = parseBrief(md, META)
    expect(parsed.sections['SITUATION STATUS']).toBe('body-single-newline')
  })
})

// ── Pathological / safety ──────────────────────────────────────────────────-

describe('parseBrief — degenerate inputs', () => {
  it('returns empty sections for empty content', () => {
    const parsed = parseBrief('', META)
    expect(parsed.sections).toEqual({})
    expect(parsed.date).toBe('')
    expect(parsed.generatedFor).toBe('')
  })

  it('ignores headers that are not in SECTION_NAMES', () => {
    const md = '## RANDOM HEADER\n\nbody'
    const parsed = parseBrief(md, META)
    expect(parsed.sections['RANDOM HEADER']).toBeUndefined()
  })
})
