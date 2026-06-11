'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { supabase } from '../../lib/supabase';
import '../auth.css';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setError(null);
    const { error: err } = await supabase.auth.signInWithPassword({ email, password });
    setBusy(false);
    if (err) { setError(err.message); return; }
    const next = typeof window !== 'undefined'
      ? new URLSearchParams(window.location.search).get('next') || '/brief'
      : '/brief';
    router.push(next);
  }

  return (
    <main className="auth-shell">
      <div className="auth-card">
        <h1>Sign in</h1>
        <p>RIG OSINT Morning Brief.</p>
        <form onSubmit={submit}>
          <label>Email
            <input type="email" required value={email} onChange={e => setEmail(e.target.value)} />
          </label>
          <label>Password
            <input type="password" required value={password} onChange={e => setPassword(e.target.value)} />
          </label>
          <button disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
          {error && <p className="auth-error">{error}</p>}
        </form>
        <p className="auth-hint">Access is invite-only. Contact RIG 360 Media for an invite.</p>
      </div>
    </main>
  );
}
