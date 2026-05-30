'use client';
import { useEffect, useState } from 'react';
import { authFetch } from '../lib/supabase';

/**
 * Block 2 — CM Perspective. Replaces the old mock "Overnight Summary" + fake
 * pull-quote. Left: a real written read of how the principal is being covered.
 * Right: "Needs Your Attention" — real opposition attacks + risk coverage.
 */

const DOT = { critical: '#fb7185', high: '#f59e0b', moderate: '#e9c46a', low: '#5b6b7a' };

export function CMPerspective() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let cancelled = false;
    authFetch('/api/brief/cm_perspective')
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setErr(String(e?.message || e)); });
    return () => { cancelled = true; };
  }, []);

  if (err) {
    return (
      <div className="mood-body">
        <div className="synthesis"><p className="exec-err">Couldn&apos;t load coverage — {err}</p></div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="mood-body">
        <div className="synthesis">
          <div className="synth-label">Compiling coverage…</div>
          <div className="exec-skeleton"><span /><span /><span /></div>
        </div>
      </div>
    );
  }

  const att = data.needs_attention || [];
  return (
    <div className="mood-body">
      <div className="synthesis">
        <div className="synth-label">{data.subject ? `On Your Watch — ${data.subject}` : 'On Your Watch'}</div>
        {data.posture ? <p className="cmp-posture">{data.posture}.</p> : null}
        <ul className="cmp-digest">
          {(data.digest || []).map((d, i) => (
            <li key={i} className={`cmp-row ${d.camp || ''}`} style={{ animationDelay: `${i * 70}ms` }}>
              <span className="cmp-entity">
                {d.entity}{d.camp === 'opposition' ? <em className="cmp-opp"> · opposition</em> : null}
              </span>
              <span className="cmp-head">{d.headline}</span>
              <span className="cmp-more">{d.count > 1 ? `+${d.count - 1} more · ` : ''}{d.outlets}</span>
            </li>
          ))}
        </ul>
      </div>

      <aside className="needs-attention">
        <div className="na-label"><span className="na-pulse" aria-hidden="true" />Needs Your Attention</div>
        {att.length === 0 ? (
          <p className="na-empty">Nothing pressing — no attacks or risk items on your watch in this window.</p>
        ) : (
          <ul>
            {att.map((a, i) => (
              <li key={a.cluster_id || i} className={`na-item ${a.kind}`} style={{ animationDelay: `${i * 90}ms` }}>
                <span className="na-dot" style={{ background: DOT[a.severity] || DOT.moderate }} aria-hidden="true" />
                <div className="na-body">
                  <p className="na-head">{a.headline}</p>
                  <div className="na-meta">
                    <span className={`na-tag ${a.kind}`}>
                      {a.kind === 'opposition' ? `attack · ${a.matched}` : (a.matched || 'risk')}
                    </span>
                    {a.outlets ? <span className="na-src">· {a.outlets}</span> : null}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  );
}
