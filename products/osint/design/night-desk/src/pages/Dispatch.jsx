import { Reveal, Magnetic } from '../lib/ui';
import Panel from '../components/Panel';
import ReportDispatch from '../components/ReportDispatch';
import { CHANNELS, SCHEDULE, RECIPIENTS, QA, ARCHIVE } from '../data/dispatch';
import { SUBJECT } from '../data/persona';
import { BLUF } from '../data/home';

export default function Dispatch() {
  return (
    <div className="page stack">
      <Reveal>
        <div className="eyebrow">REPORTS &amp; DELIVERY</div>
        <h1 className="h-sec" style={{ marginTop: 6 }}>Dispatch</h1>
        <div className="sub">Compose, verify, schedule, and ship the briefing — Gmail, PDF, newsletter, or MCP.</div>
      </Reveal>

      <Reveal><ReportDispatch /></Reveal>

      <div className="disp-grid">
        <Reveal><Panel label="Briefing Preview · One-Pager">
          <div className="paper-preview">
            <div className="eyebrow">NIGHT DESK · SITUATION BRIEF</div>
            <h2 className="subject" style={{ fontSize: '2.4rem', marginTop: 8 }}>{SUBJECT.first} <em>{SUBJECT.last}</em></h2>
            <div className="subline"><span>{SUBJECT.role} {SUBJECT.person} · {SUBJECT.state}</span><span className="sep" /><span className="mono">{SUBJECT.asOf}</span></div>
            <div className="rule-orn" style={{ marginTop: 14 }}>◆</div>
            <p className="bluf" style={{ fontSize: '1rem', marginTop: 14 }}>{BLUF}</p>
            <p className="sub" style={{ marginTop: 16 }}>+ 3 findings · Narrative DNA · Target Heat · Counter-narrative · full analytics appendix</p>
          </div>
        </Panel></Reveal>

        <Reveal delay={0.06} className="stack" style={{ '--mt': '16px' }}>
          <Panel label="Channels">
            {CHANNELS.map((c) => (
              <div className="channel" key={c.name}>
                <span className="ci" style={{ fontSize: '1.1rem' }}>{c.ic}</span>
                <div className="meta"><b>{c.name}</b><span>{c.desc}</span></div>
                <span className={'conf ' + (c.state === 'connected' ? 'high' : c.state === 'beta' ? 'medium' : '')}>{c.state}</span>
              </div>
            ))}
          </Panel>

          <Panel label="Schedule &amp; Recipients" className="flat">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div><div className="mono" style={{ fontSize: '0.55rem', color: 'var(--muted)', letterSpacing: '0.14em' }}>CADENCE</div><div style={{ fontWeight: 600, marginTop: 4 }}>{SCHEDULE.cadence}</div></div>
              <div className="mono" style={{ fontSize: '0.7rem', color: 'var(--muted)' }}>next: {SCHEDULE.next}</div>
            </div>
            <div className="rows" style={{ marginTop: 12 }}>
              {RECIPIENTS.map((r) => (<div className="srow" key={r.addr} style={{ gridTemplateColumns: '1fr auto', padding: '7px 0' }}><span className="hd" style={{ fontWeight: 500 }}>{r.name}</span><span className="meta">{r.addr}</span></div>))}
            </div>
          </Panel>

          <Panel label="Coverage-QA Gate · pre-send">
            <div className="qa-gate" style={{ marginBottom: 12 }}>✓ Brief passes the echo-chamber / blindspot check</div>
            {QA.checks.map((c, i) => (<div key={i} style={{ display: 'flex', gap: 10, fontSize: '0.82rem', marginBottom: 8, color: c.ok ? 'var(--ink-2)' : 'var(--gold)' }}><span>{c.ok ? '✓' : '⚠'}</span><span>{c.t}</span></div>))}
          </Panel>

          <Magnetic className="btn primary">Send brief now →</Magnetic>
        </Reveal>
      </div>

      <Reveal delay={0.1}><Panel label="Brief Archive" className="archive">
        {ARCHIVE.map((a) => (<div className="ar" key={a.date}><span className="mono" style={{ color: 'var(--faint)', fontSize: '0.7rem' }}>{a.date}</span><span>{a.title}</span><span className="mono" style={{ color: 'var(--muted)' }}>opens {a.opens}</span></div>))}
      </Panel></Reveal>
    </div>
  );
}
