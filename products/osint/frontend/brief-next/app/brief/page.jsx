'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Providers } from '../providers.jsx';
import App from '../../components/app.jsx';
import { useMe } from '../../lib/useMe';
import '../auth.css';

/**
 * /brief — the actual Morning Brief.
 * Auth-gated: anonymous → /login?next=/brief; pre-onboarded → /onboarding.
 * If the backend's /api/me fails (backend down), we still render the brief
 * so the user isn't blocked — boss's design falls back to mock data anyway.
 */
export default function BriefPage() {
  const router = useRouter();
  const { loading, me, error } = useMe();

  useEffect(() => {
    if (loading) return;
    if (error) return; // backend unreachable — render anyway
    if (!me) { router.push('/login?next=/brief'); return; }
    if (!me.onboarded) { router.push('/onboarding'); return; }
  }, [loading, me, error, router]);

  if (loading) {
    return (
      <main className="auth-shell">
        <div className="auth-card"><h1>Loading…</h1></div>
      </main>
    );
  }
  if (!me && !error) {
    return (
      <main className="auth-shell">
        <div className="auth-card"><h1>Redirecting to sign-in…</h1></div>
      </main>
    );
  }

  return (
    <Providers>
      <App />
    </Providers>
  );
}
