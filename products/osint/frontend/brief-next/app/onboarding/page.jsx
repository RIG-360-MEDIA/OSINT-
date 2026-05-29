'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { authFetch } from '../../lib/supabase';
import { useMe } from '../../lib/useMe';
import { EntityTypeahead } from '../../components/EntityTypeahead.jsx';
import '../auth.css';

const STEPS = [
  { id: 1,  title: 'Purpose & Persona',     desc: 'How will you use the brief? (LLM tone, edition cadence)' },
  { id: 2,  title: 'Primary Subject',       desc: 'The single most important figure for your brief.' },
  { id: 3,  title: 'Watchlist',             desc: 'Allies, opposition, bureaucrats, civil society.' },
  { id: 4,  title: 'Geographic Scope',      desc: 'States, districts, countries you track.' },
  { id: 5,  title: 'Topics',                desc: 'Subjects to surface or suppress.' },
  { id: 6,  title: 'Languages',             desc: 'What you read in.' },
  { id: 7,  title: 'Sources & Outlets',     desc: 'Trusted publications and ones to exclude.' },
  { id: 8,  title: 'Stance & Tone',         desc: 'How critical, how balanced toward your subject.' },
  { id: 9,  title: 'Events to Track',       desc: 'Cabinet meetings, court verdicts, elections, etc.' },
  { id: 10, title: 'Delivery & Notifications', desc: 'Email digest, alerts, timezone.' },
  { id: 11, title: 'Brief Personality',     desc: 'Reading depth, voice, density.' },
  { id: 12, title: 'Preview & Confirm',     desc: 'See a sample brief built from your picks.' },
];

export default function OnboardingPage() {
  const router = useRouter();
  const { loading, me } = useMe();
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  // Real wizard state — replaces step placeholders as fields land.
  const [watchlist, setWatchlist] = useState([]); // [{id, name, party, state, type}]

  useEffect(() => {
    if (loading) return;
    if (!me) { router.push('/login?next=/onboarding'); return; }
    if (me.onboarded) { router.push('/brief'); return; }
  }, [loading, me, router]);

  const current = STEPS[step];

  async function finish() {
    setBusy(true); setError(null);
    try {
      // Real payload — Step 3 (Watchlist) now populated from typeahead.
      // Remaining 11 steps still send placeholders {} until their forms land.
      const watchlistPayload = {
        // Single flat list for now; entities endpoint reads .entity_ids first.
        entity_ids: watchlist.map((w) => w.id),
        entity_meta: watchlist.map((w) => ({
          id: w.id, name: w.name, party: w.party, state: w.state, type: w.type,
        })),
        allies: [], opposition: [], bureaucrats: [], civil_society: [],
        auto_adjacents: true,
      };
      await authFetch('/api/onboarding/complete', {
        method: 'POST',
        body: JSON.stringify({
          watchlist: watchlistPayload,
          regions: {}, topics: {}, languages: {}, sources: {},
          stance: {}, events: {}, delivery: {}, personality: {},
        }),
      });
      router.push('/brief');
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  if (loading || !me) {
    return <main className="auth-shell"><div className="auth-card">Loading…</div></main>;
  }

  return (
    <main className="onboarding-shell">
      <div className="onboarding-progress">
        Step {step + 1} of {STEPS.length} — {current.title}
        <div className="progress-bar"><div style={{ width: `${((step + 1) / STEPS.length) * 100}%` }} /></div>
      </div>
      <div className="onboarding-card">
        <h1>{current.title}</h1>
        <p className="onboarding-desc">{current.desc}</p>
        {current.id === 3 ? (
          <div className="onboarding-step-real">
            <p className="onboarding-fieldhint">
              Type at least 2 letters. Pick people, parties, officials, or civil-society
              voices you want the brief to track. Most are politicians but you can also
              add bureaucrats, journalists, or anyone in <code>entity_dictionary</code>.
            </p>
            <EntityTypeahead
              value={watchlist}
              onChange={setWatchlist}
              placeholder="Try: Modi, Rahul Gandhi, Owaisi, Yogi…"
              types="person"
              maxSelections={20}
            />
            <p className="onboarding-fieldhint" style={{ marginTop: 18 }}>
              These will replace the default <em>Naidu / Rahul / Akhilesh / Owaisi</em>{' '}
              entity cards in your brief once you finish onboarding.
            </p>
          </div>
        ) : (
          <div className="onboarding-placeholder">
            [Step {current.id} fields land later — click <strong>Continue</strong> to advance]
          </div>
        )}
        <div className="onboarding-controls">
          {step > 0
            ? <button type="button" onClick={() => setStep(step - 1)}>← Back</button>
            : <span />}
          {step < STEPS.length - 1
            ? <button type="button" onClick={() => setStep(step + 1)}>Continue →</button>
            : <button type="button" disabled={busy} onClick={finish}>{busy ? 'Saving…' : 'Finish & view my brief'}</button>}
        </div>
        {error && <p className="auth-error">{error}</p>}
      </div>
    </main>
  );
}
