/**
 * CoverageMap — V2 Chronicle coverage visualisation.
 *
 * Renders a bar chart of article volume per time window, coloured by narrative
 * tone. Windows with detected silences get a ⊘ marker above their bar.
 * Detected silences are listed in full beneath the chart.
 *
 * Expects `windows` shaped as returned by _run_chronicle_v2:
 *   { start, end, n_articles, tone, silence, summary }[]
 */

const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

function shortDate(dateStr) {
  if (!dateStr) return '';
  const parts = dateStr.split('-');
  if (parts.length < 3) return dateStr;
  const m = parseInt(parts[1], 10);
  const d = parseInt(parts[2], 10);
  return `${MONTHS[m - 1]} ${d}`;
}

/**
 * Map Phase-1 tone string (e.g. "manufactured — coordinated burst…") to a
 * CSS class suffix. Only the first word is used; everything after a space or
 * em-dash is a prose explanation.
 */
function parseToneClass(toneStr) {
  if (!toneStr) return 'neutral';
  const word = toneStr.trim().split(/[\s—\-]/)[0].toLowerCase();
  const MAP = {
    neutral:      'neutral',
    supportive:   'supportive',
    critical:     'critical',
    alarmed:      'critical',
    manufactured: 'manufactured',
    media:        'amplifier',
  };
  return MAP[word] || 'neutral';
}

/* ── Single window bar column ─────────────────────────────────────────────── */
function WindowBar({ window, pct }) {
  const tone = parseToneClass(window.tone);
  const label = window.tone ? window.tone.split(/[\s—\-]/)[0] : 'neutral';
  const tip = [
    `${shortDate(window.start)} → ${shortDate(window.end)}`,
    `${window.n_articles} articles`,
    label,
    window.summary ? `\n${window.summary}` : '',
    window.silence ? `\nSilence: ${window.silence}` : '',
  ].filter(Boolean).join('  ·  ');

  return (
    <div className="cov-col" title={tip}>
      {/* silence marker — floats above bar */}
      <div className="cov-col-top">
        {window.silence && <span className="cov-nil">⊘</span>}
      </div>

      {/* variable-height bar */}
      <div className="cov-col-bar">
        <div
          className={`cov-bar tone-${tone}`}
          style={{ height: `${pct}%` }}
        />
      </div>

      {/* article count */}
      <span className="cov-col-n">{window.n_articles}</span>

      {/* abbreviated date */}
      <span className="cov-col-date">{shortDate(window.start)}</span>
    </div>
  );
}

/* ── Main component ───────────────────────────────────────────────────────── */
export default function CoverageMap({ windows }) {
  if (!windows?.length) return null;

  const maxN = Math.max(...windows.map((w) => w.n_articles), 1);
  const totalArticles = windows.reduce((sum, w) => sum + w.n_articles, 0);
  const silenced = windows.filter((w) => w.silence);

  return (
    <div className="cov-map">
      {/* ── Header ── */}
      <div className="cov-map-header">
        <span className="cov-map-eyebrow">COVERAGE ARC</span>
        <span className="cov-map-stat">
          {windows.length} windows · {totalArticles} articles
        </span>

        {/* tone legend */}
        <div className="cov-legend">
          {[
            { cls: 'neutral',      label: 'Neutral'      },
            { cls: 'supportive',   label: 'Supportive'   },
            { cls: 'critical',     label: 'Critical'     },
            { cls: 'manufactured', label: 'Manufactured' },
            { cls: 'amplifier',    label: 'Amplified'    },
          ].map(({ cls, label }) => (
            <span key={cls} className="cov-legend-item">
              <span className={`cov-legend-dot tone-${cls}`} />
              {label}
            </span>
          ))}
        </div>
      </div>

      {/* ── Bar chart ── */}
      <div className="cov-bars" aria-hidden="true">
        {windows.map((w, i) => {
          // min visual height 6% so tiny windows are still visible
          const pct = Math.max(6, Math.round((w.n_articles / maxN) * 100));
          return <WindowBar key={i} window={w} pct={pct} />;
        })}
      </div>

      {/* ── Axis line (drawn by CSS border-bottom on .cov-bars) ── */}

      {/* ── Detected silences ── */}
      {silenced.length > 0 && (
        <div className="cov-silences">
          <span className="cov-silences-label">SILENCES DETECTED</span>
          {silenced.map((w, i) => (
            <div key={i} className="cov-silence-row">
              <span className="cov-silence-glyph">⊘</span>
              <div className="cov-silence-body">
                <span className="cov-silence-when">
                  {shortDate(w.start)} — {shortDate(w.end)}
                </span>
                <span className="cov-silence-text">{w.silence}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
