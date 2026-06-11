import { useEffect, useRef, useState } from 'react';
import Panel from './Panel';
import { authFetch, getAccessToken, API_BASE } from '../lib/supabase';

// The real daily intelligence brief: live stats + INLINE PDF viewer + email-to-me.
// The PDF endpoint (/api/brief/report.pdf) is auth-gated (401 without a bearer
// token), so a plain <iframe src> cannot load it — we fetch it as a blob with the
// Supabase token and render an object URL. The same object URL powers Download.
export default function ReportDispatch() {
  const [r, setR] = useState(null);
  const [status, setStatus] = useState({ loading: true, error: null });
  const [pdf, setPdf] = useState({ url: null, loading: true, error: null });
  const [busy, setBusy] = useState('');
  const [msg, setMsg] = useState(null);
  const pdfUrlRef = useRef(null);

  // Live stats (header KPIs).
  useEffect(() => {
    let cancelled = false;
    authFetch('/api/brief/report')
      .then((d) => { if (!cancelled) { setR(d); setStatus({ loading: false, error: null }); } })
      .catch((e) => { if (!cancelled) setStatus({ loading: false, error: String(e?.message || e) }); });
    return () => { cancelled = true; };
  }, []);

  // Fetch the PDF as a blob (auth header required) and hold an object URL.
  useEffect(() => {
    let cancelled = false;
    setPdf({ url: null, loading: true, error: null });
    (async () => {
      try {
        const token = await getAccessToken();
        if (!token) throw new Error('Not signed in');
        const res = await fetch(`${API_BASE}/api/brief/report.pdf`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error(`PDF ${res.status}`);
        const blob = await res.blob();
        if (cancelled) return;
        const url = URL.createObjectURL(blob);
        pdfUrlRef.current = url;
        setPdf({ url, loading: false, error: null });
      } catch (e) {
        if (!cancelled) setPdf({ url: null, loading: false, error: String(e?.message || e) });
      }
    })();
    return () => {
      cancelled = true;
      if (pdfUrlRef.current) { URL.revokeObjectURL(pdfUrlRef.current); pdfUrlRef.current = null; }
    };
  }, []);

  function downloadPdf() {
    if (!pdf.url) return;
    const a = document.createElement('a');
    a.href = pdf.url;
    a.download = `daily-brief-${(r && r.state_code) || 'osint'}.pdf`;
    document.body.appendChild(a); a.click(); a.remove();
  }

  async function emailMe() {
    setBusy('email'); setMsg(null);
    try {
      const res = await authFetch('/api/brief/report/send', { method: 'POST' });
      setMsg({ ok: true, t: `Sent to ${res.to}` });
    } catch (e) { setMsg({ ok: false, t: `Send failed — ${String(e?.message || e)}` }); }
    setBusy('');
  }

  if (status.loading) return <Panel label="Daily Intelligence Brief"><div className="sub">Assembling today's brief…</div></Panel>;
  if (status.error) return <Panel label="Daily Intelligence Brief"><div className="sub">Couldn’t build the brief — {status.error}</div></Panel>;

  const k = r.kpis;
  const sevCount = (r.domains || []).reduce((a, d) => { a[d.severity] = (a[d.severity] || 0) + 1; return a; }, {});
  return (
    <Panel label="Daily Intelligence Brief · PDF">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <div className="eyebrow" style={{ color: 'var(--gold)' }}>RIG OSINT · DAILY STATE BRIEF</div>
          <h2 className="h-sec" style={{ margin: '4px 0' }}>{r.state} — Situation Snapshot</h2>
          <div className="sub">{r.principal} desk · 24-hour window · confidence {r.confidence}</div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn" onClick={downloadPdf} disabled={!pdf.url} style={btn}>
            ⤓ Download PDF
          </button>
          <button className="btn primary" onClick={emailMe} disabled={busy === 'email'} style={{ ...btn, background: 'var(--gold)', color: '#1a1407', border: 'none' }}>
            {busy === 'email' ? 'Sending…' : '✉ Email it to me'}
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px,1fr))', gap: 10, marginTop: 16 }}>
        {[
          ['STORIES · 24H', k.n24, `${k.delta_pct >= 0 ? '▲' : '▼'} ${Math.abs(k.delta_pct)}% vs prior`],
          ['NET SENTIMENT', `${k.net_sentiment >= 0 ? '+' : ''}${k.net_sentiment}%`, `${k.pos} for · ${k.neg} against`],
          ['DISTRICTS', k.districts_active, r.districts[0] ? `${r.districts[0].name} leads` : ''],
          ['ADVERSE SHARE', `${k.adverse_pct}%`, `${sevCount.HIGH || 0} high · ${sevCount.MODERATE || 0} mod`],
        ].map(([l, v, d]) => (
          <div key={l} style={{ background: 'var(--surface,#14110d)', border: '1px solid var(--line)', borderRadius: 10, padding: '11px 13px' }}>
            <div style={{ fontFamily: 'var(--mono)', fontSize: '0.56rem', letterSpacing: '0.1em', color: 'var(--faint)' }}>{l}</div>
            <div style={{ fontSize: '1.3rem', fontWeight: 600 }}>{v}</div>
            <div style={{ fontSize: '0.66rem', color: 'var(--faint)', marginTop: 2 }}>{d}</div>
          </div>
        ))}
      </div>

      {/* Inline PDF viewer — rendered from the auth-fetched blob object URL. */}
      <div
        style={{
          marginTop: 16, border: '1px solid var(--line)', borderRadius: 10, overflow: 'hidden',
          background: 'var(--surface,#14110d)', minHeight: '80vh',
        }}
      >
        {pdf.loading && (
          <div style={{ padding: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', height: '80vh' }}>
            <div className="sub">Generating brief…</div>
          </div>
        )}
        {!pdf.loading && pdf.error && (
          <div style={{ padding: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', height: '80vh' }}>
            <div className="sub" style={{ color: 'var(--neg,#fb7185)' }}>Couldn’t load the brief — {pdf.error}</div>
          </div>
        )}
        {!pdf.loading && !pdf.error && pdf.url && (
          <iframe
            src={pdf.url}
            title="Daily Intelligence Brief"
            style={{ width: '100%', height: '80vh', border: 'none', display: 'block' }}
          />
        )}
      </div>

      <div className="sub" style={{ marginTop: 14, fontSize: '0.82rem' }}>
        Contains: today's top stories · the big stories explained · coverage landscape ·
        mood · what's coming · the analyst's read · sources. Regenerated on demand.
      </div>
      {msg && <div style={{ marginTop: 10, fontSize: '0.82rem', color: msg.ok ? 'var(--supportive,#3cd6a0)' : 'var(--neg,#fb7185)' }}>{msg.t}</div>}
    </Panel>
  );
}

const btn = {
  padding: '9px 15px', borderRadius: 8, border: '1px solid var(--line)', background: 'transparent',
  color: 'var(--ink)', cursor: 'pointer', fontWeight: 600, fontSize: '0.82rem', whiteSpace: 'nowrap',
};
