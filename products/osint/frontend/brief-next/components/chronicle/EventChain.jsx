'use client';
import { useEffect, useRef } from 'react';

const SIGNAL_LABELS = {
  organic: 'Organic',
  manufactured: 'Manufactured',
  reactive: 'Reactive',
  escalation: 'Escalation',
  dormant: 'Dormant',
  resolution: 'Resolution',
};

function EventCard({ event }) {
  const sig = event.signal_type || 'organic';
  return (
    <div className={`event-card ${sig ? `sig-${sig}` : ''}`}>
      <div className="event-card-top">
        <span className="event-date">{event.date}</span>
        {sig && (
          <span className={`event-signal-badge sig-${sig}`}>
            {SIGNAL_LABELS[sig] || sig}
          </span>
        )}
      </div>

      <h3 className="event-headline">{event.event}</h3>

      {event.why_it_happened && (
        <div className="event-block">
          <span className="event-block-label">Why it happened</span>
          <p className="event-block-text">{event.why_it_happened}</p>
        </div>
      )}

      {event.caused && (
        <div className="event-block">
          <span className="event-block-label">Set in motion</span>
          <div className="event-caused">
            <span className="event-caused-arrow">→</span>
            <span>{event.caused}</span>
          </div>
        </div>
      )}

      {event.key_quote && (
        <div className="event-quote">
          <p>"{event.key_quote}"</p>
        </div>
      )}

      {event.evidence && event.evidence.length > 0 && (
        <div className="event-evidence">
          {event.evidence.map((e, i) => (
            <span key={i} className="event-evidence-item">{e}</span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function EventChain({ events = [] }) {
  const nodeRefs = useRef([]);
  const bridgeRefs = useRef([]);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible');
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
    );

    nodeRefs.current.forEach((el) => el && observer.observe(el));
    bridgeRefs.current.forEach((el) => el && observer.observe(el));

    return () => observer.disconnect();
  }, [events]);

  if (!events || events.length === 0) {
    return (
      <div className="event-chain">
        <div className="event-spine" />
        <p style={{ color: 'rgba(255,255,255,0.25)', fontStyle: 'italic', fontSize: 14 }}>
          No event chain available.
        </p>
      </div>
    );
  }

  return (
    <div className="event-chain">
      <div className="event-spine" />

      {events.map((event, i) => (
        <div key={i}>
          <div
            className="event-node"
            ref={(el) => { nodeRefs.current[i] = el; }}
            style={{ transitionDelay: `${i * 60}ms` }}
          >
            <div className={`event-dot sig-${event.signal_type || 'organic'}`} />
            <EventCard event={event} />
          </div>

          {i < events.length - 1 && event.caused && (
            <div
              className="causal-bridge"
              ref={(el) => { bridgeRefs.current[i] = el; }}
              style={{ transitionDelay: `${i * 60 + 80}ms` }}
            >
              <span className="causal-bridge-icon">↓</span>
              <span className="causal-bridge-text">caused →</span>
            </div>
          )}
          {i < events.length - 1 && !event.caused && (
            <div style={{ height: 24 }} />
          )}
        </div>
      ))}
    </div>
  );
}
