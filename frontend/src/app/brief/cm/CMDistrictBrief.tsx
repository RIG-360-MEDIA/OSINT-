'use client'

/**
 * <CMDistrictBrief> — district-focused view.
 *
 * Mounted at /brief/cm/preview/[district]. Reuses the same masthead,
 * ticker and footer as the state Lead view, but the body is replaced
 * with district-specific panels:
 *
 *   - Breadcrumb back to the state brief
 *   - District hero (name, facts, stability dial, one-liner)
 *   - Map mini (Telangana with this district highlighted)
 *   - Six priority panels (News · ACLED · Mandi · Welfare · Power · Live Media)
 *   - Optional Counter-Narrative card when a P0/P1 window exists
 *
 * Empty states are explicit ("Quiet day in Adilabad — no events in the
 * last 24 hours") because silence is also signal.
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { HEADER, TICKER_EVENTS } from './editorial/data'
import { TelanganaMap } from './editorial/TelanganaMap'
import {
  type DistrictBriefData,
  getDistrictBrief,
} from './editorial/district-data'
import styles from './editorial/styles.module.css'

interface CMDistrictBriefProps {
  districtId: string
  token?: string | null
}

export function CMDistrictBrief({ districtId }: CMDistrictBriefProps) {
  const data = getDistrictBrief(districtId)
  if (!data) {
    return (
      <section className={styles.shell}>
        <div className={styles.frame}>
          <Header />
          <div className={styles.body}>
            <section className={styles.section}>
              <div className={styles.sectionInner}>
                <p>District not found: {districtId}.</p>
                <Link className={styles.heroLink} href="/brief/cm/preview">
                  ← Back to state brief
                </Link>
              </div>
            </section>
          </div>
        </div>
      </section>
    )
  }

  return (
    <section className={styles.shell} data-district={data.id}>
      <div className={styles.frame}>
        <Header />
        <div className={styles.body}>
          <div className={styles.demoWatermark} aria-hidden="true">
            <span>DEMO</span>
          </div>
          <Breadcrumb />
          <DistrictHero data={data} />
          <DistrictAtlas districtId={data.id} oneliner={data.oneliner} />
          {data.counterNarrative && <CounterNarrativeCard data={data} />}
          <DistrictPanels data={data} />
        </div>
        <Ticker />
        <p className={styles.editorsNote}>
          Editor’s note · district focus · {data.facts.hqCity}, Telangana ·
          surface only what’s actionable for the next 24 hours.
        </p>
        <p className={styles.demoDisclaimer}>
          Preview build · figures and quotations are illustrative, generated for
          layout review · not derived from live intelligence.
        </p>
      </div>
    </section>
  )
}

export default CMDistrictBrief

/* ------------------------------------------------------------------ */
/* Header (same dossier-black masthead)                                */
/* ------------------------------------------------------------------ */

function Header() {
  return (
    <header className={styles.header}>
      <div className={styles.headerLeft}>
        <span className={styles.ornament} aria-hidden="true" />
        <span>
          {HEADER.briefTitle} · {HEADER.region}
        </span>
      </div>
      <div className={styles.headerCenter}>
        {HEADER.dateline} · {useClock()}
      </div>
      <div className={styles.headerRight}>
        <span className={styles.demoStamp}>Preview · Demo data</span>
        <span className={styles.liveStamp}>
          <span className={styles.liveDot} />
          <span>As of {HEADER.asOf} · Live feed</span>
        </span>
        <span className={styles.cmName}>
          <span className={styles.cmAvatar}>R</span>
          <span>
            {HEADER.cmName} · {HEADER.cmParty}
          </span>
        </span>
      </div>
    </header>
  )
}

function useClock(): string {
  const [now, setNow] = useState<string>(() => HEADER.asOf + ':22 IST')
  useEffect(() => {
    const fmt = () => {
      const d = new Date()
      const hh = String(d.getHours()).padStart(2, '0')
      const mm = String(d.getMinutes()).padStart(2, '0')
      const ss = String(d.getSeconds()).padStart(2, '0')
      return `${hh}:${mm}:${ss} IST`
    }
    setNow(fmt())
    const id = window.setInterval(() => setNow(fmt()), 1000)
    return () => window.clearInterval(id)
  }, [])
  return now
}

/* ------------------------------------------------------------------ */
/* Breadcrumb                                                          */
/* ------------------------------------------------------------------ */

