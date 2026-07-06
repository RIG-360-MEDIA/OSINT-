// Keyword Intelligence — type any keyword, get a live cross-source dossier.
// Backed by GET /api/keywords/search (classification, volume, sentiment, social,
// top/harmful accounts, related entities, top articles) + POST /api/keywords/track.
import { useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { authFetch } from '../lib/supabase.js';
import { AreaTrend, RankBars, StackBar } from '../lib/charts.jsx';

const TONE = { supportive: 'var(--supportive)', hostile: 'var(--hostile)', neutral: 'var(--muted)' };
const STANCE_COLOR = {
  supportive: 'supportive', sympathetic: 'cool', neutral: 'muted',
  critical: 'hostile', hostile: 'hostile', mocking: 'rival',
};

function Panel({ title, sub, children, span }) {
  return (
    <section className="panel" style={{ gridColumn: span ? `span ${span}` : 'auto', padding: '18px 20px' }}>
      {title && (
        <header style={{ marginBottom: 12 }}>
          <div className="mono" style={{ fontSize: '0.62rem', letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--muted)' }}>{title}</div>
          {sub && <div style={{ fontSize: '0.78rem', color: 'var(--faint)', marginTop: 2 }}>{sub}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

function ClassBadge({ c, perspective }) {
  if (!c) return null;
  const label = c.type === 'topic' ? 'topic' : `${c.type}${c.party ? ' · ' + c.party : ''}`;
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
      <span className="mono" style={{ fontSize: '0.66rem', padding: '3px 9px', borderRadius: 999, background: 'oklch(0.28 0.03 270)', color: 'var(--gold)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>{label}</span>
      {c.canonical && c.canonical.toLowerCase() !== '' && <span style={{ fontSize: '0.8rem', color: 'var(--faint)' }}>{c.canonical}</span>}
      <span className="mono" style={{ fontSize: '0.62rem', color: 'var(--muted)', marginLeft: 'auto' }}>perspective: {perspective}</span>
    </div>
  );
}

export default function Keywords() {
  const [q, setQ] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const [tracked, setTracked] = useState(false);

  const run = useCallback(async (kw) => {
    const query = (kw ?? q).trim();
    if (!query) return;
    setLoading(true); setErr(''); setData(null); setTracked(false);
    try {
      const d = await authFetch(`/api/keywords/search?q=${encodeURIComponent(query)}&days=7`);
      setData(d);
    } catch (e) {
      setErr(e?.message || 'Search failed');
    } finally {
      setLoading(false);
    }
  }, [q]);

  const track = useCallback(async () => {
    if (!data?.query) return;
    try {
      await authFetch(`/api/keywords/track?q=${encodeURIComponent(data.query)}&days=7`, { method: 'POST' });
      setTracked(true);
    } catch (e) {
      setErr(e?.message || 'Track failed');
    }
  }, [data]);

  const series = data?.volume?.series?.map((p) => p.count) || [];
  const labels = data?.volume?.series?.map((p) => p.date.slice(5)) || [];
  const dist = data?.sentiment?.distribution || {};
  const sentSegments = Object.entries(dist).map(([k, v]) => ({ label: k, value: v, color: STANCE_COLOR[k] || 'muted' }));
  const socialByPlatform = data?.social?.by_platform || {};

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '28px 20px 80px' }}>
      <motion.h1 initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
        style={{ fontSize: '1.5rem', fontWeight: 500, letterSpacing: '-0.01em', marginBottom: 4 }}>
        Keyword Intelligence
      </motion.h1>
      <p style={{ color: 'var(--faint)', fontSize: '0.85rem', marginBottom: 20 }}>
        Type anything — a person, company, place, event or phrase — for a live cross-source dossier.
      </p>

      <form onSubmit={(e) => { e.preventDefault(); run(); }} style={{ display: 'flex', gap: 10, marginBottom: 22 }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. Modi, Reliance, semiconductor…"
          style={{ flex: 1, padding: '12px 16px', borderRadius: 10, background: 'oklch(0.2 0.02 270)', border: '1px solid var(--line)', color: 'var(--ink)', fontSize: '0.95rem' }} />
        <button type="submit" disabled={loading}
          style={{ padding: '12px 22px', borderRadius: 10, background: 'var(--gold)', color: '#1a1205', border: 'none', fontWeight: 600, cursor: 'pointer', opacity: loading ? 0.6 : 1 }}>
          {loading ? 'Searching…' : 'Search'}
        </button>
      </form>

      {err && <div style={{ color: 'var(--hostile)', fontSize: '0.85rem', marginBottom: 16 }}>⚠ {err}</div>}

      {data && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 14 }}>
          <Panel span={2}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
              <ClassBadge c={data.classification} perspective={data.perspective_default} />
              <button onClick={track} disabled={tracked}
                style={{ padding: '8px 16px', borderRadius: 8, background: tracked ? 'oklch(0.3 0.05 150)' : 'transparent', border: '1px solid var(--line)', color: tracked ? 'var(--supportive)' : 'var(--ink)', cursor: 'pointer', fontSize: '0.82rem', whiteSpace: 'nowrap' }}>
                {tracked ? '✓ Tracking' : '📌 Track'}
              </button>
            </div>
          </Panel>

          <Panel title="Volume" sub={`${data.volume.total} articles · ${data.volume.velocity_pct >= 0 ? '+' : ''}${data.volume.velocity_pct ?? 0}% vs prior week`}>
            {series.length > 1 ? <AreaTrend data={series} labels={labels} color="cool" /> : <div style={{ color: 'var(--faint)' }}>Not enough data for a trend.</div>}
          </Panel>

          <Panel title="Sentiment" sub={`${data.sentiment.label} · lean ${data.sentiment.lean ?? '—'} · n=${data.sentiment.n}`}>
            {sentSegments.length ? <StackBar segments={sentSegments.map((s) => ({ ...s, value: s.value }))} /> : <div style={{ color: 'var(--faint)' }}>No stance data.</div>}
          </Panel>

          <Panel title="Social" sub={`${data.social.total} posts across platforms`}>
            <RankBars items={Object.entries(socialByPlatform).map(([label, value]) => ({ label, value }))} color="rival" />
          </Panel>

          <Panel title="Top accounts" sub="loudest voices">
            {data.top_accounts?.length ? (
              <RankBars items={data.top_accounts.slice(0, 6).map((a) => ({ label: `${a.platform}·@${a.username}`, value: a.posts }))} />
            ) : <div style={{ color: 'var(--faint)' }}>None.</div>}
          </Panel>

          <Panel title="⚠ Harmful accounts" sub="toxic / coordinated" span={data.harmful_accounts?.length ? 1 : 2}>
            {data.harmful_accounts?.length ? (
              <div style={{ display: 'grid', gap: 7 }}>
                {data.harmful_accounts.slice(0, 6).map((a, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem' }}>
                    <span>{a.platform}·@{a.username}</span>
                    <span style={{ color: 'var(--hostile)' }}>tox {a.max_toxicity}{a.coordinated_posts ? ` · coord ${a.coordinated_posts}` : ''}</span>
                  </div>
                ))}
              </div>
            ) : <div style={{ color: 'var(--faint)' }}>None flagged (clean topic).</div>}
          </Panel>

          <Panel title="Related entities" sub="what this connects to" span={2}>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {(data.related_entities || []).map((e, i) => (
                <span key={i} style={{ fontSize: '0.8rem', padding: '4px 11px', borderRadius: 999, background: 'oklch(0.24 0.02 270)', color: 'var(--ink-2)' }}>{e.name} <b style={{ color: 'var(--muted)' }}>{e.count}</b></span>
              ))}
            </div>
          </Panel>

          <Panel title="Top articles" span={2}>
            <div style={{ display: 'grid', gap: 9 }}>
              {(data.top_articles || []).slice(0, 8).map((a, i) => (
                <a key={i} href={a.url || '#'} target="_blank" rel="noreferrer"
                  style={{ display: 'flex', gap: 10, alignItems: 'baseline', textDecoration: 'none', color: 'var(--ink)', fontSize: '0.88rem' }}>
                  <span style={{ width: 6, height: 6, borderRadius: 999, background: TONE[a.tone] || 'var(--muted)', flexShrink: 0, marginTop: 5 }} />
                  <span style={{ flex: 1 }}>{a.headline}</span>
                  {a.age_hours != null && <span className="mono" style={{ fontSize: '0.66rem', color: 'var(--faint)' }}>{a.age_hours < 24 ? `${Math.round(a.age_hours)}h` : `${Math.round(a.age_hours / 24)}d`}</span>}
                </a>
              ))}
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}
