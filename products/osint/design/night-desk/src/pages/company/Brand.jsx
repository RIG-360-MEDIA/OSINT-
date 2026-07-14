/* View 6 — Brand & Collector Pulse */
import { BRAND } from '../../data/windlass';
import { COMPANY } from '../../data/windlass';
import { PageHead, Card, Pill, Unconfirmed } from './coUi';
import { TrendLine } from './coCharts';

export default function Brand() {
  const trend = BRAND.sentimentTrend.map((v, i) => ({ y: `M${i + 1}`, v }));
  return (
    <div className="co-page">
      <PageHead eyebrow="Brand & Collector Pulse" title="The film-and-collector heritage most defence firms would kill for" sub={BRAND.intro} />

      <div className="co-grid co-g-2-1" style={{ marginBottom: 18 }}>
        <Card title="Positive-mention trend" icon="◆" x="collector sentiment · illustrative">
          <TrendLine data={trend} w={640} h={200} color="good" unit="%" />
          <div className="co-flex" style={{ gap: 10, marginTop: 6, flexWrap: 'wrap' }}>
            {BRAND.reputation.positives.map((p, i) => <Pill key={i} tone="good">{p}</Pill>)}
          </div>
        </Card>
        <Card title="Reputation" icon="◐">
          <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 8 }}>{BRAND.reputation.label}</div>
          <div style={{ fontSize: 12.5, color: 'var(--co-faint)', marginBottom: 5 }}>Recurring criticisms</div>
          <div className="co-flex" style={{ gap: 8, flexWrap: 'wrap' }}>
            {BRAND.reputation.negatives.map((n, i) => <Pill key={i} tone="warn">{n}</Pill>)}
          </div>
          <div style={{ marginTop: 12, fontSize: 12.5, color: 'var(--co-faint)', lineHeight: 1.5 }}>
            {BRAND.reputation.trustNote} <Unconfirmed />
          </div>
        </Card>
      </div>

      <div className="co-grid co-g2" style={{ marginBottom: 18 }}>
        <Card title="Channel strength" icon="▤">
          {BRAND.channels.map((c, i) => (
            <div key={i} style={{ marginBottom: 12 }}>
              <div className="co-between" style={{ marginBottom: 4 }}>
                <span style={{ fontSize: 14, fontWeight: 550 }}>{c.name}</span>
                <span className="co-mono co-tnum" style={{ fontSize: 13, color: 'var(--co-muted)' }}>{c.strength}</span>
              </div>
              <div className={'co-score ' + (c.strength >= 60 ? 'good' : c.strength >= 40 ? 'warn' : '')}><i style={{ width: `${c.strength}%` }} /></div>
              <div style={{ fontSize: 12.5, color: 'var(--co-faint)', marginTop: 4 }}>{c.note}</div>
            </div>
          ))}
        </Card>
        <Card title="On-screen credits" icon="🎬" x="licensed & confirmed">
          <div className="co-flex" style={{ gap: 8, flexWrap: 'wrap' }}>
            {COMPANY.filmCredits.confirmed.map((f, i) => <Pill key={i} tone="info">{f}</Pill>)}
          </div>
          <div style={{ fontSize: 12.5, color: 'var(--co-faint)', margin: '12px 0 5px' }}>Claimed — not confirmed against a primary source</div>
          <div className="co-flex" style={{ gap: 8, flexWrap: 'wrap' }}>
            {COMPANY.filmCredits.claimed.map((f, i) => <Pill key={i} tone="flat">{f}</Pill>)}
          </div>
        </Card>
      </div>

      <Card title="2026 historical slate — fresh credit is dormant equity" icon="◆">
        <div className="co-grid co-g2" style={{ marginBottom: 12 }}>
          {BRAND.upcomingProductions.map((p, i) => (
            <div key={i} className="co-list-row">
              <span className="co-pill info">{p.year}</span>
              <div><b style={{ fontSize: 14 }}>{p.title}</b><div style={{ fontSize: 13, color: 'var(--co-muted)' }}>{p.note}</div></div>
            </div>
          ))}
        </div>
        <div className="co-brief"><span className="move" style={{ marginTop: 0 }}><b>Recommended move — </b>{BRAND.move}</span></div>
      </Card>
    </div>
  );
}
