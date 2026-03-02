import { Incident, AnalyticsData, TimelineEvent, IncidentContext } from './types';

const BASE = '';

async function fetchJSON<T>(url: string): Promise<T> {
  const res = await fetch(`${BASE}${url}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const api = {
  health: () => fetchJSON<{ status: string }>('/api/health'),
  incidents: (params?: { page?: number; limit?: number; status?: string; severity?: string; search?: string }) => {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.status) query.set('status', params.status);
    if (params?.severity) query.set('severity', params.severity);
    if (params?.search) query.set('search', params.search);
    const qs = query.toString();
    return fetchJSON<{ incidents: Incident[]; total: number }>(`/api/incidents${qs ? `?${qs}` : ''}`);
  },
  incident: (id: string) => fetchJSON<Incident>(`/api/incidents/${id}`),
  incidentTimeline: (id: string) => fetchJSON<TimelineEvent[]>(`/api/incidents/${id}/timeline`),
  incidentContext: (id: string) => fetchJSON<IncidentContext>(`/api/incidents/${id}/context`),
  analytics: () => fetchJSON<AnalyticsData>('/api/analytics'),
  syncStatus: () => fetchJSON<{ last_attempt: string | null; last_success: string | null; last_error: string | null; status: string }>('/api/incidents/sync-status'),
  forceSync: () => fetch(`${BASE}/api/incidents/sync`, { method: 'POST', credentials: 'include' }).then(res => res.json()),
};
