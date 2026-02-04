# 🔌 API Reference

Incident Copilot provides a comprehensive REST API for integration, automation, and custom tooling.

---

## 🔐 Authentication

### API Key Authentication

Include your API key in the `Authorization` header:

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
  https://your-instance.com/api/analytics/mttr
```

### Generate API Keys

See [API Keys Management](./admin/api-keys.md) for creating and managing API keys.

---

## 📍 Base URL

| Environment | Base URL |
|-------------|----------|
| Local Development | `http://localhost:8000` |
| Docker | `http://localhost:8000` |
| Production | `https://your-domain.com` |

---

## 🏥 Health Endpoints

### Basic Health Check

```
GET /health
```

Returns basic health status.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-15T10:00:00Z",
  "version": "0.1.0",
  "uptime_seconds": 3600.5
}
```

### Full Health Check

```
GET /health?full=true
```

Returns health status of all components.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-15T10:00:00Z",
  "version": "0.1.0",
  "uptime_seconds": 3600.5,
  "components": [
    {"name": "redis", "status": "healthy", "latency_ms": 1.2},
    {"name": "database", "status": "healthy", "latency_ms": 5.4},
    {"name": "pagerduty", "status": "healthy", "latency_ms": 150.3},
    {"name": "github", "status": "healthy", "latency_ms": 89.2},
    {"name": "datadog", "status": "healthy", "latency_ms": 120.5},
    {"name": "slack", "status": "healthy", "latency_ms": 95.1},
    {"name": "anthropic", "status": "healthy", "latency_ms": 200.8}
  ]
}
```

### Kubernetes Probes

```
GET /health/live   # Liveness probe
GET /health/ready  # Readiness probe
```

---

## 📊 Analytics API

### Get MTTR Statistics

```
GET /api/analytics/mttr
```

Returns Mean Time To Resolve statistics.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | integer | 7 | Number of days to analyze (1-365) |
| `service` | string | - | Filter by service name |
| `severity` | string | - | Filter by severity level |

**Response:**
```json
{
  "period": "7d",
  "period_start": "2025-01-08T00:00:00Z",
  "period_end": "2025-01-15T00:00:00Z",
  "mean_mttr_seconds": 1380,
  "median_mttr_seconds": 1200,
  "p90_mttr_seconds": 2400,
  "incidents_count": 23,
  "resolved_count": 21,
  "mean_time_to_acknowledge_seconds": 138,
  "mean_time_to_context_card_seconds": 6.4
}
```

### Compare Periods

```
GET /api/analytics/mttr/compare
```

Compare current period with previous period.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | integer | 30 | Period length in days |

**Response:**
```json
{
  "current_period": {
    "period_start": "2024-12-16T00:00:00Z",
    "period_end": "2025-01-15T00:00:00Z",
    "mean_mttr_seconds": 1380,
    "incidents_count": 47
  },
  "previous_period": {
    "period_start": "2024-11-16T00:00:00Z",
    "period_end": "2024-12-16T00:00:00Z",
    "mean_mttr_seconds": 1620,
    "incidents_count": 52
  },
  "mttr_change_percent": -14.8,
  "incident_count_change_percent": -9.6,
  "trend": "improving"
}
```

### Get Incident Metrics

```
GET /api/analytics/incidents
```

Returns detailed metrics for incidents.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | integer | 7 | Number of days to fetch |
| `service` | string | - | Filter by service name |
| `severity` | string | - | Filter by severity level |
| `limit` | integer | 100 | Maximum incidents (1-1000) |

**Response:**
```json
{
  "incidents": [
    {
      "id": "inc_12345",
      "service_name": "payments-api",
      "title": "High Error Rate",
      "severity": "high",
      "triggered_at": "2025-01-15T02:47:00Z",
      "acknowledged_at": "2025-01-15T02:49:00Z",
      "resolved_at": "2025-01-15T03:10:00Z",
      "time_to_acknowledge_seconds": 120,
      "time_to_resolve_seconds": 1380,
      "context_card_delivered_at": "2025-01-15T02:47:06Z"
    }
  ]
}
```

### Get Service Statistics

```
GET /api/analytics/services
```

Returns per-service incident statistics.

**Response:**
```json
{
  "services": [
    {
      "service_name": "payments-api",
      "incidents_count": 12,
      "mean_mttr_seconds": 1080,
      "top_error_patterns": ["ConnectionTimeout", "Retry exceeded"]
    },
    {
      "service_name": "auth-service",
      "incidents_count": 8,
      "mean_mttr_seconds": 1440,
      "top_error_patterns": ["InvalidToken", "SessionExpired"]
    }
  ]
}
```

---

## 🔔 Webhook Endpoints

### PagerDuty Webhook

```
POST /webhooks/pagerduty
```

Receives PagerDuty webhook events.

**Headers:**
- `X-PagerDuty-Signature`: HMAC signature for validation

**Events Handled:**
- `incident.triggered`
- `incident.acknowledged`
- `incident.resolved`

### Opsgenie Webhook

```
POST /webhooks/opsgenie
```

Receives Opsgenie webhook events.

**Headers:**
- `X-OpsGenie-Signature`: HMAC signature for validation

### Webhook Health

```
GET /webhooks/health
```

Returns webhook endpoint status.

---

## 🎮 Demo API

### Trigger Demo Incident

```
POST /demo/trigger
```

Trigger a simulated incident for testing.

