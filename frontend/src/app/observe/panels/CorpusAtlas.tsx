'use client'

import { observeApi } from '@/lib/observe-client'
import { useObservePoll } from '../hooks/useObservePoll'
import styles from '../observe.module.css'
import { Panel } from './Panel'

const TYPE_ICON: Record<string, string> = {
  news: '📰', other: '📄', analysis: '🔍', sports_result: '🏆',
  explainer: '🧠', opinion: '💭', interview: '🎙️',
  live_blog: '📡', listicle: '📋', press_release: '📢',
  recipe: '🍳', horoscope: '✨', editorial: '✍️',
}

const STANCE_COLOR: Record<string, string> = {
  neutral: 'var(--color-navy-700)',
  supportive: 'var(--color-emerald)',
  critical: 'var(--color-rose)',
  sympathetic: 'var(--color-amber)',
  defensive: 'var(--color-cobalt)',
  admiration: 'var(--color-violet)',
  concerned: 'var(--color-amber-hover)',
  analytical: 'var(--color-navy-600)',
}

export function CorpusAtlas() {
  const { data, isLoading, error } = useObservePoll(
    ['article-types'],
    () => observeApi.articleTypes(),
    { visibleIntervalMs: 120_000, hiddenIntervalMs: 600_000 }
  )

  const typeMax = data?.article_types[0]?.n ?? 1
  const langTotal = (data?.languages_24h ?? []).reduce((acc, x) => acc + x.n, 0) || 1
  const stanceTotal = (data?.stances ?? []).reduce((acc, x) => acc + x.n, 0) || 1
  const countryMax = data?.top_countries[0]?.n ?? 1

  return (
    <Panel
      title="🗺️ Corpus Atlas"
      subtitle="What this corpus is — types, languages, stances, countries"
      help="Aggregated across all v3-ok articles. Updates every 2 min."
      loading={isLoading}
      error={error}
      span2
    >
      {data && (
        <div className={styles.atlasGrid}>
          {/* Article types */}
          <section className={styles.atlasCol}>
            <h4 className={styles.atlasHead}>Article Types</h4>
            <ul className={styles.atlasList}>
              {data.article_types.slice(0, 10).map((t) => (
                <li key={t.type} className={styles.atlasRow}>
                  <span className={styles.atlasIcon}>{TYPE_ICON[t.type] ?? '·'}</span>
                  <span className={styles.atlasLabel}>{t.type.replace(/_/g, ' ')}</span>
                  <div className={styles.atlasBarTrack}>
                    <div
                      className={styles.atlasBarFill}
                      style={{
                        width: `${(t.n / typeMax) * 100}%`,
                        background: 'var(--color-amber-soft)',
                      }}
                    />
                  </div>
                  <span className={styles.atlasCount}>{t.n.toLocaleString()}</span>
                </li>
              ))}
            </ul>
          </section>

          {/* Languages 24h */}
          <section className={styles.atlasCol}>
            <h4 className={styles.atlasHead}>Languages (24h)</h4>
            <ul className={styles.atlasList}>
              {data.languages_24h.slice(0, 10).map((l) => (
                <li key={l.lang} className={styles.atlasRow}>
                  <span className={styles.atlasIcon}>🌐</span>
                  <span className={styles.atlasLabel}>{l.lang || '?'}</span>
                  <div className={styles.atlasBarTrack}>
                    <div
                      className={styles.atlasBarFill}
                      style={{
                        width: `${(l.n / langTotal) * 100}%`,
                        background: 'var(--color-cobalt-pale)',
                      }}
                    />
                  </div>
                  <span className={styles.atlasCount}>
                    {l.n.toLocaleString()}{' '}
                    <span className={styles.trendSrc}>
                      ({Math.round((l.n / langTotal) * 100)}%)
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </section>

          {/* Stances */}
          <section className={styles.atlasCol}>
            <h4 className={styles.atlasHead}>Stance Mix</h4>
            <ul className={styles.atlasList}>
              {data.stances.map((s) => (
                <li key={s.stance} className={styles.atlasRow}>
                  <span
                    className={styles.atlasDot}
                    style={{ background: STANCE_COLOR[s.stance] ?? 'var(--color-navy-600)' }}
                  />
                  <span className={styles.atlasLabel}>{s.stance}</span>
                  <div className={styles.atlasBarTrack}>
                    <div
                      className={styles.atlasBarFill}
                      style={{
                        width: `${(s.n / stanceTotal) * 100}%`,
                        background: STANCE_COLOR[s.stance] ?? 'var(--color-navy-600)',
                        opacity: 0.35,
                      }}
                    />
                  </div>
                  <span className={styles.atlasCount}>{s.n.toLocaleString()}</span>
                </li>
              ))}
            </ul>
          </section>

          {/* Top countries */}
          <section className={styles.atlasCol}>
            <h4 className={styles.atlasHead}>Top Countries (locations)</h4>
            <ul className={styles.atlasList}>
              {data.top_countries.map((c) => (
                <li key={c.country} className={styles.atlasRow}>
                  <span className={styles.atlasIcon}>📍</span>
                  <span className={styles.atlasLabel}>{c.country}</span>
                  <div className={styles.atlasBarTrack}>
                    <div
                      className={styles.atlasBarFill}
                      style={{
                        width: `${(c.n / countryMax) * 100}%`,
                        background: 'var(--color-emerald-pale)',
                      }}
                    />
                  </div>
                  <span className={styles.atlasCount}>{c.n.toLocaleString()}</span>
                </li>
              ))}
            </ul>
          </section>

          {/* Entity dictionary */}
          <section className={`${styles.atlasCol} ${styles.atlasSpan2}`}>
            <h4 className={styles.atlasHead}>Entity Dictionary</h4>
            <div className={styles.entityGrid}>
              <EntityStat icon="👥" label="People" n={data.entity_dictionary.people} />
              <EntityStat icon="🏢" label="Organisations" n={data.entity_dictionary.orgs} />
              <EntityStat icon="📍" label="Locations" n={data.entity_dictionary.locations} />
              <EntityStat icon="🗳️" label="Constituencies" n={data.entity_dictionary.constituencies} />
              <EntityStat icon="📚" label="Total" n={data.entity_dictionary.total} accent />
            </div>
          </section>
        </div>
      )}
    </Panel>
  )
}

function EntityStat({ icon, label, n, accent }: { icon: string; label: string; n: number; accent?: boolean }) {
  return (
    <div className={`${styles.entityStat} ${accent ? styles.entityStatAccent : ''}`}>
      <span className={styles.entityStatIcon}>{icon}</span>
      <div>
        <div className={styles.entityStatValue}>{n.toLocaleString()}</div>
        <div className={styles.entityStatLabel}>{label}</div>
      </div>
    </div>
  )
}
