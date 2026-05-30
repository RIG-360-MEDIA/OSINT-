'use client';
import { useEffect, useState } from 'react';
import { supabase, authFetch, getAccessToken } from './supabase';

/**
 * Resolve the current principal via GET /api/me.
 *
 *   { loading: true }                         → still working
 *   { loading: false, me: null }              → not signed in
 *   { loading: false, me: { … } }             → signed in (may have onboarded:false)
 *   { loading: false, error: 'msg' }          → fetch failed (e.g., backend down)
 */
export function useMe() {
  const [state, setState] = useState({ loading: true, me: null, error: null });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const token = await getAccessToken();
        if (!token) {
          if (!cancelled) setState({ loading: false, me: null, error: null });
          return;
        }
        const me = await authFetch('/api/me');
        if (!cancelled) setState({ loading: false, me, error: null });
      } catch (e) {
        // An auth failure (expired/invalid session) must route the user to
        // sign-in — NOT fall through to the brief's "backend down" mock render.
        const authFail = e?.status === 401 || e?.status === 403;
        if (!cancelled) setState({ loading: false, me: null, error: authFail ? null : String(e.message || e) });
      }
    }
    load();
    // React to auth changes (signin/signout in other tabs)
    const { data: sub } = supabase.auth.onAuthStateChange(() => load());
    return () => { cancelled = true; sub?.subscription?.unsubscribe(); };
  }, []);

  return state;
}
