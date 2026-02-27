import { Incident, AnalyticsData } from './types';

const BASE = '';

async function fetchJSON<T>(url: string): Promise<T> {
  const res = await fetch(`${BASE}${url}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const api = {
  health: () => fetchJSON<{ status: string }>('/api/health'),
  incidents: () => fetchJSON<Incident[]>('/api/incidents'),
  incident: (id: string) => fetchJSON<Incident>(`/api/incidents/${id}`),
  analytics: () => fetchJSON<AnalyticsData>('/api/analytics'),
};
