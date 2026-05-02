'use client'

/**
 * Layer-aware feed panel — sits to the right of the map. Each layer
 * gets its own component shape, not just a recoloured fill. World-Monitor
 * inspired: changing the layer changes what you read on the side.
 */

import {
  ACLED_FEED,
  MANDI_FEED,
  NEWS_FEED,
  POWER_FEED,
  SENTIMENT_FEED,
  STABILITY_FEED,
  WELFARE_FEED,
} from './layer-feeds'
import { getLayer } from './layers'
import styles from './styles.module.css'

interface LayerFeedProps {
  activeLayerId: string
}

export function LayerFeed({ activeLayerId }: LayerFeedProps) {
  const layer = getLayer(activeLayerId)
  return (
    <aside className={styles.layerFeed}>
      <header className={styles.layerFeedHeader}>
        <span className={styles.layerFeedEyebrow}>Layer Feed · {layer.label}</span>
        <span className={styles.layerFeedMeta}>{layer.category}</span>
      </header>
      <p className={styles.layerFeedDescription}>{layer.description}</p>
      <div className={styles.layerFeedBody}>
        {activeLayerId === 'news-hotspot' && <NewsFeed />}
        {activeLayerId === 'sentiment' && <SentimentFeed />}
        {activeLayerId === 'acled' && <AcledFeed />}
        {activeLayerId === 'mandi' && <MandiFeed />}
        {activeLayerId === 'welfare' && <WelfareFeed />}
        {activeLayerId === 'power' && <PowerFeed />}
        {activeLayerId === 'stability' && <StabilityFeed />}
      </div>
    </aside>
  )
}

/* ------------------------------------------------------------------ */
/* News Hotspot — top stories ranked                                   */
/* ------------------------------------------------------------------ */

function NewsFeed() {
  return (
    <ol className={styles.feedList}>
      {NEWS_FEED.map((n, i) => (
        <li key={i} className={styles.feedItem}>
          <div className={styles.feedItemTop}>
            <span className={styles.feedItemRank}>{String(i + 1).padStart(2, '0')}</span>
            <span className={styles.feedItemMeta}>
              {n.district} · {n.source} · {n.ageLabel}
            </span>
            <span className={styles.chip}>{n.sentiment.toFixed(1)}</span>
          </div>
          <p className={styles.feedItemHeadline}>{n.headline}</p>
        </li>
      ))}
    </ol>
  )
}

/* ------------------------------------------------------------------ */
/* Sentiment — gauge + quotes + rankings                               */
/* ------------------------------------------------------------------ */

function SentimentFeed() {
  const v = SENTIMENT_FEED.statewide
  const delta = SENTIMENT_FEED.delta
  return (
    <>
      <div className={styles.feedGauge}>
        <div className={styles.feedGaugeLabel}>Statewide sentiment</div>
        <div className={styles.feedGaugeValue}>{v.toFixed(2)}</div>
        <div className={`${styles.pulseDelta} ${styles.pulseDeltaDown}`}>
          ▼ {delta.toFixed(2)} since 09:00
        </div>
      </div>
      <div className={styles.feedSubsection}>
        <div className={styles.feedSubHeader}>Most negative districts</div>
        {SENTIMENT_FEED.topNegativeDistricts.map((d, i) => (
          <div key={i} className={styles.feedRanked}>
            <span className={styles.feedRankedRank}>{i + 1}</span>
            <span className={styles.feedRankedLabel}>{d.name}</span>
            <span className={styles.chip}>{d.value.toFixed(2)}</span>
          </div>
        ))}
      </div>
      <div className={styles.feedSubsection}>
        <div className={styles.feedSubHeader}>Voices driving the dip</div>
        {SENTIMENT_FEED.quotes.map((q, i) => (
          <blockquote key={i} className={styles.feedQuote}>
            <p>{q.text}</p>
            <cite>
              — {q.author} · {q.district} · {q.channel}
            </cite>
          </blockquote>
        ))}
      </div>
    </>
  )
}

/* ------------------------------------------------------------------ */
/* ACLED — event log + breakdown                                       */
/* ------------------------------------------------------------------ */

