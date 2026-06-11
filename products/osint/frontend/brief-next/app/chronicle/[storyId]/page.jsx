'use client';
import { useEffect, useState, useRef } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { useMe } from '../../../lib/useMe';
import { authFetch } from '../../../lib/supabase';
import EventChain from '../../../components/chronicle/EventChain';
import InsightBomb from '../../../components/chronicle/InsightBomb';
import ActorCard from '../../../components/chronicle/ActorCard';
import ChronicleLoader from '../../../components/chronicle/ChronicleLoader';
import '../chronicle.css';

export default function ChroniclePage() {
  const router = useRouter();
  const params = useParams();
  const storyId = params.storyId;

  const { loading: authLoading, me } = useMe();
  const [meta, setMeta] = useState(null);
  const [chronicle, setChronicle] = useState(null);
  const [chronicleError, setChronicleError] = useState(null);
  const [activeSection, setActiveSection] = useState('story');

  const storyRef = useRef(null);
  const insightsRef = useRef(null);
  const playersRef = useRef(null);

  // Auth gate
  useEffect(() => {
    if (authLoading) return;
    if (!me) { router.push(`/login?next=/chronicle/${storyId}`); return; }
    if (!me.onboarded) { router.push('/onboarding'); }
  }, [authLoading, me, router, storyId]);

  // Fetch story metadata (fast — just DB query)
  useEffect(() => {
    if (!me || !storyId) return;
    authFetch(`/api/chronicle/${storyId}/meta`).then(setMeta).catch(() => {});
  }, [me, storyId]);

  // Fetch full Chronicle (slow — LLM, cached 24h)
  useEffect(() => {
    if (!me || !storyId) return;
    authFetch(`/api/chronicle/${storyId}`)
      .then(setChronicle)
      .catch((err) => setChronicleError(err.message || 'Analysis unavailable'));
  }, [me, storyId]);

  // Intersection observer for sticky tab highlight
  useEffect(() => {
    const sections = [
      { ref: storyRef, id: 'story' },
      { ref: insightsRef, id: 'insights' },
      { ref: playersRef, id: 'players' },
    ];
    const obs = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setActiveSection(entry.target.dataset.section);
          }
        });
      },
      { rootMargin: '-40% 0px -55% 0px', threshold: 0 }
    );
    sections.forEach(({ ref }) => ref.current && obs.observe(ref.current));
    return () => obs.disconnect();
  }, [chronicle]);

  const scrollTo = (ref, section) => {
    setActiveSection(section);
    ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  // Show minimal spinner while auth resolves
  if (authLoading || (!me && !authLoading)) {
    return (
      <div className="chr-shell">
        <div className="chr-spinner" />
      </div>
    );
  }

  const title = meta?.title || chronicle?.title || '…';
  const spanDays = meta?.span_days || chronicle?.span_days;

  return (
    <div className="chronicle-page">

      {/* ── Sticky header ── */}
      <header className="chr-header">
        <div className="chr-header-inner">
          <button className="chr-back" onClick={() => router.push('/brief')}>
            ← Stories
          </button>

          <div className="chr-title-block">
            <h1 className="chr-title">{title}</h1>
            {meta && (
              <div className="chr-meta-row">
                {meta.first_seen && <span>{meta.first_seen}</span>}
                {meta.first_seen && meta.last_seen && <span className="chr-sep">—</span>}
                {meta.last_seen && <span>{meta.last_seen}</span>}
                {spanDays && <><span className="chr-dot">·</span><span>{spanDays} days</span></>}
                {meta.article_count && <><span className="chr-dot">·</span><span>{meta.article_count} articles</span></>}
                {meta.source_count && <><span className="chr-dot">·</span><span>{meta.source_count} sources</span></>}
              </div>
            )}
          </div>

          <nav className="chr-tabs" aria-label="Chronicle sections">
            <button
              className={`chr-tab ${activeSection === 'story' ? 'active' : ''}`}
              onClick={() => scrollTo(storyRef, 'story')}
            >
              The Story
            </button>
            <button
              className={`chr-tab ${activeSection === 'insights' ? 'active' : ''}`}
              onClick={() => scrollTo(insightsRef, 'insights')}
            >
              What It Means
            </button>
            <button
              className={`chr-tab ${activeSection === 'players' ? 'active' : ''}`}
              onClick={() => scrollTo(playersRef, 'players')}
            >
              The Players
            </button>
          </nav>
        </div>
      </header>

      {/* ── Content ── */}
      <main className="chr-main">

        {/* ── Section 1: The Story (Event Chain) ── */}
        <section
          className="chr-section"
          ref={storyRef}
          id="chronicle-story"
          data-section="story"
        >
          <div className="chr-section-head">
            <span className="chr-section-label">The Story</span>
            <p className="chr-section-sub">
              A causal reconstruction of events — not what was reported, but what actually happened and why each thing caused the next
            </p>
          </div>

          {chronicleError ? (
            <div className="chr-error">
              <span>Chronicle analysis could not be generated.</span>
              <code>{chronicleError}</code>
            </div>
          ) : !chronicle ? (
            <ChronicleLoader />
          ) : (
            <EventChain events={chronicle.event_chain} />
          )}
        </section>

        {/* ── Section 2: What It Means (Insights) ── */}
        <section
          className="chr-section chr-section--dark"
          ref={insightsRef}
          id="chronicle-insights"
          data-section="insights"
        >
          <div className="chr-section-head">
            <span className="chr-section-label">What It Means</span>
            <p className="chr-section-sub">
              Analytical findings invisible to the headline reader — the deductions that reframe everything
            </p>
          </div>

          {chronicle?.insights?.length > 0
            ? chronicle.insights.map((insight, i) => (
                <InsightBomb key={i} insight={insight} index={i} />
              ))
            : chronicle && (
                <p style={{ color: 'rgba(255,255,255,0.25)', fontStyle: 'italic', fontSize: 14 }}>
                  No insights available for this story.
                </p>
              )}
        </section>

        {/* ── Section 3: The Players ── */}
        <section
          className="chr-section"
          ref={playersRef}
          id="chronicle-players"
          data-section="players"
        >
          <div className="chr-section-head">
            <span className="chr-section-label">The Players</span>
            <p className="chr-section-sub">
              Who is actually playing what game — stated positions, real agendas, and what to watch for next
            </p>
          </div>

          {chronicle?.actors?.length > 0 ? (
            <div className="chr-actors-grid">
              {chronicle.actors.map((actor, i) => (
                <ActorCard
                  key={i}
                  actor={actor}
                  storySpanDays={spanDays}
                  index={i}
                />
              ))}
            </div>
          ) : chronicle ? (
            <p style={{ color: 'rgba(255,255,255,0.25)', fontStyle: 'italic', fontSize: 14 }}>
              No actor analysis available for this story.
            </p>
          ) : null}
        </section>

        {/* ── Footer ── */}
        <div className="chr-footer">
          <button className="chr-back-btn" onClick={() => router.push('/brief')}>
            ← Back to Stories
          </button>
        </div>
      </main>
    </div>
  );
}
