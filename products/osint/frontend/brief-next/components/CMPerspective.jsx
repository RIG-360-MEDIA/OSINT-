'use client';
import { useEffect, useState } from 'react';
import { authFetch } from '../lib/supabase';

/**
 * CM Perspective — the full, consolidated view of how the principal is being
 * covered and what it means. All real data + a grounded LLM strategic read:
 *   - Narrative balance (real coverage-volume split: govt vs opposition driven)
 *   - Strategic Read (LLM deep analysis) + recommended actions
 *   - This week's coverage (LLM prose summary)
 *   - Opposition fronts active
 *   - Needs Your Attention (response-worthy items)
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
      <section className="container section cm-section">
        <p className="cmx-state">Couldn&apos;t load your perspective — {err}</p>
      </section>
    );
  }
  if (!data) {
    return (
      <section className="container section cm-section">
        <div className="cmx-state">Compiling your perspective…</div>
      </section>
    );
  }

  const subj = data.subject || 'Your Principal';
  const nb = data.narrative_balance || {};
  const da = data.deep_analysis;
  const att = data.needs_attention || [];
  const fronts = data.opposition_fronts || [];

  return (
    <section className="container section cm-section">
      <header className="cmx-header">
        <div>
          <h2 className="cmx-title">CM Perspective — {subj}</h2>
          <p className="cmx-sub">How your principal is being covered — and what it means.</p>
        </div>
        <aside className="cmx-header-quote">
          <span className="cmx-q" aria-hidden="true">&ldquo;</span>
          <p>Power is not only what is held, but what is perceived.</p>
          <span className="cmx-q-attr">— RIG Intelligence Desk</span>
        </aside>
      </header>

      {nb.total ? (
        <div className="cmx-balance">
          <div className="cmx-bal-bar" title={`${nb.govt_pct}% government-driven · ${nb.attack_pct}% opposition-driven`}>
            <span className="cmx-bal-govt" style={{ width: `${nb.govt_pct}%` }} />
            <span className="cmx-bal-opp" style={{ width: `${nb.attack_pct}%` }} />
          </div>
          <div className="cmx-bal-legend">
            <span className="govt"><i /> {nb.govt_pct}% you / government setting the narrative</span>
            <span className="opp"><i /> {nb.attack_pct}% opposition-driven</span>
          </div>
        </div>
      ) : null}

      <div className="cmx-grid">
        <div className="cmx-main">
          {da && da.read ? (
            <div className="cmx-block cmx-read-block">
              <div className="cmx-label">Strategic Read</div>
              <p className="cmx-read">{da.read}</p>
              {da.actions && da.actions.length ? (
                <>
                  <div className="cmx-label cmx-label-actions">Recommended actions</div>
                  <ul className="cmx-actions">{da.actions.map((a, i) => <li key={i}>{a}</li>)}</ul>
                </>
              ) : null}
            </div>
          ) : null}

          {data.summary ? (
            <div className="cmx-block">
              <div className="cmx-label">This Week&apos;s Coverage</div>
              <p className="cmx-summary">{data.summary}</p>
            </div>
          ) : null}

          {fronts.length ? (
            <div className="cmx-fronts">
              <span className="cmx-fronts-lbl">Opposition active —</span>
              {fronts.map((f, i) => <span key={i} className="cmx-front-chip">{f}</span>)}
            </div>
          ) : null}
        </div>

        <aside className="cmx-attention">
          <div className="cmx-att-label"><span className="na-pulse" aria-hidden="true" />Needs Your Attention</div>
          {att.length === 0 ? (
            <p className="cmx-att-empty">Nothing pressing — no attacks or risk items on your watch in this window.</p>
          ) : (
            <ul>
              {att.map((a, i) => (
                <li key={a.cluster_id || i} className={`cmx-att-item ${a.kind}`} style={{ animationDelay: `${i * 80}ms` }}>
                  <span className="cmx-att-dot" style={{ background: DOT[a.severity] || DOT.moderate }} aria-hidden="true" />
                  <div className="cmx-att-body">
                    <p className="cmx-att-head">{a.headline}</p>
                    <span className="cmx-att-meta">
                      {a.kind === 'opposition' ? `attack · ${a.matched}` : (a.matched || 'risk')}
                      {a.outlets ? ` · ${a.outlets}` : ''}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
    </section>
  );
}
