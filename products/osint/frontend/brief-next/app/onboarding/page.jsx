'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { authFetch } from '../../lib/supabase';
import { useMe } from '../../lib/useMe';
import { STEP_BY_ID } from '../../components/onboarding/steps.jsx';
import '../auth.css';

const STEPS = [
  { id: 1,  title: 'Purpose & Persona',        desc: 'How will you use the brief? (tone + intent)' },
  { id: 2,  title: 'Primary Subject',          desc: 'The single most important figure for your brief.' },
  { id: 3,  title: 'Watchlist',                desc: 'Allies, opposition, bureaucrats, civil society.' },
  { id: 4,  title: 'Geographic Scope',         desc: 'States, UTs and countries you track.' },
  { id: 5,  title: 'Topics',                   desc: 'Subjects to surface or suppress.' },
  { id: 6,  title: 'Languages',                desc: 'What the brief should read across.' },
  { id: 7,  title: 'Stance & Tone',            desc: 'How critical or balanced toward your subject.' },
  { id: 8,  title: 'Events to Track',          desc: 'Cabinet, court verdicts, elections, and more.' },
  { id: 9,  title: 'Delivery & Notifications', desc: 'Timezone and (coming) email digest.' },
  { id: 10, title: 'Brief Personality',        desc: 'Reading depth, voice, density.' },
  { id: 11, title: 'Preview & Confirm',        desc: 'Review the brief built from your picks.' },
];

const INITIAL_PREFS = {
  purpose: { use_cases: [], llm_tone: 'neutral' },
  primarySubject: [],                                 // [0..1] (EntityTypeahead needs an array)
  watchlist: [],                                      // [{id,name,party,state,type}]
  geography: { states: [], countries: ['IN'], districts: [] },
  topics: { include: [], exclude: [] },
  languages: ['en'],
  stance: { toward: 'balanced', echo_floor: true },
  events: [],                                         // [ids]
  delivery: { timezone: 'Asia/Kolkata', email_digest: false },
  personality: { depth: 'standard', voice: 'formal', density: 'comfortable' },
};

export default function OnboardingPage() {
  const router = useRouter();
  const { loading, me } = useMe();
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [prefs, setPrefs] = useState(INITIAL_PREFS);

  useEffect(() => {
    if (loading) return;
    if (!me) { router.push('/login?next=/onboarding'); return; }
    if (me.onboarded) { router.push('/brief'); return; }
  }, [loading, me, router]);

  const set = (key, value) => setPrefs((p) => ({ ...p, [key]: value }));
  const current = STEPS[step];
  const StepComp = STEP_BY_ID[current.id];

  async function finish() {
    setBusy(true); setError(null);
    try {
      const subj = prefs.primarySubject[0] || null;
      await authFetch('/api/onboarding/complete', {
        method: 'POST',
        body: JSON.stringify({
          primary_subject_id: subj?.id || null,
          primary_subject_meta: subj || {},
          watchlist: {
            entity_ids: prefs.watchlist.map((w) => w.id),
            entity_meta: prefs.watchlist,
            auto_adjacents: true,
          },
          regions: prefs.geography,
          topics: prefs.topics,
          languages: { read: prefs.languages },
          stance: prefs.stance,
          events: { types: prefs.events },
          delivery: prefs.delivery,
          // purpose/persona folded into personality (one JSONB blob about voice/intent)
          personality: { ...prefs.personality, ...prefs.purpose },
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
        {StepComp ? <StepComp prefs={prefs} set={set} /> : null}
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
