import { Incident, AnalyticsData, TimelineEvent, IncidentContext, PdSyncStatus } from './types';

const BASE = '';

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, { credentials: 'include', ...init });
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
  syncStatus: () => fetchJSON<PdSyncStatus>('/api/incidents/sync-status'),
  forceSync: () => fetchJSON<{ ok: boolean; status: string }>('/api/incidents/sync', { method: 'POST' }),
  analytics: () => fetchJSON<AnalyticsData>('/api/analytics'),
};
