/* View 10 — Signal Feed (unified stream, filterable) */
import { useState, useMemo } from 'react';
import { SIGNALS } from '../../data/windlass';
import { PageHead, Card, Pill } from './coUi';

const URG = { high: 'risk', med: 'warn', low: 'flat' };
const TYPES = ['All', ...Array.from(new Set(SIGNALS.map((s) => s.type)))];

export default function Signals() {
  const [type, setType] = useState('All');
  const [kind, setKind] = useState('all');
  const rows = useMemo(() => SIGNALS.filter((s) =>
    (type === 'All' || s.type === type) && (kind === 'all' || s.kind === kind)), [type, kind]);

  return (
    <div className="co-page">
      <PageHead eyebrow="Signal Feed" title="Everything, in one stream"
        sub="Every tracked signal — tenders, geopolitics, competitors, trade, brand — in the standard schema: what · where · when · opportunity or risk · how urgent · what to do. Filter to cut to what matters." />

      <div className="co-flex" style={{ gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        {TYPES.map((t) => (
          <button key={t} onClick={() => setType(t)} className={'co-chip-btn' + (type === t ? ' on' : '')}
            style={type === t ? { background: 'var(--co-accent)', color: '#fff', borderColor: 'var(--co-accent)' } : {}}>{t}</button>
        ))}
        <span style={{ width: 1, background: 'var(--co-line)', margin: '0 4px' }} />
        {['all', 'opportunity', 'risk'].map((k) => (
          <button key={k} onClick={() => setKind(k)} className={'co-chip-btn'}
            style={kind === k ? { background: k === 'risk' ? 'var(--co-risk)' : k === 'opportunity' ? 'var(--co-good)' : 'var(--co-ink)', color: '#fff', borderColor: 'transparent' } : {}}>{k}</button>
        ))}
      </div>

      <Card className="pad0">
        {rows.map((s, i) => (
          <div key={i} className="co-sig">
            <div className={'stripe ' + (s.kind === 'risk' ? 'risk' : 'good')} />
            <div className="body">
              <div className="co-flex" style={{ gap: 8, flexWrap: 'wrap' }}>
                <Pill tone="flat">{s.type}</Pill>
                <span className="hl">{s.headline}</span>
              </div>
              <div className="meta">
                <span className="co-flag">{s.flag}</span><span>{s.country}</span>
                <span>· {s.source}</span><span>· {s.date}</span>
                <Pill tone={s.kind === 'risk' ? 'risk' : 'good'}>{s.kind}</Pill>
                <Pill tone={URG[s.urgency]}>{s.urgency}</Pill>
              </div>
              <div style={{ marginTop: 8, padding: '9px 12px', background: 'var(--co-accent-t)', borderLeft: '3px solid var(--co-accent)', borderRadius: '0 8px 8px 0', fontSize: 13.5, lineHeight: 1.5, color: 'var(--co-ink)' }}>
                <b style={{ color: 'var(--co-accent-d)' }}>Action — </b>{s.action}
              </div>
            </div>
          </div>
        ))}
        {!rows.length && <div style={{ padding: 30, textAlign: 'center', color: 'var(--co-faint)' }}>No signals match this filter.</div>}
      </Card>
    </div>
  );
}
