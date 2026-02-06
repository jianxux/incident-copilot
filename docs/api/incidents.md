# Incidents API Reference

The Incidents API provides endpoints for managing incident lifecycle, postmortems, and related data.

## Core Concepts

### Incident Model

```json
{
  "incident_id": "INC-12345",
  "title": "High Error Rate on payments-api",
  "description": "Error rate exceeded 5% threshold",
  "severity": "high",
  "service_name": "payments-api",
  "service_id": "PXXXXXX",
  "triggered_at": "2024-01-15T10:30:00Z",
  "acknowledged_at": "2024-01-15T10:35:00Z",
  "resolved_at": "2024-01-15T11:30:00Z",
  "html_url": "https://pagerduty.com/incidents/INC-12345",
  "assigned_to": ["jane.doe@example.com"],
  "status": "resolved"
}
```

### Severity Levels

| Value | Description | SLA Response |
|-------|-------------|--------------|
| `critical` | P1 - Service down, revenue impact | 15 minutes |
| `high` | P2 - Major feature impacted | 30 minutes |
| `medium` | P3 - Partial degradation | 2 hours |
| `low` | P4 - Minor issue | 8 hours |
| `info` | Informational only | Best effort |

---

## Dashboard Endpoints

### List Incidents

Retrieve all incidents with optional filtering.

```http
GET /dashboard/api/incidents
```

**Response:**

```json
{
  "incidents": [
    {
      "incident_id": "Q0JBXQZ7T8QXXX",
      "title": "High Error Rate on payments-api",
      "service_name": "payments-api",
      "severity": "high",
      "status": "completed",
      "triggered_at": "2024-01-15T02:47:23Z",
      "processed_at": "2024-01-15T02:47:28Z"
    }
  ]
}
```

### Get Dashboard Stats

Retrieve incident statistics for the dashboard.

```http
GET /dashboard/api/stats
```

**Response:**

```json
{
  "total_incidents": 150,
  "critical_count": 5,
  "high_count": 25,
  "mttr_minutes": 45,
  "incidents_today": 3
}
```

---

## Postmortem Endpoints

### Generate Postmortem

Generate an AI-powered postmortem from incident data.

```http
POST /api/postmortems/generate
```

**Request Body:**

```json
{
  "incident_id": "INC-12345",
  "format": "markdown",
  "include_ai_analysis": true,
  "custom_context": "Additional context about the incident"
}
```

**Response:**

```json
{
  "postmortem": {
    "id": "pm-abc123",
    "incident_id": "INC-12345",
    "title": "Postmortem: High Error Rate on payments-api",
    "status": "draft",
    "severity": "high",
    "service_name": "payments-api",
    "summary": "...",
    "timeline": [...],
    "root_cause_analysis": {...},
    "impact_assessment": {...},
    "action_items": [...],
    "ai_generated": true,
    "version": 1,
    "created_at": "2024-01-16T10:00:00Z"
  },
  "message": "Postmortem generated successfully"
}
```

### Generate Postmortem from Context Card

Generate a postmortem with full context data already available.

```http
POST /api/postmortems/generate-from-context
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `include_ai_analysis` | boolean | `true` | Include AI-generated analysis |

**Request Body:** Full `ContextCard` object

### Get Postmortem

Retrieve a postmortem by ID.

```http
GET /api/postmortems/{postmortem_id}
```

**Response:** Full `Postmortem` object

### Get Postmortem by Incident

Retrieve a postmortem by its associated incident ID.

```http
GET /api/postmortems/by-incident/{incident_id}
```

### Update Postmortem

Update an existing postmortem.

```http
PUT /api/postmortems/{postmortem_id}
```

**Request Body:**

```json
{
  "title": "Updated title",
  "summary": "Updated summary",
  "timeline": [...],
  "root_cause_analysis": {...},
  "impact_assessment": {...},
  "action_items": [...]
}
```

### Delete Postmortem

Permanently delete a postmortem.

```http
DELETE /api/postmortems/{postmortem_id}
```

**Response:**

```json
{
  "message": "Postmortem pm-abc123 deleted successfully"
}
```

### List Postmortems

List postmortems with optional filters.

```http
GET /api/postmortems
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | Filter by status: `draft`, `in_review`, `approved`, `published` |
| `service` | string | Filter by service name |
| `limit` | integer | Max results (1-100, default 50) |

