export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info';
export type Status = 'triggered' | 'acknowledged' | 'resolved' | 'processing';

export interface Incident {
  id: string;
  title: string;
  description?: string;
  severity: Severity;
  status: Status;
  source: string;
  service: string;
  assignee?: string;
  team?: string;
  created_at: string;
  updated_at: string;
  acknowledged_at?: string;
  resolved_at?: string;
  ttd?: number; // Time to detection (ms)
  tta?: number; // Time to acknowledge (ms)
  ttr?: number; // Time to resolve (ms)
  tags?: string[];
  labels?: Record<string, string>;
  related_incidents?: string[];
  runbooks?: Runbook[];
  context?: ContextCard;
}

export interface Runbook {
  id: string;
  title: string;
  url: string;
  source: string;
  relevance_score?: number;
}

export interface ContextCard {
  id: string;
  incident_id: string;
  created_at: string;
  github_context?: GitHubContext;
  datadog_context?: DatadogContext;
  ai_summary?: AISummary;
  similar_incidents?: SimilarIncident[];
  runbooks?: Runbook[];
  on_call?: OnCallInfo;
}

export interface GitHubContext {
  recent_commits?: Commit[];
  recent_deployments?: Deployment[];
  recent_prs?: PullRequest[];
}

export interface Commit {
  sha: string;
  message: string;
  author: string;
  timestamp: string;
  url: string;
}

export interface Deployment {
  id: string;
  environment: string;
  status: string;
  sha: string;
  description?: string;
  created_at: string;
  url: string;
}

export interface PullRequest {
  number: number;
  title: string;
  author: string;
  merged_at?: string;
  url: string;
}

export interface DatadogContext {
  logs?: LogEntry[];
  metrics?: MetricPoint[];
  traces?: Trace[];
}

export interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
  service: string;
  host?: string;
  attributes?: Record<string, unknown>;
}

export interface MetricPoint {
  name: string;
  value: number;
  timestamp: string;
  tags?: string[];
}

export interface Trace {
  trace_id: string;
  service: string;
  operation: string;
  duration_ms: number;
  status: string;
  error?: string;
}

export interface AISummary {
  summary: string;
  root_cause?: string;
  recommended_actions?: string[];
  confidence?: number;
  generated_at: string;
}

export interface SimilarIncident {
  id: string;
  title: string;
  similarity_score: number;
  resolved_at?: string;
  resolution_notes?: string;
}

export interface OnCallInfo {
  current_responder: Responder;
  escalation_chain?: Responder[];
  schedule_name?: string;
}

export interface Responder {
  id: string;
  name: string;
  email: string;
  phone?: string;
  avatar_url?: string;
}

export interface IncidentFilter {
  status?: Status[];
  severity?: Severity[];
  service?: string[];
  team?: string[];
  assignee?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
}

export interface IncidentStats {
  total: number;
  by_status: Record<Status, number>;
  by_severity: Record<Severity, number>;
  mttr_hours: number;
  mtta_minutes: number;
  incidents_today: number;
  incidents_week: number;
}

export interface TimelineEvent {
  id: string;
  incident_id: string;
  type: 'created' | 'acknowledged' | 'escalated' | 'comment' | 'runbook' | 'resolved' | 'context_added';
  description: string;
  actor?: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}
