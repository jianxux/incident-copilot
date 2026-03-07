export interface Incident {
  id: string;
  incident_id: string;
  title: string;
  description?: string | null;
  service: string;
  service_name: string;
  severity: string;
  status: string;
  source: string;
  source_url: string;
  source_id?: string;
  assignee?: string | null;
  team?: string | null;
  created_at: string;
  updated_at: string;
  triggered_at: string;
  processed_at: string | null;
  acknowledged_at?: string | null;
  resolved_at?: string | null;
  duration_seconds?: number | null;
  verdict_summary?: string | null;
  ttd?: number | null;
  tta?: number | null;
  ttr?: number | null;
  tags?: string[];
  labels?: Record<string, string>;
  related_incidents?: string[];
  runbooks?: string[];
  context?: Record<string, unknown> | null;
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
  incident_id?: string;
  timestamp: string;
  type: string;
  title?: string;
  description: string;
  actor?: string | null;
  metadata?: Record<string, unknown>;
}

export interface IncidentContext {
  id?: string;
  incident_id?: string;
  created_at?: string;
  github_context?: Record<string, unknown>;
  datadog_context?: Record<string, unknown>;
  on_call?: Record<string, unknown>;
  [key: string]: unknown;
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

export interface PdSyncStatus {
  last_attempt: string | null;
  last_success: string | null;
  last_error: string | null;
  status: 'synced' | 'syncing' | 'error' | 'never' | 'stale' | 'in_progress';
}
