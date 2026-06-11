'use client';
import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { supabase, API_BASE } from '../../lib/supabase';
import '../auth.css';

function SignupContent() {
  const router = useRouter();
  const params = useSearchParams();
  const inviteToken = params.get('invite');

  const [peek, setPeek] = useState(null);
  const [peekError, setPeekError] = useState(null);
  const [fullName, setFullName] = useState('');
  const [designation, setDesignation] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPwd, setConfirmPwd] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!inviteToken) { setPeekError('Missing invite token in the URL.'); return; }
    fetch(`${API_BASE}/api/onboarding/invite/${inviteToken}`)
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
        return data;
      })
      .then(setPeek)
      .catch((e) => setPeekError(String(e.message || e)));
  }, [inviteToken]);

  async function submit(e) {
    e.preventDefault();
    setError(null);
    if (password.length < 8) { setError('Password must be at least 8 characters.'); return; }
    if (password !== confirmPwd) { setError('Passwords do not match.'); return; }
    if (!fullName.trim()) { setError('Full name is required.'); return; }

    setBusy(true);
    try {
      const r = await fetch(`${API_BASE}/api/onboarding/accept`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          invite_token: inviteToken,
          password,
          full_name: fullName.trim(),
          designation: designation.trim() || null,
        }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);

      // Set Supabase session so subsequent /api/me calls see the user.
      const { error: sessErr } = await supabase.auth.setSession({
        access_token: data.session.access_token,
        refresh_token: data.session.refresh_token,
      });
      if (sessErr) throw sessErr;

      router.push('/onboarding');
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  if (peekError) {
    return (
      <main className="auth-shell">
        <div className="auth-card">
          <h1>Invite problem</h1>
          <p className="auth-error">{peekError}</p>
          <p className="auth-hint">If the link is old, ask RIG 360 Media for a fresh one.</p>
        </div>
      </main>
    );
  }
  if (!peek) {
    return (
      <main className="auth-shell">
        <div className="auth-card"><h1>Loading invite…</h1></div>
      </main>
    );
  }

  return (
    <main className="auth-shell">
      <div className="auth-card">
        <h1>Welcome to RIG OSINT</h1>
        <p>You've been invited as <strong>{peek.role_template}</strong> for <strong>{peek.org_name}</strong> ({peek.email}). Set a password to continue.</p>
        <form onSubmit={submit}>
          <label>Full name
            <input required value={fullName} onChange={e => setFullName(e.target.value)} />
          </label>
          <label>Designation (optional)
            <input value={designation} onChange={e => setDesignation(e.target.value)} placeholder="Senior Analyst, Telangana CMO" />
          </label>
          <label>Password
            <input type="password" required value={password} onChange={e => setPassword(e.target.value)} />
          </label>
          <label>Confirm password
            <input type="password" required value={confirmPwd} onChange={e => setConfirmPwd(e.target.value)} />
          </label>
          <button disabled={busy}>{busy ? 'Creating account…' : 'Create account & start onboarding'}</button>
          {error && <p className="auth-error">{error}</p>}
        </form>
      </div>
    </main>
  );
}

export default function SignupPage() {
  return (
    <Suspense fallback={<main className="auth-shell"><div className="auth-card"><h1>Loading…</h1></div></main>}>
      <SignupContent />
    </Suspense>
  );
}
