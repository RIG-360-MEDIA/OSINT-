/* Shared corporate-theme UI atoms for Company OSINT pages. */
import { Spark } from './coCharts';

export function PageHead({ eyebrow, title }) {
  return (
    <div className="co-page-head">
      {eyebrow && <div className="co-eyebrow">{eyebrow}</div>}
      <h1 className="co-h1">{title}</h1>
    </div>
  );
}

export function Card({ title, x, icon, children, className = '', style }) {
  return (
    <section className={`co-card ${className}`} style={style}>
      {(title || x) && (
        <div className="co-card-h">
          {title && <div className="co-card-t">{icon && <span className="ic">{icon}</span>}{title}</div>}
          {x && <div className="co-card-x">{x}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Kpi({ label, value, delta, dir, spark, note }) {
  return (
    <div className="co-kpi">
      <div className="co-between" style={{ alignItems: 'flex-start' }}>
        <div>
          <div className="k">{label}</div>
          <div className="v">{value}</div>
        </div>
        {spark && <Spark data={spark} color={dir === 'down' ? 'risk' : 'good'} />}
      </div>
      {delta && (
        <div className="d">
          {dir === 'up' || dir === 'down'
            ? <span className={dir === 'down' ? 'dn' : 'up'}>{dir === 'down' ? '▾' : '▴'} {delta}</span>
            : <span style={{ color: 'var(--co-muted)' }}>{delta}</span>}
        </div>
      )}
      {note && <div style={{ fontSize: 13.5, color: 'var(--co-ink-2)', marginTop: 10, lineHeight: 1.55 }}>{note}</div>}
    </div>
  );
}

const TONE = { good: 'good', warn: 'warn', risk: 'risk', flat: 'flat', info: 'info', you: 'info', rival: 'warn' };
export function Pill({ tone = 'flat', children }) {
  return <span className={`co-pill ${TONE[tone] || 'flat'}`}>{children}</span>;
}

/* strategist brief: detailed prose + a clear recommended move */
export function Brief({ children, move }) {
  return (
    <div className="co-brief">
      <p style={{ margin: 0 }}>{children}</p>
      {move && <span className="move"><b>Recommended move — </b>{move}</span>}
    </div>
  );
}

export function Unconfirmed() {
  return <span className="co-pill flat" title="Not confirmed from a primary source" style={{ opacity: .8 }}>UNCONFIRMED</span>;
}