**Response:**

```json
{
  "postmortems": [...],
  "total": 25
}
```

### Export Postmortem

Export a postmortem in various formats.

```http
POST /api/postmortems/{postmortem_id}/export
```

**Request Body:**

```json
{
  "format": "markdown"
}
```

**Supported Formats:**

| Format | Description |
|--------|-------------|
| `markdown` | Clean Markdown document |
| `confluence` | Confluence wiki markup |
| `slack` | Slack Block Kit JSON |
| `json` | Structured JSON |

**Response:**

```json
{
  "format": "markdown",
  "content": "# Postmortem: High Error Rate...",
  "postmortem_id": "pm-abc123"
}
```

### Export Postmortem (Raw)

Export a postmortem and return raw content directly.

```http
GET /api/postmortems/{postmortem_id}/export/{format}
```

Returns the content with appropriate content type headers.

### Refresh Postmortem

Re-run AI analysis on specific sections.

```http
POST /api/postmortems/{postmortem_id}/refresh
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `sections` | array | Sections to refresh: `timeline`, `root_cause`, `impact`, `action_items` |

### Update Postmortem Status

Update the status of a postmortem.

```http
POST /api/postmortems/{postmortem_id}/status
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | New status (required) |
| `approved_by` | string | User who approved (optional) |

**Valid Status Transitions:**

```
draft → in_review → approved → published
              ↑          ↑
              └──────────┘
```

---

## Alert Correlation Endpoints

### Create Correlation Rule

Create a new alert correlation rule.

```http
POST /correlation/rules
```

**Request Body:**

```json
{
  "name": "Payment Service Alerts",
  "description": "Correlate all payment-related alerts",
  "strategy": "service",
  "enabled": true,
  "priority": 10,
  "time_window_seconds": 300,
  "services": ["payments-api", "payment-processor"],
  "match_tags": ["payment", "transaction"],
  "group_by_tags": ["service", "region"],
  "title_patterns": ["payment.*error", "transaction.*failed"],
  "similarity_threshold": 0.7,
  "suppress_duplicates": true,
  "max_alerts_before_notify": 1,
  "re_notify_after_seconds": 1800
}
```

**Correlation Strategies:**

| Strategy | Description |
|----------|-------------|
| `service` | Group by service name |
| `tag` | Group by matching tags |
| `similarity` | Group by title/content similarity |
| `time_window` | Group alerts within time window |
| `custom` | Custom rule logic |

**Response:**

```json
{
  "rule_id": "rule_abc123def456",
  "name": "Payment Service Alerts"
}
```

### List Correlation Rules

```http
GET /correlation/rules
```

**Response:**

```json
{
  "rules": [
    {
      "rule_id": "rule_abc123def456",
      "name": "Payment Service Alerts",
      "strategy": "service",
      "enabled": true
    }
  ],
  "total": 5
}
```

### Get Correlation Rule

```http
GET /correlation/rules/{rule_id}
```

### Delete Correlation Rule

```http
DELETE /correlation/rules/{rule_id}
```

### List Alert Groups

List active alert groups (correlated alerts).

```http
GET /correlation/groups
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `service` | string | Filter by service |
| `limit` | integer | Max results (1-500, default 100) |

**Response:**

```json
{
  "groups": [
    {
      "group_id": "grp_abc123",
      "service": "payments-api",
      "alert_count": 5,
      "summary": "Multiple payment failures detected"
    }
  ],
  "total": 3
}
```

### Get Alert Group

```http
GET /correlation/groups/{group_id}
```

**Response:**

```json
{
  "group_id": "grp_abc123",
  "rule_id": "rule_abc123def456",
  "service": "payments-api",
  "alert_count": 5,
  "alert_ids": ["alert_1", "alert_2", "alert_3", "alert_4", "alert_5"],
  "summary": "Multiple payment failures detected",
  "suppressed_count": 3,
  "status": "active"
}
```

### Close Alert Group

```http
POST /correlation/groups/{group_id}/close
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | Close status: `closed`, `resolved`, `suppressed` |

