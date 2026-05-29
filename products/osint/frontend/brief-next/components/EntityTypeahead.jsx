'use client';
import { useEffect, useRef, useState } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8002';

/**
 * Entity typeahead with chip selection.
 *
 * Props:
 *   value          — array of {id, name, party, state, type}
 *   onChange(next) — called with the new array on add/remove
 *   placeholder    — input placeholder text
 *   types          — comma-list passed to /search_entities (default 'person,politician')
 *   maxSelections  — optional cap (returns early if reached)
 */
export function EntityTypeahead({
  value = [],
  onChange,
  placeholder = 'Type a name…',
  types = 'person,politician',
  maxSelections,
}) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const debRef = useRef(null);
  const containerRef = useRef(null);

  // Debounced search.
  useEffect(() => {
    if (debRef.current) clearTimeout(debRef.current);
    if (q.trim().length < 2) {
      setResults([]);
      return;
    }
    debRef.current = setTimeout(async () => {
      try {
        const r = await fetch(
          `${API_BASE}/api/onboarding/search_entities?q=${encodeURIComponent(q)}&types=${types}&limit=8`,
        );
        if (!r.ok) return;
        const data = await r.json();
        const selectedIds = new Set(value.map((v) => v.id));
        setResults((data.results || []).filter((r) => !selectedIds.has(r.id)));
        setHighlight(0);
      } catch {
        // silent — server hiccups are common during dev
      }
    }, 180);
    return () => clearTimeout(debRef.current);
  }, [q, types, value]);

  // Close dropdown on outside click.
  useEffect(() => {
    const onDoc = (e) => {
      if (!containerRef.current?.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  function pick(item) {
    if (maxSelections && value.length >= maxSelections) return;
    onChange([...value, item]);
    setQ('');
    setResults([]);
    setOpen(false);
  }

  function remove(id) {
    onChange(value.filter((v) => v.id !== id));
  }

  function onKeyDown(e) {
    if (!open || !results.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlight((h) => (h + 1) % results.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight((h) => (h - 1 + results.length) % results.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      pick(results[highlight]);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  }

  return (
    <div className="entity-typeahead" ref={containerRef}>
      <div className="entity-chips">
        {value.map((v) => (
          <span key={v.id} className="entity-chip">
            <strong>{v.name}</strong>
            {v.party && <span className="entity-chip-meta">{v.party}</span>}
            {v.state && <span className="entity-chip-meta">· {v.state}</span>}
            <button
              type="button"
              aria-label={`Remove ${v.name}`}
              onClick={() => remove(v.id)}
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <input
        type="text"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        autoComplete="off"
      />
      {open && results.length > 0 && (
        <ul className="entity-dropdown" role="listbox">
          {results.map((r, i) => (
            <li
              key={r.id}
              className={i === highlight ? 'highlight' : ''}
              role="option"
              aria-selected={i === highlight}
              onMouseEnter={() => setHighlight(i)}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => pick(r)}
            >
              <span className="entity-dd-name">{r.name}</span>
              {r.party && <span className="entity-dd-meta">{r.party}</span>}
              {r.state ? (
                <span className="entity-dd-meta">{r.state}</span>
              ) : (
                <span className="entity-dd-meta-faded">National</span>
              )}
            </li>
          ))}
        </ul>
      )}
      {maxSelections && (
        <p className="entity-counter">
          {value.length} / {maxSelections} picked
        </p>
      )}
    </div>
  );
}
