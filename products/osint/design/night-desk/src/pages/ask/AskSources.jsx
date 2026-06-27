import { useState } from 'react';

/**
 * Collapsible Sources panel. Opens on toggle, or when a parent forces it open
 * (e.g. a citation pill was clicked). The forced-open flag is additive — the
 * user can still collapse it afterwards.
 *
 * @param {{ sources: Array<Record<string, any>>, forceOpen?: boolean,
 *   hotMarker?: string | null }} props
 */
export default function AskSources({ sources, forceOpen, hotMarker }) {
  const [open, setOpen] = useState(false);
  const isOpen = open || forceOpen;
  if (!sources || !sources.length) return null;

  return (
    <div className="ask-sources">
      <button
        type="button"
        className={'ask-sources-summary' + (isOpen ? ' open' : '')}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={isOpen}
      >
        <span className="ask-car">▶</span> Sources ({sources.length})
      </button>
      {isOpen ? (
        <div className="ask-srclist">
          {sources.map((s) => {
            const date = s.published_at ? s.published_at.slice(0, 10) : '';
            const lang = (s.language || '').toUpperCase();
            const hot = hotMarker && s.marker === hotMarker;
            return (
              <div className={'ask-src' + (hot ? ' hot' : '')} data-src={s.marker} key={s.marker}>
                <span className="ask-n">{s.marker}</span>
                <div className="ask-body">
                  {s.url
                    ? <a className="ask-t" href={s.url} target="_blank" rel="noopener noreferrer">{s.title || s.url}</a>
                    : <span className="ask-t">{s.title || 'Untitled'}</span>}
                  <div className="ask-meta">
                    {s.kind ? <span className={'ask-badge ' + s.kind}>{s.kind}</span> : null}
                    {lang ? <span>{lang}</span> : null}
                    {date ? <span>{date}</span> : null}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