### Get Correlation Stats

```http
GET /correlation/stats
```

**Response:**

```json
{
  "total_rules": 10,
  "enabled_rules": 8,
  "active_groups": 5,
  "alerts_correlated_today": 150,
  "alerts_suppressed_today": 75,
  "suppression_rate": 0.5
}
```

### Test Correlation

Test how an alert would be correlated without creating actual groups.

```http
POST /correlation/test
```

**Request Body:**

```json
{
  "alert_id": "test-alert-001",
  "source": "manual",
  "title": "Payment API Error Rate High",
  "service": "payments-api",
  "severity": "high",
  "tags": ["payment", "production"]
}
```

**Response:**

```json
{
  "correlated": true,
  "group_id": "grp_existing_123",
  "new_group": false,
  "rule_matched": "Payment Service Alerts",
  "should_notify": false,
  "suppression_reason": "Grouped with existing incident"
}
```

### Trigger Cleanup

Schedule cleanup of stale alert groups.

```http
POST /correlation/cleanup
```

**Response:**

```json
{
  "status": "cleanup_scheduled"
}
```

---

## Timeline Endpoints

### Get Incident Timeline

Retrieve the interactive timeline for an incident.

```http
GET /dashboard/api/incidents/{incident_id}/timeline
```

**Response:**

```json
{
  "incident_id": "INC-12345",
  "events": [
    {
      "event_type": "alert_triggered",
      "timestamp": "2024-01-15T10:30:00Z",
      "description": "Alert triggered: High Error Rate",
      "metadata": {...},
      "is_key_event": true
    },
    {
      "event_type": "deployment",
      "timestamp": "2024-01-15T10:15:00Z",
      "description": "Deployment abc123 by jane.doe",
      "metadata": {...},
      "is_key_event": true
    }
  ]
}
```

**Event Types:**

| Type | Description |
|------|-------------|
| `alert_triggered` | Initial alert |
| `alert_acknowledged` | Alert acknowledged |
| `alert_resolved` | Alert resolved |
| `deployment` | Related deployment |
| `log_error` | Error log spike |
| `metric_anomaly` | Metric threshold breach |
| `runbook_opened` | Runbook accessed |
| `notification_sent` | Slack/Teams notification |

---

## Runbook Endpoints

### Search Runbooks

Search for relevant runbooks.