function AcledFeed() {
  return (
    <>
      <div className={styles.feedGauge}>
        <div className={styles.feedGaugeLabel}>Events · last 7 days</div>
        <div className={styles.feedGaugeValue}>{ACLED_FEED.total7d}</div>
        <div className={styles.feedBreakdown}>
          {ACLED_FEED.breakdown.map((b, i) => (
            <span key={i} className={styles.feedBreakdownItem}>
              <span className={styles.feedBreakdownCount}>{b.count}</span>{' '}
              <span className={styles.feedBreakdownLabel}>{b.type}</span>
            </span>
          ))}
        </div>
      </div>
      <div className={styles.feedSubsection}>
        <div className={styles.feedSubHeader}>Recent events</div>
        {ACLED_FEED.events.map((e, i) => (
          <div key={i} className={styles.feedEvent}>
            <div className={styles.feedEventTop}>
              <span className={styles.feedEventDate}>{e.date}</span>
              <span className={`${styles.chip} ${e.type === 'Riot' ? styles.chipMed : ''}`}>
                {e.type}
              </span>
              <span className={styles.feedEventDistrict}>{e.district}</span>
            </div>
            <p className={styles.feedEventSummary}>{e.summary}</p>
          </div>
        ))}
      </div>
    </>
  )
}

/* ------------------------------------------------------------------ */
/* Mandi — top movers                                                  */
/* ------------------------------------------------------------------ */

function MandiFeed() {
  return (
    <>
      <div className={styles.feedSubsection}>
        <div className={styles.feedSubHeader}>Top movers · last 24h</div>
        {MANDI_FEED.topMovers.map((m, i) => (
          <div key={i} className={styles.feedMandiRow}>
            <span className={styles.feedMandiCommodity}>{m.commodity}</span>
            <span className={styles.feedMandiPrice}>{m.price}</span>
            <span
              className={`${styles.feedMandiDelta} ${
                m.trend === 'up'
                  ? styles.watchDeltaUp
                  : m.trend === 'down'
                    ? styles.watchDeltaDown
                    : styles.watchDeltaFlat
              }`}
            >
              {m.trend === 'up' ? '▲' : m.trend === 'down' ? '▼' : '→'} {m.delta}
            </span>
            <span className={styles.feedMandiMarket}>
              {m.market} · {m.district}
            </span>
          </div>
        ))}
      </div>
      <div className={styles.feedSubsection}>
        <div className={styles.feedSubHeader}>Volatile markets</div>
        <div className={styles.feedTagRow}>
          {MANDI_FEED.volatileMarkets.map((m, i) => (
            <span key={i} className={styles.feedTag}>
              {m}
            </span>
          ))}
        </div>
      </div>
    </>
  )
}

/* ------------------------------------------------------------------ */
/* Welfare — coverage rankings                                         */
/* ------------------------------------------------------------------ */

function WelfareFeed() {
  return (
    <>
      <div className={styles.feedSubsection}>
        <div className={styles.feedSubHeader}>Statewide coverage</div>
        {WELFARE_FEED.statewide.map((s, i) => (
          <div key={i} className={styles.feedScheme}>
            <div className={styles.feedSchemeTop}>
              <span className={styles.feedSchemeName}>{s.scheme}</span>
              <span className={styles.feedSchemePct}>{s.coveragePct}%</span>
            </div>
            <div className={styles.breakdownBar}>
              <div
                className={styles.breakdownBarFill}
                style={{
                  width: `${s.coveragePct}%`,
                  background:
                    s.coveragePct >= 85
                      ? '#1d3557'
                      : s.coveragePct >= 65
                        ? '#a07a45'
                        : '#9c2b1f',
                }}
              />
            </div>
          </div>
        ))}
      </div>
      <div className={styles.feedSubsection}>
        <div className={styles.feedSubHeader}>At risk</div>
        {WELFARE_FEED.atRisk.map((d, i) => (
          <div key={i} className={styles.feedRanked}>
            <span className={styles.feedRankedLabel}>{d.district}</span>
            <span className={styles.feedRankedSub}>{d.scheme}</span>
            <span className={`${styles.chip} ${styles.chipMed}`}>{d.value}%</span>
          </div>
        ))}
      </div>
    </>
  )
}

