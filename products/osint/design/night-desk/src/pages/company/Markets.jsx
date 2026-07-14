/* View 3 — Market Expansion */
import { MARKETS } from '../../data/windlass';
import { PageHead, Card, Pill } from './coUi';

const TIERS = [
  { key: 'priority', label: 'Priority — pursue now', min: 75, tone: 'good', desc: 'Budget, tradition and reach all line up.' },
  { key: 'secondary', label: 'Secondary — build next', min: 60, tone: 'warn', desc: 'Strong fit, smaller or slower to convert.' },
  { key: 'watch', label: 'Watch — opportunistic', min: 0, tone: 'flat', desc: 'Real tradition, but low budget or hard access.' },
];

export default function Markets() {
  const ranked = [...MARKETS.items].sort((a, b) => b.score - a.score);
  const tiers = TIERS.map((t, i) => ({
    ...t,
    items: ranked.filter((m) => m.score >= t.min && (i === 0 || m.score < TIERS[i - 1].min)),
  }));
  const scoreColor = (s) => (s >= 75 ? 'var(--co-good)' : s >= 60 ? 'var(--co-warn)' : 'var(--co-muted)');

  return (
    <div className="co-page">
      <PageHead eyebrow="Market Expansion" title="Where Windlass should point its sales effort next" sub={MARKETS.intro} />

      <Card title="Opportunity tiers" icon="◈" x="score = defence budget × ceremonial tradition × access" style={{ marginBottom: 18 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          {tiers.map((t) => (
            <div key={t.key}>
              <div className="co-flex" style={{ gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
                <Pill tone={t.tone}>{t.label}</Pill>
                <span style={{ fontSize: 13, color: 'var(--co-faint)' }}>{t.desc}</span>
              </div>
              <div className="co-flex" style={{ gap: 10, flexWrap: 'wrap' }}>
                {t.items.map((m, i) => (
                  <div key={i} className="co-flex" style={{ gap: 9, padding: '8px 13px', border: '1px solid var(--co-line)',
                    borderRadius: 10, background: 'var(--co-panel-2)', minWidth: 150 }}>
                    <span className="co-flag" style={{ fontSize: 17 }}>{m.flag}</span>
                    <span style={{ fontSize: 14.5, fontWeight: 600, flex: 1 }}>{m.country}</span>
                    <span className="co-mono co-tnum" style={{ fontSize: 14, fontWeight: 700, color: scoreColor(m.score) }}>{m.score}</span>
                  </div>
                ))}
                {!t.items.length && <span style={{ fontSize: 13.5, color: 'var(--co-faint)' }}>— none —</span>}
              </div>
            </div>
          ))}
        </div>
      </Card>

      <div className="co-grid co-g2">
        {ranked.map((m, i) => (
          <div className="co-mkt" key={i}>
            <div className="co-mkt-h">
              <span className="co-flag" style={{ fontSize: 20 }}>{m.flag}</span>
              <span className="nm">{m.country}</span>
              <span className="sc" style={{ color: m.score >= 75 ? 'var(--co-good)' : m.score >= 60 ? 'var(--co-warn)' : 'var(--co-muted)' }}>{m.score}</span>
            </div>
            <div className="co-flex" style={{ gap: 8, flexWrap: 'wrap' }}>
              <Pill tone={m.tone}>opportunity {m.score}</Pill>
              <span className="co-mono" style={{ fontSize: 12.5, color: 'var(--co-muted)' }}>defence ${m.budget}B · SIPRI 2025</span>
            </div>
            <div className="co-score" style={{ marginTop: 2 }}>
              <i style={{ width: `${m.score}%`, background: m.score >= 75 ? 'linear-gradient(90deg,var(--co-good),#3fb985)' : undefined }} />
            </div>
            <p style={{ fontSize: 14, lineHeight: 1.58, color: 'var(--co-ink-2)', margin: '4px 0 0' }}>{m.thesis}</p>
          </div>
        ))}
      </div>
      <p style={{ fontSize: 12.5, color: 'var(--co-faint)', marginTop: 16 }}>
        Defence budgets are real SIPRI 2025 figures. Score = analyst read on budget × ceremonial tradition × ease of access; it is a prioritisation aid, not a forecast.
      </p>
    </div>
  );
}
