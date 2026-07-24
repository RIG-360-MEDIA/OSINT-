import { useState } from 'react';
import { authFetch, getAccessToken, API_BASE } from '../lib/supabase';

// Dispatch = the rebuilt Daily Media Briefing, shown full-page.
// The report is a complete, self-contained HTML page (own masthead, KPI strip,
// sections, styling) served by the backend at /api/brief/media-briefing — so we
// simply embed it in a full-height iframe. No stale header/KPIs from the legacy
// /report JSON. Download PDF (auth-gated blob) and Email are the only actions.
export default function ReportDispatch() {
  const [busy, setBusy] = useState('');
  const [msg, setMsg] = useState(null);
  const src = `${API_BASE}/api/brief/media-briefing`;

  async function downloadPdf() {
    setBusy('pdf'); setMsg(null);
    try {
      const token = await getAccessToken();
      if (!token) throw new Error('Not signed in');
      const res = await fetch(`${API_BASE}/api/brief/report.pdf`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`PDF ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'Telangana-Media-Briefing.pdf';
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (e) {
      setMsg({ ok: false, t: `Download failed — ${String(e?.message || e)}` });
    }
    setBusy('');
  }

  async function emailMe() {
    setBusy('email'); setMsg(null);
    try {
      const res = await authFetch('/api/brief/report/send', { method: 'POST' });
      setMsg({ ok: true, t: `Sent to ${res.to}` });
    } catch (e) {
      setMsg({ ok: false, t: `Send failed — ${String(e?.message || e)}` });
    }
    setBusy('');
  }

  return (
    <div className="stack">
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, flexWrap: 'wrap' }}>
        <a className="btn" href={src} target="_blank" rel="noreferrer" style={btn}>↗ Open full page</a>
        <button className="btn" onClick={downloadPdf} disabled={busy === 'pdf'} style={btn}>
          {busy === 'pdf' ? 'Preparing…' : '⤓ Download PDF'}
        </button>
        <button className="btn primary" onClick={emailMe} disabled={busy === 'email'}
          style={{ ...btn, background: 'var(--gold)', color: '#1a1407', border: 'none' }}>
          {busy === 'email' ? 'Sending…' : '✉ Email it to me'}
        </button>
      </div>
      {msg && (
        <div style={{ fontSize: '0.82rem', color: msg.ok ? 'var(--supportive,#3cd6a0)' : 'var(--neg,#fb7185)' }}>
          {msg.t}
        </div>
      )}
      <div style={{ borderRadius: 12, overflow: 'hidden', border: '1px solid var(--line)', background: '#fff' }}>
        <iframe
          src={src}
          title="Daily Media Briefing"
          style={{ width: '100%', height: '90vh', border: 'none', display: 'block', background: '#fff' }}
        />
      </div>
    </div>
  );
}

const btn = {
  padding: '9px 15px', borderRadius: 8, border: '1px solid var(--line)', background: 'transparent',
  color: 'var(--ink)', cursor: 'pointer', fontWeight: 600, fontSize: '0.82rem',
  whiteSpace: 'nowrap', textDecoration: 'none', display: 'inline-block',
};
