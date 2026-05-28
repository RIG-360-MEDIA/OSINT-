'use client'

/**
 * DossierPanel — self-contained Dossier mode UI.
 *
 * Mounted inside the Analyst page when NEXT_PUBLIC_DOSSIER_ENABLED === 'true'.
 * Owns its own state, API calls, and styling. Zero shared state with the rest
 * of the analyst page so it can be unmounted with no side-effects.
 *
 * Findings are categorised into readable sections (identity, verified accounts,
 * roles, sanctions, news, breaches, web mentions, …) instead of being dumped
 * as raw JSON. Each section has a renderer tuned to its data shape.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { createClient } from '@/lib/supabase/client'

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

type TargetType = 'name' | 'email' | 'phone' | 'username' | 'domain'

interface Finding {
  source: string
  field: string
  value: unknown
  source_url: string | null
  confidence: number
  found_at: string
}

interface DossierSummary {
  total_findings?: number
  by_source?: Record<string, number>
  by_field?: Record<string, number>
  sources_attempted?: string[]
  sources_failed?: string[]
}

interface Dossier {
  id: string
  target: string
  target_type: TargetType
  status: 'pending' | 'running' | 'completed' | 'failed' | 'partial'
  summary: DossierSummary | null
  error: string | null
  purpose_note: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  findings: Finding[]
}

interface IdentityValue {
  qid?: string
  label?: string
  description?: string
  wikidata_url?: string
  image_url?: string
}

interface ResolvedQid {
  qid?: string
  label?: string
  description?: string | null
  wikidata_url?: string
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const TARGET_TYPES: TargetType[] = ['name', 'email', 'phone', 'username', 'domain']
const POLL_INTERVAL_MS = 1500
const POLL_MAX_MS = 120_000

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

interface DossierPanelProps {
  onClose: () => void
}

export default function DossierPanel({ onClose }: DossierPanelProps) {
  const [target, setTarget] = useState('')
  const [targetType, setTargetType] = useState<TargetType>('name')
  const [purposeNote, setPurposeNote] = useState('')
  const [dossier, setDossier] = useState<Dossier | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const authHeaders = useCallback(async (): Promise<HeadersInit> => {
    const supabase = createClient()
    const { data } = await supabase.auth.getSession()
    const token = data.session?.access_token
    return token
      ? { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
      : { 'Content-Type': 'application/json' }
  }, [])

  const submit = useCallback(async () => {
    if (!target.trim()) {
      setError('Target is required')
      return
    }
    setLoading(true)
    setError(null)
    setDossier(null)

    try {
      const headers = await authHeaders()
      const resp = await fetch(`${API_BASE}/api/dossier/run`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          target: target.trim(),
          target_type: targetType,
          purpose_note: purposeNote.trim() || null,
          allow_sensitive: false,
        }),
      })
      if (!resp.ok) {
        const text = await resp.text()
        throw new Error(text || `HTTP ${resp.status}`)
      }
      const created: Dossier = await resp.json()
      setDossier(created)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Unknown error'
      setError(msg)
      setLoading(false)
    }
  }, [target, targetType, purposeNote, authHeaders])

  useEffect(() => {
    if (!dossier?.id) return
    if (dossier.status !== 'pending' && dossier.status !== 'running') {
      setLoading(false)
      return
    }

    const startedAt = Date.now()
    let cancelled = false

    const tick = async () => {
      if (cancelled) return
      try {
        const headers = await authHeaders()
        const resp = await fetch(`${API_BASE}/api/dossier/${dossier.id}`, { headers })
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const fresh: Dossier = await resp.json()
        if (cancelled) return
        setDossier(fresh)
        if (fresh.status === 'pending' || fresh.status === 'running') {
          if (Date.now() - startedAt < POLL_MAX_MS) {
            setTimeout(tick, POLL_INTERVAL_MS)
          } else {
            setError('Dossier timed out — no terminal status received')
            setLoading(false)
          }
        } else {
          setLoading(false)
        }
      } catch (e: unknown) {
        if (cancelled) return
        const msg = e instanceof Error ? e.message : 'Poll failed'
        setError(msg)
        setLoading(false)
      }
    }

    const handle = setTimeout(tick, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearTimeout(handle)
    }
  }, [dossier?.id, dossier?.status, authHeaders])

  const sections = useMemo(
    () => categoriseFindings(dossier?.findings ?? []),
    [dossier?.findings],
  )

  return (
    <div style={panelStyle}>
      <div style={headerStyle}>
        <div>
          <div style={eyebrowStyle}>RIG · Dossier</div>
          <div style={titleStyle}>Entity enrichment</div>
        </div>
        <button onClick={onClose} style={closeBtnStyle} aria-label="Close dossier panel">
          close
        </button>
      </div>

      {/* ── Form ─────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gap: '12px', marginBottom: '20px' }}>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          {TARGET_TYPES.map((t) => {
            const active = targetType === t
            return (
              <button
                key={t}
                onClick={() => setTargetType(t)}
                style={pillStyle(active)}
                disabled={loading}
              >
                {t}
              </button>
            )
          })}
        </div>

        <input
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          placeholder={placeholderFor(targetType)}
          disabled={loading}
          style={inputStyle}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void submit()
          }}
        />

        <input
          value={purposeNote}
          onChange={(e) => setPurposeNote(e.target.value)}
          placeholder="Optional · purpose note (required only for sensitive sub-actions)"
          disabled={loading}
          style={{ ...inputStyle, fontSize: '13px' }}
        />

        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <button onClick={() => void submit()} disabled={loading || !target.trim()} style={runBtnStyle(loading)}>
            {loading ? 'Running…' : 'Run dossier'}
          </button>
          {dossier?.status && <StatusChip status={dossier.status} />}
        </div>
      </div>

      {error && <div style={errorBoxStyle}>{error}</div>}

      {dossier?.summary && (
        <SummaryBar summary={dossier.summary} status={dossier.status} />
      )}

      {/* ── Categorised sections ─────────────────────────────── */}
      {sections.length > 0 && (
        <div style={{ display: 'grid', gap: '14px' }}>
          {sections.map((sec) => (
            <SectionCard key={sec.id} section={sec} />
          ))}
        </div>
      )}

      {dossier && dossier.status !== 'pending' && dossier.status !== 'running' &&
        (dossier.findings?.length ?? 0) === 0 && (
          <div style={{ ...summaryBoxStyle, fontStyle: 'italic', color: 'var(--rig-ink-3)' }}>
            No findings. Try a different target type or a more specific value.
          </div>
        )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Categorisation — group raw findings into readable sections
// ─────────────────────────────────────────────────────────────────────────────

type SectionId =
  | 'identity'
  | 'accounts'
  | 'roles'
  | 'education'
  | 'politics'
  | 'sanctions'
  | 'news'
  | 'discovery'
  | 'breaches'
  | 'web'
  | 'archive'
  | 'corporate'
  | 'other'

interface Section {
  id: SectionId
  title: string
  emoji: string
  findings: Finding[]
}

const SECTION_ORDER: SectionId[] = [
  'identity', 'accounts', 'roles', 'education', 'politics',
  'sanctions', 'news', 'discovery', 'breaches', 'web', 'archive', 'corporate', 'other',
]

const SECTION_META: Record<SectionId, { title: string; emoji: string }> = {
  identity:  { title: 'Identity',                   emoji: '◉' },
  accounts:  { title: 'Verified accounts',          emoji: '✦' },
  roles:     { title: 'Roles & affiliations',       emoji: '✸' },
  education: { title: 'Education',                  emoji: '✎' },
  politics:  { title: 'Politics & citizenship',     emoji: '⚑' },
  sanctions: { title: 'Sanctions / PEP exposure',   emoji: '⚠' },
  news:      { title: 'News coverage',              emoji: '⊳' },
  discovery: { title: 'Account discovery (cascade)',emoji: '⌖' },
  breaches:  { title: 'Breach exposure',            emoji: '☠' },
  web:       { title: 'Web mentions',               emoji: '◌' },
  archive:   { title: 'Web archive',                emoji: '⏳' },
  corporate: { title: 'Corporate records',          emoji: '▢' },
  other:     { title: 'Other findings',             emoji: '•' },
}

const HANDLE_FIELDS = new Set([
  'twitter', 'instagram', 'facebook', 'github', 'tiktok',
  'youtube', 'telegram', 'linkedin', 'reddit', 'subreddit', 'vk',
  'official_website',
])

function bucketFor(f: Finding): SectionId {
  const field = (f.field || '').toLowerCase()
  const source = (f.source || '').toLowerCase()

  if (field === 'identity') return 'identity'
  if (HANDLE_FIELDS.has(field)) return 'accounts'
  if (['position_held', 'occupation', 'employer'].includes(field)) return 'roles'
  if (['educated_at', 'doctoral_advisor'].includes(field)) return 'education'
  if (['political_party', 'country_of_citizenship', 'gender',
       'place_of_birth', 'date_of_birth', 'date_of_death',
       'given_name', 'family_name'].includes(field)) return 'politics'
  if (source === 'opensanctions') return 'sanctions'
  if (source === 'gdelt' || field === 'news_mention') return 'news'
  if (source === 'whatsmyname' || source === 'holehe_lite' ||
      field === 'linked_account' || field === 'email_registered_on_site') return 'discovery'
  if (source === 'xposedornot' || source === 'hudsonrock' ||
      field === 'breach' || field === 'infostealer_hit') return 'breaches'
  if (source === 'searxng' || field === 'web_mention') return 'web'
  if (source === 'wayback' || field === 'archive_snapshot') return 'archive'
  if (source === 'opencorporates' || field === 'company_record') return 'corporate'
  return 'other'
}

function categoriseFindings(findings: Finding[]): Section[] {
  const buckets: Record<SectionId, Finding[]> = {
    identity: [], accounts: [], roles: [], education: [], politics: [],
    sanctions: [], news: [], discovery: [], breaches: [], web: [], archive: [],
    corporate: [], other: [],
  }
  for (const f of findings) buckets[bucketFor(f)].push(f)
  return SECTION_ORDER
    .filter((id) => buckets[id].length > 0)
    .map((id) => ({ id, ...SECTION_META[id], findings: buckets[id] }))
}

// ─────────────────────────────────────────────────────────────────────────────
// Section card — dispatches to the right renderer per section
// ─────────────────────────────────────────────────────────────────────────────

function SectionCard({ section }: { section: Section }) {
  return (
    <div style={sectionCardStyle}>
      <div style={sectionHeaderStyle}>
        <span style={sectionEmojiStyle}>{section.emoji}</span>
        <span style={sectionTitleStyle}>{section.title}</span>
        <span style={sectionCountStyle}>{section.findings.length}</span>
      </div>
      <div style={{ padding: '14px 18px' }}>
        {renderSectionBody(section)}
      </div>
    </div>
  )
}

function renderSectionBody(section: Section) {
  switch (section.id) {
    case 'identity':  return <IdentitySection findings={section.findings} />
    case 'accounts':  return <AccountsSection findings={section.findings} />
    case 'roles':
    case 'education':
    case 'politics':  return <LabeledQidSection findings={section.findings} />
    case 'sanctions': return <SanctionsSection findings={section.findings} />
    case 'news':      return <NewsSection findings={section.findings} />
    case 'discovery': return <DiscoverySection findings={section.findings} />
    case 'breaches':  return <BreachSection findings={section.findings} />
    case 'web':       return <WebMentionSection findings={section.findings} />
    case 'archive':   return <ArchiveSection findings={section.findings} />
    case 'corporate': return <CorporateSection findings={section.findings} />
    default:          return <RawSection findings={section.findings} />
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Section renderers
// ─────────────────────────────────────────────────────────────────────────────

function IdentitySection({ findings }: { findings: Finding[] }) {
  const id = (findings[0]?.value ?? {}) as IdentityValue
  return (
    <div style={{ display: 'grid', gridTemplateColumns: id.image_url ? '120px 1fr' : '1fr', gap: '18px' }}>
      {id.image_url && (
        <img
          src={id.image_url}
          alt={id.label || ''}
          style={{
            width: '120px',
            height: '120px',
            objectFit: 'cover',
            border: '1px solid var(--rig-rule)',
            backgroundColor: 'var(--rig-cream)',
          }}
        />
      )}
      <div>
        <div style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: '24px', fontWeight: 600 }}>
          {id.label || '—'}
        </div>
        {id.description && (
          <div style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: '15px', fontStyle: 'italic', color: 'var(--rig-ink-2)', marginTop: '4px' }}>
            {id.description}
          </div>
        )}
        {id.qid && (
          <div style={{ marginTop: '8px' }}>
            <a href={id.wikidata_url || `https://www.wikidata.org/wiki/${id.qid}`} target="_blank" rel="noreferrer" style={linkStyle}>
              wikidata: {id.qid}
            </a>
          </div>
        )}
      </div>
    </div>
  )
}