```http
GET /api/runbooks
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `query` | string | Search query (required) |
| `service` | string | Filter by service name |
| `limit` | integer | Max results (1-20, default 5) |

**Response:**

```json
[
  {
    "title": "Payment API Troubleshooting",
    "url": "https://wiki.example.com/runbooks/payment-api",
    "source": "confluence",
    "relevance_score": 0.92,
    "matched_terms": ["payment", "error", "api"]
  }
]
```

### Get Runbook Stats

```http
GET /api/runbooks/stats
```

**Response:**

```json
{
  "indexed": true,
  "built_at": "2024-01-15T00:00:00Z",
  "total_runbooks": 150,
  "vocabulary_size": 5000,
  "sources": {
    "confluence:engineering-wiki": 100,
    "github:runbooks-repo": 50
  }
}
```

---

## Context Card Model

The assembled context card delivered to engineers:

```json
{
  "incident_id": "Q0JBXQZ7T8QXXX",
  "title": "High Error Rate on payments-api",
  "severity": "high",
  "service_name": "payments-api",
  "triggered_at": "2024-01-15T02:47:23Z",
  "alert_url": "https://pagerduty.com/incidents/Q0JBXQZ7T8QXXX",
  "github": {
    "repo": "mycompany/payments-api",
    "recent_deploys": [
      {
        "sha": "abc123def456789",
        "short_sha": "abc123d",
        "author": "Sarah",
        "message": "Fix retry logic for Stripe API calls",
        "timestamp": "2024-01-15T01:30:00Z",
        "url": "https://github.com/mycompany/payments-api/commit/abc123def456789",
        "files_changed": ["src/stripe.py"],
        "additions": 42,
        "deletions": 15
      }
    ],
    "codeowners": ["@platform-team", "@sarah"]
  },
  "datadog": {
    "service": "payments-api",
    "logs": [...],
    "log_summaries": [
      {
        "pattern": "ConnectionTimeout to stripe-api",
        "count": 847,
        "level": "error",
        "sample_message": "ConnectionTimeout to stripe-api after 30s"
      }
    ],
    "metrics": {
      "error_rate": 0.087,
      "error_rate_baseline": 0.002,
      "latency_p99_ms": 5420,
      "request_count": 15234
    }
  },
  "ai_summary": {
    "top_issues": [
      "ConnectionTimeout to stripe-api (847 occurrences)",
      "Retry limit exceeded (612 occurrences)"
    ],
    "explanation": "The service is experiencing timeouts when connecting to Stripe's API...",
    "likely_cause": "Recent deployment abc123d modified Stripe API retry behavior",
    "suggested_actions": [
      "Check Stripe status page for incidents",
      "Review commit abc123d for retry logic changes"
    ]
  },
  "similar_incidents": [
    {
      "incident_id": "P0JBXQZ7T8QXXX",
      "title": "Stripe API Timeouts",
      "service": "payments-api",
      "occurred_at": "2023-11-20T14:30:00Z",
      "resolution": "Stripe had a partial outage. Resolved when they fixed it.",
      "similarity_score": 0.92
    }
  ],
  "runbooks": [
    {
      "title": "Stripe API Troubleshooting",
      "url": "https://wiki.example.com/runbooks/stripe",
      "relevance_score": 0.89
    }
  ],
  "oncall": {
    "schedule_id": "PXXXXXX",
    "schedule_name": "Platform On-Call",
    "provider": "pagerduty",
    "oncall_persons": [
      {
        "id": "PUSER1",
        "name": "Jane Doe",
        "email": "jane@example.com",
        "slack_user_id": "U12345"
      }
    ]
  },
  "owners": ["@sarah", "@platform-team"],
  "dashboard_url": "https://app.datadoghq.com/dashboard/abc-xyz-123",
  "assembled_at": "2024-01-15T02:47:28Z",
  "assembly_time_ms": 3420,
  "errors": []
}
```

---

## Demo Endpoints

### List Demo Scenarios

```http
GET /demo/scenarios
```

**Response:**

```json
{
  "scenarios": [
    {
      "id": "database-connection-pool",
      "name": "Database Connection Pool Exhaustion",
      "description": "Simulates connection pool issues",
      "severity": "high"
    }
  ],
  "count": 5
}
```

### Trigger Demo Incident

```http
POST /demo/trigger
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `scenario_id` | string | Specific scenario (optional) |
| `simulate_delays` | boolean | Add realistic delays (default true) |

### Stream Demo Incident

Stream demo incident with progress updates via SSE.

```http
GET /demo/trigger/stream
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `scenario_id` | string | Specific scenario (optional) |

**SSE Events:**

```
event: alert_received
data: {"step": "alert_received", "incident_id": "..."}

event: github_started
data: {"step": "github_started"}

event: github_complete
data: {"step": "github_complete", "deploys": 3}

event: complete
data: {"step": "complete", "context_card": {...}}
```

### Preview Slack Message

```http
POST /demo/slack-preview
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `scenario_id` | string | Specific scenario (optional) |

**Response:**

```json
{
  "demo_mode": true,
  "channel": "#incidents",
  "blocks": [...],
  "text_fallback": "🚨 High Error Rate on payments-api"
}
```

---

*See also: [Analytics API](analytics.md) | [Integrations API](integrations.md)*
