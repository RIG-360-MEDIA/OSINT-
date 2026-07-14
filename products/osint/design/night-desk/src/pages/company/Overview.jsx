/* View 1 — Command Overview */
import { OVERVIEW, MARKETS, SIGNALS, META } from '../../data/windlass';
import { PageHead, Card, Kpi, Pill } from './coUi';
import Coverage from './Coverage';

export default function Overview({ go }) {
  const ranked = [...MARKETS.items].sort((a, b) => b.score - a.score).slice(0, 6);
  const urgent = SIGNALS.filter((s) => s.urgency === 'high').slice(0, 4);
  return (
    <div className="co-page">
      <PageHead eyebrow="Command Overview" title="Windlass — global position at a glance"
        sub={`${META.tagline}. This is the one-screen read: the money on the table, the markets worth chasing, and the three moves that matter right now.`} />

      <div className="co-grid co-g4" style={{ marginBottom: 18 }}>
        {OVERVIEW.kpis.map((k, i) => <Kpi key={i} {...k} />)}
      </div>

      <div className="co-grid co-g-2-1" style={{ marginBottom: 18 }}>
        <Card title="Where to focus next" icon="◈" x="top markets · opportunity score">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 13 }}>
            {ranked.map((m, i) => (
              <div key={i}>
                <div className="co-between" style={{ marginBottom: 5 }}>
                  <span style={{ fontSize: 14.5, fontWeight: 600 }}>
                    <span className="co-mono" style={{ color: 'var(--co-faint)', marginRight: 8 }}>{i + 1}</span>
                    <span className="co-flag">{m.flag}</span> {m.country}
                  </span>
                  <span className="co-mono co-tnum" style={{ fontSize: 13.5, fontWeight: 700, color: m.score >= 75 ? 'var(--co-good)' : m.score >= 60 ? 'var(--co-warn)' : 'var(--co-muted)' }}>{m.score}<span style={{ color: 'var(--co-faint)', fontWeight: 400 }}>/100</span></span>
                </div>
                <div className={'co-score ' + (m.score >= 75 ? 'good' : m.score >= 60 ? 'warn' : '')}>
                  <i style={{ width: `${m.score}%` }} />
                </div>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 13.5, color: 'var(--co-muted)', marginTop: 14, lineHeight: 1.5 }}>
            Longer bar = bigger opportunity, scored on defence budget × ceremonial tradition × ease of access. Full country-by-country detail on <button className="co-linkish" onClick={() => go('markets')} style={linkBtn}>Market Expansion →</button>
          </div>
        </Card>
        <Card title="Needs attention now" icon="⚑" x="high urgency">
          <div>
            {urgent.map((s, i) => (
              <div key={i} className="co-list-row" style={{ alignItems: 'flex-start' }}>
                <span className="co-flag" style={{ marginTop: 1 }}>{s.flag}</span>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.35 }}>{s.headline}</div>
                  <div className="co-flex" style={{ gap: 7, marginTop: 5 }}>
                    <Pill tone={s.kind === 'risk' ? 'risk' : 'good'}>{s.kind}</Pill>
                    <span style={{ fontSize: 12.5, color: 'var(--co-faint)' }}>{s.type}</span>
                  </div>
                </div>
              </div>
            ))}
            <button className="co-navi" onClick={() => go('signals')} style={{ marginTop: 10, color: 'var(--co-accent-d)', padding: '6px 0' }}>See the full signal feed →</button>
          </div>
        </Card>
      </div>

      <Card title="Top moves this week" icon="◉" x="analyst stand-up">
        <div className="co-grid co-g3">
          {OVERVIEW.topMoves.map((m, i) => (
            <div key={i} style={{ border: '1px solid var(--co-line)', borderRadius: 12, padding: 16, background: 'var(--co-panel-2)' }}>
              <div className="co-flex" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
                <Pill tone={m.tone}>{m.tag}</Pill>
              </div>
              <div style={{ fontWeight: 700, fontSize: 15, lineHeight: 1.35, marginBottom: 8 }}>{m.title}</div>
              <p style={{ fontSize: 14, lineHeight: 1.6, color: 'var(--co-ink-2)', margin: 0 }}>{m.body}</p>
              <div style={{ marginTop: 10, padding: '10px 12px', background: 'var(--co-accent-t)', borderLeft: '3px solid var(--co-accent)', borderRadius: '0 8px 8px 0', fontSize: 13.5, lineHeight: 1.5 }}>
                <b style={{ color: 'var(--co-accent-d)' }}>Move — </b>{m.move}
              </div>
            </div>
          ))}
        </div>
      </Card>

      <div style={{ margin: '26px 0 18px' }}>
        <div className="co-eyebrow" style={{ marginBottom: 14 }}>Sector Watch</div>
        <Coverage />
      </div>

      <p style={{ fontSize: 12.5, color: 'var(--co-faint)', marginTop: 18, lineHeight: 1.5, maxWidth: '80ch' }}>{META.generatedNote}</p>
    </div>
  );
}
const linkBtn = { background: 'none', border: 'none', color: 'var(--co-accent-d)', fontWeight: 600, cursor: 'pointer', padding: 0, font: 'inherit' };
