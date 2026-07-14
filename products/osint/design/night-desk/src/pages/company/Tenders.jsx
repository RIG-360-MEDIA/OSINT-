/* View 2 — Tender Intelligence (the priority view) */
import { TENDERS } from '../../data/windlass';
import { PageHead, Card, Pill, Unconfirmed } from './coUi';

const URG = { high: 'risk', med: 'warn', low: 'flat' };

function Tender({ t }) {
  return (
    <div className="co-tender">
      <div className="co-flex" style={{ justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
        <div className="tt">{t.title}</div>
        <span className="co-flag">{t.flag}</span>
      </div>
      <div className="mt">
        <Pill tone={URG[t.urgency]}>{t.urgency} priority</Pill>
        <span>· {t.portal}</span>
        <span>· {t.value}</span>
        {!t.verified && <Unconfirmed />}
      </div>
      <p style={{ fontSize: 13.5, lineHeight: 1.55, color: 'var(--co-ink-2)', margin: '10px 0 0' }}>{t.read}</p>
      <div style={{ marginTop: 8, fontSize: 12.5, color: 'var(--co-faint)' }}>◷ {t.deadline}</div>
    </div>
  );
}

export default function Tenders() {
  return (
    <div className="co-page">
      <PageHead eyebrow="Tender Intelligence · priority" title="Government sword & edged-weapon opportunities"
        sub={TENDERS.intro} />

      {/* Honesty banner — no live public tender confirmed open today */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', padding: '12px 16px', marginBottom: 20,
        background: 'var(--co-warn-t)', border: '1px solid var(--co-line)', borderRadius: 12 }}>
        <span style={{ fontSize: 16 }}>⚠️</span>
        <div style={{ fontSize: 13.5, lineHeight: 1.5, color: 'var(--co-ink-2)' }}>{TENDERS.asOf}</div>
      </div>

      <div className="co-board" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))' }}>
        {TENDERS.pipeline.map((col, i) => (
          <div className="co-col" key={i}>
            <div className="co-col-h">
              <span>{col.stage}</span>
              <span className="co-pill flat">{col.items.length}</span>
            </div>
            {col.items.map((t, j) => <Tender key={j} t={t} />)}
          </div>
        ))}
      </div>

      {/* Where these deals actually get made */}
      <Card title="Where these deals actually get made" icon="◈" x="verified expo dates" style={{ marginTop: 18 }}>
        <p style={{ fontSize: 14, lineHeight: 1.55, color: 'var(--co-ink-2)', margin: '0 0 14px' }}>
          Ceremonial and presentation swords are won through relationships, not portals — so the highest-value action isn’t bidding, it’s being in the room. These are the events where the buyers are:
        </p>
        <div className="co-grid co-g3">
          {TENDERS.expos.map((e, i) => (
            <div key={i} style={{ border: '1px solid var(--co-line)', borderRadius: 12, padding: 15, background: 'var(--co-panel-2)' }}>
              <div className="co-between" style={{ marginBottom: 4 }}>
                <b style={{ fontSize: 14.5 }}>{e.name}</b>
                {!e.verified && <Unconfirmed />}
              </div>
              <div className="co-mono" style={{ fontSize: 12.5, color: 'var(--co-accent-d)', marginBottom: 8 }}>{e.when} · {e.where}</div>
              <p style={{ fontSize: 13.5, lineHeight: 1.5, color: 'var(--co-ink-2)', margin: 0 }}>{e.why}</p>
            </div>
          ))}
        </div>
      </Card>

      <div className="co-grid co-g-2-1" style={{ marginTop: 18 }}>
        <Card title="How Britain actually decides — and why Windlass should defend, not chase" icon="⚑">
          <div className="co-brief">
            <p style={{ margin: 0 }}>
              Across the real record, Britain settles its all-forces sword supply on <b>cost plus continuity of delivery</b> — not on craftsmanship, where German houses like WKC already win the top end. Windlass already makes every British regimental pattern at volume, so it meets the authenticity bar and undercuts a small British workshop. It is now the <b>incumbent</b>, not the challenger: the last independent maker to hold this work, Pooley Sword, stepped back around 2018 rather than keep re-tendering against low-cost imports. The risk is complacency — a revived Pooley or a WKC bid could try to prise the contract back open on a "made-in-Britain" argument, which is exactly what Windlass’s UK (Borehamwood) entity exists to neutralise.
            </p>
            <span className="move"><b>Recommended move — </b>Defend the incumbency like a live campaign: keep delivery performance and fresh pattern samples in front of the MoD, hold a credible UK-delivery record through Borehamwood, and monitor Find-a-Tender and the Defence Sourcing Portal so any re-compete is spotted the day it publishes.</span>
          </div>
        </Card>
        <Card title="Portals monitored in production" icon="▤" x="live feed">
          <p style={{ fontSize: 13.5, lineHeight: 1.55, color: 'var(--co-ink-2)', margin: '0 0 12px' }}>
            In the live product these are polled continuously for any open sword / kukri / edged-weapon solicitation. Here they’re listed for reference — and as of today none shows a confirmable open bid.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {TENDERS.portals.map((p, i) => (
              <div key={i} className="co-flex" style={{ gap: 9, fontSize: 13.5 }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--co-faint)', flex: 'none' }} />
                {p}
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
