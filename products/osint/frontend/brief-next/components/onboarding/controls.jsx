'use client';

/**
 * Reusable onboarding controls — all controlled, all immutable updates.
 * Shared by every wizard step so the look + keyboard/aria behaviour stays
 * consistent.
 */

/** Single-select pill row. options: [{id,label}]. */
export function SegmentedChoice({ options, value, onChange }) {
  return (
    <div className="ob-segmented" role="radiogroup">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          role="radio"
          aria-checked={value === o.id}
          className={value === o.id ? 'ob-seg active' : 'ob-seg'}
          onClick={() => onChange(o.id)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Multi-select chips. options: [{id,label,note?}]. selected: array of ids. */
export function ChipToggleGroup({ options, selected = [], onChange, idKey = 'id', labelKey = 'label' }) {
  const set = new Set(selected);
  const toggle = (id) => {
    const next = new Set(set);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange([...next]);
  };
  return (
    <div className="ob-chipgroup">
      {options.map((o) => {
        const id = o[idKey];
        const on = set.has(id);
        return (
          <button
            key={id}
            type="button"
            className={on ? 'ob-chip on' : 'ob-chip'}
            aria-pressed={on}
            onClick={() => toggle(id)}
          >
            {o[labelKey]}
            {o.note ? <span className="ob-chip-note">{o.note}</span> : null}
          </button>
        );
      })}
    </div>
  );
}

/**
 * Tri-state chips: each option cycles neutral → include → exclude → neutral.
 * value: { include: [ids], exclude: [ids] }.
 */
export function TriStateChips({ options, value = { include: [], exclude: [] }, onChange, idKey = 'id', labelKey = 'label' }) {
  const inc = new Set(value.include || []);
  const exc = new Set(value.exclude || []);
  const cycle = (id) => {
    const ni = new Set(inc);
    const ne = new Set(exc);
    if (ni.has(id)) { ni.delete(id); ne.add(id); }       // include → exclude
    else if (ne.has(id)) { ne.delete(id); }              // exclude → neutral
    else { ni.add(id); }                                 // neutral → include
    onChange({ include: [...ni], exclude: [...ne] });
  };
  return (
    <>
      <div className="ob-chipgroup">
        {options.map((o) => {
          const id = o[idKey];
          const state = inc.has(id) ? 'inc' : exc.has(id) ? 'exc' : '';
          return (
            <button key={id} type="button" className={`ob-chip tri ${state}`} onClick={() => cycle(id)}>
              {state === 'inc' ? '✓ ' : state === 'exc' ? '✕ ' : ''}{o[labelKey]}
            </button>
          );
        })}
      </div>
      <p className="ob-legend">
        <span className="ob-dot inc" /> tap once: prioritise
        <span className="ob-dot exc" /> tap twice: mute
      </p>
    </>
  );
}

/** On/off toggle with label + optional hint. */
export function Toggle({ checked, onChange, label, hint }) {
  return (
    <button
      type="button"
      className={checked ? 'ob-toggle on' : 'ob-toggle'}
      aria-pressed={checked}
      onClick={() => onChange(!checked)}
    >
      <span className="ob-toggle-track"><span className="ob-toggle-knob" /></span>
      <span className="ob-toggle-label">{label}{hint ? <em>{hint}</em> : null}</span>
    </button>
  );
}
