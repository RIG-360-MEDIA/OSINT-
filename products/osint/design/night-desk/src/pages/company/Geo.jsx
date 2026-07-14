/* View 8 — Geopolitical & Defence Spend */
import { GEO } from '../../data/windlass';
import { PageHead, Card, Pill } from './coUi';
import { TrendLine, HBars } from './coCharts';

export default function Geo() {
  const trend = GEO.trend.map((t) => ({ y: t.y, v: t.v }));
  const spenders = GEO.topSpenders.map((s) => ({ label: `${s.flag} ${s.country}`, value: s.bn }));
  return (
    <div className="co-page">
      <PageHead eyebrow="Geopolitical & Defence Spend" title="More budget, more parades — the tailwind behind every sword" sub={GEO.intro} />

      <div className="co-grid co-g4" style={{ marginBottom: 18 }}>
        <div className="co-kpi"><div className="k">World defence spend · 2024</div><div className="v">{GEO.world2024.total}</div><div className="d"><span className="up">▴ {GEO.world2024.yoy}</span></div></div>
        <Card style={{ gridColumn: 'span 3' }} title="World military expenditure" icon="▲" x="SIPRI · $ trillion">
          <TrendLine data={trend} w={720} h={180} color="accent" unit="T" />
          <div style={{ fontSize: 12.5, color: 'var(--co-faint)', marginTop: 4 }}>{GEO.world2024.note}</div>
        </Card>
      </div>

      <div className="co-grid co-g-2-1" style={{ marginBottom: 18 }}>
        <Card title="Top defence spenders 2024" icon="◈" x="SIPRI · $ billion">
          <HBars items={spenders} unit="B" fmt={(v) => `$${v}B`} />
        </Card>
        <Card title="Ceremonial-demand triggers" icon="⚑" x="dated events">
          {GEO.events.map((e, i) => (
            <div key={i} className="co-list-row" style={{ alignItems: 'flex-start' }}>
              <span className="co-mono" style={{ fontSize: 11.5, color: 'var(--co-accent-d)', width: 74, flex: 'none', paddingTop: 2 }}>{e.date}</span>
              <div>
                <div className="co-flex" style={{ gap: 6 }}><b style={{ fontSize: 13.5 }}>{e.label}</b>{!e.verified && <Pill tone="flat">inference</Pill>}</div>
                <div style={{ fontSize: 12.5, color: 'var(--co-muted)', marginTop: 2 }}>{e.note}</div>
              </div>
            </div>
          ))}
        </Card>
      </div>

      <Card title="Reading the macro">
        <div className="co-brief">
          <p style={{ margin: 0 }}>Global defence budgets are rising at the fastest rate since the Cold War, and a rare cluster of ceremonial one-offs — two NATO accessions and a British coronation inside three years — means more honour guards needing more dress swords over the next 24 months than in any recent period.</p>
          <span className="move"><b>Recommended move — </b>{GEO.move}</span>
        </div>
        <p style={{ fontSize: 12.5, color: 'var(--co-faint)', marginTop: 12 }}>{GEO.unverifiedNote}</p>
      </Card>
    </div>
  );
}
