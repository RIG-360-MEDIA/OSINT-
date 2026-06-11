'use client';
import Link from 'next/link';
import { useMe } from '../lib/useMe';
import './auth.css';

/**
 * / — landing page.
 * Anonymous users see "Sign in"; authenticated users see "Open my brief →".
 * Access is invite-only — no public signup link exposed here.
 */
export default function LandingPage() {
  const { loading, me } = useMe();

  return (
    <main className="landing-shell">
      <div className="landing-inner">
        <h1 className="landing-mark">RIG <span>OSINT</span></h1>
        <p className="landing-tagline">Daily intelligence brief for government, PR, and analyst teams.</p>
        <p className="landing-sub">
          Invite-only access. Real-time political, narrative, and event-cluster
          intelligence across India and beyond — curated to your watchlist.
        </p>
        <div className="landing-cta">
          {loading ? (
            <span className="landing-btn landing-btn-ghost">Loading…</span>
          ) : me ? (
            <Link href="/brief" className="landing-btn">Open my brief →</Link>
          ) : (
            <Link href="/login" className="landing-btn">Sign in</Link>
          )}
          {me?.is_super_admin && (
            <Link href="/admin" className="landing-btn landing-btn-ghost">Admin</Link>
          )}
        </div>
        <p className="landing-hint">
          No public signup. Contact <a href="mailto:hello@rig360media.com">hello@rig360media.com</a> for an invite.
        </p>
      </div>
    </main>
  );
}
