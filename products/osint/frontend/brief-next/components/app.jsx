'use client';
// All page sections for RIG Intelligence Morning Brief
// Ported from brief-app/app.jsx — globals replaced with ES imports.

import React, { useState } from 'react';
import {
  Icon, Sparkline, MetricNumber, StanceDot, LanguagePill, LiveDot,
  Countdown, Reveal, SectionHead, ImageSlot, MethodPopover
} from './primitives.jsx';
import {
  SPARK, STORIES, ENTITIES, HORIZON, CLIMBING, BLINDSPOT, RECOMMENDED, nextRefreshAt
} from '../lib/data.js';
import { ExecutiveRead } from './ExecutiveRead.jsx';
import { CMPerspective } from './CMPerspective.jsx';


// === Live API hook for KPI tiles (Day 1) ===
const RIG_API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8002";
function useLiveKpi() {
  const [kpi, setKpi] = React.useState({
    articlesParsed: 247, outlets: 18, languages: 3, sentiment: -0.4,
    lang_breakdown: []
  });
  React.useEffect(() => {
    let cancelled = false;
    const fetchIt = () => fetch(`${RIG_API_BASE}/api/brief/kpi`)
      .then(r => r.ok ? r.json() : null)
      .then(j => { if (j && !cancelled) setKpi(j); })
      .catch(() => {});
    fetchIt();
    const t = setInterval(fetchIt, 60000);  // refresh every 60s
    return () => { cancelled = true; clearInterval(t); };
  }, []);
  return kpi;
}

function useLiveEntities() {
  const [entities, setEntities] = React.useState(null);  // null = use static WATCHED fallback
  React.useEffect(() => {
    let cancelled = false;
    const fetchIt = () => fetch(`${RIG_API_BASE}/api/brief/entities`)
      .then(r => r.ok ? r.json() : null)
      .then(j => { if (j && j.entities && !cancelled) setEntities(j.entities); })
      .catch(() => {});
    fetchIt();
    const t = setInterval(fetchIt, 120000);  // refresh every 2 min
    return () => { cancelled = true; clearInterval(t); };
  }, []);
  return entities;
}

