/**
 * Generic SSE consumer using fetch + ReadableStream.
 *
 * Why not EventSource? It can't set custom headers (we need
 * Authorization: Bearer). fetch + ReadableStream gives us full control,
 * abort support via AbortController, and handles reconnect ourselves.
 *
 * Server frames: `event: <name>\ndata: <json>\n\n`
 * If event line is omitted, we treat it as event="message".
 */

export interface SSEEvent {
  event: string
  data: string
}

export interface ConsumeSSEOptions {
  url: string
  body?: unknown
  headers?: Record<string, string>
  method?: 'GET' | 'POST'
  signal?: AbortSignal
  onEvent: (evt: SSEEvent) => void
  onError?: (err: Error) => void
}

/**
 * Consume an SSE stream until the response completes or the signal aborts.
 *
 * Returns a Promise that resolves on clean stream-end, rejects on error
 * (network, non-2xx, or aborted).
 */
export async function consumeSSE(opts: ConsumeSSEOptions): Promise<void> {
  const { url, body, headers = {}, method = 'POST', signal, onEvent, onError } = opts

  const res = await fetch(url, {
    method,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
    cache: 'no-store',
  })

  if (!res.ok) {
    const err = new Error(`SSE failed: HTTP ${res.status}`)
    onError?.(err)
    throw err
  }

  const reader = res.body?.getReader()
  if (!reader) {
    const err = new Error('SSE response has no body')
    onError?.(err)
    throw err
  }

  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // Frames separated by \n\n. Process all complete frames; keep tail.
      let frameEnd = buffer.indexOf('\n\n')
      while (frameEnd !== -1) {
        const frame = buffer.slice(0, frameEnd)
        buffer = buffer.slice(frameEnd + 2)
        const evt = parseFrame(frame)
        if (evt) onEvent(evt)
        frameEnd = buffer.indexOf('\n\n')
      }
    }
  } catch (err: unknown) {
    if (err instanceof Error) {
      if (err.name === 'AbortError') return // clean abort
      onError?.(err)
      throw err
    }
    throw err
  } finally {
    try {
      reader.releaseLock()
    } catch {
      /* ignore */
    }
  }
}

function parseFrame(frame: string): SSEEvent | null {
  let event = 'message'
  const dataLines: string[] = []
  for (const rawLine of frame.split('\n')) {
    const line = rawLine.trimEnd()
    if (!line || line.startsWith(':')) continue
    if (line.startsWith('event:')) {
      event = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).replace(/^\s/, ''))
    }
  }
  if (dataLines.length === 0) return null
  return { event, data: dataLines.join('\n') }
}
