'use client';
import { createClient } from '@supabase/supabase-js';

const URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const ANON = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!URL || !ANON) {
  // Will surface as a runtime error in the browser console — env not loaded.
  console.error('Supabase env missing: NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY');
}

export const supabase = createClient(URL || '', ANON || '', {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: false,
    storageKey: 'sb-osint-auth-token',
  },
});

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'https://robin-osi.rig360media.com/osint';

/**
 * Fetch wrapper that adds the user's Supabase access token as Bearer auth.
 * Throws if not signed in.
 */
export async function authFetch(path, opts = {}) {
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) throw new Error('Not signed in');
  const r = await fetch(`${API_BASE}${path}`, {
    ...opts,
    headers: {
      ...(opts.headers || {}),
      Authorization: `Bearer ${session.access_token}`,
      'Content-Type': opts.headers?.['Content-Type'] || 'application/json',
    },
  });
  let data;
  try { data = await r.json(); } catch { data = null; }
  if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
  return data;
}
