/* View 5 — Social vs Competitors (REAL public follower numbers) */
import { SOCIAL } from '../../data/windlass';
import { PageHead, Card, Pill } from './coUi';
import { HBars } from './coCharts';

const fmtK = (n) => (n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}K` : String(n));

export default function Social() {
  const ig = SOCIAL.brands.filter((b) => b.ig != null)
    .map((b) => ({ label: b.name, value: b.ig, you: b.tone === 'you' }))
    .sort((a, b) => b.value - a.value);
  const li = SOCIAL.brands.filter((b) => b.li != null)
    .map((b) => ({ label: b.name, value: b.li, you: b.tone === 'you' }))
    .sort((a, b) => b.value - a.value);

  return (
    <div className="co-page">
      <PageHead eyebrow="Social vs Competitors · real data" title="Unbeatable on the product, invisible online" sub={SOCIAL.intro} />

      <div className="co-grid co-g2" style={{ marginBottom: 18 }}>
        <Card title="Instagram followers" icon="◐" x="public accounts · Jul 2026">
          <HBars items={ig} fmt={fmtK} />
          <p style={{ fontSize: 12.5, color: 'var(--co-faint)', marginTop: 12, lineHeight: 1.5 }}>{SOCIAL.note}</p>
        </Card>
        <Card title="LinkedIn followers" icon="◑" x="public pages">
          <HBars items={li} fmt={fmtK} />
          <div style={{ marginTop: 14, padding: '12px 14px', background: 'var(--co-risk-t)', borderRadius: 10 }}>
            <div className="co-flex" style={{ gap: 8 }}><Pill tone="risk">gap</Pill><b style={{ fontSize: 14 }}>~145× reach deficit vs Cold Steel on Instagram</b></div>
            <p style={{ fontSize: 13.5, margin: '6px 0 0', color: 'var(--co-ink-2)', lineHeight: 1.5 }}>
              A budget knife brand with no government contracts commands the sword conversation. That is the single most fixable weakness in this report.
            </p>
          </div>
        </Card>
      </div>

      <Card title="The people who shape sword-buying opinion" icon="◆" x="creator reach" style={{ marginBottom: 18 }}>
        <div className="co-grid co-g3">
          {SOCIAL.influencers.map((inf, i) => (
            <div key={i} style={{ border: '1px solid var(--co-line)', borderRadius: 12, padding: 14, background: 'var(--co-panel-2)' }}>
              <div className="co-between"><b style={{ fontSize: 14.5 }}>{inf.name}</b><span className="co-mono" style={{ fontSize: 13, color: 'var(--co-accent-d)' }}>{inf.subs}</span></div>
              <div style={{ fontSize: 12.5, color: 'var(--co-faint)', margin: '2px 0 6px' }}>{inf.platform}</div>
              <p style={{ fontSize: 13, lineHeight: 1.5, color: 'var(--co-ink-2)', margin: 0 }}>{inf.note}</p>
            </div>
          ))}
        </div>
      </Card>

      <Card title={SOCIAL.gap.title} icon="⚑">
        <div className="co-brief">
          <p style={{ margin: 0 }}>{SOCIAL.gap.body}</p>
          <span className="move"><b>Recommended move — </b>{SOCIAL.gap.move}</span>
        </div>
      </Card>
    </div>
  );
}
