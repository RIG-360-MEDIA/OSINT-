'use client'

import { useAccess } from '@/lib/access'

import { AuditQueue } from './panels/AuditQueue'
import { CrossTabAnalyst } from './panels/CrossTabAnalyst'
import { GeoHeatmap } from './panels/GeoHeatmap'
import { IngestPulse } from './panels/IngestPulse'
import { LiveArticleTail } from './panels/LiveArticleTail'
import { QualityMonitor } from './panels/QualityMonitor'
import { SourceScorecard } from './panels/SourceScorecard'
import { StoryPulse } from './panels/StoryPulse'
import { usePersona, type Persona } from './ObservePersonaContext'

export default function ObservePage() {
  const { access, loading } = useAccess()
  const { persona, setPersona } = usePersona()

  if (loading) {
    return <div className="p-8 text-center">Loading…</div>
  }
  if (!access || access.role !== 'super_admin') {
    return (
      <div className="p-8">
        <h1 className="font-serif text-2xl">Forbidden</h1>
        <p className="text-sm text-neutral-600">/observe is for super-admins only.</p>
      </div>
    )
  }

  return (
    <main className="mx-auto max-w-7xl p-4">
      <header className="mb-4 flex items-baseline justify-between">
        <h1 className="font-serif text-2xl font-semibold tracking-tight">
          /observe
          <span className="ml-2 text-sm text-neutral-500">RIG data-quality console</span>
        </h1>
        <nav className="flex gap-1 text-xs" data-testid="persona-switcher">
          {(['developer', 'auditor', 'journalist'] as Persona[]).map((p) => (
            <button
              key={p}
              onClick={() => setPersona(p)}
              className={`rounded px-2 py-1 ${persona === p ? 'bg-emerald-600 text-white' : 'bg-neutral-200 text-neutral-700'}`}
            >
              {p}
            </button>
          ))}
        </nav>
      </header>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3" data-testid="observe-panels">
        <IngestPulse />
        <QualityMonitor />
        <StoryPulse />
        <SourceScorecard />
        <GeoHeatmap />
        <LiveArticleTail />
        <CrossTabAnalyst />
        <AuditQueue />
      </section>
    </main>
  )
}
