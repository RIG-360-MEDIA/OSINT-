'use client'

/**
 * CM Intelligence Grid — 7 themed cards, each with its own visual
 * language. No more identical-template cards. Asymmetric Bento grid:
 *
 *   [ NEWS ON CM (2 wide)          ] [ ACTIONS (1) ]
 *   [ OPPOSITION (1) ] [ MONITOR (2 wide)          ]
 *   [ THREATS (1)    ] [ OUTLOOK (2 wide)          ]
 *   [ LIVE PULSE (full width 3-col strip)          ]
 *
 * All cards share paper-cream background, Tiempos / Söhne Mono type,
 * and the wax-red / ink-blue / sepia palette — but the *treatment*
 * inside each card is bespoke so the page reads as a folio, not a
 * dashboard with 7 of the same widget.
 */

import {
  CM_ACTIONS,
  CM_ANALYSIS,
  CM_NEWS,
  CM_MONITOR,
  CM_OPPOSITION,
  CM_OUTLOOK,
  CM_PULSE,
  CM_THREATS,
} from './cm-intel-data'
import {
  panelMode,
  useCMActions,
  useCMAnalysis,
  useCMLivePulse,
  useCMMonitor,
  useCMNewsOnChair,
  useCMOpposition,
  useCMOutlook,
  useCMThreats,
} from './hooks'
import styles from './styles.module.css'

/** Tiny banner shown above any card whose live feed is degraded. */
function DegradedBanner() {
  return (
    <div
      style={{
        fontFamily:
          "'Söhne Mono','IBM Plex Mono','Menlo',monospace",
        fontSize: 9,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        color: '#9c2b1f',
        opacity: 0.85,
        padding: '2px 0 6px',
        fontStyle: 'italic',
      }}
    >
      live feed degraded · showing reference layout
    </div>
  )
}

