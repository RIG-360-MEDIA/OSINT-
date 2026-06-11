import { useEffect, useRef } from 'react';

const SIGNAL_LABELS = {
  organic: 'Organic',
  manufactured: 'Manufactured',
  reactive: 'Reactive',
  escalation: 'Escalation',
  dormant: 'Dormant',
  resolution: 'Resolution',
};

/* ── Evidence → Article matcher ──────────────────────────────────────────
   The LLM's `evidence` array contains partial article titles. We fuzzy-match
   each one against the story's article pool to get URL + source + date.     */
function findArticle(evidenceStr, articles) {
  if (!evidenceStr || !articles?.length) return null;
  const ev = evidenceStr.toLowerCase().trim();

  // 1. Evidence is a substring of an article title
  let match = articles.find((a) => {
    const t = (a.title || '').toLowerCase();
    return t.includes(ev.slice(0, 55));
  });
  if (match) return match;

  // 2. Article title is a substring of the evidence string
  match = articles.find((a) => {
    const t = (a.title || '').toLowerCase().trim();
    return t.length > 20 && ev.includes(t.slice(0, 45));
  });
  if (match) return match;

  // 3. Word-overlap fallback (≥4 consecutive shared words)
  const evWords = ev.split(/\s+/);
  return articles.find((a) => {
    const tWords = (a.title || '').toLowerCase().split(/\s+/);
    for (let i = 0; i <= evWords.length - 4; i++) {
      const chunk = evWords.slice(i, i + 4).join(' ');
      if (tWords.join(' ').includes(chunk)) return true;
    }
    return false;
  }) || null;
}

/* ── Single event source row ─────────────────────────────────────────── */
function EvidenceRow({ evidenceStr, articles }) {
  const article = findArticle(evidenceStr, articles);

  if (article?.url) {
    return (
      <a
        className="ev-source-item ev-source-linked"
        href={article.url}
        target="_blank"
        rel="noopener noreferrer"
      >
        <span className="ev-source-icon">↗</span>
        <span className="ev-source-body">
          <span className="ev-source-title">{article.title}</span>
          <span className="ev-source-meta">
            {article.source}{article.pub_date ? ` · ${article.pub_date}` : ''}
          </span>
        </span>
      </a>
    );
  }

  // No URL match — render the LLM evidence string as plain text
  return (
    <div className="ev-source-item ev-source-plain">
      <span className="ev-source-icon">·</span>
      <span className="ev-source-title">{evidenceStr}</span>
    </div>
  );
}

/* ── Event card ──────────────────────────────────────────────────────── */
function EventCard({ event, articles }) {
  const sig = event.signal_type || 'organic';
  const hasEvidence = event.evidence && event.evidence.length > 0;

  return (
    <div className="event-card">
      <div className="event-card-top">
        <span className="event-date">{event.date}</span>
        <span className={`event-signal-badge sig-${sig}`}>{SIGNAL_LABELS[sig] || sig}</span>
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
            <span className="event-caused-arrow">&rarr;</span>
            <span>{event.caused}</span>
          </div>
        </div>
      )}

      {event.key_quote && (
        <div className="event-quote">
          <p>&ldquo;{event.key_quote}&rdquo;</p>
        </div>
      )}

      {hasEvidence && (
        <div className="ev-sources">
          <span className="ev-sources-label">Sources</span>
          <div className="ev-sources-list">
            {event.evidence.map((e, i) => (
              <EvidenceRow key={i} evidenceStr={e} articles={articles} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Event chain ─────────────────────────────────────────────────────── */
export default function EventChain({ events = [], articles = [] }) {
  const nodeRefs   = useRef([]);
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
        <p className="chron-muted">No event chain available.</p>
      </div>
    );
  }

  return (
    <div className="event-chain">
      <div className="event-spine" />
      {events.map((event, i) => (
        <div key={i}>
          <div
            className={`event-node sig-${event.signal_type || 'organic'}`}
            ref={(el) => { nodeRefs.current[i] = el; }}
            style={{ transitionDelay: `${i * 60}ms` }}
          >
            <div className="event-dot" />
            <EventCard event={event} articles={articles} />
          </div>

          {i < events.length - 1 && event.caused && (
            <div
              className="causal-bridge"
              ref={(el) => { bridgeRefs.current[i] = el; }}
              style={{ transitionDelay: `${i * 60 + 80}ms` }}
            >
              <span className="causal-bridge-icon">&darr;</span>
              <span className="causal-bridge-text">caused &rarr;</span>
            </div>
          )}
          {i < events.length - 1 && !event.caused && <div style={{ height: 24 }} />}
        </div>
      ))}
    </div>
  );
}
