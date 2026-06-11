'use client';
import { EntityTypeahead } from '../EntityTypeahead.jsx';
import { SegmentedChoice, ChipToggleGroup, TriStateChips, Toggle } from './controls.jsx';
import * as O from '../../lib/onboardingOptions';

/**
 * One component per wizard step. Each receives:
 *   prefs — the whole wizard state object
 *   set(key, value) — immutably replace one top-level prefs field
 * The page assembles these into the /complete payload.
 */

export function StepPurpose({ prefs, set }) {
  const p = prefs.purpose;
  return (
    <div className="onboarding-step-real">
      <p className="onboarding-fieldhint">How you&apos;ll use the brief shapes what we surface first and how the AI writes. Pick all that apply.</p>
      <label className="ob-label">Primary use</label>
      <ChipToggleGroup options={O.PURPOSE_OPTIONS} selected={p.use_cases} onChange={(v) => set('purpose', { ...p, use_cases: v })} />
      <label className="ob-label" style={{ marginTop: 22 }}>Writing tone</label>
      <SegmentedChoice options={O.LLM_TONE} value={p.llm_tone} onChange={(v) => set('purpose', { ...p, llm_tone: v })} />
    </div>
  );
}

export function StepPrimarySubject({ prefs, set }) {
  return (
    <div className="onboarding-step-real">
      <p className="onboarding-fieldhint">The single most important figure for your brief — your principal, or the person you track most closely. The brief centres its narrative on them.</p>
      <EntityTypeahead
        value={prefs.primarySubject}
        onChange={(v) => set('primarySubject', v.slice(-1))}
        placeholder="Search one person…"
        types="person,politician"
        maxSelections={1}
      />
    </div>
  );
}

export function StepWatchlist({ prefs, set }) {
  return (
    <div className="onboarding-step-real">
      <label className="ob-label">Track closely</label>
      <p className="onboarding-fieldhint">
        Allies, opposition, bureaucrats, or civil-society voices central to you. These surface on
        <em> any</em> mention and replace the default entity cards in your brief.
      </p>
      <EntityTypeahead
        value={prefs.watchlist}
        onChange={(v) => set('watchlist', v)}
        placeholder="Try: your deputy, your main rival, key bureaucrats…"
        types="person"
        maxSelections={20}
      />
      <label className="ob-label" style={{ marginTop: 22 }}>Context &amp; national figures</label>
      <p className="onboarding-fieldhint">
        National leaders or neighbouring heads (Modi, Amit Shah, a neighbouring CM…). These surface
        <em> only when a story also touches your region or subject</em> — so national news that has
        nothing to do with you stays out of your brief.
      </p>
      <EntityTypeahead
        value={prefs.watchlistContext}
        onChange={(v) => set('watchlistContext', v)}
        placeholder="Try: Modi, Amit Shah, a neighbouring CM…"
        types="person,organization"
        maxSelections={10}
      />
    </div>
  );
}

export function StepGeography({ prefs, set }) {
  const g = prefs.geography;
  return (
    <div className="onboarding-step-real">
      <p className="onboarding-fieldhint">Which places matter? Coverage is heaviest for Telangana, Andhra Pradesh, Tamil Nadu and Delhi.</p>
      <label className="ob-label">States &amp; UTs</label>
      <ChipToggleGroup
        options={O.INDIAN_STATES.map((s) => ({ id: s, label: s }))}
        selected={g.states}
        onChange={(v) => set('geography', { ...g, states: v })}
      />
      <label className="ob-label" style={{ marginTop: 22 }}>Countries</label>
      <ChipToggleGroup
        options={O.COUNTRIES.map((c) => ({ id: c.code, label: c.label }))}
        selected={g.countries}
        onChange={(v) => set('geography', { ...g, countries: v })}
      />
    </div>
  );
}

export function StepTopics({ prefs, set }) {
  return (
    <div className="onboarding-step-real">
      <p className="onboarding-fieldhint">Tap a topic once to prioritise it, twice to mute it. Leave neutral to keep default weighting.</p>
      <TriStateChips options={O.TOPIC_CATEGORIES} value={prefs.topics} onChange={(v) => set('topics', v)} />
    </div>
  );
}

export function StepLanguages({ prefs, set }) {
  return (
    <div className="onboarding-step-real">
      <p className="onboarding-fieldhint">Which languages should the brief read across? English has the widest coverage; Telugu, Kannada and Hindi add strong regional depth.</p>
      <ChipToggleGroup
        options={O.LANGUAGES.map((l) => ({ id: l.iso, label: l.label, note: l.note }))}
        selected={prefs.languages}
        onChange={(v) => set('languages', v)}
      />
    </div>
  );
}

