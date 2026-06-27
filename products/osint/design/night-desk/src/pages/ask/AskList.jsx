const WHEN_MAP = { 1: 'last hour', 24: 'last 24h', 48: 'last 48h', 168: 'last 7 days', 720: 'last 30 days' };

/**
 * @param {number | undefined} h
 * @returns {string}
 */
function fmtWhen(h) {
  if (!h) return '';
  return ' · ' + (WHEN_MAP[h] || `last ${h}h`);
}

/**
 * Renders an enumerate `list` SSE event as a header + article cards.
 * @param {{ ev: Record<string, any>, onExplain: (item: Record<string, any>) => void }} props
 */
export default function AskList({ ev, onExplain }) {
  const f = ev.filters || {};
  const subj = ev.subject || null;
  const items = ev.items || [];

  let head;
  if (f.recent) {
    head = (
      <>🕒 <b>Most recent</b> article{ev.shown === 1 ? '' : 's'}
        {subj ? <> on <b>{subj}</b></> : null}{fmtWhen(f.since_hours)}, newest first</>
    );
  } else {
    head = (
      <>Found <b>{(ev.total || 0).toLocaleString()}</b> article{ev.total === 1 ? '' : 's'} on{' '}
        <b>{subj || 'the corpus'}</b>{fmtWhen(f.since_hours)}</>
    );
  }
  const langSuffix = f.languages ? ' · ' + f.languages.join('/').toUpperCase() : '';

  let note = null;
  if (f.sentiment && f.sentiment_applied) {
    note = <>Showing the <b>{ev.shown}</b> classified <b>{f.sentiment}</b> among the latest {ev.scanned}.</>;
  } else if (f.sentiment && !f.sentiment_applied) {
    note = <>Couldn&apos;t auto-classify tone — showing the latest {ev.shown}.</>;
  } else if (ev.shown < ev.total) {
    note = <>Showing the latest <b>{ev.shown}</b>.</>;
  }
  if (!items.length) note = <>No matching articles.</>;

  return (
    <div>
      <div className="ask-listhdr">
        {head}{langSuffix}
        {note ? <div className="ask-listnote">{note}</div> : null}
      </div>
      <div className="ask-lcards">
        {items.map((it, i) => {
          const date = it.published_at ? it.published_at.slice(0, 16).replace('T', ' ') : '';
          const lang = (it.language || '').toUpperCase();
          return (
            <div className="ask-lcard" key={it.id || i}>
              <div className="ask-lcard-n">{i + 1}</div>
              <div className="ask-lcard-body">
                <div className="ask-lcard-title">
                  {it.url
                    ? <a href={it.url} target="_blank" rel="noopener noreferrer">{it.title}</a>
                    : it.title}
                </div>
                <div className="ask-lcard-meta">
                  {lang ? <span>{lang}</span> : null}
                  {date ? <span>{date}</span> : null}
                </div>
                {it.snippet ? <div className="ask-lcard-snip">{it.snippet}</div> : null}
                <button type="button" className="ask-explain-btn" onClick={() => onExplain(it)}>Explain</button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