function Breadcrumb() {
  return (
    <div className={styles.breadcrumb}>
      <Link className={styles.breadcrumbBack} href="/brief/cm/preview">
        ← State brief
      </Link>
      <span className={styles.breadcrumbSep}>/</span>
      <span className={styles.breadcrumbCurrent}>District focus</span>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* District Hero                                                       */
/* ------------------------------------------------------------------ */

export function DistrictHero({ data }: { data: DistrictBriefData }) {
  const total =
    data.facts.mlaSplit.brs +
    data.facts.mlaSplit.bjp +
    data.facts.mlaSplit.inc +
    data.facts.mlaSplit.other
  return (
    <section className={styles.districtHero}>
      <div className={styles.districtHeroInner}>
        <div className={styles.districtHeroLeft}>
          <div className={styles.districtKicker}>DISTRICT FOCUS</div>
          <h1 className={styles.districtName}>{data.name}</h1>
          <p className={styles.districtOneliner}>{data.oneliner}</p>
          <dl className={styles.districtFacts}>
            <div>
              <dt>HQ</dt>
              <dd>{data.facts.hqCity}</dd>
            </div>
            <div>
              <dt>Population</dt>
              <dd>{data.facts.population}</dd>
            </div>
            <div>
              <dt>Area</dt>
              <dd>{data.facts.area}</dd>
            </div>
            <div>
              <dt>MLAs</dt>
              <dd>
                {data.facts.mlaCount}
                <span className={styles.factSub}>
                  {' '}· BRS {data.facts.mlaSplit.brs} · BJP{' '}
                  {data.facts.mlaSplit.bjp} · INC {data.facts.mlaSplit.inc}
                  {data.facts.mlaSplit.other > 0
                    ? ` · OTH ${data.facts.mlaSplit.other}`
                    : ''}
                </span>
              </dd>
            </div>
            <div className={styles.factWide}>
              <dt>Notable</dt>
              <dd>{data.facts.notableLandmark}</dd>
            </div>
          </dl>
        </div>
        <div className={styles.districtHeroRight}>
          <StabilityDial breakdown={data.stability} />
        </div>
      </div>
      <span className={styles.factSubMeta}>
        MLA split totals {total} · last electoral cycle.
      </span>
    </section>
  )
}

function StabilityDial({
  breakdown,
}: {
  breakdown: DistrictBriefData['stability']
}) {
  const overall = breakdown.overall
  const verdict =
    overall >= 70 ? 'STABLE' : overall >= 45 ? 'MONITOR' : 'STRESSED'
  const color =
    overall >= 70
      ? '#1d3557'
      : overall >= 45
        ? '#a07a45'
        : '#9c2b1f'
  const radius = 56
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - overall / 100)
  return (
    <div className={styles.stabilityDial}>
      <svg viewBox="0 0 140 140" width={140} height={140}>
        <circle
          cx={70}
          cy={70}
          r={radius}
          fill="none"
          stroke="rgba(58,42,26,0.18)"
          strokeWidth={6}
        />
        <circle
          cx={70}
          cy={70}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={6}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform="rotate(-90 70 70)"
          strokeLinecap="round"
        />
        <text
          x={70}
          y={66}
          textAnchor="middle"
          fontFamily="'Söhne Mono','IBM Plex Mono','Menlo',monospace"
          fontSize={28}
          fontWeight={500}
          fill="#1a1a1a"
        >
          {overall}
        </text>
        <text
          x={70}
          y={86}
          textAnchor="middle"
          fontFamily="'Tiempos Headline','Playfair Display','Georgia',serif"
          fontSize={9}
          letterSpacing="0.22em"
          fill={color}
          fontWeight={600}
        >
          {verdict}
        </text>
      </svg>
      <div className={styles.stabilityBreakdown}>
        <div className={styles.stabilityRow}>
          <span>Air quality</span>
          <BreakdownBar value={breakdown.airQuality} />
        </div>
        <div className={styles.stabilityRow}>
          <span>Heat stress</span>
          <BreakdownBar value={breakdown.heatStress} />
        </div>
        <div className={styles.stabilityRow}>
          <span>Conflict</span>
          <BreakdownBar value={breakdown.conflict} />
        </div>
        <div className={styles.stabilityRow}>
          <span>News anomaly</span>
          <BreakdownBar value={breakdown.newsAnomaly} />
        </div>
      </div>
    </div>
  )
}

function BreakdownBar({ value }: { value: number }) {
  return (
    <div className={styles.breakdownBar} aria-label={`Score ${value}/100`}>
      <div
        className={styles.breakdownBarFill}
        style={{ width: `${value}%` }}
      />
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Atlas section showing this district highlighted                     */
/* ------------------------------------------------------------------ */

function DistrictAtlas({
  districtId,
  oneliner,
}: {
  districtId: string
  oneliner: string
}) {
  return (
    <section className={styles.atlas}>
      <div className={styles.atlasInner}>
        <header className={styles.sectionHeader}>
          <span className={styles.sectionEyebrow}>
            The Atlas · This district
          </span>
          <span className={styles.sectionMeta}>click another district to switch</span>
        </header>
        <TelanganaMap highlightDistrictId={districtId} />
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ */
/* Counter-narrative banner — only when present                        */
/* ------------------------------------------------------------------ */

export function CounterNarrativeCard({ data }: { data: DistrictBriefData }) {
  const cn = data.counterNarrative
  if (!cn) return null
  return (
    <section className={styles.counterCard}>
      <div className={styles.counterCardInner}>
        <div className={styles.counterCardLeft}>
          <span
            className={`${styles.priorityChip} ${
              cn.priority === 'P0'
                ? styles.priorityP0
                : cn.priority === 'P1'
                  ? styles.priorityP1
                  : styles.priorityP2
            }`}
          >
            {cn.priority}
          </span>
          <span className={styles.counterCardEyebrow}>
            COUNTER-NARRATIVE WINDOW
          </span>
        </div>
        <h2 className={styles.counterCardHeadline}>{cn.headline}</h2>
        <div className={styles.counterCardDeadline}>{cn.deadline}</div>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ */
/* The six priority panels                                             */
/* ------------------------------------------------------------------ */

export function DistrictPanels({ data }: { data: DistrictBriefData }) {
  return (
    <section className={styles.intel}>
      <div className={styles.intelInner}>
        <header className={styles.sectionHeader}>
          <span className={styles.sectionEyebrow}>
            District Desk · {data.facts.hqCity}
          </span>
          <span className={styles.sectionMeta}>6 panels · last 24h</span>
        </header>
        <div className={styles.cards}>
          <NewsCard data={data} />
          <AcledCard data={data} />
          <MandiCard data={data} />
          <WelfareCard data={data} />
          <PowerCard data={data} />
          <LiveMediaCard data={data} />
        </div>
      </div>
    </section>
  )
}

function NewsCard({ data }: { data: DistrictBriefData }) {
  return (
    <section className={styles.card}>
      <div className={styles.deskHeader}>
        <span>News Desk</span>
        <span className={styles.deskMeta}>
          {data.newsHotspot.count24h} stories · 24h
        </span>
      </div>
      {data.newsHotspot.items.length === 0 ? (
        <EmptyState text={`No notable coverage of ${data.facts.hqCity} in the last 24 hours.`} />
      ) : (
        data.newsHotspot.items.slice(0, 4).map((item, i) => (
          <div key={i} className={styles.row}>
            <span className={styles.sourcePill}>{item.source}</span>
            <span className={styles.rowBody}>{item.headline}</span>
            <span className={styles.rowMeta}>
              <span className={styles.chip}>{item.sentiment.toFixed(1)}</span>{' '}
              {item.ageLabel}
            </span>
          </div>
        ))
      )}
    </section>
  )
}

function AcledCard({ data }: { data: DistrictBriefData }) {
  return (
    <section className={styles.card}>
      <div className={styles.deskHeader}>
        <span>ACLED Events</span>
        <span className={styles.deskMeta}>
          {data.acled.count7d} events · 7d
        </span>
      </div>
      {data.acled.events.length === 0 ? (
        <EmptyState text={`No protests, riots or strategic developments recorded in the last 7 days.`} />
      ) : (
        data.acled.events.slice(0, 4).map((e, i) => (
          <div key={i} className={styles.row}>
            <span className={styles.sourcePill}>{e.date}</span>
            <span className={styles.rowBody}>{e.summary}</span>
            <span className={styles.rowMeta}>
              <span className={styles.chip}>{e.type}</span>
            </span>
          </div>
        ))
      )}
    </section>
  )
}

function MandiCard({ data }: { data: DistrictBriefData }) {
  return (
    <section className={styles.card}>
      <div className={styles.deskHeader}>
        <span>Mandi Prices</span>
        <span className={styles.deskMeta}>{data.mandi.length} commodities</span>
      </div>
      {data.mandi.length === 0 ? (
        <EmptyState text="No active markets reporting from this district." />
      ) : (
        data.mandi.map((m, i) => (
          <div key={i} className={styles.row}>
            <span className={styles.sourcePill}>{m.market}</span>
            <span className={styles.rowBody}>
              {m.commodity}{' '}
              <span style={{ opacity: 0.65, fontStyle: 'italic' }}>
                {m.price}
              </span>
            </span>
            <span className={styles.rowMeta}>
              <span
                className={`${styles.watchDelta} ${
                  m.trend === 'up'
                    ? styles.watchDeltaUp
                    : m.trend === 'down'
                      ? styles.watchDeltaDown
                      : styles.watchDeltaFlat
                }`}
              >
                {m.delta}
              </span>
            </span>
          </div>
        ))
      )}
    </section>
  )
}

function WelfareCard({ data }: { data: DistrictBriefData }) {
  return (
    <section className={styles.card}>
      <div className={styles.deskHeader}>
        <span>Welfare Delivery</span>
        <span className={styles.deskMeta}>
          {data.welfare.length} schemes · district
        </span>
      </div>
      {data.welfare.map((w, i) => (
        <div key={i} className={styles.welfareRow}>
          <div className={styles.welfareTopRow}>
            <span className={styles.welfareScheme}>{w.scheme}</span>
            <span className={styles.welfarePct}>{w.coveragePct}%</span>
          </div>
          <div className={styles.breakdownBar}>
            <div
              className={styles.breakdownBarFill}
              style={{
                width: `${w.coveragePct}%`,
                background:
                  w.coveragePct >= 85
                    ? '#1d3557'
                    : w.coveragePct >= 65
                      ? '#a07a45'
                      : '#9c2b1f',
              }}
            />
          </div>
          <div className={styles.welfareDetail}>{w.detail}</div>
        </div>
      ))}
    </section>
  )
}

function PowerCard({ data }: { data: DistrictBriefData }) {
  const levelClass =
    data.power.level === 'normal'
      ? styles.powerOk
      : data.power.level === 'stressed'
        ? styles.powerStressed
        : styles.powerShedding
  return (
    <section className={styles.card}>
      <div className={styles.deskHeader}>
        <span>Power · Water</span>
        <span className={`${styles.deskMeta} ${levelClass}`}>
          {data.power.level === 'normal'
            ? 'Normal'
            : data.power.level === 'stressed'
              ? 'Stressed'
              : 'Load shedding'}
        </span>
      </div>
      <div className={styles.powerBlock}>
        <div className={styles.powerNumbers}>
          <div className={styles.powerNumber}>
            <span className={styles.powerLabel}>Demand</span>
            <span className={styles.powerValue}>{data.power.demand}</span>
          </div>
          <div className={styles.powerNumber}>
            <span className={styles.powerLabel}>Supply</span>
            <span className={styles.powerValue}>{data.power.supply}</span>
          </div>
        </div>
        <p className={styles.powerStatus}>{data.power.status}</p>
      </div>
    </section>
  )
}

function LiveMediaCard({ data }: { data: DistrictBriefData }) {
  return (
    <section className={styles.card}>
      <div className={styles.deskHeader}>
        <span>Live Media</span>
        <span className={styles.deskMeta}>
          {data.liveMedia.tvMentions.length} mentions · 24h
        </span>
      </div>
      {data.liveMedia.tvMentions.length === 0 ? (
        <EmptyState text={`No Telugu live-TV segments mentioned ${data.facts.hqCity} in the last 24 hours.`} />
      ) : (
        data.liveMedia.tvMentions.slice(0, 3).map((m, i) => (
          <div key={i} className={styles.mediaRow}>
            <div className={styles.mediaRowTop}>
              <span className={styles.sourcePill}>{m.channel}</span>
              <span className={styles.rowMeta}>{m.timestamp}</span>
            </div>
            <p className={styles.mediaSnippet}>{m.snippet}</p>
          </div>
        ))
      )}
      {data.liveMedia.channels.length > 0 && (
        <div className={styles.channelStrip}>
          {data.liveMedia.channels.map((c, i) => (
            <a
              key={i}
              href={c.url}
              target="_blank"
              rel="noopener noreferrer"
              className={styles.channelLink}
            >
              ▶ {c.label}
            </a>
          ))}
        </div>
      )}
    </section>
  )
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className={styles.emptyState}>
      <span className={styles.emptyStateOrnament}>·</span>
      <p>{text}</p>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Bottom ticker                                                       */
/* ------------------------------------------------------------------ */

function Ticker() {
  const [idx, setIdx] = useState(0)
  useEffect(() => {
    const id = window.setInterval(
      () => setIdx((i) => (i + 1) % TICKER_EVENTS.length),
      4000,
    )
    return () => window.clearInterval(id)
  }, [])
  return (
    <div className={styles.tickerRail} aria-live="polite">
      {TICKER_EVENTS.map((e, i) => (
        <div
          key={i}
          className={`${styles.tickerEvent} ${i === idx ? styles.tickerEventActive : ''}`}
        >
          <span className={styles.tickerArrow}>»</span>
          <span className={styles.tickerTime}>{e.time}</span>
          <span>{e.text}</span>
          <span className={styles.tickerArrow}>«</span>
        </div>
      ))}
    </div>
  )
}
