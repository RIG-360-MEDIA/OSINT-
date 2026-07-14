/* View 7 — Trade & Regulatory Radar */
import { TRADE } from '../../data/windlass';
import { PageHead, Card, Pill } from './coUi';
import { FlowBars } from './coCharts';

export default function Trade() {
  return (
    <div className="co-page">
      <PageHead eyebrow="Trade & Regulatory Radar" title="Following the money under one customs code" sub={TRADE.intro} />

      <div className="co-grid co-g-2-1" style={{ marginBottom: 18 }}>
        <Card title="India HS-9307 exports — where they flow" icon="▤" x="UN Comtrade · 2024 share of value">
          <FlowBars items={TRADE.destinations} />
        </Card>
        <div className="co-grid" style={{ gap: 14, alignContent: 'start' }}>
          <div className="co-kpi">
            <div className="k">India HS-9307 exports · 2024</div>
            <div className="v">{TRADE.hs9307.indiaExports2024}</div>
            <div className="d"><span className="up">▴ {TRADE.hs9307.growthSince2019} since 2019</span></div>
          </div>
          <Card title="HS 9307" x="what it covers">
            <p style={{ fontSize: 13.5, lineHeight: 1.55, color: 'var(--co-ink-2)', margin: 0 }}>{TRADE.hs9307.code}. {TRADE.hs9307.note}</p>
          </Card>
        </div>
      </div>

      <Card title="Regulatory timeline" icon="▲" style={{ marginBottom: 18 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
          {TRADE.regulatory.map((r, i) => (
            <div key={i} className="co-sig" style={{ paddingLeft: 0 }}>
              <div className={'stripe ' + (r.tone === 'risk' ? 'risk' : r.tone === 'good' ? 'good' : 'info')} />
              <div className="body">
                <div className="co-flex" style={{ gap: 8 }}><Pill tone={r.tone}>{r.when}</Pill><span className="hl" style={{ fontSize: 14.5 }}>{r.title}</span></div>
                <p style={{ fontSize: 13.5, lineHeight: 1.55, color: 'var(--co-ink-2)', margin: '6px 0 0' }}>{r.body}</p>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Fact-check note">
        <p style={{ fontSize: 13.5, color: 'var(--co-ink-2)', margin: 0, lineHeight: 1.55 }}>{TRADE.correction}</p>
      </Card>
    </div>
  );
}
