/* View 9 — Room to Grow (B2C / collector / entertainment) */
import { GROW } from '../../data/windlass';
import { PageHead, Card, Pill } from './coUi';

const SIZE = { High: 'good', Med: 'warn', Low: 'flat' };

export default function Grow() {
  return (
    <div className="co-page">
      <PageHead eyebrow="Room to Grow · secondary" title="The consumer upside most defence firms never get" sub={GROW.intro} />

      <div className="co-grid co-g2" style={{ marginBottom: 18 }}>
        {GROW.openings.map((o, i) => (
          <Card key={i} title={o.name} icon="◰">
            <div className="co-flex" style={{ gap: 8, marginBottom: 10 }}>
              <Pill tone={SIZE[o.size]}>upside {o.size}</Pill>
              <Pill tone="flat">effort {o.effort}</Pill>
            </div>
            <p style={{ fontSize: 14, lineHeight: 1.58, color: 'var(--co-ink-2)', margin: 0 }}>{o.body}</p>
          </Card>
        ))}
      </div>

      <Card title="Keeping the lane in its place" icon="⚑">
        <div className="co-brief">
          <p style={{ margin: 0 }}>Military swords remain the core and the priority. But Windlass already owns the factory, the film credits and two collector brands — so the consumer upside costs almost nothing to switch on. The trap is letting it distract from tenders; the discipline is funding it from marketing, not from the sales effort aimed at governments.</p>
          <span className="move"><b>Recommended move — </b>{GROW.move}</span>
        </div>
        <p style={{ fontSize: 12.5, color: 'var(--co-faint)', marginTop: 12 }}>{GROW.marketNote}</p>
      </Card>
    </div>
  );
}
