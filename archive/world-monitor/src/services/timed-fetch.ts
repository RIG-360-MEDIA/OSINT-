/**
 * A fetch wrapper that adds a default 12s timeout to every request.
 * If the caller already passes a signal, the shorter of the two wins.
 * Used by all generated ServiceClient instances to prevent indefinite hangs.
 */
const DEFAULT_TIMEOUT_MS = 12_000;

export function timedFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const callerSignal = init?.signal ?? null;

  if (callerSignal?.aborted) {
    return Promise.reject(new DOMException('Aborted', 'AbortError'));
  }

  const timeoutController = new AbortController();
  const timerId = setTimeout(() => timeoutController.abort(), DEFAULT_TIMEOUT_MS);

  // If caller provides a signal, abort our controller when it fires too
  const onCallerAbort = () => timeoutController.abort();
  if (callerSignal) {
    callerSignal.addEventListener('abort', onCallerAbort, { once: true });
  }

  return globalThis
    .fetch(input, { ...init, signal: timeoutController.signal })
    .finally(() => {
      clearTimeout(timerId);
      if (callerSignal) {
        callerSignal.removeEventListener('abort', onCallerAbort);
      }
    });
}
