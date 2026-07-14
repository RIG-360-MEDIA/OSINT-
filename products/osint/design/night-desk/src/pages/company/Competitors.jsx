/* View 4 — Competitor Watch */
import { COMPETITORS } from '../../data/windlass';
import { PageHead, Card, Pill } from './coUi';

const PRICE = ['', 'Budget', 'Budget–mid', 'Mid–premium', 'Premium'];

export default function Competitors() {
  const items = [...COMPETITORS.items].sort((a, b) => b.contracts - a.contracts);
  return (
    <div className="co-page">
      <PageHead eyebrow="Competitor Watch" title="Who else can arm a military — and who just makes noise" sub={COMPETITORS.intro} />

      <Card className="pad0" style={{ marginBottom: 18 }}>
        <div className="co-table-wrap">
          <table className="co-table">
            <thead>
              <tr><th>Maker</th><th>Base</th><th>Price tier</th><th>Govt / ceremonial strength</th><th>Read</th></tr>
            </thead>
            <tbody>
              {items.map((c, i) => (
                <tr key={i}>
                  <td style={{ fontWeight: 650 }}><span className="co-flag">{c.flag}</span> {c.name}</td>
                  <td style={{ color: 'var(--co-muted)' }}>{c.country}</td>
                  <td><Pill tone={c.price >= 4 ? 'info' : c.price >= 3 ? 'flat' : 'warn'}>{PRICE[c.price]}</Pill></td>
                  <td style={{ minWidth: 150 }}>
                    <div className="co-flex" style={{ gap: 8 }}>
                      <div className={'co-score ' + (c.contracts >= 70 ? '' : 'warn')} style={{ flex: 1 }}><i style={{ width: `${c.contracts}%` }} /></div>
                      <span className="co-mono co-tnum" style={{ fontSize: 12.5, width: 24 }}>{c.contracts}</span>
                    </div>
                  </td>
                  <td style={{ fontSize: 13, color: 'var(--co-ink-2)', maxWidth: 320, lineHeight: 1.45 }}>{c.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="co-grid co-g2">
        {items.filter((c) => c.tone === 'risk').map((c, i) => (
          <Card key={i} title={c.name} icon="⚔" x={c.country}>
            <div className="co-brief"><p style={{ margin: 0 }}>{c.threat}</p></div>
          </Card>
        ))}
      </div>
      <Card title="The bottom line on competition" style={{ marginTop: 18 }}>
        <div className="co-brief">
          <p style={{ margin: 0 }}>
            Only <b>two</b> makers actually threaten Windlass on tenders: <b>Pooley Sword</b> (the British price-and-continuity rival for the UK contract) and <b>WKC of Solingen</b> (the premium ceremonial benchmark). Everyone else — Cold Steel, Hanwei, Albion — competes for collectors and social attention, not contracts. And one supposed heavyweight, <b>Wilkinson Sword</b>, no longer makes swords at all; it’s a razor brand now. Windlass even <b>owns</b> one name on this list (Marto/Bermejo of Toledo), which is better used as its European face than treated as a rival.
          </p>
          <span className="move"><b>Recommended move — </b>Concentrate competitive energy on exactly two fronts: out-price Pooley on the UK contract via the Borehamwood entity, and out-value WKC everywhere ceremonial. Ignore the collector-brand noise on the tender field, and put Marto’s Toledo name to work opening the NATO-new markets.</span>
        </div>
      </Card>
    </div>
  );
}
