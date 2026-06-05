import { Reveal } from '../lib/ui';
import Panel from '../components/Panel';
import ReportDispatch from '../components/ReportDispatch';
import { QA, ARCHIVE } from '../data/dispatch';

export default function Dispatch() {
  return (
    <div className="page stack">
      <Reveal>
        <div className="eyebrow">REPORTS &amp; DELIVERY</div>
        <h1 className="h-sec" style={{ marginTop: 6 }}>Dispatch</h1>
        <div className="sub">Compose, verify, and ship the daily intelligence brief — PDF or Gmail.</div>
      </Reveal>

      <Reveal><ReportDispatch /></Reveal>

      <Reveal delay={0.06}><Panel label="Coverage-QA Gate · pre-send">
        <div className="qa-gate" style={{ marginBottom: 12 }}>✓ Brief passes the echo-chamber / blindspot check</div>
        {QA.checks.map((c, i) => (
          <div key={i} style={{ display: 'flex', gap: 10, fontSize: '0.82rem', marginBottom: 8, color: c.ok ? 'var(--ink-2)' : 'var(--gold)' }}>
            <span>{c.ok ? '✓' : '⚠'}</span><span>{c.t}</span>
          </div>
        ))}
      </Panel></Reveal>

      <Reveal delay={0.1}><Panel label="Brief Archive" className="archive">
        {ARCHIVE.map((a) => (
          <div className="ar" key={a.date}>
            <span className="mono" style={{ color: 'var(--faint)', fontSize: '0.7rem' }}>{a.date}</span>
            <span>{a.title}</span>
            <span className="mono" style={{ color: 'var(--muted)' }}>opens {a.opens}</span>
          </div>
        ))}
      </Panel></Reveal>
    </div>
  );
}
