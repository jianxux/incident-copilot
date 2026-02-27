import { Incident, Service, TimelineEvent, Verdict, AnalyticsData } from './types';

export const mockIncidents: Incident[] = [
  { id: 'INC-001', incident_id: 'INC-001', title: 'High latency on payments-api', service: 'payments-api', service_name: 'payments-api', severity: 'P1', status: 'investigating', source: 'PagerDuty', source_url: '', source_id: 'PD-123', created_at: '2026-02-26T14:23:00Z', updated_at: '2026-02-26T15:10:00Z', triggered_at: '2026-02-26T14:23:00Z', processed_at: '2026-02-26T14:25:00Z' },
  { id: 'INC-002', incident_id: 'INC-002', title: 'orders-db connection pool exhausted', service: 'orders-db', service_name: 'orders-db', severity: 'P1', status: 'open', source: 'Datadog', source_url: '', source_id: 'DD-456', created_at: '2026-02-26T14:30:00Z', updated_at: '2026-02-26T14:30:00Z', triggered_at: '2026-02-26T14:30:00Z', processed_at: null },
  { id: 'INC-003', incident_id: 'INC-003', title: 'Elevated 5xx on auth-service', service: 'auth-service', service_name: 'auth-service', severity: 'P2', status: 'resolved', source: 'PagerDuty', source_url: '', source_id: 'PD-789', created_at: '2026-02-25T09:00:00Z', updated_at: '2026-02-25T10:30:00Z', triggered_at: '2026-02-25T09:00:00Z', processed_at: '2026-02-25T09:05:00Z' },
  { id: 'INC-004', incident_id: 'INC-004', title: 'CDN cache miss rate spike', service: 'cdn-edge', service_name: 'cdn-edge', severity: 'P3', status: 'resolved', source: 'CloudWatch', source_url: '', source_id: 'CW-101', created_at: '2026-02-24T16:00:00Z', updated_at: '2026-02-24T17:00:00Z', triggered_at: '2026-02-24T16:00:00Z', processed_at: '2026-02-24T16:02:00Z' },
  { id: 'INC-005', incident_id: 'INC-005', title: 'Notification service queue backlog', service: 'notification-svc', service_name: 'notification-svc', severity: 'P4', status: 'closed', source: 'Datadog', source_url: '', source_id: 'DD-202', created_at: '2026-02-23T11:00:00Z', updated_at: '2026-02-23T12:00:00Z', triggered_at: '2026-02-23T11:00:00Z', processed_at: '2026-02-23T11:03:00Z' },
];

export const mockServices: Service[] = [
  { name: 'payments-api', tier: 1, team: 'Payments', status: 'degraded', latency_ms: 450, error_rate: 5.2 },
  { name: 'orders-db', tier: 1, team: 'Payments', status: 'down', latency_ms: 2000, error_rate: 15.0 },
  { name: 'auth-service', tier: 1, team: 'Platform', status: 'healthy', latency_ms: 12, error_rate: 0.1 },
  { name: 'cdn-edge', tier: 2, team: 'Infra', status: 'healthy', latency_ms: 8, error_rate: 0.0 },
  { name: 'notification-svc', tier: 2, team: 'Platform', status: 'healthy', latency_ms: 35, error_rate: 0.3 },
  { name: 'user-service', tier: 1, team: 'Platform', status: 'healthy', latency_ms: 18, error_rate: 0.2 },
];

export const mockTimeline: TimelineEvent[] = [
  { id: '1', timestamp: '2026-02-26T14:23:00Z', type: 'alert', title: 'Alert triggered', description: 'PagerDuty alert: High latency on payments-api (P1)' },
  { id: '2', timestamp: '2026-02-26T14:25:00Z', type: 'investigation', title: 'Investigation started', description: 'Copilot auto-investigation initiated. Gathering logs, metrics, and deployment history.' },
  { id: '3', timestamp: '2026-02-26T14:25:30Z', type: 'deployment', title: 'Recent deployment detected', description: 'Deploy abc123d by @jsmith 42 minutes before alert. Modified PaymentProcessor.process()' },
  { id: '4', timestamp: '2026-02-26T14:26:00Z', type: 'investigation', title: 'Log analysis complete', description: 'Found N+1 query pattern in payment processing path. DB query time 5ms → 500ms.' },
  { id: '5', timestamp: '2026-02-26T14:27:00Z', type: 'action', title: 'Context card delivered', description: 'Analysis complete. Root cause identified with 85% confidence.' },
];

export const mockVerdict: Verdict = {
  summary: 'Payment processing latency spiked after deployment abc123d introduced an N+1 query in PaymentProcessor.',
  root_cause_hypothesis: 'Deployment abc123d introduced an N+1 query in PaymentProcessor.process() that causes O(n) database calls per transaction instead of batched queries.',
  confidence: 85,
  key_findings: [
    'Error rate increased 10x starting at 14:23 UTC',
    'Database query time increased from 5ms to 500ms',
    'Deployment abc123d modified PaymentProcessor.process()',
    'orders-db connection pool utilization at 98%',
  ],
  recommended_actions: [
    'Rollback to previous version (xyz789a)',
    'Review the database query in PaymentProcessor',
    'Add query optimization or caching layer',
    'Set up connection pool alerts at 80% threshold',
  ],
  rollback_recommended: true,
  rollback_target: 'xyz789a',
};

export const mockAnalytics: AnalyticsData = {
  mttr_trend: [
    { date: '2026-02-20', mttr_minutes: 45 },
    { date: '2026-02-21', mttr_minutes: 38 },
    { date: '2026-02-22', mttr_minutes: 52 },
    { date: '2026-02-23', mttr_minutes: 30 },
    { date: '2026-02-24', mttr_minutes: 28 },
    { date: '2026-02-25', mttr_minutes: 22 },
    { date: '2026-02-26', mttr_minutes: 18 },
  ],
  incidents_by_severity: [
    { severity: 'P1', count: 4 },
    { severity: 'P2', count: 8 },
    { severity: 'P3', count: 15 },
    { severity: 'P4', count: 6 },
  ],
  resolution_times: [
    { service: 'payments-api', avg_minutes: 35 },
    { service: 'auth-service', avg_minutes: 22 },
    { service: 'orders-db', avg_minutes: 48 },
    { service: 'cdn-edge', avg_minutes: 15 },
    { service: 'notification-svc', avg_minutes: 12 },
  ],
};
