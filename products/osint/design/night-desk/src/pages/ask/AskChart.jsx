import { useEffect, useRef } from 'react';
import {
  Chart,
  LineController, BarController, DoughnutController, PieController,
  LineElement, PointElement, BarElement, ArcElement,
  CategoryScale, LinearScale, Legend, Tooltip,
} from 'chart.js';

// Register only what we use (tree-shakeable Chart.js v4 contract).
Chart.register(
  LineController, BarController, DoughnutController, PieController,
  LineElement, PointElement, BarElement, ArcElement,
  CategoryScale, LinearScale, Legend, Tooltip,
);

/**
 * Resolve a CSS custom property to a concrete color, with a fallback.
 * @param {string} name
 * @param {string} fallback
 * @returns {string}
 */
function cssVar(name, fallback) {
  const cs = getComputedStyle(document.documentElement);
  return cs.getPropertyValue(name).trim() || fallback;
}

/**
 * Build the Chart.js config from an SSE `chart` event, themed to night-desk.
 * Mirrors the legacy drawChart(): line / bar / doughnut / pie.
 * @param {Record<string, unknown>} ev
 */
function buildConfig(ev) {
  const ink = cssVar('--ink-2', '#a8a49a');
  const grid = cssVar('--line', 'rgba(150,150,170,0.2)');
  const paper = cssVar('--surface', '#120f18');
  const gold = cssVar('--gold', '#d6a23a');

  const named = { negative: cssVar('--hostile', '#d05a45'), neutral: cssVar('--faint', '#8a8577'), positive: cssVar('--supportive', '#5fbf8f'), articles: gold };
  const cycle = [gold, cssVar('--cool', '#5aa0e0'), cssVar('--supportive', '#5fbf8f'), cssVar('--faint', '#8a8577'), '#c99a4e', '#7a6fae', '#4aa3a3', '#b5683f'];

  const kind = ev.kind || 'bar';
  const pieish = kind === 'pie' || kind === 'doughnut';
  const line = kind === 'line';

  const datasets = (ev.series || []).map((s, i) => {
    const col = named[s.label] || cycle[i % cycle.length];
    if (pieish) {
      return {
        label: s.label,
        data: s.data,
        backgroundColor: s.data.map((_, j) => cycle[j % cycle.length]),
        borderColor: paper,
        borderWidth: 2,
      };
    }
    return {
      label: s.label,
      data: s.data,
      backgroundColor: line ? 'transparent' : col,
      borderColor: col,
      borderWidth: 2,
      tension: 0.3,
      fill: false,
      pointRadius: 3,
      pointBackgroundColor: col,
      borderRadius: 4,
    };
  });

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 400 },
    plugins: {
      legend: {
        display: pieish || (ev.series || []).length > 1,
        position: pieish ? 'right' : 'top',
        labels: { color: ink, boxWidth: 12, font: { size: 11 } },
      },
    },
  };
  if (!pieish) {
    options.scales = {
      x: { stacked: !!ev.stacked, ticks: { color: ink, font: { size: 11 } }, grid: { color: grid } },
      y: { stacked: !!ev.stacked, beginAtZero: true, ticks: { color: ink, font: { size: 11 }, precision: 0 }, grid: { color: grid } },
    };
  }

  return { type: kind, data: { labels: ev.labels || [], datasets }, options };
}

/**
 * @param {{ ev: Record<string, unknown> }} props
 */
export default function AskChart({ ev }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    let chart;
    try {
      chart = new Chart(canvas, buildConfig(ev));
    } catch {
      /* a malformed chart spec should never crash the page */
    }
    return () => { if (chart) chart.destroy(); };
  }, [ev]);

  return (
    <div>
      {ev.title ? <div className="ask-chart-title">{ev.title}</div> : null}
      <div className="ask-chart-wrap"><canvas ref={canvasRef} /></div>
      {ev.note ? <div className="ask-chart-note">{ev.note}</div> : null}
    </div>
  );
}
