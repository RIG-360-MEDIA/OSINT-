import { useCallback, useRef, useState } from 'react';

/**
 * @typedef {{ role: 'user' | 'assistant', content: string }} HistoryTurn
 * @typedef {{ title?: string, url?: string, marker?: string, kind?: string,
 *   language?: string, published_at?: string }} Source
 * @typedef {{
 *   id: string,
 *   q: string,
 *   status: string,
 *   answer: string,
 *   sources: Source[] | null,
 *   list: Record<string, unknown> | null,
 *   chart: Record<string, unknown> | null,
 *   error: string | null,
 *   streaming: boolean,
 * }} BotTurn
 */

const ENDPOINT = '/ask/chat';

/** Immutable patch of the last turn in a turns array. */
function patchLast(turns, patch) {
  if (!turns.length) return turns;
  const next = turns.slice();
  next[next.length - 1] = { ...next[next.length - 1], ...patch };
  return next;
}

/**
 * Drives the Ask-RIG POST-SSE chat stream.
 *
 * EventSource cannot be used (the endpoint is POST), so we read the response
 * body with a ReadableStream reader, split on the SSE frame delimiter
 * ("\n\n") and parse each `data:` line as JSON.
 *
 * Returns conversation state plus `ask` / `stop` / `reset` actions. The
 * `history` field (LLM contract: [{role, content}]) is kept in a ref so it
 * is always current when a follow-up fires.
 */
export function useAskStream() {
  const [turns, setTurns] = useState(/** @type {Array<{role:'user',content:string} | BotTurn & {role:'bot'}>} */ ([]));
  const [busy, setBusy] = useState(false);
  const historyRef = useRef(/** @type {HistoryTurn[]} */ ([]));
  const lastListItemsRef = useRef(/** @type {Array<Record<string, unknown>>} */ ([]));
  const abortRef = useRef(/** @type {AbortController | null} */ (null));
  const idRef = useRef(0);

  const stop = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
  }, []);

  const reset = useCallback(() => {
    stop();
    historyRef.current = [];
    lastListItemsRef.current = [];
    setTurns([]);
  }, [stop]);

  const ask = useCallback(async (rawQuery, opts = {}) => {
    const q = (rawQuery || '').trim();
    if (!q || abortRef.current) return;

    // typed "explain #5" → resolve to the 5th item of the last list, if any.
    let articleId = opts.articleId || null;
    if (!articleId) {
      const m = q.match(/^(?:explain|open|expand|tell me about)\s+#?(\d+)\b/i);
      const idx = m ? Number(m[1]) - 1 : -1;
      if (m && lastListItemsRef.current[idx]) articleId = lastListItemsRef.current[idx].id;
    }

    const botId = `b${idRef.current++}`;
    setTurns((t) => [
      ...t,
      { role: 'user', content: q },
      { role: 'bot', id: botId, q, status: 'Reading your question', answer: '',
        sources: null, list: null, chart: null, error: null, streaming: true },
    ]);
    setBusy(true);

    const history = historyRef.current;
    const ctl = new AbortController();
    abortRef.current = ctl;

    let raw = '';
    let gotBody = false;
    let turnSources = null;
    let listEv = null;
    let chartEv = null;

    try {
      const resp = await fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q, history, article_id: articleId }),
        signal: ctl.signal,
      });
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let buf = '';

      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let nl;
        while ((nl = buf.indexOf('\n\n')) >= 0) {
          const frame = buf.slice(0, nl);
          buf = buf.slice(nl + 2);
          const dataLine = frame.split('\n').find((l) => l.startsWith('data:'));
          if (!dataLine) continue;
          let ev;
          try { ev = JSON.parse(dataLine.slice(5).trim()); } catch { continue; }

          if (ev.type === 'status') {
            if (!gotBody) setTurns((t) => patchLast(t, { status: ev.text }));
          } else if (ev.type === 'sources') {
            turnSources = ev.sources;
            setTurns((t) => patchLast(t, { sources: ev.sources }));
          } else if (ev.type === 'token') {
            gotBody = true;
            raw += ev.text;
            setTurns((t) => patchLast(t, { answer: raw }));
          } else if (ev.type === 'list') {
            gotBody = true;
            listEv = ev;
            lastListItemsRef.current = ev.items || [];
            setTurns((t) => patchLast(t, { list: ev }));
          } else if (ev.type === 'chart') {
            gotBody = true;
            chartEv = ev;
            setTurns((t) => patchLast(t, { chart: ev }));
          } else if (ev.type === 'error') {
            raw += (raw ? '\n\n' : '') + '⚠️ ' + ev.text;
            setTurns((t) => patchLast(t, { answer: raw, error: ev.text }));
          }
          // ev.type === 'done' → loop ends when the stream closes.
        }
      }

      // Finalize history for follow-ups.
      historyRef.current = [
        ...history,
        { role: 'user', content: q },
        { role: 'assistant', content: chartEv ? '(returned a chart)'
          : listEv ? '(returned a list of matching articles)' : raw },
      ];
    } catch (err) {
      if (err.name !== 'AbortError') {
        const msg = (raw ? raw + '\n\n' : '') + '⚠️ Connection lost: ' + err.message;
        setTurns((t) => patchLast(t, { answer: msg, error: err.message }));
      } else if (!raw && !listEv && !chartEv) {
        setTurns((t) => patchLast(t, { answer: '_stopped_' }));
      }
    } finally {
      setTurns((t) => patchLast(t, { streaming: false }));
      setBusy(false);
      abortRef.current = null;
    }
  }, []);

  return { turns, busy, ask, stop, reset };
}