**Request Body:**
```json
{
  "service_name": "payments-api",
  "title": "High Error Rate",
  "severity": "high"
}
```

**Response:**
```json
{
  "incident_id": "demo_12345",
  "context_card_sent": true,
  "channel": "#incidents"
}
```

---

## 📝 Postmortem API

### Generate Postmortem

```
POST /api/postmortems/generate
```

Generate an AI-powered postmortem for an incident.

**Request Body:**
```json
{
  "incident_id": "inc_12345",
  "format": "markdown",
  "include_timeline": true,
  "include_metrics": true
}
```

**Response:**
```json
{
  "postmortem_id": "pm_67890",
  "incident_id": "inc_12345",
  "title": "Postmortem: payments-api High Error Rate",
  "content": "# Incident Postmortem...",
  "format": "markdown",
  "generated_at": "2025-01-15T10:00:00Z"
}
```

### Get Postmortem

```
GET /api/postmortems/{postmortem_id}
```

Retrieve a generated postmortem.

### List Postmortems

```
GET /api/postmortems
```

List all postmortems.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `incident_id` | string | - | Filter by incident |
| `service` | string | - | Filter by service |
| `limit` | integer | 20 | Results per page |
| `offset` | integer | 0 | Pagination offset |

---

## 📅 Reports API

### List Report Schedules

```
GET /api/reports/schedules
```

List all configured report schedules.

**Response:**
```json
{
  "schedules": [
    {
      "id": "sched_123",
      "name": "Weekly Engineering Report",
      "report_type": "weekly",
      "schedule": "0 9 * * MON",
      "timezone": "America/Los_Angeles",
      "next_run": "2025-01-20T09:00:00-08:00",
      "enabled": true
    }
  ]
}
```

### Create Report Schedule

```
POST /api/reports/schedules
```

Create a new report schedule.

**Request Body:**
```json
{
  "name": "Daily Digest",
  "report_type": "daily",
  "schedule": "0 9 * * *",
  "timezone": "America/New_York",
  "delivery": {
    "slack_channels": ["#incidents"],
    "email_recipients": ["oncall@company.com"]
  },
  "filters": {
    "services": ["payments-api"],
    "min_severity": "medium"
  }
}
```

### Generate Report On-Demand

```
POST /api/reports/generate
```

Generate a report immediately.

**Request Body:**
```json
{
  "report_type": "weekly",
  "period_start": "2025-01-08",
  "period_end": "2025-01-15",
  "delivery": {
    "slack_channels": ["#incidents"]
  }
}
```

### Get Report History

```
GET /api/reports/history
```

List generated reports.

---

## 🔍 Correlation API

### Find Similar Incidents

```
GET /api/correlation/similar
```

Find incidents similar to a given incident.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `incident_id` | string | Source incident ID |
| `limit` | integer | Max results (default: 5) |
| `threshold` | float | Similarity threshold (0-1) |

**Response:**
```json
{
  "similar_incidents": [
    {
      "incident_id": "inc_11111",
      "similarity_score": 0.92,
      "service_name": "payments-api",
      "title": "Stripe API Timeout",
      "resolved_at": "2024-12-10T05:30:00Z",
      "resolution_notes": "Stripe was having an outage..."
    }
  ]
}
```

---

## 📚 Runbooks API

### Get Runbook

```
GET /api/runbooks/{service_name}
```

Get runbook for a service.

**Response:**
```json
{
  "service_name": "payments-api",
  "runbook_url": "https://wiki.company.com/runbooks/payments-api",
  "quick_actions": [
    {"name": "Restart Service", "command": "kubectl rollout restart..."},
    {"name": "Check Logs", "url": "https://datadog.com/logs?service=payments-api"}
  ]
}
```

---

## 🔌 Plugin API

### List Plugins

```
GET /api/plugins
```

List available plugins.

### Enable Plugin

```
POST /api/plugins/{plugin_id}/enable
```

### Disable Plugin

```
POST /api/plugins/{plugin_id}/disable
```

---

## 🔍 Audit API

### List Audit Events

```
GET /api/audit/events
```

List audit log events.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `tenant_id` | string | Tenant ID (required) |
| `user_id` | string | Filter by user |
| `event_type` | string | Filter by event type |
| `category` | string | Filter by category |
| `limit` | integer | Max results |

---

## 🚨 Error Responses

All endpoints return consistent error responses:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request parameters",
    "details": {
      "field": "days",
      "issue": "Must be between 1 and 365"
    }
  }
}
```

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request - Invalid parameters |
| 401 | Unauthorized - Invalid/missing API key |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found |
| 422 | Validation Error |
| 429 | Rate Limited |
| 500 | Internal Server Error |

---

## ⏱️ Rate Limits

| Tier | Limit |
|------|-------|
| Free | 100 req/min |
| Pro | 1000 req/min |
| Enterprise | Custom |

Rate limit headers are included in responses:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1705329660
```

---

## 📖 OpenAPI Specification

Interactive API documentation is available at:

- **Swagger UI:** `https://your-instance.com/docs`
- **ReDoc:** `https://your-instance.com/redoc`
- **OpenAPI JSON:** `https://your-instance.com/openapi.json`

---

## 📚 Related Documentation

- [Getting Started](./getting-started.md) - Initial setup
- [CLI Reference](./cli.md) - Command line tools
- [API Keys](./admin/api-keys.md) - Key management

---

*Need help? Check the [Troubleshooting Guide](./troubleshooting.md) or open an issue on GitHub.*
