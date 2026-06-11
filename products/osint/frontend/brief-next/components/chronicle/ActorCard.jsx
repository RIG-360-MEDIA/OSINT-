'use client';
import { useEffect, useRef } from 'react';

function initials(name) {
  if (!name) return '?';
  const parts = name.split(/\s+/);
  if (parts.length === 1) return parts[0][0].toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function roleClass(role) {
  const r = (role || '').toLowerCase();
  if (r.includes('antagonist')) return 'antagonist';
  if (r.includes('enabler')) return 'enabler';
  return '';
}

export default function ActorCard({ actor, storySpanDays, index = 0 }) {
  const ref = useRef(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          el.classList.add('visible');
          observer.unobserve(el);
        }
      },
      { threshold: 0.1 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const spanDays = storySpanDays || 30;
  const start = Math.max(0, (actor.presence_start || 1) - 1);
  const endRaw = actor.presence_end;
  const end = endRaw === 'ongoing' || !endRaw ? spanDays : Math.min(Number(endRaw), spanDays);
  const leftPct = (start / spanDays) * 100;
  const widthPct = Math.max(4, ((end - start) / spanDays) * 100);

  return (
    <div
      className="actor-card"
      ref={ref}
      style={{ transitionDelay: `${index * 100}ms` }}
    >
      <div className="actor-card-head">
        <div className="actor-avatar">{initials(actor.name)}</div>
        <div className="actor-name-block">
          <h4 className="actor-name">{actor.name}</h4>
          <span className={`actor-role-badge ${roleClass(actor.role)}`}>
            {actor.role || 'Actor'}
          </span>
        </div>
      </div>

      <div className="actor-presence">
        <div className="actor-presence-label">
          <span>Presence in story</span>
          <span>
            Day {actor.presence_start || 1} →{' '}
            {actor.presence_end === 'ongoing' ? 'ongoing' : `Day ${actor.presence_end}`}
          </span>
        </div>
        <div className="actor-presence-track">
          <div
            className="actor-presence-fill"
            style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
          />
        </div>
      </div>

      <div className="actor-sections">
        {actor.behavior_pattern && (
          <div className="actor-field">
            <span className="actor-field-label">Behaviour pattern</span>
            <p className="actor-field-value">{actor.behavior_pattern}</p>
          </div>
        )}

        {actor.stated_position && (
          <div className="actor-field">
            <span className="actor-field-label">Stated position</span>
            <p className="actor-field-value">{actor.stated_position}</p>
          </div>
        )}

        {actor.actual_agenda && (
          <div className="actor-field">
            <span className="actor-field-label">Actual agenda</span>
            <p className="actor-field-value accent">{actor.actual_agenda}</p>
          </div>
        )}

        {actor.watch_for && (
          <div className="actor-watch-for">
            <span className="actor-watch-label">Watch for</span>
            <p className="actor-watch-text">{actor.watch_for}</p>
          </div>
        )}
      </div>
    </div>
  );
}
