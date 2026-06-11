// Supabase auth client + authed fetch for the OSINT backend.
// Ported from brief-next/lib/supabase.js — Vite env (import.meta.env.VITE_*)
// instead of Next's process.env.NEXT_PUBLIC_*. The osint-backend is reached
// DIRECTLY at VITE_BRIEF_API (CORS-allowed) — the vite /api proxy is reserved
// for the map's external data-source proxy (server/proxy.mjs).
import { createClient } from '@supabase/supabase-js';

const URL = import.meta.env.VITE_SUPABASE_URL;
const ANON = import.meta.env.VITE_SUPABASE_ANON_KEY;
const STORAGE_KEY = 'sb-osint-auth-token';

if (!URL || !ANON) {
  console.error('Supabase env missing: VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY');
}

/** Lock wrapper that can never wedge the auth subsystem: cap the navigator.locks
 *  wait at 5s and, if it can't acquire, run without the lock rather than hang. */
async function safeLock(name, _acquireTimeout, fn) {
  if (typeof navigator === 'undefined' || !navigator.locks) return fn();
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), 5000);
  try {
    return await navigator.locks.request(name, { mode: 'exclusive', signal: ac.signal }, () => fn());
  } catch {
    return fn();
  } finally {
    clearTimeout(timer);
  }
}

export const supabase = createClient(URL || '', ANON || '', {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: false,
    storageKey: STORAGE_KEY,
    lock: safeLock,
  },
});

export const API_BASE = import.meta.env.VITE_BRIEF_API || 'http://localhost:8002';

function withTimeout(promise, ms, label) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

function tokenFromStorage() {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed?.access_token || parsed?.currentSession?.access_token || null;
  } catch {
    return null;
  }
}

/** Resolve the current access token without ever hanging (races getSession vs a
 *  3s timeout, falls back to localStorage). */
export async function getAccessToken() {
  try {
    const { data } = await withTimeout(supabase.auth.getSession(), 3000, 'getSession');
    const token = data?.session?.access_token;
    if (token) return token;
  } catch {
    /* lock hang / SDK error → fall through to storage */
  }
  return tokenFromStorage();
}

/** Fetch wrapper that adds the Supabase access token as Bearer auth.
 *  Throws if not signed in, on a 30s timeout, or on a non-2xx response. */
export async function authFetch(path, opts = {}) {
  const token = await getAccessToken();
  if (!token) throw new Error('Not signed in');

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  let r;
  try {
    r = await fetch(`${API_BASE}${path}`, {
      ...opts,
      signal: controller.signal,
      headers: {
        ...(opts.headers || {}),
        Authorization: `Bearer ${token}`,
        'Content-Type': opts.headers?.['Content-Type'] || 'application/json',
      },
    });
  } catch (e) {
    if (e?.name === 'AbortError') throw new Error('Request timed out — backend unreachable');
    throw e;
  } finally {
    clearTimeout(timer);
  }

  let data;
  try { data = await r.json(); } catch { data = null; }
  if (!r.ok) {
    const err = new Error(data?.detail || `HTTP ${r.status}`);
    err.status = r.status;
    throw err;
  }
  return data;
}
