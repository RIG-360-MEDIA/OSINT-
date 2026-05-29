'use client';
import { createClient } from '@supabase/supabase-js';

const URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const ANON = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
const STORAGE_KEY = 'sb-osint-auth-token';

if (!URL || !ANON) {
  // Will surface as a runtime error in the browser console — env not loaded.
  console.error('Supabase env missing: NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY');
}

/**
 * Lock wrapper for the auth client that can never wedge the whole subsystem.
 *
 * supabase-js's default navigator.locks lock waits indefinitely
 * (acquireTimeout = -1). A holder that never releases — e.g. a stuck refresh,
 * or a page navigation mid-lock during invite accept — then hangs every later
 * auth call forever. We cap the wait at 5s and, if we can't acquire, just run
 * without the lock rather than block. Cross-tab coordination still works in
 * the normal case; only a genuinely stuck lock is bypassed.
 */
async function safeLock(name, _acquireTimeout, fn) {
  if (typeof navigator === 'undefined' || !navigator.locks) return fn();
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), 5000);
  try {
    return await navigator.locks.request(name, { mode: 'exclusive', signal: ac.signal }, () => fn());
  } catch {
    // AbortError (contended/stuck) or unsupported → proceed without the lock.
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

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'https://robin-osi.rig360media.com/osint';

/** Reject `promise` if it doesn't settle within `ms`. */
function withTimeout(promise, ms, label) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

/** Read the persisted access token straight from localStorage (lock-free fallback). */
function tokenFromStorage() {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    // supabase-js v2 stores the session object directly; v1 nested it under currentSession.
    return parsed?.access_token || parsed?.currentSession?.access_token || null;
  } catch {
    return null;
  }
}

/**
 * Resolve the current access token WITHOUT ever hanging.
 *
 * `supabase.auth.getSession()` acquires a navigator.locks lock. A stuck lock
 * — e.g. signup calls `setSession()` then immediately `router.push()`, which
 * unmounts the page mid-lock — makes every later `getSession()` hang forever.
 * We race it against a short timeout and fall back to reading the persisted
 * session straight from localStorage so the app can never wedge.
 */
export async function getAccessToken() {
  try {
    const { data } = await withTimeout(supabase.auth.getSession(), 3000, 'getSession');
    const token = data?.session?.access_token;
    if (token) return token;
  } catch {
    // lock hang / SDK error → fall through to storage
  }
  return tokenFromStorage();
}

/**
 * Fetch wrapper that adds the user's Supabase access token as Bearer auth.
 * Throws if not signed in, on a 30s timeout, or on a non-2xx response.
 */
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
  if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
  return data;
}
