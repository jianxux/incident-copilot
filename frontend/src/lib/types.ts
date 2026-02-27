export interface Incident {
  id: string;
  incident_id: string;
  title: string;
  service: string;
  service_name: string;
  severity: 'P1' | 'P2' | 'P3' | 'P4';
  status: 'open' | 'investigating' | 'resolved' | 'closed';
  source: string;
  source_url: string;
  source_id: string;
  created_at: string;
  updated_at: string;
  triggered_at: string;
  processed_at: string | null;
}

export interface Service {
  name: string;
  tier: number;
  team: string;
  status: 'healthy' | 'degraded' | 'down';
  latency_ms: number;
  error_rate: number;
}

export interface TimelineEvent {
  id: string;
  timestamp: string;
  type: 'alert' | 'investigation' | 'action' | 'resolution' | 'deployment';
  title: string;
  description: string;
}

export interface Verdict {
  summary: string;
  root_cause_hypothesis: string;
  confidence: number;
  key_findings: string[];
  recommended_actions: string[];
  rollback_recommended: boolean;
  rollback_target?: string;
}

export interface AnalyticsData {
  mttr_trend: { date: string; mttr_minutes: number }[];
  incidents_by_severity: { severity: string; count: number }[];
  resolution_times: { service: string; avg_minutes: number }[];
}
