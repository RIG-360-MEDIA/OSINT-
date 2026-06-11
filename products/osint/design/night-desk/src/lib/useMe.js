// Resolve the current principal via GET /api/me. Ported from brief-next.
//   { loading:true }                  → still working
//   { loading:false, me:null }        → not signed in (show Login)
//   { loading:false, me:{…} }         → signed in
//   { loading:false, error:'msg' }    → fetch failed (e.g. backend down)
import { useEffect, useState } from 'react';
import { supabase, authFetch, getAccessToken } from './supabase';

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
        // 401/403 → not signed in (route to Login), not a "backend down" error.
        const authFail = e?.status === 401 || e?.status === 403;
        if (!cancelled) setState({ loading: false, me: null, error: authFail ? null : String(e.message || e) });
      }
    }
    load();
    const { data: sub } = supabase.auth.onAuthStateChange(() => load());
    return () => { cancelled = true; sub?.subscription?.unsubscribe(); };
  }, []);

  return state;
}
