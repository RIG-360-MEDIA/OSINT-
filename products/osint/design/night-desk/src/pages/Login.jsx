import { useState } from 'react';
import { supabase } from '../lib/supabase';

// Minimal, on-brand sign-in. On success, supabase persists the session and
// useMe()'s onAuthStateChange re-runs → the app shell renders. No redirect needed.
export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
      if (error) setError(error.message || 'Sign-in failed');
      // success → onAuthStateChange in useMe re-loads /api/me and the gate swaps in the app
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setBusy(false);
    }
  }

  const field = {
    width: '100%', padding: '12px 14px', marginTop: 8, borderRadius: 8,
    background: 'var(--surface, #14110d)', color: 'var(--ink, #f8f5ef)',
    border: '1px solid var(--line, rgba(255,255,255,.12))', fontSize: '0.95rem', outline: 'none',
  };

  return (
    <main style={{
      minHeight: '100vh', display: 'grid', placeItems: 'center',
      background: 'var(--void, #07060a)', color: 'var(--ink, #f8f5ef)', padding: 24,
    }}>
      <form onSubmit={submit} style={{
        width: 'min(380px, 92vw)', padding: 32, borderRadius: 14,
        background: 'var(--void-2, #0b0a10)', border: '1px solid var(--line, rgba(255,255,255,.12))',
        boxShadow: '0 30px 80px rgba(0,0,0,.55)',
      }}>
        <div className="mono" style={{ letterSpacing: '0.34em', fontSize: '0.66rem', color: 'var(--faint, #8a8577)' }}>RIG · OSINT</div>
        <h1 style={{ fontSize: '1.6rem', margin: '10px 0 4px', fontWeight: 600 }}>Night Desk</h1>
        <p style={{ color: 'var(--faint, #8a8577)', fontSize: '0.85rem', marginBottom: 22 }}>Sign in to your situation brief.</p>

        <label className="mono" style={{ fontSize: '0.62rem', letterSpacing: '0.2em', color: 'var(--faint, #8a8577)' }}>EMAIL</label>
        <input style={field} type="email" autoComplete="email" value={email}
               onChange={(e) => setEmail(e.target.value)} required />

        <label className="mono" style={{ fontSize: '0.62rem', letterSpacing: '0.2em', color: 'var(--faint, #8a8577)', display: 'block', marginTop: 16 }}>PASSWORD</label>
        <input style={field} type="password" autoComplete="current-password" value={password}
               onChange={(e) => setPassword(e.target.value)} required />

        <button type="submit" disabled={busy} style={{
          width: '100%', marginTop: 24, padding: '12px 14px', borderRadius: 8, border: 'none',
          background: 'var(--gold, #e9c46a)', color: '#1a1407', fontWeight: 600, fontSize: '0.95rem',
          cursor: busy ? 'default' : 'pointer', opacity: busy ? 0.7 : 1,
        }}>{busy ? 'Signing in…' : 'Sign in'}</button>

        {error && <p style={{ color: 'var(--neg, #fb7185)', fontSize: '0.82rem', marginTop: 14 }}>{error}</p>}
      </form>
    </main>
  );
}