function AccountsSection({ findings }: { findings: Finding[] }) {
  return (
    <div style={{ display: 'grid', gap: '8px' }}>
      {findings.map((f, i) => {
        const handle = typeof f.value === 'string' ? f.value : ''
        const href = handleUrl(f.field, handle)
        return (
          <div key={i} style={accountRowStyle}>
            <span style={platformBadgeStyle}>{f.field}</span>
            {href ? (
              <a href={href} target="_blank" rel="noreferrer" style={accountHandleStyle}>
                {f.field === 'official_website' ? handle : `@${handle}`}
              </a>
            ) : (
              <span style={accountHandleStyle}>{handle}</span>
            )}
            <ConfChip conf={f.confidence} />
          </div>
        )
      })}
    </div>
  )
}

function LabeledQidSection({ findings }: { findings: Finding[] }) {
  return (
    <div style={{ display: 'grid', gap: '8px' }}>
      {findings.map((f, i) => {
        const v = f.value as ResolvedQid | string | undefined
        if (typeof v === 'string') {
          return (
            <div key={i} style={qidRowStyle}>
              <span style={fieldLabelStyle}>{prettyField(f.field)}</span>
              <span style={qidValueStyle}>{v}</span>
            </div>
          )
        }
        const label = v?.label || v?.qid || '—'
        return (
          <div key={i} style={qidRowStyle}>
            <span style={fieldLabelStyle}>{prettyField(f.field)}</span>
            <div>
              <div style={qidValueStyle}>{label}</div>
              {v?.description && (
                <div style={qidDescStyle}>{v.description}</div>
              )}
              {v?.wikidata_url && (
                <a href={v.wikidata_url} target="_blank" rel="noreferrer" style={subtleLinkStyle}>
                  {v.qid}
                </a>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function SanctionsSection({ findings }: { findings: Finding[] }) {
  return (
    <div style={{ display: 'grid', gap: '10px' }}>
      {findings.map((f, i) => {
        const v = f.value as {
          id?: string; name?: string; topics?: string[]; country?: string[]; score?: number
        } | undefined
        return (
          <div key={i} style={sanctionRowStyle}>
            <div style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: '17px', fontWeight: 600 }}>
              {v?.name || '—'}
              {typeof v?.score === 'number' && (
                <span style={{ marginLeft: '8px', fontFamily: "'DM Mono', monospace", fontSize: '11px', color: 'var(--rig-oxblood)' }}>
                  match {(v.score * 100).toFixed(0)}%
                </span>
              )}
            </div>
            {v?.topics && v.topics.length > 0 && (
              <div style={{ marginTop: '4px' }}>
                {v.topics.map((t) => <span key={t} style={tagStyle('oxblood')}>{t}</span>)}
              </div>
            )}
            {v?.country && v.country.length > 0 && (
              <div style={{ marginTop: '4px' }}>
                {v.country.map((c) => <span key={c} style={tagStyle('neutral')}>{c}</span>)}
              </div>
            )}
            {f.source_url && (
              <a href={f.source_url} target="_blank" rel="noreferrer" style={linkStyle}>
                opensanctions →
              </a>
            )}
          </div>
        )
      })}
    </div>
  )
}

function NewsSection({ findings }: { findings: Finding[] }) {
  return (
    <div style={{ display: 'grid', gap: '12px' }}>
      {findings.map((f, i) => {
        const v = f.value as {
          title?: string; domain?: string; language?: string; seendate?: string; tone?: number
        } | undefined
        return (
          <div key={i} style={newsRowStyle}>
            <a href={f.source_url || '#'} target="_blank" rel="noreferrer" style={{
              fontFamily: "'Cormorant Garamond', serif", fontSize: '16px', color: 'var(--rig-ink-1)',
              textDecoration: 'none', fontWeight: 600,
            }}>
              {v?.title || '(untitled)'}
            </a>
            <div style={{ fontFamily: "'DM Mono', monospace", fontSize: '11px', color: 'var(--rig-ink-3)', marginTop: '4px' }}>
              {v?.domain || ''} {v?.seendate ? `· ${formatGdeltDate(v.seendate)}` : ''} {v?.language ? `· ${v.language}` : ''}
              {typeof v?.tone === 'number' && <ToneBadge tone={v.tone} />}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function DiscoverySection({ findings }: { findings: Finding[] }) {
  return (
    <div style={{ display: 'grid', gap: '6px', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}>
      {findings.map((f, i) => {
        const v = f.value as { site?: string; category?: string } | undefined
        return (
          <a
            key={i}
            href={f.source_url || '#'}
            target="_blank"
            rel="noreferrer"
            style={discoveryChipStyle}
          >
            <div style={{ fontFamily: "'DM Mono', monospace", fontSize: '12px', color: 'var(--rig-ink-1)', fontWeight: 700 }}>
              {v?.site || '—'}
            </div>
            {v?.category && (
              <div style={{ fontFamily: "'DM Mono', monospace", fontSize: '10px', color: 'var(--rig-ink-3)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                {v.category}
              </div>
            )}
            <div style={{ fontFamily: "'DM Mono', monospace", fontSize: '10px', color: 'var(--rig-gold)', marginTop: '2px' }}>
              {f.source}
            </div>
          </a>
        )
      })}
    </div>
  )
}

function BreachSection({ findings }: { findings: Finding[] }) {
  return (
    <div style={{ display: 'grid', gap: '8px' }}>
      {findings.map((f, i) => {
        const v = (f.value && typeof f.value === 'object') ? f.value as Record<string, unknown> : {}
        return (
          <div key={i} style={breachRowStyle}>
            <div style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: '15px', fontWeight: 600, color: 'var(--rig-oxblood)' }}>
              {String(v.breach || v.site || v.name || '—')}
            </div>
            {v.date != null && (
              <div style={{ fontFamily: "'DM Mono', monospace", fontSize: '11px', color: 'var(--rig-ink-3)' }}>
                {String(v.date)}
              </div>
            )}
            {f.source_url && (
              <a href={f.source_url} target="_blank" rel="noreferrer" style={linkStyle}>{f.source}</a>
            )}
          </div>
        )
      })}
    </div>
  )
}

function WebMentionSection({ findings }: { findings: Finding[] }) {
  return (
    <div style={{ display: 'grid', gap: '10px' }}>
      {findings.map((f, i) => {
        const v = f.value as { title?: string; engine?: string; snippet?: string } | undefined
        return (
          <div key={i} style={webMentionRowStyle}>
            <a href={f.source_url || '#'} target="_blank" rel="noreferrer" style={{
              fontFamily: "'Cormorant Garamond', serif", fontSize: '15px', color: 'var(--rig-ink-1)',
              textDecoration: 'none', fontWeight: 600,
            }}>
              {v?.title || '(untitled)'}
            </a>
            {v?.snippet && (
              <div style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: '13px', fontStyle: 'italic', color: 'var(--rig-ink-2)', marginTop: '3px' }}>
                {v.snippet}
              </div>
            )}
            <div style={{ fontFamily: "'DM Mono', monospace", fontSize: '10px', color: 'var(--rig-ink-3)', marginTop: '3px' }}>
              {v?.engine && `via ${v.engine}`}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ArchiveSection({ findings }: { findings: Finding[] }) {
  return (
    <div style={{ display: 'grid', gap: '6px' }}>
      {findings.map((f, i) => {
        const v = (f.value && typeof f.value === 'object') ? f.value as Record<string, unknown> : {}
        return (
          <a
            key={i}
            href={f.source_url || '#'}
            target="_blank"
            rel="noreferrer"
            style={{ ...accountRowStyle, textDecoration: 'none' }}
          >
            <span style={fieldLabelStyle}>{String(v.timestamp || v.date || '—')}</span>
            <span style={accountHandleStyle}>{String(v.url || v.snapshot || f.source_url || '')}</span>
          </a>
        )
      })}
    </div>
  )
}

function CorporateSection({ findings }: { findings: Finding[] }) {
  return (
    <div style={{ display: 'grid', gap: '10px' }}>
      {findings.map((f, i) => {
        const v = (f.value && typeof f.value === 'object') ? f.value as Record<string, unknown> : {}
        return (
          <div key={i} style={sanctionRowStyle}>
            <div style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: '16px', fontWeight: 600 }}>
              {String(v.name || v.company_name || '—')}
            </div>
            <div style={{ fontFamily: "'DM Mono', monospace", fontSize: '11px', color: 'var(--rig-ink-3)' }}>
              {String(v.jurisdiction || '')} {v.incorporation_date ? `· founded ${String(v.incorporation_date)}` : ''}
            </div>
            {f.source_url && (
              <a href={f.source_url} target="_blank" rel="noreferrer" style={linkStyle}>opencorporates →</a>
            )}
          </div>
        )
      })}
    </div>
  )
}

function RawSection({ findings }: { findings: Finding[] }) {
  return (
    <div style={{ display: 'grid', gap: '10px' }}>
      {findings.map((f, i) => (
        <div key={i} style={{ display: 'grid', gap: '4px' }}>
          <span style={fieldLabelStyle}>{prettyField(f.field)} · {f.source}</span>
          <pre style={preStyle}>{JSON.stringify(f.value, null, 2)}</pre>
          {f.source_url && (
            <a href={f.source_url} target="_blank" rel="noreferrer" style={linkStyle}>source</a>
          )}
        </div>
      ))}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Small UI atoms
// ─────────────────────────────────────────────────────────────────────────────

function StatusChip({ status }: { status: Dossier['status'] }) {
  const color =
    status === 'completed' ? '#2d5a2d' :
    status === 'failed'    ? 'var(--rig-oxblood)' :
    status === 'partial'   ? '#8a6d00' :
                              'var(--rig-ink-3)'
  return (
    <span style={{
      fontFamily: "'DM Mono', monospace",
      fontSize: '10px',
      textTransform: 'uppercase',
      letterSpacing: '0.12em',
      padding: '3px 10px',
      border: `1px solid ${color}`,
      color,
    }}>
      {status}
    </span>
  )
}

function SummaryBar({ summary, status }: { summary: DossierSummary; status: Dossier['status'] }) {
  const total = summary.total_findings ?? 0
  const sourcesUsed = Object.keys(summary.by_source ?? {}).length
  const failed = summary.sources_failed ?? []
  return (
    <div style={summaryBoxStyle}>
      <div style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: '17px', fontWeight: 600 }}>
        {total} findings across {sourcesUsed} sources
      </div>
      {Object.entries(summary.by_source ?? {}).length > 0 && (
        <div style={{ marginTop: '8px' }}>
          {Object.entries(summary.by_source ?? {})
            .sort(([, a], [, b]) => b - a)
            .map(([src, n]) => (
              <span key={src} style={tagStyle('neutral')}>{src}: {n}</span>
            ))}
        </div>
      )}
      {status === 'partial' && failed.length > 0 && (
        <div style={{ fontFamily: "'DM Mono', monospace", fontSize: '11px', color: 'var(--rig-oxblood)', marginTop: '6px' }}>
          {failed.length} failed: {failed.slice(0, 6).join(', ')}{failed.length > 6 ? '…' : ''}
        </div>
      )}
    </div>
  )
}

function ConfChip({ conf }: { conf: number }) {
  const pct = Math.round(conf * 100)
  return (
    <span style={{
      fontFamily: "'DM Mono', monospace", fontSize: '10px',
      color: 'var(--rig-ink-3)', marginLeft: 'auto',
    }}>
      {pct}%
    </span>
  )
}

function ToneBadge({ tone }: { tone: number }) {
  const color = tone > 1 ? '#2d5a2d' : tone < -1 ? 'var(--rig-oxblood)' : 'var(--rig-ink-3)'
  return (
    <span style={{ marginLeft: '6px', color, fontFamily: "'DM Mono', monospace", fontSize: '11px' }}>
      tone {tone.toFixed(1)}
    </span>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Pure helpers
// ─────────────────────────────────────────────────────────────────────────────

function placeholderFor(t: TargetType): string {
  switch (t) {
    case 'email':    return 'someone@example.com'
    case 'phone':    return '+91 9876543210'
    case 'username': return 'handle (no @)'
    case 'domain':   return 'example.com'
    default:         return 'Full name'
  }
}

function prettyField(field: string): string {
  return field.replace(/_/g, ' ')
}

function handleUrl(platform: string, handle: string): string | null {
  if (!handle) return null
  const h = handle.replace(/^@/, '')
  switch (platform) {
    case 'twitter':  return `https://twitter.com/${h}`
    case 'instagram': return `https://www.instagram.com/${h}`
    case 'facebook': return `https://www.facebook.com/${h}`
    case 'github':   return `https://github.com/${h}`
    case 'tiktok':   return `https://www.tiktok.com/@${h}`
    case 'youtube':  return `https://www.youtube.com/${h.startsWith('UC') ? `channel/${h}` : `@${h}`}`
    case 'telegram': return `https://t.me/${h}`
    case 'linkedin': return `https://www.linkedin.com/in/${h}`
    case 'reddit':   return `https://www.reddit.com/user/${h}`
    case 'subreddit':return `https://www.reddit.com/r/${h}`
    case 'vk':       return `https://vk.com/${h}`
    case 'official_website':
      return /^https?:\/\//.test(handle) ? handle : `https://${handle}`
    default:         return null
  }
}

function formatGdeltDate(s: string): string {
  // GDELT format: YYYYMMDDTHHMMSSZ → YYYY-MM-DD
  if (/^\d{8}T\d{6}Z$/.test(s)) {
    return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`
  }
  return s
}

// ─────────────────────────────────────────────────────────────────────────────
// Styles
// ─────────────────────────────────────────────────────────────────────────────

const panelStyle: React.CSSProperties = {
  backgroundColor: 'var(--rig-cream)',
  border: '1px solid var(--rig-rule)',
  padding: '24px 28px',
  marginBottom: '20px',
}

const headerStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'flex-start',
  marginBottom: '20px',
  paddingBottom: '12px',
  borderBottom: '1px solid var(--rig-rule)',
}

const eyebrowStyle: React.CSSProperties = {
  fontFamily: "'DM Mono', monospace",
  fontSize: '10px',
  textTransform: 'uppercase',
  letterSpacing: '0.14em',
  color: 'var(--rig-gold)',
}

const titleStyle: React.CSSProperties = {
  fontFamily: "'Cormorant Garamond', serif",
  fontSize: '22px',
  fontWeight: 600,
  color: 'var(--rig-ink-1)',
}

const closeBtnStyle: React.CSSProperties = {
  fontFamily: "'DM Mono', monospace",
  fontSize: '10px',
  textTransform: 'uppercase',
  letterSpacing: '0.12em',
  padding: '4px 12px',
  border: '1px solid var(--rig-rule)',
  backgroundColor: 'transparent',
  color: 'var(--rig-ink-3)',
  cursor: 'pointer',
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 14px',
  border: '1px solid var(--rig-rule)',
  backgroundColor: 'var(--rig-paper)',
  fontFamily: "'Cormorant Garamond', serif",
  fontSize: '16px',
  color: 'var(--rig-ink-1)',
}

const errorBoxStyle: React.CSSProperties = {
  padding: '10px 14px',
  border: '1px solid var(--rig-rule)',
  borderLeft: '3px solid var(--rig-oxblood)',
  backgroundColor: 'var(--rig-paper)',
  fontFamily: "'Cormorant Garamond', serif",
  fontStyle: 'italic',
  color: 'var(--rig-oxblood)',
  marginBottom: '16px',
}

const summaryBoxStyle: React.CSSProperties = {
  padding: '12px 16px',
  border: '1px solid var(--rig-rule)',
  backgroundColor: 'var(--rig-paper)',
  marginBottom: '16px',
}

function pillStyle(active: boolean): React.CSSProperties {
  return {
    padding: '4px 12px',
    border: `1px solid ${active ? 'var(--rig-gold)' : 'var(--rig-rule)'}`,
    backgroundColor: active ? 'color-mix(in srgb, var(--rig-gold) 10%, transparent)' : 'transparent',
    fontFamily: "'DM Mono', monospace",
    fontSize: '10px',
    fontWeight: 700,
    letterSpacing: '0.1em',
    color: active ? 'var(--rig-gold)' : 'var(--rig-ink-3)',
    cursor: 'pointer',
    textTransform: 'uppercase',
  }
}

function runBtnStyle(loading: boolean): React.CSSProperties {
  return {
    padding: '8px 20px',
    border: '1px solid var(--rig-gold)',
    backgroundColor: loading ? 'transparent' : 'var(--rig-gold)',
    color: loading ? 'var(--rig-gold)' : 'var(--rig-paper)',
    fontFamily: "'DM Mono', monospace",
    fontSize: '11px',
    fontWeight: 700,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
    cursor: loading ? 'progress' : 'pointer',
  }
}

const sectionCardStyle: React.CSSProperties = {
  border: '1px solid var(--rig-rule)',
  backgroundColor: 'var(--rig-paper)',
}

const sectionHeaderStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '10px',
  padding: '10px 18px',
  borderBottom: '1px solid var(--rig-rule)',
  backgroundColor: 'var(--rig-paper-2)',
}

const sectionEmojiStyle: React.CSSProperties = {
  fontSize: '14px',
  color: 'var(--rig-gold)',
  width: '16px',
  textAlign: 'center',
}

const sectionTitleStyle: React.CSSProperties = {
  fontFamily: "'DM Mono', monospace",
  fontSize: '11px',
  textTransform: 'uppercase',
  letterSpacing: '0.14em',
  color: 'var(--rig-ink-1)',
  fontWeight: 700,
}

const sectionCountStyle: React.CSSProperties = {
  fontFamily: "'DM Mono', monospace",
  fontSize: '10px',
  color: 'var(--rig-ink-3)',
  marginLeft: 'auto',
}

const accountRowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '12px',
  padding: '6px 10px',
  border: '1px solid var(--rig-rule)',
  backgroundColor: 'var(--rig-cream)',
}

const platformBadgeStyle: React.CSSProperties = {
  fontFamily: "'DM Mono', monospace",
  fontSize: '10px',
  textTransform: 'uppercase',
  letterSpacing: '0.1em',
  color: 'var(--rig-gold)',
  minWidth: '90px',
}

const accountHandleStyle: React.CSSProperties = {
  fontFamily: "'DM Mono', monospace",
  fontSize: '13px',
  color: 'var(--rig-ink-1)',
  textDecoration: 'none',
  flex: 1,
  wordBreak: 'break-all',
}

const qidRowStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '180px 1fr',
  gap: '12px',
  padding: '6px 0',
  borderBottom: '1px dashed var(--rig-rule)',
  alignItems: 'start',
}

const fieldLabelStyle: React.CSSProperties = {
  fontFamily: "'DM Mono', monospace",
  fontSize: '10px',
  textTransform: 'uppercase',
  letterSpacing: '0.1em',
  color: 'var(--rig-ink-3)',
}

const qidValueStyle: React.CSSProperties = {
  fontFamily: "'Cormorant Garamond', serif",
  fontSize: '15px',
  color: 'var(--rig-ink-1)',
}

const qidDescStyle: React.CSSProperties = {
  fontFamily: "'Cormorant Garamond', serif",
  fontSize: '13px',
  fontStyle: 'italic',
  color: 'var(--rig-ink-3)',
  marginTop: '2px',
}

const sanctionRowStyle: React.CSSProperties = {
  padding: '10px 12px',
  border: '1px solid var(--rig-rule)',
  borderLeft: '3px solid var(--rig-oxblood)',
  backgroundColor: 'var(--rig-cream)',
}

const newsRowStyle: React.CSSProperties = {
  padding: '8px 12px',
  borderBottom: '1px dashed var(--rig-rule)',
}

const webMentionRowStyle: React.CSSProperties = {
  padding: '6px 0',
  borderBottom: '1px dashed var(--rig-rule)',
}

const breachRowStyle: React.CSSProperties = {
  padding: '8px 12px',
  border: '1px solid var(--rig-rule)',
  borderLeft: '3px solid var(--rig-oxblood)',
  backgroundColor: 'var(--rig-cream)',
}

const discoveryChipStyle: React.CSSProperties = {
  display: 'block',
  padding: '8px 12px',
  border: '1px solid var(--rig-rule)',
  backgroundColor: 'var(--rig-cream)',
  textDecoration: 'none',
}

const linkStyle: React.CSSProperties = {
  fontFamily: "'DM Mono', monospace",
  fontSize: '11px',
  color: 'var(--rig-gold)',
  textDecoration: 'underline',
}

const subtleLinkStyle: React.CSSProperties = {
  fontFamily: "'DM Mono', monospace",
  fontSize: '10px',
  color: 'var(--rig-ink-3)',
  textDecoration: 'underline',
}

const preStyle: React.CSSProperties = {
  fontFamily: "'DM Mono', monospace",
  fontSize: '12px',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  margin: '4px 0 0',
  padding: '6px 10px',
  backgroundColor: 'var(--rig-cream)',
  border: '1px solid var(--rig-rule)',
}

function tagStyle(variant: 'neutral' | 'oxblood'): React.CSSProperties {
  const color = variant === 'oxblood' ? 'var(--rig-oxblood)' : 'var(--rig-ink-3)'
  return {
    display: 'inline-block',
    fontFamily: "'DM Mono', monospace",
    fontSize: '10px',
    textTransform: 'uppercase',
    letterSpacing: '0.1em',
    padding: '2px 8px',
    marginRight: '6px',
    marginBottom: '4px',
    border: `1px solid ${color}`,
    color,
  }
}
