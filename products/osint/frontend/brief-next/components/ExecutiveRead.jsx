'use client';
import { useEffect, useState } from 'react';
import { authFetch } from '../lib/supabase';

/**
 * Block 1 — The Executive Read.
 * Textual situation top-fold: a bottom-line-up-front line + 5-7 written
 * findings, each with a deterministic severity dot, real headline + context,
 * and source attribution. Personalized for the signed-in user (their
 * watchlist/topics/geography drive ranking server-side).
 */

const SEV_LABEL = { critical: 'Critical', high: 'High', moderate: 'Watch', low: 'Routine' };
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function fmtAsOf(iso) {
  if (!iso) return '';
  try {
    const [d, t] = iso.split('T');
    const [, m, day] = d.split('-').map(Number);
    return `${day} ${MONTHS[m - 1]} · ${(t || '').slice(0, 5)}`;
  } catch {
    return iso;
  }
}

export function ExecutiveRead() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let cancelled = false;
    authFetch('/api/brief/executive')
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setErr(String(e?.message || e)); });
    return () => { cancelled = true; };
  }, []);

  if (err) {
    return (
      <section className="exec-read exec-state">
        <p className="exec-err">Couldn&apos;t load the situation read — {err}</p>
      </section>
    );
  }

  if (!data) {
    return (
      <section className="exec-read exec-state" aria-busy="true">
        <div className="exec-eyebrow"><span className="exec-pulse" aria-hidden="true" />Compiling situation read…</div>
        <div className="exec-skeleton"><span /><span /><span /></div>
      </section>
    );
  }

  const findings = data.findings || [];
  return (
    <section className="exec-read">
      <div className="exec-head">
        <div className="exec-eyebrow">
          <span className="exec-pulse" aria-hidden="true" />
          Executive Read{data.personalized ? ' · personalized' : ''}
        </div>
        <div className="exec-asof">as of {fmtAsOf(data.as_of)}</div>
      </div>

      <p className="exec-bluf">{data.bluf}</p>

      <ol className="exec-findings">
        {findings.map((f, i) => (
          <li
            key={f.cluster_id || i}
            className={`exec-finding sev-${f.severity}`}
            style={{ animationDelay: `${i * 70}ms` }}
          >
            <span className={`exec-dot sev-${f.severity}`} title={SEV_LABEL[f.severity] || ''} aria-hidden="true" />
            <div className="exec-finding-body">
              <p className="exec-finding-head">{f.headline}</p>
              {f.context ? <p className="exec-finding-ctx">{f.context}</p> : null}
              <div className="exec-finding-meta">
                {f.topic ? <span className="exec-tag">{f.topic}</span> : null}
                <span>{f.sources} {f.sources === 1 ? 'source' : 'sources'}</span>
                {f.outlets ? <span className="exec-outlets">· {f.outlets}</span> : null}
                {f.vs ? <span className={`exec-vs ${f.vs.startsWith('+') ? 'up' : ''}`}>· {f.vs}</span> : null}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
