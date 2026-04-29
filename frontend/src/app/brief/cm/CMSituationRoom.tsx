'use client'

/**
 * <CMSituationRoom> — the 14-section political situation room rendered
 * in two contexts:
 *
 *   1. /brief?view=cm  — embedded as a third toggle alongside Intel /
 *      Monitor inside the existing Brief page (preferred entry point).
 *   2. /brief/cm       — standalone deep link, kept for backward compat.
 *
 * Auth is the parent's responsibility: pass a Supabase access_token in
 * via `token`. The component returns null while token is null so the
 * parent can render its own loading state.
 */
import { useMemo, useState } from 'react'

import { CMCommandBar } from './components/CMCommandBar'
import { CMSection } from './components/CMSection'
import { CounterNarrativeCard } from './components/CounterNarrativeCard'
import { DissentCard } from './components/DissentCard'
import { DivergenceStrips } from './components/DivergenceStrips'
import { EvidenceModal } from './components/EvidenceModal'
import { IssueRow } from './components/IssueRow'
import { MoodHeatmap } from './components/MoodHeatmap'
import { PromiseTrackerTable } from './components/PromiseTrackerRow'
import { PulseMeter } from './components/PulseMeter'
import { QuoteCardGrid } from './components/QuoteCard'
import { RiskCalendar } from './components/RiskCalendar'
import { SilenceList } from './components/SilenceList'
import { SpokespersonLeaderboard } from './components/SpokespersonLeaderboard'
import {
  GlobalSkeletonStyles,
  GridSkeleton,
  RowsSkeleton,
  SparklineSkeleton,
} from './components/skeletons'
import { TrajectorySparkline } from './components/TrajectorySparkline'
import { VoiceShareDelta } from './components/VoiceShareBar'
import type { IssueCard } from './types'
import { useCMDashboard } from './useCMDashboard'

interface CMSituationRoomProps {
  token: string | null
  /** When the room is mounted inside the Brief page the brief layout
   *  already provides outer padding + width; embedded mode flattens the
   *  margin so it doesn't double-pad. */
  embedded?: boolean
}

function fmtFreshness(d: Date | null): string {
  if (!d) return ''
  const ageS = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000))
  if (ageS < 60) return `${ageS}s ago`
  const m = Math.floor(ageS / 60)
  if (m < 60) return `${m}m ago`
  return `${Math.floor(m / 60)}h ago`
}

