'use client'

import { useAccess } from '@/lib/access'

import styles from './observe.module.css'
import { CorpusBanner } from './CorpusBanner'
import { AuditQueue } from './panels/AuditQueue'
import { BreakingNow } from './panels/BreakingNow'
import { CorpusAtlas } from './panels/CorpusAtlas'
import { CrossTabAnalyst } from './panels/CrossTabAnalyst'
import { GeoHeatmap } from './panels/GeoHeatmap'
import { IngestPulse } from './panels/IngestPulse'
import { LiveArticleTail } from './panels/LiveArticleTail'
import { PipelineHealth } from './panels/PipelineHealth'
import { QualityMonitor } from './panels/QualityMonitor'
import { SourceScorecard } from './panels/SourceScorecard'
import { StoryPulse } from './panels/StoryPulse'
import { TopSpeakers } from './panels/TopSpeakers'
import { TrendingNow } from './panels/TrendingNow'
import { usePersona, type Persona } from './ObservePersonaContext'

const PERSONA_LABELS: Record<Persona, { label: string; hint: string }> = {
  developer:  { label: 'Developer',  hint: 'Focus on raw counters & anomalies' },
  auditor:    { label: 'Auditor',    hint: 'Focus on quality, drift, audit queue' },
  journalist: { label: 'Journalist', hint: 'Focus on stories, geo, source coverage' },
}

export default function ObservePage() {
  const { access, loading } = useAccess()
  const { persona, setPersona } = usePersona()

  if (loading) {
    return (
      <div style={{ padding: '4rem', textAlign: 'center', color: 'var(--color-navy-600)' }}>
        Checking your access…
      </div>
    )
  }
  if (!access || access.role !== 'super_admin') {
    return (
      <div style={{ maxWidth: 480, margin: '4rem auto', padding: '0 1rem', textAlign: 'center' }}>
        <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '2rem', color: 'var(--color-navy)' }}>Restricted</h1>
        <p style={{ marginTop: '0.5rem', color: 'var(--color-navy-700)' }}>
          The <code>/observe</code> console is available to super-administrators only.
        </p>
        <p style={{ marginTop: '0.25rem', fontSize: 12, color: 'var(--color-navy-600)' }}>
          Signed in as <strong>{access?.email}</strong> · role <code>{access?.role ?? 'guest'}</code>
        </p>
      </div>
    )
  }

  return (
    <main className={styles.page}>
      <div className={styles.header}>
        <div className={styles.headerInner}>
          <div>
            <div className={styles.eyebrow}>
              <span className={styles.pulse} />
              Live data-quality console
            </div>
            <h1 className={styles.title}>Observe</h1>
            <p className={styles.tagline}>Watch the corpus breathe — ingest, accuracy, geography, stories.</p>
          </div>

          <div className={styles.personaWrap}>
            <span className={styles.personaLabel}>View as</span>
            <div className={styles.personaSwitch} data-testid="persona-switcher" role="tablist">
              {(Object.keys(PERSONA_LABELS) as Persona[]).map((p) => (
                <button
                  key={p}
                  onClick={() => setPersona(p)}
                  role="tab"
                  aria-selected={persona === p}
                  title={PERSONA_LABELS[p].hint}
                  className={`${styles.personaBtn} ${persona === p ? styles.personaActive : ''}`}
                >
                  {PERSONA_LABELS[p].label}
                </button>
              ))}
            </div>
            <span className={styles.personaHint}>{PERSONA_LABELS[persona].hint}</span>
          </div>
        </div>
      </div>

      <CorpusBanner />

      <section className={styles.grid} data-testid="observe-panels">
        <PipelineHealth />
        <IngestPulse />
        <QualityMonitor />
        <BreakingNow />
        <TrendingNow />
        <TopSpeakers />
        <StoryPulse />
        <CorpusAtlas />
        <SourceScorecard />
        <GeoHeatmap />
        <LiveArticleTail />
        <CrossTabAnalyst />
        <AuditQueue />
      </section>

      <footer className={styles.footer}>
        Polling pauses when the tab is hidden · refreshes every 5–60 s ·
        Signed in as <strong>{access.email}</strong>
      </footer>
    </main>
  )
}