function useLiveEmerging() {
  const [signals, setSignals] = React.useState(null);  // null = use static EMERGING_SIGNALS fallback
  React.useEffect(() => {
    let cancelled = false;
    const fetchIt = () => fetch(`${RIG_API_BASE}/api/brief/emerging`)
      .then(r => r.ok ? r.json() : null)
      .then(j => { if (j && j.signals && !cancelled) setSignals(j.signals); })
      .catch(() => {});
    fetchIt();
    const t = setInterval(fetchIt, 60000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);
  return signals;
}

function useLiveStories() {
  const [stories, setStories] = React.useState(null);
  React.useEffect(() => {
    let cancelled = false;
    const fetchIt = () => fetch(`${RIG_API_BASE}/api/brief/stories?limit=5`)
      .then(r => r.ok ? r.json() : null)
      .then(j => { if (j && j.stories && !cancelled) setStories(j.stories); })
      .catch(() => {});
    fetchIt();
    const t = setInterval(fetchIt, 120000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);
  return stories;
}

// Phase 4 endpoints — voices, climbing, horizon, mood.
// All four are auth-free read-only and follow the same null-fallback pattern.
function useLiveVoices() {
  const [v, setV] = React.useState(null);
  React.useEffect(() => {
    let c = false;
    const f = () => fetch(`${RIG_API_BASE}/api/brief/voices?limit=5&since_hours=12`)
      .then(r => r.ok ? r.json() : null)
      .then(j => { if (j && !c) setV(j); }).catch(() => {});
    f(); const t = setInterval(f, 120000);
    return () => { c = true; clearInterval(t); };
  }, []);
  return v;
}

function useLiveClimbing() {
  const [climbing, setClimbing] = React.useState(null);
  React.useEffect(() => {
    let c = false;
    const f = () => fetch(`${RIG_API_BASE}/api/brief/climbing?limit=3&since_hours=4`)
      .then(r => r.ok ? r.json() : null)
      .then(j => { if (j && j.climbing && !c) setClimbing(j.climbing); }).catch(() => {});
    f(); const t = setInterval(f, 120000);
    return () => { c = true; clearInterval(t); };
  }, []);
  return climbing;
}

function useLiveHorizon() {
  const [horizon, setHorizon] = React.useState(null);
  React.useEffect(() => {
    let c = false;
    const f = () => fetch(`${RIG_API_BASE}/api/brief/horizon?days=7`)
      .then(r => r.ok ? r.json() : null)
      .then(j => { if (j && j.days && !c) setHorizon(j); }).catch(() => {});
    f(); const t = setInterval(f, 300000);  // 5-min refresh — calendar moves slowly
    return () => { c = true; clearInterval(t); };
  }, []);
  return horizon;
}

function useLiveMood() {
  const [mood, setMood] = React.useState(null);
  React.useEffect(() => {
    let c = false;
    const f = () => fetch(`${RIG_API_BASE}/api/brief/mood?since_hours=24`)
      .then(r => r.ok ? r.json() : null)
      .then(j => { if (j && !c) setMood(j); }).catch(() => {});
    f(); const t = setInterval(f, 120000);
    return () => { c = true; clearInterval(t); };
  }, []);
  return mood;
}


const stanceColor = (s) =>
  s === "supportive" ? "var(--stance-supportive)" :
  s === "critical" ? "var(--stance-critical)" : "var(--stance-neutral)";

const ringColor = (r) => ({
  violet: "#a78bfa", teal: "#5eead4", amber: "#fbbf24", rose: "#fb7185",
  emerald: "#34d399", blue: "#60a5fa", purple: "#c084fc", pink: "#f472b6",
}[r] || "#a78bfa");

// Parse "+1,240%" / "−8%" / "+12%" → numeric velocity (handles - and U+2212)
const parseVelocity = (s) =>
  parseFloat(String(s).replace(/[+,%\s]/g, "").replace("−", "-")) || 0;

// Lens triad selector: prefer Telugu / English / Hindi one each, backfill
const selectLensTriad = (lens) => {
  const te = lens.find((l) => l.lang === "telugu");
  const en = lens.find((l) => l.lang === "english");
  const hi = lens.find((l) => l.lang === "hindi");
  const triad = [te, en, hi].filter(Boolean);
  const used = new Set(triad);
  for (const l of lens) {
    if (triad.length >= 3) break;
    if (!used.has(l)) { triad.push(l); used.add(l); }
  }
  return triad.slice(0, 3);
};

// Stable id slug from a freeform name
const slugify = (s) =>
  String(s).toLowerCase().replace(/[^\w]+/g, "-").replace(/^-+|-+$/g, "");

// Smooth-scroll helper for in-page anchor clicks
const handleAnchorClick = (id, block = "start") => (e) => {
  e.preventDefault();
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: "smooth", block });
};

// ── Methodology dictionary for all <M k="..."/> trigger sites ─────
const METHODS = {
  articlesParsed: { title: "Articles Parsed", body: <><p>Total news items ingested from monitored outlets in the last 24 hours.</p><p>De-duplicated by URL canonicalization and headline similarity (cosine ≥ 0.92).</p><span className="caveat">Wire-service syndication counted once.</span></> },
  outlets:        { title: "Outlets",          body: <><p>Distinct sources contributing to today's coverage. Counts only outlets meeting the integrity threshold (≥ 60%).</p><span className="caveat">OSINT feeds and verified social handles tracked separately.</span></> },
  languages:      { title: "Languages",        body: <p>Languages represented in today's coverage volume.</p> },
  sentiment:      { title: "Sentiment",        body: <><p>Mean stance across all parsed articles, weighted by outlet reach (Alexa 14-day rolling). Range −1.0 to +1.0.</p><span className="formula">Σ(stance × log(reach)) / Σ log(reach)</span><span className="caveat">Short-form social weighted at 0.3× to prevent volume bias.</span></> },
  synthesis:      { title: "Overnight Synthesis", body: <p>Editorial summary generated from clustered article themes, ranked by composite score (mentions × reach × novelty). Cluster threshold: ≥ 5 articles in 6-hour window.</p> },

  impactVelocity: { title: "Impact Velocity",  body: <><p>Composite measure of story momentum: mention acceleration, outlet diversity, reach amplification over 6-hour window.</p><span className="formula">0.4×Δmentions + 0.3×outlet_diversity + 0.3×reach_log</span><span className="caveat">Scored against 30-day rolling baseline.</span></> },
  sentimentShift: { title: "Sentiment Shift",  body: <><p>Change in aggregate sentiment over the last 24 hours vs the previous 24, per-story across all covering outlets.</p><span className="caveat">Stories with &lt;10 articles flagged low-confidence.</span></> },
  peakTime:       { title: "Peak Time",        body: <p>Timestamp of the highest mention-density 15-minute window in the last 24 hours.</p> },
  mediaMomentum:  { title: "Media Momentum",   body: <p>Hourly mention count over the past 12 hours, normalized to the story's peak. Each bar = 1 hour.</p> },

  influenceScore: { title: "Influence Score",  body: <><p>Composite of media reach, sentiment-weighted mentions, regional traction, social amplification.</p><span className="formula">0.35×reach + 0.25×|sentiment|×mentions + 0.20×regions + 0.20×social_log</span><span className="caveat">Recalculated every 6 hours.</span></> },
  influenceDelta: { title: "Change vs Yesterday", body: <p>Percentage change in Influence Score versus the same time yesterday.</p> },
  sevenDaySent:   { title: "7-Day Sentiment",  body: <p>Rolling 7-day average sentiment across all entity mentions, weighted by outlet reach. Range −1.0 to +1.0.</p> },
  mediaVelocity:  { title: "Media Velocity",   body: <p>Mention frequency over last 48 hours relative to 30-day baseline. HIGH ≥ 2×, VERY HIGH ≥ 4×.</p> },
  regionalTrac:   { title: "Regional Traction", body: <p>Primary geography where mentions concentrate, from outlet origin + content geo-tagging of past 7 days.</p> },

  blindspotHead:  { title: "Blindspot Comparison", body: <><p>A blindspot is a high-impact story being undercovered relative to its expected coverage.</p><span className="formula">Blindspot Risk = Impact × (1 − coverage_rate)</span></> },
  gapPct:         { title: "Narrative Gap %",  body: <><p>Mean blindspot score across top 10 stories of the day. HIGH ≥ 60%, MEDIUM 30–60%, LOW &lt; 30%.</p><span className="caveat">Weighted toward stories with impact ≥ 50.</span></> },
  storiesUnder:   { title: "Stories Underreported", body: <p>Stories with impact ≥ 50 covered by &lt; 30% of monitored outlets in last 24 hours.</p> },
  covDisparity:   { title: "Coverage Disparity", body: <p>Average difference between max and min outlet coverage for top stories.</p> },
  blindUnder:     { title: "Undercoverage %",  body: <p>Percentage of monitored outlets that gave this story minimal or no coverage, weighted by reach.</p> },
  blindImpact:    { title: "Impact Score",     body: <p>Same composite as Defining Stories' Impact Velocity, scored against 30-day baseline for the category.</p> },
  outletBias:     { title: "Outlet Bias Snapshot", body: <><p>Outlets categorized using SST-7 outlet variance model, n=18, weighted by Alexa reach (14-day rolling).</p><span className="caveat">Independent verification recommended for individual classifications.</span></> },
  diversityScore: { title: "Narrative Diversity Score", body: <><p>Shannon entropy of outlet stance distribution across top 10 stories.</p><span className="formula">H = − Σ p_i log(p_i)</span><span className="caveat">7-day rolling window.</span></> },

  horizonHead:    { title: "Horizon 7 Days",   body: <p>Forward-looking event prediction combining scheduled political events, predicted reactions to current news, and signal patterns from historical periods.</p> },
  strategicRisk:  { title: "Strategic Risk",   body: <p>Composite risk for next 7 days: high-profile event count, predicted opposition pressure, historical volatility.</p> },
  confidenceLvl:  { title: "Confidence Level", body: <p>Model agreement across three forecast methods (event-based, pattern-match, sentiment-trend extrapolation).</p> },
  forecastPulse:  { title: "Forecast Pulse",   body: <p>Projected daily narrative pressure across next 7 days: scheduled event load + predicted reactions + historical analogues.</p> },

  cmSentNum:      { title: "CM Sentiment Score", body: <><p>Aggregate public sentiment toward CM across all monitored mentions in past 7 days, weighted by outlet reach and recency.</p><span className="formula">Σ(stance × reach_log × recency_decay) / Σ weights</span></> },
  cmSentDelta:    { title: "Change vs Yesterday", body: <p>Change in CM Sentiment Score over the past 24 hours.</p> },
  cmDriving:      { title: "What's Driving Conversation", body: <p>Top themes identified by topic clustering across CM-related coverage, ranked by mention share. Stance per theme = aggregate sentiment for that theme.</p> },
  oppPressure:    { title: "Opposition Pressure", body: <><p>Composite of opposition mention volume, attack intensity (negative sentiment density), coordinated messaging signals.</p><span className="caveat">Forward projection uses scheduled opposition events + predicted reactions.</span></> },

  voicesHead:     { title: "Voices Overnight", body: <p>Five quotes ranked by amplification (cross-outlet mention volume in past 24 hours). One quote per major political camp where possible. All verified against original source.</p> },
};

const M = ({ k, placement = "top" }) => {
  const m = METHODS[k];
  if (!m) return null;
  return <MethodPopover title={m.title} placement={placement}>{m.body}</MethodPopover>;
};

// Cite reference (PROMOTE-4): inline superscript [N] anchor → story rank N's lens block
const Cite = ({ n }) => {
  const id = `lens-${String(n).padStart(2, "0")}`;
  return (
    <a
      href={`#${id}`}
      className="cite"
      onClick={handleAnchorClick(id, "center")}
      aria-label={`Source ${n}`}
    >
      [{n}]
    </a>
  );
};

/* ════════════════════════════════════════════════════════════
   TOP BAR + SYSTEM STATUS BAND (cinematic intelligence chassis)
   ════════════════════════════════════════════════════════════ */
/* ATMOSPHERE LAYER — page-wide ambient signal field */
const NETWORK_NODES = [
  /* upper band */
  [200,40,1.5,0.5],[260,30,1.4,0.4],[320,70,1.6,0.55],[370,50,1.3,0.4],[420,90,1.7,0.6],
  [490,60,1.4,0.45],[555,110,1.6,0.55],[605,55,1.3,0.4],[660,130,1.5,0.5],[710,92,1.4,0.45],[760,62,1.3,0.4],
  /* middle band */
  [220,130,1.4,0.45],[285,105,1.3,0.4],[345,160,1.5,0.5],[405,180,1.4,0.45],[480,200,1.6,0.55],
  [550,170,1.4,0.45],[620,210,1.5,0.5],[680,180,1.3,0.4],[740,240,1.4,0.45],
  /* lower band */
  [305,220,1.3,0.4],[365,250,1.4,0.45],[425,230,1.3,0.4],[480,260,1.4,0.45],[560,240,1.5,0.5],
  [620,270,1.3,0.4],[680,240,1.4,0.45],[745,202,1.3,0.4],
  /* sparse extras */
  [150,80,0.8,0.25],[180,170,0.7,0.22],[460,30,0.8,0.30],[525,32,0.7,0.22],[720,152,0.7,0.22],[770,170,0.8,0.25],
  [80,110,0.6,0.20],[110,200,0.7,0.22],[400,250,0.6,0.20],
];
const NETWORK_LINES = [
  [0,1],[1,2],[2,3],[3,4],[4,5],[5,6],[6,7],[7,8],[8,9],[9,10],
  [11,12],[12,13],[13,14],[14,15],[15,16],[16,17],[17,18],[18,19],
  [20,21],[21,22],[22,23],[23,24],[24,25],[25,26],[26,27],
  [1,11],[2,12],[3,13],[4,14],[5,15],[6,16],[7,17],[8,18],[9,19],
  [13,20],[14,21],[15,22],[16,23],[17,24],[18,25],[19,26],
];
const NetworkPanel = () => (
  <svg viewBox="0 0 800 280" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
    <g className="net-lines">
      {NETWORK_LINES.map(([i, j], k) => {
        const a = NETWORK_NODES[i], b = NETWORK_NODES[j];
        if (!a || !b) return null;
        return <line key={k} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="#e9c46a" strokeOpacity="0.10" strokeWidth="0.4"/>;
      })}
    </g>
    <g className="net-nodes">
      {NETWORK_NODES.map(([x, y, r, o], i) => (
        <circle key={i} cx={x} cy={y} r={r} fill="#e9c46a" opacity={o} style={{ animationDelay: `${(i % 5) * 0.7}s` }}/>
      ))}
    </g>
  </svg>
);

/* ATMOSPHERE LAYER — page-wide ambient signal field */
const AtmosphereLayer = () => (
  <div className="atmosphere" aria-hidden="true">
    <div className="atm-grid"></div>
    <div className="atm-grid-fine"></div>
    <svg viewBox="0 0 1600 1000" preserveAspectRatio="xMidYMid slice">
      <g className="atm-drift">
        {/* Cluster A — upper left */}
        <circle className="atm-hub" cx="180" cy="220" r="1.8" fill="#e9c46a" opacity="0.6"/>
        <circle cx="260" cy="190" r="0.8" fill="#e9c46a" opacity="0.30"/>
        <circle cx="120" cy="280" r="0.8" fill="#e9c46a" opacity="0.30"/>
        <circle cx="80"  cy="180" r="0.7" fill="#e9c46a" opacity="0.25"/>
        <circle cx="300" cy="260" r="0.6" fill="#e9c46a" opacity="0.20"/>
        <line x1="180" y1="220" x2="260" y2="190" stroke="#e9c46a" strokeOpacity="0.10" strokeWidth="0.4"/>
        <line x1="180" y1="220" x2="120" y2="280" stroke="#e9c46a" strokeOpacity="0.10" strokeWidth="0.4"/>
        <line x1="180" y1="220" x2="80"  y2="180" stroke="#e9c46a" strokeOpacity="0.08" strokeWidth="0.4"/>
        <line x1="180" y1="220" x2="300" y2="260" stroke="#e9c46a" strokeOpacity="0.08" strokeWidth="0.4"/>

        {/* Cluster B — center */}
        <circle className="atm-hub h2" cx="850" cy="420" r="2" fill="#e9c46a" opacity="0.65"/>
        <circle cx="780" cy="380" r="0.8" fill="#e9c46a" opacity="0.32"/>
        <circle cx="920" cy="460" r="0.9" fill="#e9c46a" opacity="0.35"/>
        <circle cx="900" cy="360" r="0.7" fill="#5fd47b" opacity="0.32"/>
        <circle cx="800" cy="480" r="0.6" fill="#e9c46a" opacity="0.20"/>
        <line x1="850" y1="420" x2="780" y2="380" stroke="#e9c46a" strokeOpacity="0.10" strokeWidth="0.4"/>
        <line x1="850" y1="420" x2="920" y2="460" stroke="#e9c46a" strokeOpacity="0.10" strokeWidth="0.4"/>
        <line x1="850" y1="420" x2="900" y2="360" stroke="#5fd47b" strokeOpacity="0.10" strokeWidth="0.4"/>

        {/* Cluster C — right (crimson) */}
        <circle className="atm-hub h3" cx="1340" cy="320" r="1.7" fill="#c8201c" opacity="0.55"/>
        <circle cx="1420" cy="280" r="0.7" fill="#c8201c" opacity="0.28"/>
        <circle cx="1280" cy="380" r="0.7" fill="#c8201c" opacity="0.28"/>
        <circle cx="1380" cy="240" r="0.6" fill="#c8201c" opacity="0.20"/>
        <line x1="1340" y1="320" x2="1420" y2="280" stroke="#c8201c" strokeOpacity="0.10" strokeWidth="0.4"/>
        <line x1="1340" y1="320" x2="1280" y2="380" stroke="#c8201c" strokeOpacity="0.10" strokeWidth="0.4"/>

        {/* Cluster D — lower */}
        <circle className="atm-hub h4" cx="540" cy="780" r="1.6" fill="#e9c46a" opacity="0.55"/>
        <circle cx="620" cy="820" r="0.8" fill="#e9c46a" opacity="0.32"/>
        <circle cx="460" cy="840" r="0.8" fill="#e9c46a" opacity="0.30"/>
        <circle cx="700" cy="760" r="0.6" fill="#5fd47b" opacity="0.28"/>
        <line x1="540" y1="780" x2="620" y2="820" stroke="#e9c46a" strokeOpacity="0.10" strokeWidth="0.4"/>
        <line x1="540" y1="780" x2="460" y2="840" stroke="#e9c46a" strokeOpacity="0.08" strokeWidth="0.4"/>
      </g>
      <g className="atm-drift-2">
        {/* Scattered satellites */}
        <circle cx="1100" cy="180" r="0.6" fill="#e9c46a" opacity="0.20"/>
        <circle cx="380"  cy="540" r="0.6" fill="#e9c46a" opacity="0.18"/>
        <circle cx="1200" cy="700" r="0.7" fill="#e9c46a" opacity="0.22"/>
        <circle cx="200"  cy="700" r="0.7" fill="#5fd47b" opacity="0.22"/>
        <circle cx="980"  cy="780" r="0.6" fill="#e9c46a" opacity="0.18"/>
        <circle cx="60"   cy="480" r="0.6" fill="#e9c46a" opacity="0.18"/>
        <circle cx="1500" cy="540" r="0.7" fill="#c8201c" opacity="0.18"/>
        <circle cx="1480" cy="820" r="0.6" fill="#e9c46a" opacity="0.18"/>
        <circle cx="320"  cy="940" r="0.7" fill="#e9c46a" opacity="0.20"/>
      </g>
      <path
        className="atm-trail"
        d="M -100 600 Q 300 580 600 620 T 1200 540 T 1700 480"
        stroke="rgba(200,32,28,0.22)"
        fill="none"
        strokeWidth="0.6"
      />
      <path
        className="atm-trail"
        d="M -100 320 Q 400 360 800 300 T 1700 280"
        stroke="rgba(233,196,106,0.16)"
        fill="none"
        strokeWidth="0.5"
        style={{ animationDelay: "-6s" }}
      />
    </svg>
  </div>
);

const Waveform = () => (
  <svg viewBox="0 0 1200 96" preserveAspectRatio="none" aria-hidden="true">
    <defs>
      <path id="wv1" d="M 0 48 Q 75 28 150 48 T 300 48 T 450 48 T 600 48 T 750 48 T 900 48 T 1050 48 T 1200 48 T 1350 48 T 1500 48"/>
      <path id="wv2" d="M 0 48 Q 100 64 200 48 T 400 48 T 600 48 T 800 48 T 1000 48 T 1200 48 T 1400 48 T 1500 48"/>
      <path id="wv3" d="M 0 48 Q 60 36 120 48 T 240 48 T 360 48 T 480 48 T 600 48 T 720 48 T 840 48 T 960 48 T 1080 48 T 1200 48 T 1500 48"/>
      <path id="wv4" d="M 0 48 Q 80 56 160 48 T 320 48 T 480 48 T 640 48 T 800 48 T 960 48 T 1120 48 T 1280 48 T 1500 48"/>
    </defs>
    <g>
      <use href="#wv1" className="wave-line l1"/>
      <use href="#wv2" className="wave-line l2"/>
      <use href="#wv3" className="wave-line l3"/>
      <use href="#wv4" className="wave-line l4"/>
    </g>
    <g className="wave-nodes" aria-hidden="true">
      <circle className="wnode amber" cx="200" cy="48" r="1.6"/>
      <circle className="wnode amber n2" cx="500" cy="48" r="2"/>
      <circle className="wnode crimson n3" cx="800" cy="48" r="1.6"/>
      <circle className="wnode green n4" cx="1050" cy="48" r="1.4"/>
    </g>
  </svg>
);

const SystemStatusBand = () => (
  <div className="status-band">
    <div className="container">
      <div className="status-ribbon" role="status" aria-label="System status">
        <div className="cell integrity">
          <span className="gdot" aria-hidden="true"></span>
          <div className="text">
            <span className="lbl">System Online</span>
            <span className="val">Source integrity 98.7%</span>
          </div>
        </div>
        <div className="cell">
          <span className="ic-w"><Icon name="target" size={20} stroke={1.4}/></span>
          <div className="text">
            <span className="lbl">247 Sources Monitored</span>
            <span className="val">
              <span className="lang-list">
                Telugu <span className="dot"></span> English <span className="dot"></span> Hindi <span className="dot"></span> Urdu
              </span>
            </span>
          </div>
        </div>
        <div className="cell">
          <span className="ic-w"><Icon name="clock" size={20} stroke={1.4}/></span>
          <div className="text">
            <span className="lbl">Last Updated 05:42 IST</span>
            <span className="val">Tuesday, 13 May 2026</span>
          </div>
        </div>
        <div className="cell next">
          <span className="ic-w"><Icon name="refresh" size={20} stroke={1.4}/></span>
          <div className="text">
            <span className="lbl">Next Refresh In</span>
            <span className="val"><Countdown to={nextRefreshAt} bare/></span>
          </div>
        </div>
      </div>
    </div>
    <div className="status-waveform"><Waveform/></div>
    <div className="status-sweep" aria-hidden="true"></div>
  </div>
);

const TopBar = () => (
  <>
    <header className="topbar"><span className="topbar-progress" aria-hidden="true"></span>
      <div className="container topbar-inner">
        <div className="wordmark">
          <span className="rig">RIG</span>
          <span className="osint-stamp">OSINT</span>
        </div>
        <label className="ask-bar" htmlFor="ask-input">
          <span className="spark" aria-hidden="true"><Icon name="sparkle" size={16} stroke={1.4}/></span>
          <input
            id="ask-input"
            type="search"
            placeholder="Ask anything about today…"
            aria-label="Ask anything about today"
          />
          <span className="kbd" aria-hidden="true">⌘K</span>
        </label>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button type="button" className="action-pill send">
            <Icon name="send" size={13} stroke={1.8}/>
            <span className="lbl">Send Report</span>
          </button>
          <button type="button" className="action-pill icon-only" title="Export" aria-label="Export">
            <Icon name="download" size={14}/>
          </button>
          <button type="button" className="action-pill icon-only" title="Notifications" aria-label="Notifications">
            <Icon name="bell" size={14}/>
            <span className="badge-dot" aria-hidden="true"></span>
          </button>
          <button type="button" className="avatar" aria-label="Open user menu">
            M<span className="online" aria-hidden="true"></span>
          </button>
        </div>
      </div>
    </header>
    <SystemStatusBand/>
  </>
);

/* ════════════════════════════════════════════════════════════
   BRIEF MASTHEAD
   ════════════════════════════════════════════════════════════ */
const BriefMasthead = () => (
  <section className="container section brief-masthead-section" style={{ paddingBottom: 16 }}>
    <div className="brief-rule"></div>
    <header className="brief-masthead">
      <div className="brief-aura" aria-hidden="true"></div>
      <div className="brief-dust" aria-hidden="true"></div>
      <div className="brief-scan" aria-hidden="true"></div>
      <Reveal>
        <h1 className="brief-title">Morning Brief</h1>
      </Reveal>
      <Reveal delay={350}>
        <div className="brief-date">Tuesday, 13 May 2026</div>
      </Reveal>
    </header>
  </section>
);

/* ════════════════════════════════════════════════════════════
   SECTION: MOOD / LAST 24 HOURS
   ════════════════════════════════════════════════════════════ */
const KPI_ICONS = { amber: "doc", cyan: "globe", violet: "chat", rose: "trendUp" };
const KPI_COLORS = { amber: "#e9c46a", cyan: "#5eead4", violet: "#c084fc", rose: "#fb7185" };

const KpiTile = ({ label, value, format = "int", tone, spark, langStack, delay = 0, arrow, methodKey }) => {
  const color = KPI_COLORS[tone] || KPI_COLORS.amber;
  return (
    <div className={`kpi-tile ${tone}`}>
      <div className="kpi-head">
        <div className="kpi-icon">
          <Icon name={KPI_ICONS[tone] || "doc"} size={16} stroke={1.5} color={color}/>
        </div>
        <div className="kpi-label">{label}{methodKey && <M k={methodKey}/>}</div>
      </div>

      <div className="kpi-value">
        <MetricNumber value={value} format={format} duration={1100 + delay}/>
        {arrow && <span className="arrow-down">↓</span>}
      </div>

      {spark && (
        <div className="kpi-spark">
          <Sparkline values={SPARK[spark]} height={36} color={color} kpi/>
        </div>
      )}
      {langStack && (
        <div className="kpi-langs">
          <div className="ln"><span className="lk">TE</span><span className="lv">142</span></div>
          <div className="ln"><span className="lk">HI</span><span className="lv">38</span></div>
          <div className="ln"><span className="lk">EN</span><span className="lv">67</span></div>
        </div>
      )}
    </div>
  );
};

// PROMOTE-6: KTR entity-link in synthesis becomes a real anchor → its EntityCard
const ktrId = `entity-${slugify("K. T. Rama Rao")}`;
const KtrLink = ({ children }) => (
  <a href={`#${ktrId}`} className="entity-link" onClick={handleAnchorClick(ktrId)}>
    {children}
  </a>
);

const MoodSection = () => {
  return (
  <section className="container section">
    <div className="glass elevated mood-card">
      <div className="mood-scan" aria-hidden="true"></div>
      <div className="mood-glow-bl" aria-hidden="true"></div>

      {/* Operational console corner brackets */}
      <span className="cb card tl" aria-hidden="true"></span>
      <span className="cb card tr" aria-hidden="true"></span>
      <span className="cb card bl" aria-hidden="true"></span>
      <span className="cb card br" aria-hidden="true"></span>

      {/* Network panel upper-right */}
      <div className="mood-network" aria-hidden="true">
        <NetworkPanel/>
      </div>

      {/* Masthead row */}
      <header className="mood-masthead">
        <div className="masthead-left">
          <div className="masthead-spotlight" aria-hidden="true"></div>
          <div className="masthead-dust" aria-hidden="true"></div>
          <div className="mood-eyebrow">
            <span className="ebr-dot" aria-hidden="true"></span>
            <span>Daily Intelligence Synthesis</span>
          </div>
          <Reveal>
            <h1 className="mood-title">Morning Brief</h1>
          </Reveal>
          <Reveal delay={300}>
            <div className="mood-meta">
              <span>Tuesday, 13 May 2026</span>
              <span className="sep">|</span>
              <span>06:00 AM IST</span>
            </div>
          </Reveal>
        </div>
        <div className="masthead-right">
          <div className="mr-lbl">Overnight Synthesis<M k="synthesis"/></div>
          <div className="mr-val">Compiled 05:42 AM IST</div>
        </div>
      </header>

      <ExecutiveRead />

      <CMPerspective />

      <div className="mood-footer">
        <div className="mf-cell">
          <span className="ic"><Icon name="target" size={14} stroke={1.4}/></span>
          <span className="lbl">Sources Scanned</span>
          <b className="val">247</b>
          <span className="mini-spark"><Sparkline values={SPARK.articles} height={14} color="#5fd47b"/></span>
        </div>
        <div className="mf-cell langs">
          <span className="lpair"><span className="lk">TE</span><b>142</b></span>
          <span className="lpair"><span className="lk">HI</span><b>38</b></span>
          <span className="lpair"><span className="lk">EN</span><b>67</b></span>
        </div>
        <div className="mf-cell">
          <span className="ic"><Icon name="clock" size={14} stroke={1.4}/></span>
          <span className="lbl">Process Time</span>
          <b className="val">4M 22S</b>
        </div>
        <div className="mf-cell">
          <span className="ic"><Icon name="building" size={14} stroke={1.4}/></span>
          <span className="lbl">Editorial Desk</span>
          <b className="val">Hyderabad Bureau</b>
        </div>
        <div className="mf-cell refresh">
          <span className="ic"><Icon name="refresh" size={14} stroke={1.4}/></span>
          <span className="lbl">Next Refresh In</span>
          <b className="val time"><Countdown to={nextRefreshAt} bare/></b>
        </div>
      </div>
    </div>
  </section>
);
};

/* ════════════════════════════════════════════════════════════
   SECTION: TOP STORIES PANEL (overview + stories + timeline + geo + integrity)
   ════════════════════════════════════════════════════════════ */
const TOP_STORIES_DATA = [
  { rank: "01", tone: "amber", icon: "doc", headline: "Telangana Cabinet clears ₹1,500 Cr Phase 1 land acquisition", outlets: "The Hindu, Indian Express, Mint + 6 more", summary: "Cabinet approves Phase 1 clearance for strategic regional infrastructure corridor despite pending farmer consultations and legal objections.", impact: "HIGH", reach: "2.8M", timestamp: "02:14 AM IST", spark: "articles" },
  { rank: "02", tone: "cyan", icon: "globe", headline: "India pushes back on UN report over 'religious freedom'", outlets: "The Hindu, PTI, NDTV + 12 more", summary: "MEA calls report \"biased and politically motivated,\" asserts India's commitment to pluralism and constitutional values.", impact: "MEDIUM", reach: "1.3M", timestamp: "12:47 AM IST", spark: "outlets" },
  { rank: "03", tone: "rose", icon: "building", headline: "Opposition parties demand JPC on electoral bond data", outlets: "Indian Express, The Wire, Deccan Herald + 8 more", summary: "Opposition leaders write to Speaker, demand judicial probe into electoral bond disclosures and data transparency issues.", impact: "HIGH", reach: "1.9M", timestamp: "12:05 AM IST", spark: "sentiment" },
];
const KEY_DEVELOPMENTS_DATA = [
  { time: "11:45 PM", icon: "gavel",     tone: "rose",   headline: "SC hears petitions on electoral bond disclosures", desc: "Multiple petitions listed for hearing." },
  { time: "12:47 AM", icon: "doc",       tone: "cyan",   headline: "MEA response to UN report",                        desc: "Official statement issued; rejects bias allegations." },
  { time: "02:14 AM", icon: "building",  tone: "amber",  headline: "Telangana Cabinet approves land acquisition",      desc: "₹1,500 crore Phase 1 clearance approved." },
  { time: "03:30 AM", icon: "megaphone", tone: "violet", headline: "Opposition demands JPC investigation",             desc: "Joint letter submitted to Lok Sabha Speaker." },
  { time: "04:48 AM", icon: "trendUp",   tone: "green",  headline: "Markets react to overnight developments",          desc: "Nifty opens flat; sectoral volatility up." },
];
const GEO_REGIONS = [
  { name: "India",         pct: "72%", color: "#fb7185" },
  { name: "South Asia",    pct: "14%", color: "#e9c46a" },
  { name: "Global",        pct: "9%",  color: "#5eead4" },
  { name: "Other Regions", pct: "5%",  color: "rgba(255,255,255,0.5)" },
];
const SOURCE_INTEGRITY_DATA = [
  { name: "The Hindu",      icon: "doc",      pct: 92 },
  { name: "Indian Express", icon: "doc",      pct: 88 },
  { name: "Mint",           icon: "doc",      pct: 74 },
  { name: "KTR (Twitter)",  icon: "send",     pct: 42 },
  { name: "V6 News",        icon: "wave",     pct: 68 },
];
const integrityColor = (pct) => pct >= 80 ? "#5fd47b" : pct >= 60 ? "#e9c46a" : "#fb7185";

/* ════════════════════════════════════════════════════════════
   MISSING DATA & HELPERS (restored)
   ════════════════════════════════════════════════════════════ */
const BS_MATRIX_OUTLETS = ["The Hindu", "Indian Express", "Mint", "NDTV", "Times Now", "Republic", "Deccan Herald", "The Wire"];
const BS_MATRIX_ICONS = ["doc", "doc", "doc", "wave", "wave", "wave", "doc", "doc"];
const BS_MATRIX_STORIES = [
  { title: "Telangana Cabinet clears ₹1,500 Cr Phase 1 land acquisition", coverage: [2, 2, 1, 2, 2, 1, 0, 0] },
  { title: "India pushes back on UN report over 'religious freedom'",         coverage: [0, 2, 0, 0, 2, 0, 2, 0] },
  { title: "Opposition parties demand JPC on electoral bond data",            coverage: [0, 0, 1, 0, 0, 0, 2, 0] },
  { title: "Protests erupt across campuses over new education policy draft",  coverage: [0, 1, 0, 1, 2, 1, 0, 0] },
  { title: "Markets react to overnight developments; Nifty opens flat",       coverage: [2, 2, 2, 0, 0, 1, 0, 0] },
];
const TOP_BLINDSPOTS = [
  { impact: "High",   tone: "rose",   image: "images/story-03-electoral-bonds.png",      headline: "Opposition writes to Speaker on electoral bond disclosures",         undercovered: 83, score: 89, icon: "building",  hue: "rose" },
  { impact: "High",   tone: "rose",   image: "images/story-02-india-un-report.png",      headline: "UN report rebuttal: India's response and implications",              undercovered: 72, score: 76, icon: "globe",     hue: "cyan" },
  { impact: "Medium", tone: "violet", image: "images/blindspot-campus-protests.png",     headline: "Campus protests: NEP draft and student dissent",                     undercovered: 61, score: 58, icon: "megaphone", hue: "violet" },
  { impact: "Medium", tone: "amber",  image: "images/blindspot-telangana-infra.png",     headline: "Telangana land acquisition: Strategic infrastructure push",          undercovered: 55, score: 52, icon: "doc",       hue: "amber" },
];

const WATCHED = [
  { rank: "01", tone: "rose",  classification: "High Influence", name: "N. Chandrababu Naidu", init: "CN", image: "images/entity-naidu.png", party: "TDP",   region: "Andhra Pradesh", influence: 89, change: "+12%", spark: "articles", sentiment: { label: "Negative", value: "-0.42", spark: "sentiment" }, velocity: "High",      velocityBars: [3,4,5,4,6,5,7,6,8,7,9,8,10,9,11],    regionalLabel: "South India",        regionKey: "south",     quote: "We will not allow injustice to Telangana. Our fight is for people's rights.",                                       quoteCtx: "Press Meet, 12 May 2026", tag: "Opposition Leader" },
  { rank: "02", tone: "cyan",  classification: "High Influence", name: "Rahul Gandhi",         init: "RG", image: "images/entity-rahul-gandhi.png", party: "INC",   region: "National",       influence: 86, change: "+8%",  spark: "outlets",  sentiment: { label: "Neutral",  value: "+0.03", spark: "outlets"   }, velocity: "Very High", velocityBars: [4,5,6,7,6,8,9,10,9,11,10,12,13,12,14], regionalLabel: "North & West India", regionKey: "north",     quote: "Democracy is under attack. India needs institutions, not intimidation.",                                            quoteCtx: "Bharat Jodo Yatra, 11 May 2026", tag: "National Figure" },
  { rank: "03", tone: "amber", classification: "Rising",         name: "Akhilesh Yadav",       init: "AY", image: "images/entity-akhilesh-yadav.png", party: "SP",    region: "Uttar Pradesh",  influence: 72, change: "+15%", spark: "articles", sentiment: { label: "Positive", value: "+0.28", spark: "articles"  }, velocity: "High",      velocityBars: [2,3,3,4,5,4,6,5,7,8,7,9,10,9,11],     regionalLabel: "Uttar Pradesh",      regionKey: "up",        quote: "We will build an India that is fair for youth, farmers and backward communities.",                                  quoteCtx: "Rally, 10 May 2026", tag: "State Leader" },
  { rank: "04", tone: "violet",classification: "Monitor",        name: "Asaduddin Owaisi",     init: "AO", image: "images/entity-owaisi.png", party: "AIMIM", region: "Telangana",      influence: 61, change: "+5%",  spark: "outlets",  sentiment: { label: "Neutral",  value: "-0.01", spark: "outlets"   }, velocity: "Medium",    velocityBars: [3,4,3,5,4,5,4,6,5,5,4,6,5,6,5],       regionalLabel: "Telangana",          regionKey: "telangana", quote: "Equal rights, social justice and dignity for every citizen is our fight.",                                          quoteCtx: "Public Meeting, 11 May 2026", tag: "Community Voice" },
];
const weTone = (t) => ({ rose: "#fb7185", cyan: "#5eead4", amber: "#e9c46a", violet: "#c084fc" }[t] || "#e9c46a");

const WatchHeader = () => (
  <header className="we-header">
    <div className="we-header-left">
      <h2 className="we-title">Watched Entities</h2>
      <p className="we-sub">Political surveillance profiles and influence tracking.</p>
    </div>
    <aside className="we-header-quote">
      <span className="we-quote-mark" aria-hidden="true">“</span>
      <p>Power is not only what is held, but what is perceived.</p>
      <span className="we-quote-attr">— RIG Intelligence Desk</span>
    </aside>
  </header>
);

const MiniBars = ({ values, color }) => {
  const max = Math.max(...values);
  return <span className="we-bars" style={{ "--bar-color": color }}>{values.map((v, i) => <span key={i} className="we-bar" style={{ height: (v / max * 100) + "%" }}></span>)}</span>;
};

const MiniIndia = ({ regionKey, tone }) => {
  const dot = { south: { x: 20, y: 36 }, north: { x: 20, y: 12 }, telangana: { x: 22, y: 26 }, up: { x: 22, y: 14 } }[regionKey] || { x: 22, y: 26 };
  return (
    <svg viewBox="0 0 44 50" aria-hidden="true" className="we-mini-india">
      <path d="M 12 4 Q 18 2 24 5 Q 30 4 33 8 Q 36 13 33 18 Q 32 23 30 27 Q 28 33 25 39 Q 22 44 19 44 Q 16 40 14 34 Q 12 28 11 22 Q 10 16 11 10 Q 11 6 12 4 Z" fill="rgba(255,255,255,0.04)" stroke="rgba(255,255,255,0.18)" strokeWidth="0.4"/>
      <circle cx={dot.x} cy={dot.y} r="3.2" fill={tone} opacity="0.7" style={{ filter: `drop-shadow(0 0 4px ${tone})` }}/>
      <circle cx={dot.x} cy={dot.y} r="1.2" fill={tone}/>
    </svg>
  );
};

const WatchedEntityCard = ({ e }) => {
  const color = weTone(e.tone);
  return (
    <article id={`entity-${slugify(e.name)}`} className={`we-card ${e.tone}`} style={{ "--tone": color }}>
      <header className="we-card-head">
        <span className="we-rank">{e.rank}</span>
        <span className="we-classification">{e.classification}</span>
      </header>
      <h3 className="we-name">{e.name}</h3>
      <div className="we-party-line">
        <span className="we-party-name">{e.party}</span>
        <span className="we-sep">·</span>
        <span className="we-region">{e.region}</span>
      </div>
      <div className="we-portrait-row">
        <div className={`we-portrait${e.image ? ' has-img' : ''}`}>
          <span className="we-portrait-ring r1" aria-hidden="true"></span>
          <span className="we-portrait-ring r2" aria-hidden="true"></span>
          {e.image ? (
            <img className="we-portrait-photo" src={e.image} alt={e.name}/>
          ) : (
            <span className="we-portrait-face">{e.init}</span>
          )}
        </div>
        <div className="we-influence">
          <span className="we-inf-lbl">Influence Score<M k="influenceScore"/></span>
          <div className="we-inf-row">
            <div className="we-inf-num"><b>{e.influence}</b><span className="we-inf-max">/100</span></div>
            <div className="we-inf-spark"><Sparkline values={SPARK[e.spark]} height={20} color={color}/></div>
          </div>
          <div className="we-inf-change">
            <span className="we-change-arrow">↗</span>
            <span className="we-change-val">{e.change}</span>
            <span className="we-change-sub">vs yesterday<M k="influenceDelta"/></span>
          </div>
        </div>
      </div>
      <div className="we-metric">
        <div className="we-metric-head"><span className="we-metric-lbl">Sentiment Trend (7D)<M k="sevenDaySent"/></span></div>
        <div className="we-sent-row">
          <div className="we-sent-spark"><Sparkline values={SPARK[e.sentiment.spark]} height={28} color={color}/></div>
          <div className="we-sent-meta">
            <span className={`we-sent-label ${e.sentiment.label.toLowerCase()}`}>{e.sentiment.label}</span>
            <span className="we-sent-val">{e.sentiment.value}</span>
          </div>
        </div>
      </div>
      <div className="we-metric we-velocity">
        <div className="we-metric-head"><Icon name="activity" size={12} stroke={1.5}/><span className="we-metric-lbl">Media Velocity<M k="mediaVelocity"/></span><span className="we-metric-val">{e.velocity}</span></div>
        <MiniBars values={e.velocityBars} color={color}/>
      </div>
      <div className="we-metric we-regional">
        <div className="we-metric-head"><Icon name="target" size={12} stroke={1.5}/><span className="we-metric-lbl">Regional Traction<M k="regionalTrac"/></span><span className="we-metric-val">{e.regionalLabel}</span></div>
        <div className="we-regional-map"><MiniIndia regionKey={e.regionKey} tone={color}/></div>
      </div>
      <div className="we-quote-block">
        <div className="we-quote-head"><Icon name="chat" size={11} stroke={1.5}/><span>Latest Quote</span></div>
        <span className="we-quote-mark-sm" aria-hidden="true">“</span>
        <p>{e.quote}</p>
        <span className="we-quote-attr-sm">— {e.quoteCtx}</span>
      </div>
      <div className="we-tag"><Icon name="warn" size={11} stroke={1.5}/><span>{e.tag}</span></div>
    </article>
  );
};

const WatchSummary = () => (
  <div className="we-summary">
    <div className="we-summary-head">
      <span className="we-summary-ic"><Icon name="target" size={18} stroke={1.4}/></span>
      <div>
        <h4>Entities Watchlist Summary</h4>
        <p>Monitoring 24 high-impact entities across politics, institutions, and influence networks.</p>
      </div>
    </div>
    <div className="we-summary-stats">
      <div className="we-stat amber"><b>8</b><span className="lbl"><Icon name="trendUp" size={10}/>High Influence</span><span className="sub">Score &gt; 75</span></div>
      <div className="we-stat rose"><b>5</b><span className="lbl"><Icon name="trendUp" size={10}/>Rising Fast</span><span className="sub">Growth &gt; 10%</span></div>
      <div className="we-stat cyan"><b>3</b><span className="lbl"><Icon name="activity" size={10}/>Declining</span><span className="sub">Drop &gt; -10%</span></div>
      <div className="we-stat rose"><b>6</b><span className="lbl"><Icon name="warn" size={10}/>Critical Watch</span><span className="sub">High risk / volatility</span></div>
      <div className="we-stat amber"><b>2</b><span className="lbl"><Icon name="sparkle" size={10}/>Emerging</span><span className="sub">Newly detected</span></div>
    </div>
  </div>
);

const WatchFooterRail = () => (
  <div className="we-footer">
    <div className="we-footer-cell"><span className="lbl">Data Sources</span><b>247</b><span className="spark"><Sparkline values={SPARK.articles} height={14} color="#5fd47b"/></span></div>
    <div className="we-footer-cell"><span className="lbl">Classification</span><b className="mono">RIG / OSINT / LEVEL 3</b></div>
    <div className="we-footer-cell"><span className="lbl">Handler</span><b>Editorial Intelligence Desk</b></div>
    <div className="we-footer-cell refresh"><Icon name="refresh" size={12} stroke={1.5}/><span className="lbl">Next Refresh</span><b className="time"><Countdown to={nextRefreshAt} bare/></b></div>
  </div>
);

const WatchedEntities = () => {
  const _live = useLiveEntities();
  const _list = _live || WATCHED;
  return (
  <section className="container section we-section">
    <WatchHeader/>
    <div className="we-grid">
      {_list.map((e, i) => <WatchedEntityCard key={e.name || i} e={e}/>)}
    </div>
    </section>
);
};

/* ════════════════════════════════════════════════════════════
   SECTION: DEFINING STORIES
   PROMOTE-2: drill → anchor
   PROMOTE-3: lens cards → buttons w/ expand state
   ════════════════════════════════════════════════════════════ */
const LensCard = ({ outlet, lang, stance, quote, id }) => {
  const [expanded, setExpanded] = useState(false);
  return (
    <button
      type="button"
      id={id}
      className={`lens-card ${expanded ? "expanded" : ""}`}
      onClick={() => setExpanded((x) => !x)}
      aria-expanded={expanded}
      aria-label={`${outlet} perspective — ${expanded ? "collapse" : "expand"}`}
    >
      <div className="lens-top">
        <StanceDot stance={stance} size={6} />
        <span className="outlet">{outlet}</span>
      </div>
      <LanguagePill lang={lang} />
      <div className="quote">"{quote}"</div>
    </button>
  );
};

const SOURCE_LENS_DATA = {
  "01": [
    { outlet: "Eenadu",          lang: "telugu",  stance: "critical",   quote: "Land grab in the guise of development; small farmers blindsided again." },
    { outlet: "The Hindu",       lang: "english", stance: "neutral",    quote: "Cabinet clears Phase 1 amid procedural questions over consultation." },
    { outlet: "Hindustan Times", lang: "hindi",   stance: "neutral",    quote: "Telangana sarkar ne Rs 1,500 crore ki manzoori di; vipaksh ne sawal uthaye." },
  ],
  "02": [
    { outlet: "NDTV",            lang: "english", stance: "supportive", quote: "MEA rebuts UN report with sharp defense of pluralism and constitutional values." },
    { outlet: "Sakshi",          lang: "telugu",  stance: "neutral",    quote: "Bharat samaadhanam: vivekam tho prathisrupinchina prati pratistha." },
    { outlet: "Dainik Jagran",   lang: "hindi",   stance: "supportive", quote: "Bharat ne UN report ko 'pakshapati' karar diya; samvidhan ki raksha dohraayi." },
  ],
  "03": [
    { outlet: "Indian Express",  lang: "english", stance: "critical",   quote: "Opposition unified on JPC demand; coordinated push on Speaker for action." },
    { outlet: "V6 News",         lang: "telugu",  stance: "critical",   quote: "Electoral bond data petti maavataniki badaludaaru raasaru opposition netalu." },
    { outlet: "Amar Ujala",      lang: "hindi",   stance: "critical",   quote: "Vipaksh ne electoral bond data par JPC ki maang ki; Speaker ko chitthi." },
  ],
};

const CM_ISSUES = [
  { icon: "building",  tone: "green", title: "Development & Infrastructure", desc: "Strong positive narrative",       badge: "Positive" },
  { icon: "chat",      tone: "amber", title: "Employment & Youth",            desc: "Growing expectation pressure",    badge: "Neutral" },
  { icon: "warn",      tone: "rose",  title: "Law & Order",                   desc: "Rising negative sentiment",       badge: "Negative" },
  { icon: "trendUp",   tone: "rose",  title: "Price Rise / Inflation",        desc: "Public criticism increasing",     badge: "Negative" },
];

const VOICES_DATA = [
  { stance: "neutral",  speaker: "Revanth Reddy",     role: "Chief Minister · INC",     source: "Khammam Rally",  contextTag: "PRESS CONFERENCE", init: "RR", quote: "Musi rejuvenation is not a project — it is the renewal contract this government signed with the people on day one." },
  { stance: "critical", speaker: "K. T. Rama Rao",    role: "Working President · BRS",   source: "Twitter / X",    contextTag: "TWEET",            init: "KT", quote: "₹85,000 crore disappeared into Kaleshwaram pillars. Who audits the auditors of the audit committee?" },
  { stance: "critical", speaker: "Sakshi Field Desk", role: "Field reporting",               source: "Field Report",   contextTag: "FIELD REPORT",     init: "S",  quote: "Farmers in three districts still cannot access mutation records flagged for correction in February." },
  { stance: "neutral",  speaker: "Akbaruddin Owaisi", role: "AIMIM Floor Leader",            source: "Assembly",       contextTag: "PARLIAMENT",       init: "AO", quote: "Old City infrastructure deserves the same budgetary urgency the rest of the city has enjoyed for twenty years." },
  { stance: "critical", speaker: "Bandi Sanjay Kumar",role: "BJP State President",           source: "Karimnagar",     contextTag: "RALLY",            init: "BS", quote: "Congress promises in Telangana have a half-life shorter than a press conference." },
];

const DEFINING_STORIES = [
  { rank: "01", tone: "amber", image: "images/story-01-telangana-cabinet.png", categories: ["Politics", "Governance"], headline: "Telangana Cabinet clears ₹1,500 Cr Phase 1 land acquisition", summary: "Infrastructure push ahead despite farmer concerns and legal challenges.", outlets: "The Hindu, Indian Express, Mint + 6 more", impact: 89, impactLabel: "Very High", sentiment: "-18%", sentimentLabel: "Negative", sentimentSpark: "sentiment", momentumBars: [3,4,5,6,5,7,8,9,8,10,11,12], momentumLabel: "Very High", peakTime: "02:14 AM IST", thumbHue: "amber" },
  { rank: "02", tone: "cyan", image: "images/story-02-india-un-report.png", categories: ["Politics", "Diplomacy"], headline: "India pushes back on UN report over 'religious freedom'", summary: "MEA calls report 'biased and politically motivated', reasserts pluralism commitment.", outlets: "The Hindu, PTI, NDTV + 12 more", impact: 76, impactLabel: "High", sentiment: "+22%", sentimentLabel: "Positive", sentimentSpark: "outlets", momentumBars: [2,3,4,5,4,6,7,8,7,9,10,11], momentumLabel: "High", peakTime: "12:47 AM IST", thumbHue: "cyan" },
  { rank: "03", tone: "rose", image: "images/story-03-electoral-bonds.png", categories: ["Politics", "Governance"], headline: "Opposition parties demand JPC on electoral bond data", summary: "Opposition leaders write to Speaker, demand judicial probe into bond disclosures.", outlets: "Indian Express, The Wire, Deccan Herald + 8 more", impact: 71, impactLabel: "High", sentiment: "-26%", sentimentLabel: "Negative", sentimentSpark: "sentiment", momentumBars: [4,5,6,7,6,8,7,9,8,10,9,11], momentumLabel: "High", peakTime: "12:05 AM IST", thumbHue: "rose" },
  { rank: "04", tone: "violet", categories: ["Society", "Law & Order"], headline: "Protests erupt across campuses over new education policy draft", summary: "Student groups allege centralization, curb on autonomy and ideological interference.", outlets: "Scroll, The Hindu, News18 + 5 more", impact: 58, impactLabel: "Medium", sentiment: "+12%", sentimentLabel: "Positive", sentimentSpark: "articles", momentumBars: [3,4,5,4,6,5,7,8,7,9,8,10], momentumLabel: "Medium", peakTime: "03:30 AM IST", thumbHue: "violet" },
  { rank: "05", tone: "amber", categories: ["Economy", "Markets"], headline: "Markets react to overnight developments; Nifty opens flat", summary: "Global cues mixed; investors weigh political uncertainty and macro signals.", outlets: "Mint, Economic Times, CNBC TV18 + 4 more", impact: 44, impactLabel: "Medium", sentiment: "+05%", sentimentLabel: "Neutral", sentimentSpark: "outlets", momentumBars: [2,3,3,4,3,5,4,5,4,6,5,4], momentumLabel: "Low", peakTime: "04:48 AM IST", thumbHue: "gold" },
];

const EMERGING_NARRATIVES = [
  { title: "Uniform Civil Code debates", desc: "resurface in key states", score: 35 },
  { title: "Border tensions escalate", desc: "in Eastern sector", score: 32 },
  { title: "Women's safety protests", desc: "gain traction nationwide", score: 28 },
  { title: "Public sector reforms", desc: "spark political pushback", score: 26 },
];

const NARRATIVE_CATEGORIES = [
  { name: "Politics",      count: 62, pct: 44, color: "#e9c46a" },
  { name: "Governance",    count: 28, pct: 20, color: "#5eead4" },
  { name: "Economy",       count: 18, pct: 13, color: "#fbbf24" },
  { name: "Society",       count: 16, pct: 11, color: "#c084fc" },
  { name: "International", count: 10, pct: 7,  color: "#94a3b8" },
  { name: "Others",        count: 8,  pct: 5,  color: "rgba(255,255,255,0.4)" },
];

const dsTone = (t) => ({ amber: "#e9c46a", cyan: "#5eead4", rose: "#fb7185", violet: "#c084fc", gold: "#fbbf24" }[t] || "#e9c46a");

/* ════════════════════════════════════════════════════════════
   SECTION: DEFINING STORIES (rebuilt)
   ════════════════════════════════════════════════════════════ */

const DefiningStatusRail = () => (
  <div className="ds-rail">
    <div className="ds-rail-head"><Icon name="doc" size={14} stroke={1.5} color="#e9c46a"/><span>Defining Stories</span></div>
    <div className="ds-rail-cell"><Icon name="trendUp" size={13} stroke={1.5}/><span className="lbl">Stories Tracked</span><b>142</b><span className="spark"><Sparkline values={SPARK.articles} height={12} color="#e9c46a"/></span></div>
    <div className="ds-rail-cell"><Icon name="warn" size={13} stroke={1.5}/><span className="lbl">High Impact</span><b className="rose">23</b><span className="we-dot rose"></span></div>
    <div className="ds-rail-cell"><Icon name="trendUp" size={13} stroke={1.5}/><span className="lbl">Accelerating</span><b className="amber">8</b><span className="ds-acc-arrow">↗</span></div>
    <div className="ds-rail-cell"><Icon name="sparkle" size={13} stroke={1.5}/><span className="lbl">Emerging</span><b className="green">11</b><span className="we-dot green"></span><span className="we-dot green"></span></div>
    <div className="ds-rail-cell"><Icon name="clock" size={13} stroke={1.5}/><span className="lbl">Last Update</span><b>05:42 AM IST</b></div>
  </div>
);

const DefiningHeader = () => (
  <header className="ds-header">
    <div className="ds-header-left">
      <h2 className="ds-title">Defining Stories</h2>
      <p className="ds-sub">Narratives shaping the national conversation.</p>
    </div>
    <aside className="ds-header-quote">
      <span className="ds-quote-mark" aria-hidden="true">“</span>
      <p>The story is not just what happened,<br/>but what the nation believes happened.</p>
      <span className="ds-quote-attr">— RIG Intelligence Desk</span>
    </aside>
  </header>
);

const ImpactRing = ({ value, color, label }) => {
  const radius = 24;
  const C = 2 * Math.PI * radius;
  const dash = (value / 100) * C;
  return (
    <div className="ds-impact-ring">
      <svg viewBox="0 0 60 60" className="ds-ring-svg">
        <circle cx="30" cy="30" r={radius} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="2.5"/>
        <circle cx="30" cy="30" r={radius} fill="none" stroke={color} strokeWidth="2.5"
          strokeDasharray={`${dash} ${C}`} strokeLinecap="round"
          transform="rotate(-90 30 30)" style={{ filter: `drop-shadow(0 0 5px ${color})` }}/>
        <text x="30" y="32" textAnchor="middle" className="ds-ring-val">{value}</text>
        <text x="30" y="44" textAnchor="middle" className="ds-ring-max">/100</text>
      </svg>
      <div className="ds-ring-label">{label}</div>
    </div>
  );
};

const MomentumBars = ({ values, color }) => {
  const max = Math.max(...values);
  return (
    <span className="ds-bars" style={{ "--bar-color": color }}>
      {values.map((v, i) => <span key={i} className="ds-bar" style={{ height: (v / max * 100) + "%" }}></span>)}
    </span>
  );
};

const Thumbnail = ({ hue, rank }) => {
  const tones = {
    amber:  "linear-gradient(135deg, #6b4815 0%, #2a1c08 60%, #1a1208 100%)",
    cyan:   "linear-gradient(135deg, #114d4d 0%, #082828 60%, #051818 100%)",
    rose:   "linear-gradient(135deg, #5a1f24 0%, #2a0f12 60%, #180a0c 100%)",
    violet: "linear-gradient(135deg, #3e2767 0%, #1c1230 60%, #110820 100%)",
    gold:   "linear-gradient(135deg, #5a4015 0%, #2a1d08 60%, #1a1208 100%)",
  };
  return (
    <div className="ds-thumb" style={{ background: tones[hue] || tones.amber }}>
      <image-slot id={`thumb-${hue}-${rank}`} shape="rect" radius="0" placeholder="Add story image" className="ds-thumb-img"></image-slot>
      <div className="ds-thumb-overlay"></div>
      <span className="ds-thumb-icon">
        <Icon name={rank === "05" ? "trendUp" : rank === "04" ? "megaphone" : rank === "03" ? "building" : rank === "02" ? "globe" : "doc"} size={28} stroke={1.2}/>
      </span>
    </div>
  );
};

const DefiningStoryRow = ({ s }) => {
  const color = dsTone(s.tone);
  const triad = (s.lens || []).slice(0, 3);
  return (
    <article className={`ds-row ${s.tone}`} style={{ "--tone": color }} id={`story-${s.rank}`}>
      <ImageSlot kind="rect" id={`story-${s.rank}-thumb`} label="STORY IMAGE" src={s.image} className="ds-row-thumb" />
      <div className="ds-row-content">
        <div className="ds-row-head">
          <span className="ds-rank">{s.rank}</span>
          <span className="ds-rule" style={{ background: color }}></span>
          <div className="ds-cats">{s.categories.map((c, i) => <React.Fragment key={i}>{i > 0 && <span className="ds-cat-sep">·</span>}<span className="ds-cat">{c}</span></React.Fragment>)}</div>
        </div>
        <h3 className="ds-headline">{s.headline}</h3>
        <p className="ds-summary">{s.summary}</p>
        <div className="ds-outlets">
          {s.outletChips && s.outletChips.map((o, i) => <span key={i} className="ds-outlet-chip">{o}</span>)}
          <span className="ds-outlet-more">{s.outletsMore || ""}</span>
        </div>
        {triad.length > 0 && (
          <div className="ds-lens-triad" id={`lens-${s.rank}`}>
            <div className="ds-lens-head"><span>Source Lens · 3 Perspectives</span></div>
            <div className="ds-lens-row">
              {triad.map((l, i) => <LensCard key={i} id={`lens-${s.rank}-${i}`} {...l} />)}
            </div>
          </div>
        )}
        <a href={`#lens-${s.rank}`} className="drill-link" onClick={handleAnchorClick(`lens-${s.rank}`)}>
          Drill into evidence <Icon name="arrowRight" size={11} />
        </a>
      </div>
      <div className="ds-row-metrics">
        <div className="ds-impact-cell">
          <span className="ds-cell-label">Impact Velocity<M k="impactVelocity" placement="left"/></span>
          <ImpactRing value={s.impact} color={color} label={s.impactLabel}/>
        </div>
        <div className="ds-sent-cell">
          <span className="ds-cell-label">Sentiment Shift<M k="sentimentShift" placement="left"/></span>
          <div className="ds-sent-row">
            <div className="ds-sent-spark"><Sparkline values={SPARK[s.sentimentSpark]} height={22} color={color}/></div>
            <div className={`ds-sent-val ${s.sentimentLabel.toLowerCase()}`}>{s.sentiment}</div>
          </div>
          <div className="ds-sent-lbl">{s.sentimentLabel}</div>
        </div>
        <div className="ds-momentum-cell">
          <span className="ds-cell-label">Media Momentum<M k="mediaMomentum" placement="left"/></span>
          <MomentumBars values={s.momentumBars} color={color}/>
          <div className="ds-momentum-lbl">{s.momentumLabel}</div>
        </div>
        <div className="ds-peak-cell">
          <span className="ds-cell-label">Peak Time<M k="peakTime" placement="left"/></span>
          <div className="ds-peak-time">{s.peakTime.split(" ")[0]}</div>
          <div className="ds-peak-sub">{s.peakTime.split(" ").slice(1).join(" ")}</div>
        </div>
      </div>
    </article>
  );
};

const DefiningStories = () => {
  const _stories = useLiveStories();
  const _list = _stories || DEFINING_STORIES;
  return (
  <section className="container section ds-section">
    <DefiningHeader/>
    <div className="ds-rows">
      {_list.slice(0, 3).map((s, i) => <DefiningStoryRow key={i} s={{...s, lens: (s.lens && s.lens.length) ? s.lens : (SOURCE_LENS_DATA[s.rank] || [])}}/>)}
    </div>
    <button type="button" className="ts-cta ds-view-all"><Icon name="doc" size={13}/><span>View All Defining Stories</span></button>
  </section>
);
};

const CoverageMatrix = () => (
  <div className="bs-panel bs-matrix-panel">
    <header className="bs-panel-head">
      <h3>Coverage Comparison Matrix</h3>
      <p>Stories vs Outlets</p>
    </header>
    <div className="bs-matrix-wrap">
      <table className="bs-matrix">
        <thead>
          <tr>
            <th className="bs-mat-th-stories">Stories</th>
            {BS_MATRIX_OUTLETS.map((o, i) => (
              <th key={i} className="bs-mat-outlet">
                <span className="bs-mat-outlet-ic"><Icon name={BS_MATRIX_ICONS[i]} size={14} stroke={1.4}/></span>
                <span className="bs-mat-outlet-name">{o}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {BS_MATRIX_STORIES.map((s, i) => (
            <tr key={i}>
              <td className="bs-mat-story">{s.title}</td>
              {s.coverage.map((c, j) => (
                <td key={j} className="bs-mat-cell"><span className={`bs-mat-dot c${c}`}></span></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    <div className="bs-mat-legend">
      <span><span className="bs-mat-dot c2"></span>Extensive Coverage</span>
      <span><span className="bs-mat-dot c1"></span>Partial Coverage</span>
      <span><span className="bs-mat-dot c0"></span>Minimal / No Coverage</span>
    </div>
  </div>
);

const NarrativeGapOverview = () => {
  const value = 64;
  const R = 60;
  const C = Math.PI * R; // half circle
  const dash = (value / 100) * C;
  return (
    <div className="bs-panel">
      <header className="bs-panel-head">
        <h3>Narrative Gap Overview<M k="gapPct"/></h3>
        <p>Overall blindspot risk</p>
      </header>
      <div className="bs-gap-body">
        <div className="bs-gauge-wrap alert-glow tone-rose" style={{ padding: 10, borderRadius: 4 }}>
          <svg viewBox="0 0 160 100" className="bs-half-gauge">
            <path d="M 20 90 A 60 60 0 0 1 140 90" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="8" strokeLinecap="round"/>
            <path d="M 20 90 A 60 60 0 0 1 140 90" fill="none" stroke="#fb7185" strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={`${dash} ${C}`}
              style={{ filter: "drop-shadow(0 0 8px #fb7185)" }}/>
            <text x="80" y="78" textAnchor="middle" className="bs-gauge-val">{value}%</text>
            <text x="80" y="92" textAnchor="middle" className="bs-gauge-lbl">High Risk</text>
            <text x="20" y="100" textAnchor="middle" className="bs-gauge-tick">0%</text>
            <text x="140" y="100" textAnchor="middle" className="bs-gauge-tick">100%</text>
          </svg>
        </div>
        <ul className="bs-gap-metrics">
          <li><span className="lbl">Stories underreported<M k="storiesUnder"/></span><b>7</b><span className="delta rose">↗ 40%</span></li>
          <li><span className="lbl">Avg. coverage disparity<M k="covDisparity"/></span><b>64%</b><span className="delta rose">↗ 18%</span></li>
          <li><span className="lbl">Major narrative gaps</span><b>4</b><span className="delta rose">4  33%</span></li>
        </ul>
      </div>
      <div className="bs-severity">
        <div className="bs-severity-head">Gap Severity Breakdown</div>
        <div className="bs-severity-tabs">
          <div className="bs-sev rose"><div className="t">High Risk</div><div className="v">4 (40%)</div></div>
          <div className="bs-sev amber"><div className="t">Medium Risk</div><div className="v">3 (30%)</div></div>
          <div className="bs-sev green"><div className="t">Low Risk</div><div className="v">3 (30%)</div></div>
        </div>
      </div>
    </div>
  );
};

const TopBlindspotsPanel = () => (
  <div className="bs-panel">
    <header className="bs-panel-head">
      <h3>Top Blindspots</h3>
      <p>Highest impact missing stories</p>
    </header>
    <div className="bs-blindspot-list">
      {TOP_BLINDSPOTS.map((b, i) => (
        <article key={i} className={`bs-blind-card ${b.tone} ${b.impact === "High" ? "alert-glow tone-rose" : ""}`}>
          <ImageSlot kind="square" id={`blindspot-${i}`} label="BLINDSPOT" src={b.image} className="bs-blind-thumb"/>
          <div className="bs-blind-body">
            <span className={`bs-impact-tag ${b.impact.toLowerCase()}`}>{b.impact} Impact</span>
            <h4>{b.headline}</h4>
            <p className="bs-blind-meta">Undercovered by <b>{b.undercovered}%</b> of outlets<M k="blindUnder" placement="left"/></p>
            <p className="bs-blind-meta">Impact Score: <b>{b.score}/100</b><M k="blindImpact" placement="left"/></p>
          </div>
          <button type="button" className="bs-blind-icon"><Icon name={b.icon} size={14} stroke={1.4}/></button>
        </article>
      ))}
    </div>
    <button type="button" className="bs-view-all"><span>View All Blindspots</span><Icon name="arrowRight" size={11}/></button>
  </div>
);

const OutletBiasSnapshot = () => {
  const data = [
    { name: "Left Leaning",  count: 5, pct: 28, color: "#5fd47b" },
    { name: "Center",        count: 7, pct: 39, color: "#e9c46a" },
    { name: "Right Leaning", count: 6, pct: 33, color: "#fb7185" },
  ];
  const R = 38;
  const C = 2 * Math.PI * R;
  let offset = 0;
  return (
    <div className="bs-panel">
      <header className="bs-panel-head"><h3>Outlet Bias Snapshot<M k="outletBias"/></h3><p>Political leaning distribution</p></header>
      <div className="bs-bias-body">
        <svg viewBox="0 0 110 110" className="bs-donut-sm">
          <circle cx="55" cy="55" r={R} fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="10"/>
          {data.map((d, i) => {
            const len = (d.pct / 100) * C;
            const seg = <circle key={i} cx="55" cy="55" r={R} fill="none" stroke={d.color} strokeWidth="10"
              strokeDasharray={`${len} ${C - len}`} strokeDashoffset={-offset}
              transform="rotate(-90 55 55)" style={{ filter: `drop-shadow(0 0 3px ${d.color})` }}/>;
            offset += len;
            return seg;
          })}
          <text x="55" y="55" textAnchor="middle" className="bs-donut-val">18</text>
          <text x="55" y="68" textAnchor="middle" className="bs-donut-lbl">Outlets</text>
        </svg>
        <ul className="bs-bias-legend">
          {data.map((d, i) => (
            <li key={i}>
              <span className="dot" style={{ background: d.color }}></span>
              <span className="name">{d.name}</span>
              <span className="count">{d.count}</span>
              <span className="pct" style={{ color: d.color }}>({d.pct}%)</span>
            </li>
          ))}
        </ul>
      </div>
      <p className="bs-panel-foot"><Icon name="warn" size={10}/> Source: SST-7 outlet variance · n=18 outlets · weighted by Alexa reach (14d).</p>
    </div>
  );
};

const NarrativeDiversityScore = () => {
  const value = 38;
  const R = 50;
  const Cv = Math.PI * R;
  const dash = (value / 100) * Cv;
  return (
    <div className="bs-panel">
      <header className="bs-panel-head"><h3>Narrative Diversity Score<M k="diversityScore"/></h3><p>How varied is the coverage?</p></header>
      <div className="bs-diversity-body">
        <svg viewBox="0 0 140 90" className="bs-half-gauge bs-half-gauge-sm">
          <path d="M 20 80 A 50 50 0 0 1 120 80" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="7" strokeLinecap="round"/>
          <path d="M 20 80 A 50 50 0 0 1 120 80" fill="none" stroke="#e9c46a" strokeWidth="7"
            strokeLinecap="round" strokeDasharray={`${dash} ${Cv}`}
            style={{ filter: "drop-shadow(0 0 6px #e9c46a)" }}/>
          <text x="70" y="68" textAnchor="middle" className="bs-gauge-val">{value}</text>
          <text x="70" y="80" textAnchor="middle" className="bs-gauge-max">/100</text>
        </svg>
        <div className="bs-diversity-side">
          <div className="bs-diversity-label">Moderate</div>
          <div className="bs-diversity-delta">
            <span>vs yesterday</span>
            <b className="rose">-6</b>
          </div>
        </div>
      </div>
      <p className="bs-panel-foot method-note">Method: Shannon entropy of outlet stance distribution · 7-day rolling window.</p>
    </div>
  );
};

const BlindspotKeyInsights = () => {
  const items = [
    { icon: "target",   text: "Political narratives around electoral bonds are significantly underreported." },
    { icon: "activity", text: "Independent outlets show higher coverage diversity but lower reach." },
    { icon: "globe",    text: "Regional stories in South & Northeast face systematic undercoverage." },
  ];
  return (
    <div className="bs-insights">
      <h4 className="bs-insights-title">Key Insights</h4>
      <ul>
        {items.map((it, i) => (
          <li key={i}>
            <span className="ic"><Icon name={it.icon} size={14} stroke={1.5}/></span>
            <span className="t">{it.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
};

/* ════════════════════════════════════════════════════════════
   SECTION: BLINDSPOT HEADER (shared by BlindspotComparison)
   ════════════════════════════════════════════════════════════ */
const BlindspotHeader = () => (
  <header className="bs-header">
    <div className="bs-header-left">
      <h2 className="bs-title">Blindspot Comparison<M k="blindspotHead"/></h2>
      <p className="bs-sub">What different news outlets are missing.</p>
    </div>
    <aside className="bs-header-quote">
      <span className="bs-quote-mark">“</span>
      <p>What is not seen, shapes what is believed.</p>
      <span className="bs-quote-attr">— RIG Intelligence Desk</span>
    </aside>
    <button type="button" className="bs-cta"><span>View Full Blindspot Matrix</span><Icon name="externalLink" size={11}/></button>
  </header>
);

/* ════════════════════════════════════════════════════════════
   SECTION: HORIZON — NEXT 7 DAYS
   ════════════════════════════════════════════════════════════ */
const HORIZON_EVENTS = [
  { day: "May", date: "13", weekday: "Tue", icon: "building",  tone: "rose",   title: "Parliament Session Begins",     desc: "Opening day likely to set tone for political narrative cycle.",     risk: "High",   riskTone: "rose"   },
  { day: "May", date: "15", weekday: "Thu", icon: "chat",      tone: "amber",  title: "Opposition Strategy Meet",       desc: "Opposition parties expected to finalize coordinated approach.",     risk: "Medium", riskTone: "amber"  },
  { day: "May", date: "17", weekday: "Sat", icon: "megaphone", tone: "amber",  title: "Major Policy Announcement",      desc: "Potential policy move could reshape public sentiment.",             risk: "Medium", riskTone: "amber"  },
  { day: "May", date: "19", weekday: "Mon", icon: "trendUp",   tone: "cyan",   title: "Economic Data Release",          desc: "Key economic indicators may influence market & narrative.",         risk: "Low",    riskTone: "green"  },
];
const EMERGING_SIGNALS = [
  { icon: "megaphone", tone: "rose",  title: "Regional protest",     sub: "chatter rising" },
  { icon: "trendUp",   tone: "amber", title: "Fuel price narrative", sub: "resurfacing" },
  { icon: "chat",      tone: "amber", title: "Cabinet reshuffle",    sub: "speculation" },
  { icon: "target",    tone: "green", title: "Farmer union",         sub: "coordination increasing" },
  { icon: "building",  tone: "cyan",  title: "Infrastructure push",  sub: "narrative gaining traction" },
];

const HorizonHeader = () => (
  <header className="hz-header">
    <div className="hz-header-left">
      <h2 className="hz-title">Horizon — Next 7 Days<M k="horizonHead"/></h2>
      <p className="hz-sub">Forward-looking intelligence to help you stay ahead of what matters.</p>
    </div>
    <aside className="hz-header-quote">
      <span className="hz-quote-mark">“</span>
      <p>The future is shaped by signals<br/>we choose to see early.</p>
      <span className="hz-quote-attr">— RIG Intelligence Desk</span>
    </aside>
  </header>
);

const HorizonOutlook = () => (
  <div className="hz-panel hz-outlook">
    <header className="hz-panel-head">
      <h3>Horizon Outlook</h3>
      <p>Strategic forecast for the next 7 days</p>
    </header>
    <div className="hz-outlook-image" aria-hidden="true">
      <div className="hz-outlook-sky"></div>
      <div className="hz-outlook-silhouette">
        <svg viewBox="0 0 360 180" preserveAspectRatio="xMidYMax slice">
          <path d="M 0 180 L 0 130 L 30 130 L 30 115 L 60 115 L 60 100 L 90 100 L 100 75 Q 120 50 140 60 L 145 35 Q 180 18 215 35 L 220 60 Q 240 50 260 75 L 270 100 L 300 100 L 300 115 L 330 115 L 330 130 L 360 130 L 360 180 Z" fill="#0a0a0e"/>
          <rect x="178" y="10" width="2" height="28" fill="#0a0a0e"/>
          <path d="M 180 12 L 192 16 L 180 20 Z" fill="rgba(233,196,106,0.4)"/>
        </svg>
      </div>
      <div className="hz-outlook-vignette"></div>
    </div>
    <h4 className="hz-outlook-statement">Parliament session likely to dominate narrative cycles through Thursday.</h4>
    <p className="hz-outlook-detail">Opposition coordination expected to intensify before weekend.</p>
    <div className="hz-outlook-metrics">
      <div className="hz-metric rose"><span className="lbl">Strategic Risk<M k="strategicRisk"/></span><div className="val-row"><Icon name="warn" size={13} stroke={1.5}/><b>High</b></div><span className="sub">Elevated Political Activity</span></div>
      <div className="hz-metric amber"><span className="lbl">Narrative Pressure</span><div className="val-row"><Icon name="activity" size={13} stroke={1.5}/><b>Rising</b></div><span className="sub">Increasing Intensity</span></div>
      <div className="hz-metric amber"><span className="lbl">Confidence Level<M k="confidenceLvl"/></span><div className="val-row"><Icon name="target" size={13} stroke={1.5}/><b>72%</b></div><span className="sub">Moderate to High</span></div>
    </div>
  </div>
);

// Map osint-backend event_type → boss's icon name.
const HZ_ICON_MAP = {
  cabinet: "building", approval: "chat", release: "trendUp",
  announcement: "megaphone", election: "vote", court: "scale",
  ruling: "scale", hearing: "scale", sports_result: "target",
  press_briefing: "chat", summit: "building", rally: "megaphone",
  policy_launch: "megaphone", budget: "trendUp",
};

const KeyEvents = () => {
  const liveHz = useLiveHorizon();

  // Flatten live horizon days → boss's per-event shape. Falls back to mock
  // until the API responds, or if no events are available.
  const events = React.useMemo(() => {
    if (!liveHz?.days) return HORIZON_EVENTS;
    const out = [];
    for (const day of liveHz.days) {
      if (!day.events?.length) continue;
      const dt = new Date(day.date);
      const dayLabel = dt.toLocaleString('en-US', { month: 'short' });
      const dateLabel = String(dt.getUTCDate());
      const weekdayLabel = dt.toLocaleString('en-US', { weekday: 'short' });
      for (const e of day.events) {
        const conf = e.confidence ?? 1.0;
        const risk = conf >= 0.8 ? "High" : conf >= 0.5 ? "Medium" : "Low";
        const riskTone = conf >= 0.8 ? "rose" : conf >= 0.5 ? "amber" : "green";
        out.push({
          day: dayLabel, date: dateLabel, weekday: weekdayLabel,
          icon: HZ_ICON_MAP[e.type] || "chat",
          tone: e.tone || "amber",
          title: (e.description || e.type || "").slice(0, 70),
          desc: e.source ? `via ${e.source}` : "",
          risk, riskTone,
        });
        if (out.length >= 6) break;
      }
      if (out.length >= 6) break;
    }
    return out.length ? out : HORIZON_EVENTS;
  }, [liveHz]);

  return (
    <div className="hz-panel">
      <header className="hz-panel-head"><h3>Key Events To Watch</h3><p>High-impact events shaping the week ahead</p></header>
      <div className="hz-events">
        {events.map((e, i) => (
          <article key={i} className={`hz-event ${e.tone} ${e.risk === "High" ? "alert-glow tone-rose" : ""}`}>
            <div className="hz-event-date"><span className="m">{e.day}</span><span className="d">{e.date}</span><span className="w">{e.weekday}</span></div>
            <div className="hz-event-icon"><Icon name={e.icon} size={18} stroke={1.4}/></div>
            <div className="hz-event-body"><h5>{e.title}</h5><p>{e.desc}</p></div>
            <div className="hz-event-risk"><span className="lbl">Risk</span><span className={`val ${e.riskTone}`}>{e.risk}</span><span className={`dot ${e.riskTone}`}></span></div>
          </article>
        ))}
      </div>
    </div>
  );
};

const ForecastPulse = () => {
  const points = [[10, 270],[80, 220],[150, 180],[220, 130],[290, 90],[360, 75],[430, 105],[500, 140]];
  let d = `M ${points[0][0]} ${points[0][1]}`;
  for (let i = 1; i < points.length; i++) {
    const [px, py] = points[i - 1]; const [x, y] = points[i];
    const cx = (px + x) / 2; d += ` Q ${cx} ${py}, ${x} ${y}`;
  }
  return (
    <div className="hz-panel">
      <header className="hz-panel-head"><h3>Forecast Pulse<M k="forecastPulse"/></h3><p>Projected narrative pressure over the next 7 days</p></header>
      <div className="hz-chart-wrap">
        <div className="hz-chart-axis-y"><span>High</span><span>Medium</span><span>Low</span></div>
        <div className="hz-chart-canvas">
          <svg viewBox="0 0 530 320" preserveAspectRatio="none" className="hz-forecast-svg">
            <defs>
              <linearGradient id="hz-stroke" x1="0" y1="0" x2="1" y2="0"><stop offset="0%"  stopColor="#e9c46a"/><stop offset="60%" stopColor="#fb7185"/><stop offset="100%" stopColor="#fb7185" stopOpacity="0.4"/></linearGradient>
              <linearGradient id="hz-area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%"  stopColor="#fb7185" stopOpacity="0.20"/><stop offset="100%" stopColor="#fb7185" stopOpacity="0"/></linearGradient>
            </defs>
            <line x1="0" y1="75" x2="530" y2="75" stroke="rgba(255,255,255,0.03)" strokeWidth="1"/>
            <line x1="0" y1="180" x2="530" y2="180" stroke="rgba(255,255,255,0.03)" strokeWidth="1"/>
            <line x1="0" y1="270" x2="530" y2="270" stroke="rgba(255,255,255,0.03)" strokeWidth="1"/>
            <path d={d} fill="none" stroke="url(#hz-stroke)" strokeWidth="2.5" strokeLinecap="round" style={{ filter: "drop-shadow(0 0 6px rgba(251,113,133,0.6))" }}/>
            <circle cx="290" cy="90" r="4" fill="#fb7185" style={{ filter: "drop-shadow(0 0 8px #fb7185)" }}/>
          </svg>
        </div>
      </div>
      <div className="hz-chart-axis-x">
        {[["May 12","Mon"],["May 13","Tue"],["May 14","Wed"],["May 15","Thu"],["May 16","Fri"],["May 17","Sat"],["May 18","Sun"]].map(([d, w], i) => (
          <div key={i} className="hz-x-day"><span className="d">{d}</span><span className="w">{w}</span></div>
        ))}
      </div>
      <div className="hz-forecast-callout">
        <Icon name="target" size={14} stroke={1.5}/>
        <p>Narrative pressure expected to peak between <b>May 15–17</b>. Prepare for increased volatility.</p>
      </div>
    </div>
  );
};

const EmergingSignals = () => {
  const _esig = useLiveEmerging();
  const _list = _esig || EMERGING_SIGNALS;
  return (
  <div className="hz-emerging">
    <div className="hz-emerging-head">
      <span className="hz-em-title">Emerging Signals</span>
      <span className="hz-em-sub">Early signals worth monitoring</span>
    </div>
    <div className="hz-em-chips">
      {_list.map((s, i) => (
        <article key={i} className={`hz-em-chip ${s.tone}`}>
          <span className="hz-em-ic"><Icon name={s.icon} size={16} stroke={1.4}/></span>
          <div className="hz-em-text"><span className="t">{s.title}</span><span className="s">{s.sub}</span></div>
          <span className={`hz-em-dot ${s.tone}`}></span>
        </article>
      ))}
    </div>
  </div>
);
};

const Horizon7Days = () => (
  <section className="container section hz-section">
    <HorizonHeader/>
    <div className="hz-grid">
      <HorizonOutlook/>
      <KeyEvents/>
      <ForecastPulse/>
    </div>
    <EmergingSignals/>
  </section>
);

/* ════════════════════════════════════════════════════════════
   SECTION: VOICES OVERNIGHT
   ════════════════════════════════════════════════════════════ */
const stanceTone = (s) => s === "supportive" ? "green" : s === "critical" ? "rose" : "amber";

const QuoteCard = ({ q }) => (
  <article className="voice-card" data-stance={q.stance}>
    <p className="quote">"{q.quote}"</p>
    <div className="meta-row">
      <ImageSlot kind="avatar" id={`voice-${slugify(q.speaker)}`} src={q.image} className="avatar-slot"/>
      <div className="attribution">
        <span className="name">{q.speaker}</span>
        <span className="role">{q.role} · {q.source}</span>
      </div>
      <span className="source-pill">{q.contextTag}</span>
    </div>
  </article>
);

const VoicesOvernight = () => (
  <section className="container section voices-section">
    <header className="voices-header">
      <div>
        <h2 className="voices-title">Voices Overnight<M k="voicesHead"/></h2>
        <p className="voices-sub">Five quotes that defined the past 24 hours.</p>
      </div>
    </header>
    <div className="voices-grid">
      {VOICES_DATA.map((q, i) => <QuoteCard key={i} q={q}/>)}
    </div>
  </section>
);

/* ════════════════════════════════════════════════════════════
   SECTION: CM PERSPECTIVE
   ════════════════════════════════════════════════════════════ */
const CmHeader = () => (
  <header className="cm-header">
    <div className="cm-header-left">
      <h2 className="cm-title">CM Perspective</h2>
      <p className="cm-sub">Public sentiment &amp; narrative intelligence</p>
    </div>
    <aside className="cm-header-quote">
      <span className="cm-quote-mark">“</span>
      <p>Perception shapes mandate.<br/>We track the pulse behind the narrative.</p>
      <span className="cm-quote-attr">— RIG Intelligence Desk</span>
    </aside>
  </header>
);

const CmInlineSentiment = () => (
  <div className="cm-inline-sent">
    <div className="cm-inline-row">
      <span className="cm-inline-lbl">Sentiment</span>
      <b className="cm-inline-val">62<span className="cm-inline-max">/100</span></b>
      <span className="cm-inline-sub">Moderately Positive</span>
      <span className="cm-inline-delta">↗ <b>+8 pts</b> vs yesterday</span>
    </div>
    <div className="cm-inline-chips">
      <span className="cm-inline-chip green"><span className="dot"></span>62% Positive</span>
      <span className="cm-inline-chip amber"><span className="dot"></span>25% Neutral</span>
      <span className="cm-inline-chip rose"><span className="dot"></span>13% Negative</span>
    </div>
  </div>
);

const CmDriving = () => (
  <div className="cm-panel cm-driving">
    <header className="cm-panel-head">
      <h3>What's Driving Conversation<M k="cmDriving"/></h3>
      <p>Top issues shaping CM perception</p>
    </header>
    <div className="cm-issues">
      {CM_ISSUES.map((i, k) => (
        <article key={k} className={`cm-issue ${i.tone}`}>
          <span className="cm-issue-ic"><Icon name={i.icon} size={18} stroke={1.4}/></span>
          <div className="cm-issue-body">
            <h4>{i.title}</h4>
            <p>{i.desc}</p>
          </div>
          <span className={`cm-badge ${i.tone}`}>{i.badge}</span>
        </article>
      ))}
    </div>
    <a href="#" className="cm-view-all" onClick={(e) => e.preventDefault()}>View All Issues <Icon name="arrowRight" size={11}/></a>
  </div>
);

const CmOppPressure = () => (
  <div className="cm-opp-row alert-glow tone-rose">
    <span className="cm-opp-lbl">Opposition Pressure<M k="oppPressure"/></span>
    <div className="cm-opp-spark"><Sparkline values={SPARK.sentiment} height={36} color="#fb7185"/></div>
    <div className="cm-opp-text">
      <b>High</b>
      <span>Likely to intensify around May 16-17</span>
    </div>
  </div>
);

const CM_MEDIA_VOICES = [
  { outlet: "Eenadu",         stance: "critical",   quote: "Musi rejuvenation costs raised in cabinet without addressing displacement concerns from corridor residents.",          context: "Editorial",     timestamp: "12 May, 18:40 IST" },
  { outlet: "The Hindu",      stance: "neutral",    quote: "Cabinet clearance for Phase 1 land acquisition signals commitment to infrastructure timeline despite consultations pending.", context: "Front page",  timestamp: "13 May, 02:14 IST" },
  { outlet: "Sakshi",         stance: "critical",   quote: "Farmers in three districts allege mutation records still inaccessible — administration silent.",                       context: "Field report",  timestamp: "12 May, 22:10 IST" },
  { outlet: "Times of India", stance: "supportive", quote: "Adilabad farmer-loan waiver tranche reflects continued agrarian focus from the administration.",                          context: "Politics desk", timestamp: "12 May, 16:55 IST" },
];

const CM_OPPOSITION_VOICES = [
  { speaker: "K. T. Rama Rao",          role: "Working President · BRS", quote: "₹85,000 crore disappeared into Kaleshwaram pillars. Who audits the auditors of the audit committee?",                       sourceType: "Tweet",            timestamp: "12 May, 02:14 IST" },
  { speaker: "Bandi Sanjay Kumar",      role: "State President · BJP",   quote: "Congress promises in Telangana have a half-life shorter than a press conference.",                                                 sourceType: "Rally",            timestamp: "12 May, 17:30 IST" },
  { speaker: "K. Chandrashekhar Rao",   role: "President · BRS",         quote: "This government promises rivers and delivers press notes — Telangana is owed accountability, not announcements.",          sourceType: "Press Conference", timestamp: "12 May, 14:20 IST" },
  { speaker: "Akbaruddin Owaisi",       role: "Floor Leader · AIMIM",    quote: "Old City infrastructure deserves the same budgetary urgency the rest of the city has enjoyed for twenty years.",                  sourceType: "Floor Speech",     timestamp: "12 May, 11:00 IST" },
];

const MediaVoiceItem = ({ v }) => (
  <article className="cm-voice-item">
    <div className="media-head">
      <span className={`voice-stance-dot ${v.stance}`}></span>
      <span className="outlet">{v.outlet}</span>
    </div>
    <p className="quote">"{v.quote}"</p>
    <div className="voice-footer">
      <span className="ctx">{v.context} · {v.timestamp}</span>
    </div>
  </article>
);

const OppVoiceItem = ({ v }) => (
  <article className="cm-voice-item">
    <div className="opp-head">
      <ImageSlot kind="avatar" id={`opp-${slugify(v.speaker)}`} className="avatar-slot"/>
      <div className="speaker-block">
        <span className="speaker">{v.speaker}</span>
        <span className="role">{v.role}</span>
      </div>
      <span className="source-pill">{v.sourceType}</span>
    </div>
    <p className="quote">"{v.quote}"</p>
    <div className="voice-footer">
      <span className="ctx">{v.timestamp}</span>
    </div>
  </article>
);

const CmVoicesGrid = () => (
  <div className="cm-voices-grid">
    <div className="cm-voice-column media">
      <header className="col-head">
        <span className="lbl">Media Voices</span>
        <span className="sub">How editorial desks are framing the CM today</span>
      </header>
      {CM_MEDIA_VOICES.map((v, i) => <MediaVoiceItem key={i} v={v}/>)}
    </div>
    <div className="cm-voice-column opposition">
      <header className="col-head">
        <span className="lbl">Opposition Voices</span>
        <span className="sub">Where rival political camps are pushing hardest</span>
      </header>
      {CM_OPPOSITION_VOICES.map((v, i) => <OppVoiceItem key={i} v={v}/>)}
    </div>
  </div>
);

const CmPerspective = () => (
  <section className="container section cm-section">
    <CmHeader/>
    <div className="cm-inline-summary">
      <span className="cm-sum-lbl">Sentiment<M k="cmSentNum"/></span>
      <b className="cm-sum-val">62<span className="max">/100</span></b>
      <span className="cm-sum-mid">Moderately Positive</span>
      <span className="cm-sum-sep">·</span>
      <span className="cm-sum-delta">↗ +8 pts vs yesterday<M k="cmSentDelta"/></span>
      <span className="cm-sum-sep">·</span>
      <span className="cm-sum-chip green"><span className="dot"></span>62% Positive</span>
      <span className="cm-sum-chip amber"><span className="dot"></span>25% Neutral</span>
      <span className="cm-sum-chip rose"><span className="dot"></span>13% Negative</span>
    </div>
    <CmVoicesGrid/>
    <CmDriving/>
    <CmOppPressure/>
  </section>
);

const BlindspotComparison = () => (
  <section className="container section bs-section">
    <BlindspotHeader/>
    <div className="bs-row-1">
      <CoverageMatrix/>
      <NarrativeGapOverview/>
      <TopBlindspotsPanel/>
    </div>
    <div className="bs-row-2">
      <OutletBiasSnapshot/>
      <NarrativeDiversityScore/>
      <BlindspotKeyInsights/>
    </div>
  </section>
);

/* ════════════════════════════════════════════════════════════
   FOOTER
   ════════════════════════════════════════════════════════════ */
const FooterStrip = () => (
  <footer className="container if-section">
    <div className="if-rail">
      <div className="if-brand">
        <div className="if-shield" aria-hidden="true">
          <svg viewBox="0 0 60 70" preserveAspectRatio="xMidYMid meet">
            <path d="M 30 4 L 52 14 L 52 38 Q 52 56 30 66 Q 8 56 8 38 L 8 14 Z" fill="rgba(233,196,106,0.05)" stroke="#e9c46a" strokeWidth="1.4"/>
            <text x="30" y="40" textAnchor="middle" className="if-shield-text">RIG</text>
          </svg>
        </div>
        <div className="if-brand-text">
          <h4>RIG Intelligence Desk</h4>
          <p className="if-brand-tags">Politics &bull; Policy &bull; Perception</p>
          <p className="if-brand-sub">OSINT Excellence</p>
        </div>
      </div>
      <div className="if-metric">
        <div className="if-metric-head">
          <span className="if-ic"><Icon name="wave" size={14} stroke={1.5}/></span>
          <span className="if-lbl">Sources Monitored</span>
        </div>
        <b className="if-val amber">300+</b>
        <span className="if-sub">Live OSINT Streams</span>
      </div>
      <div className="if-metric">
        <div className="if-metric-head">
          <span className="if-ic"><Icon name="activity" size={14} stroke={1.5}/></span>
          <span className="if-lbl">Narrative Volatility</span>
        </div>
        <b className="if-val rose">HIGH</b>
        <span className="if-sub">Elevated Narrative Shifts</span>
      </div>
      <div className="if-metric">
        <div className="if-metric-head">
          <span className="if-ic"><Icon name="target" size={14} stroke={1.5}/></span>
          <span className="if-lbl">Intel Confidence</span>
        </div>
        <b className="if-val amber">MODERATE TO HIGH</b>
        <span className="if-sub">Validated &amp; Cross-Checked</span>
      </div>
      <div className="if-metric">
        <div className="if-metric-head">
          <span className="if-ic"><Icon name="activity" size={14} stroke={1.5}/></span>
          <span className="if-lbl">Update Frequency</span>
        </div>
        <b className="if-val green">REAL-TIME</b>
        <span className="if-sub">Continuous Monitoring</span>
      </div>
      <div className="if-metric if-last">
        <div className="if-metric-head">
          <span className="if-ic"><Icon name="clock" size={14} stroke={1.5}/></span>
          <span className="if-lbl">Last Update</span>
        </div>
        <b className="if-val">05:42 AM IST</b>
        <span className="if-sub">Tuesday, 13 May 2026</span>
      </div>
    </div>
  </footer>
);

/* ════════════════════════════════════════════════════════════
   APP
   ════════════════════════════════════════════════════════════ */
const App = () => (
  <>
    <AtmosphereLayer/>
    <TopBar />
    <div className="shell">
      <MoodSection />
      <DefiningStories />
      <VoicesOvernight />
      <WatchedEntities />
      <BlindspotComparison />
      <Horizon7Days />
      <CmPerspective />
      <FooterStrip />
    </div>
  </>
);

export default App;
