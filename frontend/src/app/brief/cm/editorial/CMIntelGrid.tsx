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
  CM_NEWS,
  CM_MONITOR,
  CM_OPPOSITION,
  CM_OUTLOOK,
  CM_PULSE,
  CM_THREATS,
} from './cm-intel-data'
import styles from './styles.module.css'

export function CMIntelGrid() {
  return (
    <div className={styles.cmIntelGrid}>
      <NewsOnCM />
      <ActionsForChair />
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
  const lead = CM_NEWS[0]
  const rest = CM_NEWS.slice(1)
  return (
    <article className={`${styles.cmCard} ${styles.cmCardNews}`}>
      <header className={styles.cmCardHeader}>
        <span className={styles.cmCardEyebrow}>News on the Chair</span>
        <span className={styles.cmCardMeta}>{CM_NEWS.length} stories · 24h</span>
      </header>
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
  return (
    <article className={`${styles.cmCard} ${styles.cmCardMemo}`}>
      <header className={styles.cmCardHeader}>
        <span className={styles.cmCardEyebrow}>For the Chair</span>
        <span className={styles.cmCardMeta}>{CM_ACTIONS.length} action items</span>
      </header>
      <ul className={styles.cmActionList}>
        {CM_ACTIONS.map((a, i) => (
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
  return (
    <article className={`${styles.cmCard} ${styles.cmCardOpp}`}>
      <header className={styles.cmCardHeader}>
        <span className={styles.cmCardEyebrow}>Opposition Watch</span>
        <span className={styles.cmCardMeta}>{CM_OPPOSITION.length} actors</span>
      </header>
      <ul className={styles.cmOppList}>
        {CM_OPPOSITION.map((o, i) => (
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
  return (
    <article className={`${styles.cmCard} ${styles.cmCardMonitor}`}>
      <header className={styles.cmCardHeader}>
        <span className={styles.cmCardEyebrow}>Watchlist · Surveillance Log</span>
        <span className={styles.cmCardMeta}>{CM_MONITOR.length} entities</span>
      </header>
      <ul className={styles.cmMonitorList}>
        {CM_MONITOR.map((m, i) => (
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
  return (
    <article className={`${styles.cmCard} ${styles.cmCardThreat}`}>
      <div className={styles.cmThreatBanner}>
        <span>RESTRICTED · THREAT REGISTER</span>
        <span>{CM_THREATS.length} tracked</span>
      </div>
      <ol className={styles.cmThreatList}>
        {CM_THREATS.map((t, i) => (
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
  return (
    <article className={`${styles.cmCard} ${styles.cmCardOutlook}`}>
      <header className={styles.cmCardHeader}>
        <span className={styles.cmCardEyebrow}>Future Outlook · 7 days</span>
        <span className={styles.cmCardMeta}>{CM_OUTLOOK.length} forecasts</span>
      </header>
      <div className={styles.cmTimeline}>
        <div className={styles.cmTimelineRule} />
        {CM_OUTLOOK.map((o, i) => (
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
/* 7. Live Pulse — wide ticker-tape strip                              */
/* ------------------------------------------------------------------ */

function LivePulse() {
  return (
    <article className={`${styles.cmCard} ${styles.cmCardPulse}`}>
      <div className={styles.cmPulseHeader}>
        <span className={styles.cmPulseLiveDot} />
        <span className={styles.cmCardEyebrow}>Live Pulse · CM-Related Metrics</span>
        <span className={styles.cmCardMeta}>refreshes every 60 s</span>
      </div>
      <div className={styles.cmPulseStrip}>
        {CM_PULSE.map((p, i) => (
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
