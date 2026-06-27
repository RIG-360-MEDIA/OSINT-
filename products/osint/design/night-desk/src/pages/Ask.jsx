import { useEffect, useRef, useState } from 'react';
import { useAskStream } from './ask/useAskStream';
import AskAnswer from './ask/AskAnswer';
import AskSources from './ask/AskSources';
import AskList from './ask/AskList';
import AskChart from './ask/AskChart';
import '../styles/ask.css';

const EXAMPLES = [
  ['Latest in Telangana', "what's developing across the state today"],
  ['Who is Revanth Reddy', 'profile from recent coverage'],
  ['India–US trade talks', 'where things stand now'],
  ['Hyderabad metro expansion', "context + what's next"],
];

const SendIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 19V5M5 12l7-7 7 7" />
  </svg>
);
const StopIcon = () => (
  <svg viewBox="0 0 24 24" fill="currentColor"><rect x="7" y="7" width="10" height="10" rx="2.5" /></svg>
);
const PlusIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 5v14M5 12h14" />
  </svg>
);

/**
 * One bot turn: status line while working, then whichever payload arrived
 * (markdown answer + sources, an enumerate list, or a chart).
 */
function BotTurn({ turn, onExplain, onCite, citeState }) {
  const hasBody = turn.answer || turn.list || turn.chart;
  return (
    <div className="ask-msg bot">
      <div className="ask-avatar" aria-hidden="true">R</div>
      <div className="ask-turn">
        {!hasBody && turn.streaming ? (
          <div className="ask-status"><span className="ask-thinking">{turn.status}</span></div>
        ) : null}

        {turn.chart ? (
          <AskChart ev={turn.chart} />
        ) : turn.list ? (
          <AskList ev={turn.list} onExplain={onExplain} />
        ) : turn.answer ? (
          <AskAnswer text={turn.answer} streaming={turn.streaming} onCite={(m) => onCite(turn.id, m)} />
        ) : null}

        {turn.sources ? (
          <AskSources
            sources={turn.sources}
            forceOpen={citeState.turnId === turn.id}
            hotMarker={citeState.turnId === turn.id ? citeState.marker : null}
          />
        ) : null}
      </div>
    </div>
  );
}

export default function Ask() {
  const { turns, busy, ask, stop, reset } = useAskStream();
  const [value, setValue] = useState('');
  const [citeState, setCiteState] = useState({ turnId: null, marker: null });
  const [corpus, setCorpus] = useState('Live news corpus');
  const scrollRef = useRef(null);
  const inputRef = useRef(null);

  // Live corpus stat for the header pill (matches the standalone app). Best-effort:
  // falls back to the generic label if /ask/stats is unreachable.
  useEffect(() => {
    let alive = true;
    fetch('/ask/stats')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (alive && d && d.surfaceable) {
          setCorpus(`${Number(d.surfaceable).toLocaleString('en-IN')} sources · ${d.languages || 4} languages`);
        }
      })
      .catch(() => { /* keep fallback */ });
    return () => { alive = false; };
  }, []);

  // Keep the latest turn in view as tokens stream in.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns]);

  const submit = () => {
    const q = value.trim();
    if (!q || busy) return;
    setValue('');
    if (inputRef.current) inputRef.current.style.height = 'auto';
    ask(q);
  };

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const onInput = (e) => {
    setValue(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 208) + 'px';
  };

  const onChip = (text) => {
    if (busy) return;
    ask(text);
  };

  const onExplain = (item) => {
    if (busy) return;
    ask(`Explain this article: "${item.title}"`, { articleId: item.id });
  };

  const onCite = (turnId, marker) => setCiteState({ turnId, marker });

  const empty = turns.length === 0;

  return (
    <div className="askapp">
      <header className="ask-head">
        <div className="ask-brand">
          <span className="ask-mark" aria-hidden="true">R</span>
          <span className="ask-wordmark">Ask RIG</span>
        </div>
        <div className="ask-head-right">
          <span className="ask-corpus">{corpus}</span>
          <button
            type="button"
            className="ask-newchat"
            onClick={reset}
            disabled={empty || busy}
            title="Start a new chat"
            aria-label="New chat"
          >
            <PlusIcon /><span>New chat</span>
          </button>
        </div>
      </header>

      <div className="ask-scroll" ref={scrollRef}>
        <div className="ask-wrap">
          {empty ? (
            <div className="ask-hero">
              <h1>What are you tracking today?</h1>
              <p>Ask anything. I search the live news corpus, the open web, and entity
                coverage — then write a grounded, cited answer.</p>
              <div className="ask-chips">
                {EXAMPLES.map(([t, s]) => (
                  <button type="button" className="ask-chip" key={t} onClick={() => onChip(t)}>
                    <b>{t}</b><span>{s}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            turns.map((turn, i) => (
              turn.role === 'user'
                ? <div className="ask-msg user" key={`u${i}`}><div className="ask-bubble">{turn.content}</div></div>
                : <BotTurn key={turn.id} turn={turn} onExplain={onExplain} onCite={onCite} citeState={citeState} />
            ))
          )}
        </div>
      </div>

      <div className="ask-composer-wrap">
        <div className="ask-composer">
          <textarea
            ref={inputRef}
            rows={1}
            value={value}
            onChange={onInput}
            onKeyDown={onKeyDown}
            placeholder="Ask anything about the news…"
            aria-label="Ask a question"
          />
          <button
            type="button"
            className="ask-send"
            onClick={() => (busy ? stop() : submit())}
            disabled={!busy && !value.trim()}
            aria-label={busy ? 'Stop' : 'Send'}
            title={busy ? 'Stop' : 'Send'}
          >
            {busy ? <StopIcon /> : <SendIcon />}
          </button>
        </div>
        <div className="ask-foot">
          Every answer is grounded in retrieved sources — responses can be incomplete, so verify via Sources.
        </div>
      </div>
    </div>
  );
}
