import { motion, AnimatePresence } from 'framer-motion';

/* "what drove it" — per-outlet supportive vs critical, diverging */
function Drove({ items, note }) {
  if (!items || !items.length) return null;
  const rows = items.map((o) => ({ ...o, net: Math.round((100 * (o.pos - o.neg)) / ((o.pos + o.neg) || 1)) }));
  return (
    <div className="vr-block">
      <div className="vr-bh">What drove it <em>· supportive vs critical, by outlet</em></div>
      <div className="vr-drove">
        {rows.map((o) => {
          const neg = o.net < 0;
          return (
            <div className="vr-drow" key={o.name}>
              <span className="vr-dname">{o.name}</span>
              <span className="vr-dcount"><b className="pos">{o.pos}</b><i>·</i><b className="neg">{o.neg}</b></span>
              <span className="vr-dtrack"><i className={neg ? 'neg' : 'pos'} style={{ width: Math.min(Math.abs(o.net), 50) + '%', [neg ? 'right' : 'left']: '50%' }} /></span>
              <span className={'vr-dv ' + (neg ? 'neg' : 'pos')}>{neg ? 'hostile' : 'friendly'}</span>
            </div>
          );
        })}
      </div>
      {note && <div className="vr-note">{note}</div>}
    </div>
  );
}

/* "the receipts" — the actual articles that most produced the number */
function Receipts({ title, tone, items }) {
  if (!items || !items.length) return null;
  return (
    <div className="vr-rgroup">
      <div className={'vr-rhead ' + tone}><span className={'vr-rdot ' + tone} />{title}<em>{items.length} strongest</em></div>
      {items.map((r, i) => (
        <div className="vr-receipt" key={i}>
          <p className="vr-rgloss">{r.gloss}</p>
          <div className="vr-rmeta"><b>{r.outlet}</b><span>{r.date}</span></div>
        </div>
      ))}
    </div>
  );
}

export default function Verify({ metric, onClose }) {
  const v = metric?.verify;
  return (
    <AnimatePresence>
      {metric && v && (
        <>
          <motion.div className="drawer-scrim" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
          <motion.aside className="drawer vr" initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }} transition={{ type: 'spring', stiffness: 300, damping: 34 }}>
            <div className="vr-top">
              <div className="label gold">Verify · {metric.label}</div>
              <button className="vr-x" onClick={onClose} aria-label="Close">✕</button>
            </div>
            {metric.value != null && <h3 className="vr-num">{metric.value}</h3>}

            {/* 1 — the plain-language read */}
            <p className="vr-read">{v.read || v.definition}</p>

            {/* 2 — how the number is built */}
            {v.how && (
              <div className="vr-block">
                <div className="vr-bh">How we read this</div>
                <p className="vr-how">{v.how}</p>
              </div>
            )}

            {/* 3 — what drove it (outlet breakdown) */}
            <Drove items={v.drove} note={v.droveNote} />

            {/* 4 — the receipts: actual articles */}
            {v.receipts && (
              <div className="vr-block">
                <div className="vr-bh">The receipts <em>· the articles that most drove it</em></div>
                <Receipts title="Supportive" tone="pos" items={v.receipts.supportive} />
                <Receipts title="Critical" tone="neg" items={v.receipts.critical} />
              </div>
            )}

            {/* 5 — fine print, for the skeptic */}
            <div className="vr-fine">
              {v.source && <span><b>Source</b> {v.source}</span>}
              {v.window && <span><b>Window</b> {v.window}</span>}
              <span><b>Sample</b> n = {metric.n?.toLocaleString?.() ?? metric.n} · <em className={'conf ' + metric.confidence}>{metric.confidence}</em></span>
              {v.formula && <span className="vr-formula"><b>Query</b> <code>{v.formula}</code></span>}
            </div>
            <p className="vr-trust">Every figure traces to the rows that produced it — open any article to read the source. No black-box stats.</p>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
