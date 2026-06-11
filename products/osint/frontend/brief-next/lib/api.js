// TanStack Query hooks for /api/brief/* endpoints.
// Replaces the hand-rolled useLive* hooks in brief-app/app.jsx.
import { useQuery } from '@tanstack/react-query';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8002';

async function get(path) {
  const r = await fetch(`${API_BASE}${path}`);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

export const useKpi      = () => useQuery({ queryKey: ['brief', 'kpi'],      queryFn: () => get('/api/brief/kpi') });
export const useEntities = () => useQuery({ queryKey: ['brief', 'entities'], queryFn: () => get('/api/brief/entities') });
export const useEmerging = (limit = 5) => useQuery({ queryKey: ['brief', 'emerging', limit], queryFn: () => get(`/api/brief/emerging?limit=${limit}`) });
export const useStories  = (limit = 5) => useQuery({ queryKey: ['brief', 'stories',  limit], queryFn: () => get(`/api/brief/stories?limit=${limit}`) });