export function CMSituationRoom({ token, embedded = false }: CMSituationRoomProps) {
  const [state, setState] = useState<string | null>(null)
  const [windowKey, setWindowKey] = useState<string>('24h')
  const [paused, setPaused] = useState(false)
  const [traceIssue, setTraceIssue] = useState<IssueCard | null>(null)

  const filters = useMemo(
    () => ({ state, window: windowKey, paused }),
    [state, windowKey, paused],
  )
  const cm = useCMDashboard(token, filters)

  const init = cm.initial.data
  const pulseData              = cm.pulse.data              ?? init?.pulse              ?? null
  const issuesData             = cm.issues.data             ?? init?.issues             ?? null
  const silenceData            = cm.silence.data            ?? init?.silence            ?? null
  const spokespersonsData      = cm.spokespersons.data      ?? init?.spokespersons      ?? null
  const cabinetOnMessageData   = cm.cabinet_onmessage.data  ?? init?.cabinet_onmessage  ?? null
  const dissentData            = cm.dissent.data            ?? init?.dissent            ?? null
  const trajectoryData         = cm.trajectory.data         ?? init?.trajectory         ?? null
  const heatmapData            = cm.heatmap.data            ?? init?.heatmap            ?? null
  const promisesData           = cm.promises.data           ?? init?.promises           ?? null
  const counterNarrativesData  = cm.counter_narratives.data ?? init?.counter_narratives ?? null
  const riskWindowData         = cm.risk_window.data        ?? init?.risk_window        ?? null
  const quotesData             = cm.quotes.data             ?? init?.quotes             ?? null
  const voiceShareData         = cm.voice_share.data        ?? init?.voice_share        ?? null
  const languageDivergenceData = cm.language_divergence.data ?? init?.language_divergence ?? null
  const mediumDivergenceData   = cm.medium_divergence.data  ?? init?.medium_divergence  ?? null

  const lastUpdated = useMemo(() => {
    const dates = [
      cm.pulse.lastUpdated,
      cm.issues.lastUpdated,
      cm.silence.lastUpdated,
      cm.trajectory.lastUpdated,
    ].filter(Boolean) as Date[]
    if (dates.length === 0) return null
    return new Date(Math.max(...dates.map((d) => d.getTime())))
  }, [cm.pulse.lastUpdated, cm.issues.lastUpdated, cm.silence.lastUpdated, cm.trajectory.lastUpdated])

  if (!token) return null

  return (
    <div
      style={
        embedded
          ? { color: 'var(--rig-ink)' }
          : {
              maxWidth: 1480,
              margin: '0 auto',
              padding: '32px 28px 80px',
              background: 'var(--rig-paper)',
              color: 'var(--rig-ink)',
            }
      }
    >
      <GlobalSkeletonStyles />

      <CMCommandBar
        filingNumber={cm.initial.data?.generated_at?.slice(11, 19) || undefined}
        state={state}
        onStateChange={setState}
        windowKey={windowKey}
        onWindowChange={setWindowKey}
        paused={paused}
        onPauseToggle={() => setPaused((v) => !v)}
        lastUpdated={lastUpdated}
        onRefreshAll={cm.refreshAll}
      />

      {!embedded && (
        <>
          <h1 className="rig-headline" style={{ fontSize: 44, marginBottom: 6, fontStyle: 'italic' }}>
            The <em>Chief Minister&rsquo;s</em> Situation Room
          </h1>
          <p className="rig-prose" style={{ fontStyle: 'italic', color: 'var(--rig-ink-3)' }}>
            Filed by the Political Desk · refreshed live
          </p>
        </>
      )}

      <CMSection
        numeral="I" title="The Pulse"
        standfirst="Political mood, this hour and this week."
        freshness={cm.pulse.lastUpdated ? `live · ${fmtFreshness(cm.pulse.lastUpdated)}` : ''}
        error={cm.pulse.error}
        onRefresh={cm.pulse.refresh}
      >
        {cm.pulse.loading && !pulseData ? (
          <GridSkeleton tiles={6} />
        ) : pulseData ? (
          <>
            <PulseMeter
              label={`OVERALL · ${pulseData.window}`}
              value={pulseData.overall.score}
              delta={pulseData.overall.delta_7d}
              n={pulseData.overall.n}
              size="hero"
            />
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
                gap: 18,
                marginTop: 18,
              }}
            >
              {pulseData.by_topic.slice(0, 6).map((t) => (
                <PulseMeter
                  key={t.topic}
                  label={`TOPIC · ${t.topic.toUpperCase()}`}
                  value={t.score} delta={t.delta_7d} n={t.n}
                />
              ))}
              {pulseData.by_region.slice(0, 4).map((r) => (
                <PulseMeter
                  key={r.region}
                  label={`REGION · ${r.region.toUpperCase()}`}
                  value={r.score} delta={r.delta_7d} n={r.n}
                />
              ))}
            </div>
          </>
        ) : null}
      </CMSection>

      <CMSection
        numeral="II" title="Issues in Play"
        standfirst="What the parties are fighting over today."
        freshness={cm.issues.lastUpdated ? `live · ${fmtFreshness(cm.issues.lastUpdated)}` : ''}
        error={cm.issues.error}
        onRefresh={cm.issues.refresh}
      >
        {cm.issues.loading && !issuesData ? (
          <RowsSkeleton rows={5} />
        ) : issuesData && issuesData.issues.length > 0 ? (
          issuesData.issues.map((iss) => (
            <IssueRow key={iss.id} issue={iss} onTrace={setTraceIssue} />
          ))
        ) : (
          <p className="rig-prose" style={{ fontStyle: 'italic', color: 'var(--rig-ink-3)' }}>
            No active flashpoints. The day is unusually quiet.
          </p>
        )}
      </CMSection>

      <CMSection
        numeral="III" title="The Silence"
        standfirst="Loud outside. Quiet from the bench."
        freshness={cm.silence.lastUpdated ? fmtFreshness(cm.silence.lastUpdated) : ''}
        error={cm.silence.error}
        onRefresh={cm.silence.refresh}
      >
        {cm.silence.loading && !silenceData ? (
          <RowsSkeleton rows={4} />
        ) : (
          <SilenceList items={silenceData?.items || []} />
        )}
      </CMSection>

      <CMSection
        numeral="IV" title="Voices Against, Voices For"
        standfirst="Who is on the offensive. Who is on the message."
        freshness={cm.spokespersons.lastUpdated ? fmtFreshness(cm.spokespersons.lastUpdated) : ''}
        error={cm.spokespersons.error || cm.cabinet_onmessage.error}
        onRefresh={() => {
          cm.spokespersons.refresh()
          cm.cabinet_onmessage.refresh()
        }}
      >
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 28 }}>
          <div>
            <h3 className="rig-byline" style={{ color: 'var(--rig-oxblood)', marginBottom: 8 }}>
              OPPOSITION ATTACKERS
            </h3>
            {cm.spokespersons.loading && !spokespersonsData ? (
              <RowsSkeleton rows={5} />
            ) : (
              <SpokespersonLeaderboard
                mode="attackers"
                rows={spokespersonsData?.rows || []}
                emptyCopy="No spokesperson activity meeting threshold."
              />
            )}
          </div>
          <div>
            <h3 className="rig-byline" style={{ color: 'var(--rig-gold)', marginBottom: 8 }}>
              CABINET ON-MESSAGE
            </h3>
            {cm.cabinet_onmessage.loading && !cabinetOnMessageData ? (
              <RowsSkeleton rows={5} />
            ) : (
              <SpokespersonLeaderboard
                mode="on-message"
                rows={cabinetOnMessageData?.rows || []}
                emptyCopy="Cabinet voice not yet quantified."
              />
            )}
          </div>
        </div>
      </CMSection>

      <CMSection
        numeral="V" title="Cracks Within"
        standfirst="Where the line is fraying — on both sides."
        freshness={cm.dissent.lastUpdated ? fmtFreshness(cm.dissent.lastUpdated) : ''}
        error={cm.dissent.error}
        onRefresh={cm.dissent.refresh}
      >
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 28 }}>
          <div>
            <h3 className="rig-byline" style={{ color: 'var(--rig-gold)', marginBottom: 8 }}>RULING</h3>
            {(dissentData?.ruling || []).map((s) => (
              <DissentCard key={s.id} signal={s} />
            ))}
            {(!dissentData || dissentData.ruling.length === 0) && (
              <p className="rig-prose" style={{ fontStyle: 'italic', color: 'var(--rig-ink-3)' }}>
                Coalition holding. No ruling-side dissent flagged.
              </p>
            )}
          </div>
          <div>
            <h3 className="rig-byline" style={{ color: 'var(--rig-oxblood)', marginBottom: 8 }}>OPPOSITION</h3>
            {(dissentData?.opposition || []).map((s) => (
              <DissentCard key={s.id} signal={s} />
            ))}
            {(!dissentData || dissentData.opposition.length === 0) && (
              <p className="rig-prose" style={{ fontStyle: 'italic', color: 'var(--rig-ink-3)' }}>
                Opposition speaking with one voice today.
              </p>
            )}
          </div>
        </div>
      </CMSection>

      <CMSection
        numeral="VI" title="The Trajectory"
        standfirst="Heating, holding, or fading."
        freshness={cm.trajectory.lastUpdated ? fmtFreshness(cm.trajectory.lastUpdated) : ''}
        error={cm.trajectory.error}
        onRefresh={cm.trajectory.refresh}
      >
        {cm.trajectory.loading && !trajectoryData ? (
          <SparklineSkeleton rows={6} />
        ) : (
          <TrajectorySparkline rows={trajectoryData?.rows || []} />
        )}
      </CMSection>

      <CMSection
        numeral="VII" title="The Map"
        standfirst="Mood, district by district."
        freshness={cm.heatmap.lastUpdated ? fmtFreshness(cm.heatmap.lastUpdated) : ''}
        error={cm.heatmap.error}
        onRefresh={cm.heatmap.refresh}
      >
        {cm.heatmap.loading && !heatmapData ? (
          <GridSkeleton tiles={12} />
        ) : (
          <MoodHeatmap cells={heatmapData?.cells || []} />
        )}
      </CMSection>

      <CMSection
        numeral="VIII" title="The Ledger"
        standfirst="Promises kept, broken, exploited."
        freshness={cm.promises.lastUpdated ? fmtFreshness(cm.promises.lastUpdated) : ''}
        error={cm.promises.error}
        onRefresh={cm.promises.refresh}
      >
        <PromiseTrackerTable rows={promisesData?.rows || []} />
      </CMSection>

      <CMSection
        numeral="IX" title="Counter-Briefs"
        standfirst="Three drafts. Not for attribution."
        freshness={cm.counter_narratives.lastUpdated ? fmtFreshness(cm.counter_narratives.lastUpdated) : ''}
        error={cm.counter_narratives.error}
        onRefresh={cm.counter_narratives.refresh}
      >
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
            gap: 18,
          }}
        >
          {(counterNarrativesData?.cards || []).map((c) => (
            <CounterNarrativeCard key={c.issue_id} card={c} />
          ))}
          {(!counterNarrativesData || counterNarrativesData.cards.length === 0) && (
            <p className="rig-prose" style={{ fontStyle: 'italic', color: 'var(--rig-ink-3)' }}>
              No attacks crossed the response threshold today.
            </p>
          )}
        </div>
      </CMSection>

      <CMSection
        numeral="X" title="The Risk Window"
        standfirst="The next seven days, weighed politically."
        freshness={cm.risk_window.lastUpdated ? fmtFreshness(cm.risk_window.lastUpdated) : ''}
        error={cm.risk_window.error}
        onRefresh={cm.risk_window.refresh}
      >
        <RiskCalendar events={riskWindowData?.events || []} days={7} />
      </CMSection>

      <CMSection
        numeral="XI" title="Verbatim"
        standfirst="Said today, in their own words."
        freshness={cm.quotes.lastUpdated ? fmtFreshness(cm.quotes.lastUpdated) : ''}
        error={cm.quotes.error}
        onRefresh={cm.quotes.refresh}
      >
        <QuoteCardGrid rows={quotesData?.rows || []} />
      </CMSection>

      <CMSection
        numeral="XII" title="Voice Share"
        standfirst="Who gained the room. Who lost it."
        freshness={cm.voice_share.lastUpdated ? fmtFreshness(cm.voice_share.lastUpdated) : ''}
        error={cm.voice_share.error}
        onRefresh={cm.voice_share.refresh}
      >
        <VoiceShareDelta rows={voiceShareData?.rows || []} />
      </CMSection>

      <CMSection
        numeral="XIII" title="Cross-Language Read"
        standfirst="When Telugu, English, and Hindi disagree."
        freshness={cm.language_divergence.lastUpdated ? fmtFreshness(cm.language_divergence.lastUpdated) : ''}
        error={cm.language_divergence.error}
        onRefresh={cm.language_divergence.refresh}
      >
        <DivergenceStrips
          rows={languageDivergenceData?.rows || []}
          emptyCopy="Languages aligned today. No divergence detected."
        />
      </CMSection>

      <CMSection
        numeral="XIV" title="Print vs Digital"
        standfirst="Editorial pages versus the timeline."
        freshness={cm.medium_divergence.lastUpdated ? fmtFreshness(cm.medium_divergence.lastUpdated) : ''}
        error={cm.medium_divergence.error}
        onRefresh={cm.medium_divergence.refresh}
      >
        <DivergenceStrips
          rows={mediumDivergenceData?.rows || []}
          emptyCopy="Print and digital reading the day similarly."
        />
      </CMSection>

      <hr className="rig-rule-strong" style={{ marginTop: 60 }} />
      <p className="rig-byline" style={{ color: 'var(--rig-ink-3)', textAlign: 'center', marginTop: 18 }}>
        End of filing — political desk
      </p>

      <EvidenceModal
        open={Boolean(traceIssue)}
        onClose={() => setTraceIssue(null)}
        title={traceIssue?.label || ''}
        kicker="ISSUE TRACE"
      >
        {traceIssue && (
          <div>
            <p className="rig-prose">{traceIssue.ruling_summary || '—'}</p>
            <p className="rig-prose" style={{ marginTop: 12 }}>
              {traceIssue.opposition_summary || '—'}
            </p>
            <p className="rig-prose" style={{ marginTop: 12, color: 'var(--rig-ink-3)' }}>
              {traceIssue.evidence_count} evidence items attached.
            </p>
          </div>
        )}
      </EvidenceModal>
    </div>
  )
}

export default CMSituationRoom
