export interface AnalyticsSummary {
  period: 'day' | 'week' | 'month' | 'quarter';
  incidents: IncidentMetrics;
  team_performance: TeamPerformance[];
  service_health: ServiceHealth[];
  trends: TrendData[];
}

export interface IncidentMetrics {
  total_incidents: number;
  resolved_incidents: number;
  open_incidents: number;
  mttr_hours: number;
  mtta_minutes: number;
  by_severity: {
    critical: number;
    high: number;
    medium: number;
    low: number;
    info: number;
  };
  by_source: Record<string, number>;
  change_from_previous: {
    incidents: number; // percentage
    mttr: number;
    mtta: number;
  };
}

export interface TeamPerformance {
  team_id: string;
  team_name: string;
  incidents_handled: number;
  avg_response_time_minutes: number;
  avg_resolution_time_hours: number;
  on_call_hours: number;
  escalation_rate: number;
}

export interface ServiceHealth {
  service_id: string;
  service_name: string;
  incident_count: number;
  critical_count: number;
  uptime_percentage: number;
  last_incident?: string;
  trend: 'improving' | 'stable' | 'degrading';
}

export interface TrendData {
  date: string;
  incidents: number;
  resolved: number;
  mttr_hours: number;
  mtta_minutes: number;
}

export interface HeatmapData {
  day_of_week: number; // 0-6
  hour_of_day: number; // 0-23
  incident_count: number;
}

export interface TopContributor {
  user_id: string;
  user_name: string;
  avatar_url?: string;
  incidents_resolved: number;
  avg_resolution_time_hours: number;
  postmortems_written: number;
  on_call_hours: number;
}

export interface InsightData {
  id: string;
  type: 'pattern' | 'anomaly' | 'recommendation' | 'trend';
  title: string;
  description: string;
  severity: 'info' | 'warning' | 'critical';
  created_at: string;
  affected_services?: string[];
  recommended_actions?: string[];
  confidence?: number;
}
