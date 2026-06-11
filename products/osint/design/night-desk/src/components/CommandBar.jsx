import { useEffect, useRef, useState } from 'react';
import { Magnetic } from '../lib/ui';
import { getAccessToken, API_BASE } from '../lib/supabase';

export default function CommandBar({ theme = 'dark', onToggle }) {
  const [busy, setBusy] = useState(false);
  const urlRef = useRef(null);

  // Revoke any outstanding object URL on unmount.
  useEffect(() => () => {
    if (urlRef.current) { URL.revokeObjectURL(urlRef.current); urlRef.current = null; }
  }, []);

  // Fetch the auth-gated brief PDF as a blob and trigger a download.
  async function exportPdf() {
    if (busy) return;
    setBusy(true);
    try {
      const token = await getAccessToken();
      if (!token) throw new Error('Not signed in');
      const res = await fetch(`${API_BASE}/api/brief/report.pdf`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`PDF ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      urlRef.current = url;
      const a = document.createElement('a');
      a.href = url;
      a.download = 'daily-brief.pdf';
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      urlRef.current = null;
    } catch (e) {
      // Surface failures without crashing the top bar.
      console.error('Export failed', e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <header className="cmd">
      <span className="clock" style={{ marginLeft: 'auto' }}>21:22 · ENG IN</span>
      <button className="btn iconbtn" onClick={onToggle} title="Toggle light / dark" aria-label="Toggle theme">{theme === 'dark' ? '☀' : '☾'}</button>
      <Magnetic className="btn" onClick={exportPdf}>
        {busy ? 'Preparing…' : 'Export'}
      </Magnetic>
    </header>
  );
}