export function StepStance({ prefs, set }) {
  const s = prefs.stance;
  return (
    <div className="onboarding-step-real">
      <p className="onboarding-fieldhint">How should the brief frame coverage of your primary subject?</p>
      <label className="ob-label">Lens</label>
      <SegmentedChoice options={O.STANCE_TOWARD} value={s.toward} onChange={(v) => set('stance', { ...s, toward: v })} />
      <div style={{ marginTop: 22 }}>
        <Toggle
          checked={s.echo_floor}
          onChange={(v) => set('stance', { ...s, echo_floor: v })}
          label="Keep me out of an echo chamber"
          hint="always include ≥30% non-aligned coverage"
        />
      </div>
    </div>
  );
}

export function StepEvents({ prefs, set }) {
  return (
    <div className="onboarding-step-real">
      <p className="onboarding-fieldhint">Which event types should trigger prominent placement and (later) alerts?</p>
      <ChipToggleGroup options={O.EVENT_TYPES} selected={prefs.events} onChange={(v) => set('events', v)} />
    </div>
  );
}

export function StepDelivery({ prefs, set }) {
  const d = prefs.delivery;
  return (
    <div className="onboarding-step-real">
      <p className="onboarding-fieldhint">For now there&apos;s one always-live brief page. Email digests &amp; alerts are coming — set your preferences and we&apos;ll honour them when they ship.</p>
      <label className="ob-label">Timezone</label>
      <select className="ob-select" value={d.timezone} onChange={(e) => set('delivery', { ...d, timezone: e.target.value })}>
        {O.TIMEZONES.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>
      <div style={{ marginTop: 20 }}>
        <Toggle
          checked={d.email_digest}
          onChange={(v) => set('delivery', { ...d, email_digest: v })}
          label="Email me a morning digest"
          hint="when this ships"
        />
      </div>
    </div>
  );
}

export function StepPersonality({ prefs, set }) {
  const p = prefs.personality;
  return (
    <div className="onboarding-step-real">
      <p className="onboarding-fieldhint">Tune the reading experience.</p>
      <label className="ob-label">Depth</label>
      <SegmentedChoice options={O.READING_DEPTH} value={p.depth} onChange={(v) => set('personality', { ...p, depth: v })} />
      <label className="ob-label" style={{ marginTop: 18 }}>Voice</label>
      <SegmentedChoice options={O.BRIEF_VOICE} value={p.voice} onChange={(v) => set('personality', { ...p, voice: v })} />
      <label className="ob-label" style={{ marginTop: 18 }}>Density</label>
      <SegmentedChoice options={O.DENSITY} value={p.density} onChange={(v) => set('personality', { ...p, density: v })} />
    </div>
  );
}

export function StepPreview({ prefs }) {
  const subj = prefs.primarySubject[0];
  const langOpts = O.LANGUAGES.map((l) => ({ id: l.iso, label: l.label }));
  return (
    <div className="onboarding-step-real">
      <p className="onboarding-fieldhint">Here&apos;s the brief we&apos;ll build for you. You can change any of this later from settings.</p>
      <ul className="ob-summary">
        <li><span>Primary subject</span><strong>{subj ? subj.name : '— none —'}</strong></li>
        <li><span>Watchlist</span><strong>{prefs.watchlist.length ? prefs.watchlist.map((w) => w.name).join(', ') : '— default —'}</strong></li>
        <li><span>Use</span><strong>{labelList(O.PURPOSE_OPTIONS, prefs.purpose.use_cases) || '—'}</strong></li>
        <li><span>Topics up</span><strong>{labelList(O.TOPIC_CATEGORIES, prefs.topics.include) || '—'}</strong></li>
        <li><span>Topics muted</span><strong>{labelList(O.TOPIC_CATEGORIES, prefs.topics.exclude) || '—'}</strong></li>
        <li><span>Geography</span><strong>{[...prefs.geography.states, ...countryLabels(prefs.geography.countries)].join(', ') || '—'}</strong></li>
        <li><span>Languages</span><strong>{labelList(langOpts, prefs.languages) || '—'}</strong></li>
        <li><span>Lens</span><strong>{cap(prefs.stance.toward)}{prefs.stance.echo_floor ? ' · echo-chamber guard on' : ''}</strong></li>
        <li><span>Events</span><strong>{labelList(O.EVENT_TYPES, prefs.events) || '—'}</strong></li>
        <li><span>Style</span><strong>{cap(prefs.personality.depth)} · {cap(prefs.personality.voice)} · {cap(prefs.personality.density)}</strong></li>
      </ul>
    </div>
  );
}

function labelList(options, ids) {
  const m = new Map(options.map((o) => [o.id, o.label]));
  return (ids || []).map((id) => m.get(id) || id).join(', ');
}
function countryLabels(codes) {
  const m = new Map(O.COUNTRIES.map((c) => [c.code, c.label]));
  return (codes || []).map((c) => m.get(c) || c);
}
function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : ''; }

export const STEP_BY_ID = {
  1: StepPurpose,
  2: StepPrimarySubject,
  3: StepWatchlist,
  4: StepGeography,
  5: StepTopics,
  6: StepLanguages,
  7: StepStance,
  8: StepEvents,
  9: StepDelivery,
  10: StepPersonality,
  11: StepPreview,
};
