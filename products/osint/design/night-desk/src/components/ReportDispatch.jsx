import { useEffect, useState } from 'react';
import Panel from './Panel';
import { authFetch, getAccessToken, API_BASE } from '../lib/supabase';

// The real daily intelligence brief: live stats + download PDF + email-to-me.
export default function ReportDispatch() {
  const [r, setR] = useState(null);
  const [status, setStatus] = useState({ loading: true, error: null });
  const [busy, setBusy] = useState('');
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    let cancelled = false;
    authFetch('/api/brief/report')
      .then((d) => { if (!cancelled) { setR(d); setStatus({ loading: false, error: null }); } })
      .catch((e) => { if (!cancelled) setStatus({ loading: false, error: String(e?.message || e) }); });
    return () => { cancelled = true; };
  }, []);

  async function downloadPdf() {
    setBusy('pdf'); setMsg(null);
    try {
      const token = await getAccessToken();
      const res = await fetch(`${API_BASE}/api/brief/report.pdf`, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) throw new Error(`PDF ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `RIG-OSINT-${(r && r.state_code) || 'brief'}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e) { setMsg({ ok: false, t: `Download failed — ${e.message}` }); }
    setBusy('');
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
          <button className="btn" onClick={downloadPdf} disabled={busy} style={btn}>
            {busy === 'pdf' ? 'Preparing…' : '⤓ Download PDF'}
          </button>
          <button className="btn primary" onClick={emailMe} disabled={busy} style={{ ...btn, background: 'var(--gold)', color: '#1a1407', border: 'none' }}>
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

      <div className="sub" style={{ marginTop: 14, fontSize: '0.82rem' }}>
        Contains: executive summary · risk heatmap (6 domains) · key developments · district map ·
        sentiment &amp; narrative · early-warning · stakeholder impact · recommended actions · top stories ·
        quotes · figures · source intelligence. Generated fresh each day; emailed automatically.
      </div>
      {msg && <div style={{ marginTop: 10, fontSize: '0.82rem', color: msg.ok ? 'var(--supportive,#3cd6a0)' : 'var(--neg,#fb7185)' }}>{msg.t}</div>}
    </Panel>
  );
}

const btn = {
  padding: '9px 15px', borderRadius: 8, border: '1px solid var(--line)', background: 'transparent',
  color: 'var(--ink)', cursor: 'pointer', fontWeight: 600, fontSize: '0.82rem', whiteSpace: 'nowrap',
};
