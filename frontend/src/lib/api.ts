import axios, { AxiosInstance, AxiosRequestConfig } from 'axios';
import { 
  Incident, 
  IncidentFilter, 
  IncidentStats, 
  ContextCard,
  TimelineEvent 
} from '@/types/incident';
import { AnalyticsSummary, InsightData } from '@/types/analytics';

// Create axios instance with default config
const api: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor for auth token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('auth_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Incident APIs
export const incidentApi = {
  list: async (filters?: IncidentFilter, page = 1, limit = 20) => {
    const params = { ...filters, page, limit };
    const response = await api.get<{ incidents: Incident[]; total: number }>('/incidents', { params });
    return response.data;
  },

  get: async (id: string) => {
    const response = await api.get<Incident>(`/incidents/${id}`);
    return response.data;
  },

  acknowledge: async (id: string) => {
    const response = await api.post<Incident>(`/incidents/${id}/acknowledge`);
    return response.data;
  },

  resolve: async (id: string, resolution?: string) => {
    const response = await api.post<Incident>(`/incidents/${id}/resolve`, { resolution });
    return response.data;
  },

  escalate: async (id: string, to?: string) => {
    const response = await api.post<Incident>(`/incidents/${id}/escalate`, { to });
    return response.data;
  },

  addNote: async (id: string, note: string) => {
    const response = await api.post(`/incidents/${id}/notes`, { content: note });
    return response.data;
  },

  getContext: async (id: string) => {
    const response = await api.get<ContextCard>(`/incidents/${id}/context`);
    return response.data;
  },

  getTimeline: async (id: string) => {
    const response = await api.get<TimelineEvent[]>(`/incidents/${id}/timeline`);
    return response.data;
  },

  getStats: async () => {
    const response = await api.get<IncidentStats>('/incidents/stats');
    return response.data;
  },

  getSimilar: async (id: string) => {
    const response = await api.get<Incident[]>(`/incidents/${id}/similar`);
    return response.data;
  },
};

// Analytics APIs
export const analyticsApi = {
  getSummary: async (period: 'day' | 'week' | 'month' | 'quarter' = 'week') => {
    const response = await api.get<AnalyticsSummary>('/analytics/summary', { params: { period } });
    return response.data;
  },

  getInsights: async () => {
    const response = await api.get<InsightData[]>('/insights');
    return response.data;
  },

  getMTTR: async (period: 'day' | 'week' | 'month' = 'week') => {
    const response = await api.get('/analytics/mttr', { params: { period } });
    return response.data;
  },

  getTeamPerformance: async () => {
    const response = await api.get('/analytics/teams');
    return response.data;
  },

  getServiceHealth: async () => {
    const response = await api.get('/analytics/services');
    return response.data;
  },

  getHeatmap: async () => {
    const response = await api.get('/analytics/heatmap');
    return response.data;
  },
};

// Auth APIs
export const authApi = {
  login: async (email: string, password: string) => {
    const response = await api.post('/auth/login', { email, password });
    return response.data;
  },

  logout: async () => {
    await api.post('/auth/logout');
    localStorage.removeItem('auth_token');
  },

  me: async () => {
    const response = await api.get('/auth/me');
    return response.data;
  },

  refresh: async () => {
    const response = await api.post('/auth/refresh');
    return response.data;
  },
};

// Integration APIs
export const integrationApi = {
  list: async () => {
    const response = await api.get('/integrations');
    return response.data;
  },

  get: async (id: string) => {
    const response = await api.get(`/integrations/${id}`);
    return response.data;
  },

  test: async (id: string) => {
    const response = await api.post(`/integrations/${id}/test`);
    const payload = response.data as { ok?: boolean; details?: string } | null;
    return {
      ok: Boolean(payload?.ok),
      details: payload?.details ?? 'No test details returned',
    };
  },

  update: async (id: string, config: Record<string, unknown>) => {
    const response = await api.put(`/integrations/${id}`, config);
    return response.data;
  },

  oauthStatus: async (provider: string) => {
    const response = await api.get(`/integrations/${provider}/status`);
    const payload = response.data as {
      provider: string;
      connected: boolean;
      token_expiry: string | null;
      scopes: string[];
    } | null;
    return {
      provider,
      connected: payload?.connected === true,
      token_expiry: payload?.token_expiry ?? null,
      scopes: Array.isArray(payload?.scopes) ? payload.scopes : [],
    };
  },

  oauthDisconnect: async (provider: string) => {
    const response = await api.delete(`/integrations/${provider}/disconnect`);
    return response.data;
  },

  oauthConnect: async (provider: string) => {
    const response = await api.get(`/integrations/${provider}/connect`, {
      headers: { Accept: 'application/json' },
      maxRedirects: 0,
      validateStatus: (s: number) => s < 400,
    });
    return response.data as { redirect_url: string };
  },
};

// On-Call APIs
export const oncallApi = {
  getCurrentShift: async () => {
    const response = await api.get('/oncall/current');
    return response.data;
  },

  getSchedule: async (start: string, end: string) => {
    const response = await api.get('/oncall/schedule', { params: { start, end } });
    return response.data;
  },
};

// Health check
export const healthApi = {
  check: async () => {
    const response = await api.get('/health');
    const payload = response.data as {
      components?: Array<{
        name: string;
        status: string;
        latency_ms?: number | null;
        message?: string | null;
        details?: Record<string, unknown> | null;
      } | null>;
      [key: string]: unknown;
    } | null;
    const components = Array.isArray(payload?.components)
      ? payload.components
          .filter((component): component is NonNullable<typeof component> => component !== null)
          .map((component) => ({
            ...component,
            details: component.details ?? {},
          }))
      : [];
    return {
      ...(payload ?? {}),
      components,
    };
  },

  ready: async () => {
    const response = await api.get('/health/ready');
    return response.data;
  },
};

export default api;