/* ------------------------------------------------------------------ */
/* Power — grid status                                                 */
/* ------------------------------------------------------------------ */

function PowerFeed() {
  return (
    <>
      <div className={styles.feedGaugeRow}>
        <div className={styles.feedGaugeMini}>
          <div className={styles.feedGaugeLabel}>Demand</div>
          <div className={styles.feedGaugeValue}>{POWER_FEED.statewide.demand}</div>
        </div>
        <div className={styles.feedGaugeMini}>
          <div className={styles.feedGaugeLabel}>Supply</div>
          <div className={styles.feedGaugeValue}>{POWER_FEED.statewide.supply}</div>
        </div>
        <div className={styles.feedGaugeMini}>
          <div className={styles.feedGaugeLabel}>Deficit</div>
          <div className={`${styles.feedGaugeValue} ${styles.watchDeltaUp}`}>
            {POWER_FEED.statewide.deficit}
          </div>
        </div>
      </div>
      <div className={styles.feedNote}>
        Peak window {POWER_FEED.statewide.peakWindow} · expect higher draw on agri feeders.
      </div>
      <div className={styles.feedSubsection}>
        <div className={styles.feedSubHeader}>Stressed feeders</div>
        {POWER_FEED.stressed.map((p, i) => (
          <div key={i} className={styles.feedPowerRow}>
            <span className={styles.feedPowerDistrict}>{p.district}</span>
            <span className={styles.feedPowerNumbers}>
              {p.demand} <span className={styles.feedSlash}>/</span> {p.supply} MW
            </span>
            <span className={`${styles.chip} ${styles.chipMed}`}>{p.deficit} MW</span>
            <span className={styles.feedPowerNote}>{p.note}</span>
          </div>
        ))}
      </div>
    </>
  )
}

/* ------------------------------------------------------------------ */
/* Stability — composite                                               */
/* ------------------------------------------------------------------ */

function StabilityFeed() {
  return (
    <>
      <div className={styles.feedGauge}>
        <div className={styles.feedGaugeLabel}>Statewide stability</div>
        <div className={styles.feedGaugeValue}>{STABILITY_FEED.statewide}/100</div>
        <div className={`${styles.pulseDelta} ${styles.pulseDeltaDown}`}>
          ▼ {STABILITY_FEED.delta} since yesterday
        </div>
      </div>
      <div className={styles.feedSubsection}>
        <div className={styles.feedSubHeader}>Most stressed districts</div>
        {STABILITY_FEED.mostStressed.map((d, i) => (
          <div key={i} className={styles.feedRanked}>
            <span className={styles.feedRankedRank}>{i + 1}</span>
            <span className={styles.feedRankedLabel}>{d.district}</span>
            <span className={`${styles.chip} ${styles.chipMed}`}>{d.score}</span>
          </div>
        ))}
      </div>
      <div className={styles.feedSubsection}>
        <div className={styles.feedSubHeader}>Most stable</div>
        {STABILITY_FEED.mostStable.map((d, i) => (
          <div key={i} className={styles.feedRanked}>
            <span className={styles.feedRankedRank}>{i + 1}</span>
            <span className={styles.feedRankedLabel}>{d.district}</span>
            <span className={`${styles.chip} ${styles.chipBlue}`}>{d.score}</span>
          </div>
        ))}
      </div>
      <div className={styles.feedSubsection}>
        <div className={styles.feedSubHeader}>Composite weights</div>
        {STABILITY_FEED.componentWeights.map((c, i) => (
          <div key={i} className={styles.feedScheme}>
            <div className={styles.feedSchemeTop}>
              <span className={styles.feedSchemeName}>{c.name}</span>
              <span className={styles.feedSchemePct}>{c.weight}%</span>
            </div>
            <div className={styles.breakdownBar}>
              <div className={styles.breakdownBarFill} style={{ width: `${c.weight * 3}%` }} />
            </div>
          </div>
        ))}
      </div>
    </>
  )
}