export function CMIntelGrid() {
  return (
    <div className={styles.cmIntelGrid}>
      <NewsOnCM />
      <ActionsForChair />
      <AnalysisColumn />
      <OppositionWatch />
      <MonitorList />
      <ThreatRegister />
      <FutureOutlook />
      <LivePulse />
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* 1. News on CM — newspaper front-page treatment                      */
/* ------------------------------------------------------------------ */

function NewsOnCM() {
  const q = useCMNewsOnChair()
  const mode = panelMode(q)
  const liveItems = q.data?.items ?? []
  const items = mode === 'live' && liveItems.length > 0 ? liveItems : CM_NEWS
  const lead = items[0]
  const rest = items.slice(1)
  return (
    <article className={`${styles.cmCard} ${styles.cmCardNews}`}>
      <header className={styles.cmCardHeader}>
        <span className={styles.cmCardEyebrow}>News on the Chair</span>
        <span className={styles.cmCardMeta}>{items.length} stories · 24h</span>
      </header>
      {mode === 'degraded' && <DegradedBanner />}
      <div className={styles.cmNewsLead}>
        <span className={styles.cmNewsLeadMeta}>
          {lead.source} · {lead.ageLabel} · sentiment {lead.sentiment.toFixed(1)}
        </span>
        <h3 className={styles.cmNewsLeadHeadline}>
          <span className={styles.cmNewsDropCap}>{lead.text.charAt(0)}</span>
          {lead.text.slice(1)}
        </h3>
      </div>
      <ul className={styles.cmNewsRest}>
        {rest.map((n, i) => (
          <li key={i}>
            <span className={styles.cmNewsRestSource}>{n.source}</span>
            <span className={styles.cmNewsRestAge}>{n.ageLabel}</span>
            <p className={styles.cmNewsRestText}>{n.text}</p>
            <span
              className={`${styles.cmSentimentChip} ${n.sentiment < 0 ? styles.cmSentimentNeg : styles.cmSentimentPos}`}
            >
              {n.sentiment > 0 ? '+' : ''}
              {n.sentiment.toFixed(1)}
            </span>
          </li>
        ))}
      </ul>
    </article>
  )
}

/* ------------------------------------------------------------------ */
/* 2. Actions for the Chair — memo card with checkboxes                */
/* ------------------------------------------------------------------ */

function ActionsForChair() {
  const q = useCMActions()
  const mode = panelMode(q)
  const liveItems = q.data?.items ?? []
  const actions = mode === 'live' && liveItems.length > 0 ? liveItems : CM_ACTIONS
  return (
    <article className={`${styles.cmCard} ${styles.cmCardMemo}`}>
      <header className={styles.cmCardHeader}>
        <span className={styles.cmCardEyebrow}>For the Chair</span>
        <span className={styles.cmCardMeta}>{actions.length} action items</span>
      </header>
      {mode === 'degraded' && <DegradedBanner />}
      <ul className={styles.cmActionList}>
        {actions.map((a, i) => (
          <li key={i} className={styles.cmActionRow}>
            <span className={styles.cmCheckbox} aria-hidden="true" />
            <span
              className={`${styles.cmActionChip} ${
                a.priority === 'P0'
                  ? styles.cmActionChipP0
                  : a.priority === 'P1'
                    ? styles.cmActionChipP1
                    : styles.cmActionChipP2
              }`}
            >
              {a.priority}
            </span>
            <div className={styles.cmActionBody}>
              <span className={styles.cmActionText}>{a.text}</span>
              {a.deadline && (
                <span className={styles.cmActionDeadline}>{a.deadline}</span>
              )}
            </div>
          </li>
        ))}
      </ul>
      <div className={styles.cmMemoFooter}>
        <span>Initialled · _________________</span>
      </div>
    </article>
  )
}

/* ------------------------------------------------------------------ */
/* 3. Opposition Watch — press-clipping feed                           */
/* ------------------------------------------------------------------ */

function OppositionWatch() {
  const q = useCMOpposition()
  const mode = panelMode(q)
  const liveItems = q.data?.items ?? []
  const items = mode === 'live' && liveItems.length > 0 ? liveItems : CM_OPPOSITION
  return (
    <article className={`${styles.cmCard} ${styles.cmCardOpp}`}>
      <header className={styles.cmCardHeader}>
        <span className={styles.cmCardEyebrow}>Opposition Watch</span>
        <span className={styles.cmCardMeta}>{items.length} actors</span>
      </header>
      {mode === 'degraded' && <DegradedBanner />}
      <ul className={styles.cmOppList}>
        {items.map((o, i) => (
          <li key={i} className={styles.cmOppEntry}>
            <div className={styles.cmOppHeader}>
              <span className={styles.cmOppAvatar}>{initials(o.actor)}</span>
              <span className={styles.cmOppName}>
                {o.actor}{' '}
                <span className={styles.cmOppParty}>({o.party})</span>
              </span>
              <span className={styles.cmOppMeta}>
                {o.channel} · {o.ageLabel}
              </span>
            </div>
            <blockquote className={styles.cmOppQuote}>{o.text}</blockquote>
            {o.reach && <span className={styles.cmOppReach}>{o.reach}</span>}
          </li>
        ))}
      </ul>
    </article>
  )
}

function initials(name: string): string {
  const parts = name.split(' ').filter(Boolean)
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase()
  return (parts[0]![0] + parts[parts.length - 1]![0]).toUpperCase()
}

/* ------------------------------------------------------------------ */
/* 4. Monitor List — dotted-leader watchlist log                       */
/* ------------------------------------------------------------------ */

function MonitorList() {
  const q = useCMMonitor()
  const mode = panelMode(q)
  const liveItems = q.data?.items ?? []
  const items = mode === 'live' && liveItems.length > 0 ? liveItems : CM_MONITOR
  return (
    <article className={`${styles.cmCard} ${styles.cmCardMonitor}`}>
      <header className={styles.cmCardHeader}>
        <span className={styles.cmCardEyebrow}>Watchlist · Surveillance Log</span>
        <span className={styles.cmCardMeta}>{items.length} entities</span>
      </header>
      {mode === 'degraded' && <DegradedBanner />}
      <ul className={styles.cmMonitorList}>
        {items.map((m, i) => (
          <li key={i} className={styles.cmMonitorRow}>
            <span className={styles.cmMonitorLabel}>{m.label}</span>
            <span className={styles.cmMonitorLeader} aria-hidden="true" />
            <span
              className={`${styles.cmMonitorStatus} ${
                m.trend === 'up'
                  ? styles.cmMonitorUp
                  : m.trend === 'down'
                    ? styles.cmMonitorDown
                    : m.trend === 'live'
                      ? styles.cmMonitorLive
                      : styles.cmMonitorFlat
              }`}
            >
              {m.status}
            </span>
          </li>
        ))}
      </ul>
    </article>
  )
}

/* ------------------------------------------------------------------ */
/* 5. Threat Register — classified-dossier card                        */
/* ------------------------------------------------------------------ */

function ThreatRegister() {
  const q = useCMThreats()
  const mode = panelMode(q)
  const liveItems = q.data?.items ?? []
  const items = mode === 'live' && liveItems.length > 0 ? liveItems : CM_THREATS
  return (
    <article className={`${styles.cmCard} ${styles.cmCardThreat}`}>
      <div className={styles.cmThreatBanner}>
        <span>RESTRICTED · THREAT REGISTER</span>
        <span>{items.length} tracked</span>
      </div>
      {mode === 'degraded' && <DegradedBanner />}
      <ol className={styles.cmThreatList}>
        {items.map((t, i) => (
          <li key={i} className={styles.cmThreatRow}>
            <span className={styles.cmThreatNum}>
              {String(i + 1).padStart(2, '0')}
            </span>
            <div className={styles.cmThreatBody}>
              <span
                className={`${styles.cmThreatLevel} ${levelClass(t.level)}`}
              >
                {t.level}
              </span>
              <p className={styles.cmThreatText}>{t.text}</p>
              <span className={styles.cmThreatPosture}>{t.posture}</span>
            </div>
          </li>
        ))}
      </ol>
    </article>
  )
}

function levelClass(level: string): string {
  if (level === 'HIGH') return styles.cmThreatHigh
  if (level === 'MED') return styles.cmThreatMed
  if (level === 'LOW-MED') return styles.cmThreatLowMed
  return styles.cmThreatLow
}

/* ------------------------------------------------------------------ */
/* 6. Future Outlook — horizontal timeline                              */
/* ------------------------------------------------------------------ */

function FutureOutlook() {
  const q = useCMOutlook()
  const mode = panelMode(q)
  const liveItems = q.data?.items ?? []
  const items = mode === 'live' && liveItems.length > 0 ? liveItems : CM_OUTLOOK
  return (
    <article className={`${styles.cmCard} ${styles.cmCardOutlook}`}>
      <header className={styles.cmCardHeader}>
        <span className={styles.cmCardEyebrow}>Future Outlook · 7 days</span>
        <span className={styles.cmCardMeta}>{items.length} forecasts</span>
      </header>
      {mode === 'degraded' && <DegradedBanner />}
      <div className={styles.cmTimeline}>
        <div className={styles.cmTimelineRule} />
        {items.map((o, i) => (
          <div key={i} className={styles.cmTimelineEntry}>
            <span className={styles.cmTimelinePeg} aria-hidden="true" />
            <span className={styles.cmTimelineWhen}>{o.when}</span>
            <p className={styles.cmTimelineText}>{o.text}</p>
          </div>
        ))}
      </div>
    </article>
  )
}

/* ------------------------------------------------------------------ */
/* 8. Analysis Column — pure editorial prose, structured op-ed         */
/* ------------------------------------------------------------------ */

function AnalysisColumn() {
  const q = useCMAnalysis()
  const mode = panelMode(q)
  // The analysis endpoint returns the latest *published* draft or null.
  // When null / errored / empty, fall back to the demo column so the
  // page never has a hole. The schema mirrors CmAnalysis so we can
  // assign directly (server uses pull_quote snake_case → coerce).
  const live = q.data?.column ?? null
  const a = live
    ? {
        eyebrow: live.eyebrow,
        byline: live.byline,
        headline: live.headline,
        deck: live.deck,
        paragraphs: live.paragraphs,
        pullQuote: (live as unknown as { pull_quote?: string }).pull_quote ?? live.pullQuote ?? '',
        endnote: live.endnote,
      }
    : CM_ANALYSIS
  // Split paragraphs around the pull-quote: roughly half before, rest after.
  const pivot = Math.ceil(a.paragraphs.length / 2)
  const before = a.paragraphs.slice(0, pivot)
  const after = a.paragraphs.slice(pivot)
  return (
    <article className={`${styles.cmCard} ${styles.cmCardAnalysis}`}>
      <header className={styles.cmAnalysisHeader}>
        <span className={styles.cmAnalysisEyebrow}>{a.eyebrow}</span>
        <span className={styles.cmAnalysisByline}>{a.byline}</span>
      </header>
      {mode === 'degraded' && <DegradedBanner />}
      <h2 className={styles.cmAnalysisHeadline}>{a.headline}</h2>
      <p className={styles.cmAnalysisDeck}>{a.deck}</p>
      <div className={styles.cmAnalysisDivider} />
      <div className={styles.cmAnalysisBody}>
        {before.map((p, i) => (
          <p key={`b-${i}`} className={styles.cmAnalysisPara}>
            {i === 0 ? (
              <>
                <span className={styles.cmAnalysisDropCap}>{p.charAt(0)}</span>
                {p.slice(1)}
              </>
            ) : (
              p
            )}
          </p>
        ))}
      </div>
      <blockquote className={styles.cmAnalysisPullQuote}>{a.pullQuote}</blockquote>
      <div className={styles.cmAnalysisBody}>
        {after.map((p, i) => (
          <p key={`a-${i}`} className={styles.cmAnalysisPara}>
            {p}
          </p>
        ))}
      </div>
      <div className={styles.cmAnalysisEndnote}>{a.endnote}</div>
    </article>
  )
}

/* ------------------------------------------------------------------ */
/* 7. Live Pulse — wide ticker-tape strip                              */
/* ------------------------------------------------------------------ */

function LivePulse() {
  const q = useCMLivePulse()
  const mode = panelMode(q)
  const liveMetrics = q.data?.metrics ?? []
  const metrics = mode === 'live' && liveMetrics.length > 0 ? liveMetrics : CM_PULSE
  return (
    <article className={`${styles.cmCard} ${styles.cmCardPulse}`}>
      <div className={styles.cmPulseHeader}>
        <span className={styles.cmPulseLiveDot} />
        <span className={styles.cmCardEyebrow}>Live Pulse · CM-Related Metrics</span>
        <span className={styles.cmCardMeta}>refreshes every 30 s</span>
      </div>
      {mode === 'degraded' && <DegradedBanner />}
      <div className={styles.cmPulseStrip}>
        {metrics.map((p, i) => (
          <div key={i} className={styles.cmPulseTile}>
            <div className={styles.cmPulseLabel}>{p.label}</div>
            <div className={styles.cmPulseValue}>{p.value}</div>
            {p.delta && (
              <div
                className={`${styles.cmPulseDelta} ${
                  p.trend === 'up'
                    ? styles.cmPulseDeltaUp
                    : p.trend === 'down'
                      ? styles.cmPulseDeltaDown
                      : styles.cmPulseDeltaFlat
                }`}
              >
                {p.delta}
              </div>
            )}
          </div>
        ))}
      </div>
    </article>
  )
}
