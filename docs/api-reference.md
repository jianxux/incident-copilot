# API Reference

This document provides a complete reference for the Incident Copilot API.

## Base URL

```
https://your-domain.com
```

## Authentication

### Webhook Authentication

All webhook endpoints verify signatures from their respective sources:

- **PagerDuty**: Uses HMAC-SHA256 signature verification via the `X-PagerDuty-Signature` header
- **Opsgenie**: Uses HMAC-SHA256 signature verification via the `X-OpsGenie-Signature` header

If webhook secrets are not configured, signature verification is skipped (not recommended for production).

### Internal API Authentication

Currently, internal API endpoints do not require authentication. When deploying in production, we recommend:

1. Running behind a reverse proxy (nginx/Traefik) with IP allowlisting
2. Adding API key authentication at the network level
3. Using a service mesh for service-to-service auth

---

## Endpoints

### Health Check

#### `GET /`

Root health check endpoint.

**Response**

```json
{
  "name": "Incident Copilot",
  "version": "0.1.0",
  "status": "running"
}
```

**Status Codes**

| Code | Description |
|------|-------------|
| 200  | Service is running |

---

### Webhook Health

#### `GET /webhooks/health`

Health check for the webhook subsystem.

**Response**

```json
{
  "status": "healthy"
}
```

**Status Codes**

| Code | Description |
|------|-------------|
| 200  | Webhook subsystem is healthy |

---

### PagerDuty Webhook

#### `POST /webhooks/pagerduty`

Receives PagerDuty v3 webhook events. On incident triggers, assembles context and delivers to Slack.

**Headers**

| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes | `application/json` |
| `X-PagerDuty-Signature` | Recommended | HMAC-SHA256 signature (`v1=<hex>`) |

**Request Body**

PagerDuty v3 webhook payload. Example for `incident.triggered`:

```json
{
  "event": {
    "id": "01BZYR9P2CWNZ5YPXXXX",
    "event_type": "incident.triggered",
    "resource_type": "incident",
    "occurred_at": "2024-01-15T02:47:23.000Z",
    "agent": {
      "html_url": "https://mycompany.pagerduty.com/users/P3Y1111",
      "id": "P3Y1111",
      "self": "https://api.pagerduty.com/users/P3Y1111",
      "summary": "Jane Doe",
      "type": "user_reference"
    },
    "client": null,
    "data": {
      "id": "Q0JBXQZ7T8QXXX",
      "type": "incident",
      "self": "https://api.pagerduty.com/incidents/Q0JBXQZ7T8QXXX",
      "html_url": "https://mycompany.pagerduty.com/incidents/Q0JBXQZ7T8QXXX",
      "incident_number": 42,
      "title": "High Error Rate on payments-api",
      "description": "Error rate exceeded 5% threshold",
      "created_at": "2024-01-15T02:47:23.000Z",
      "updated_at": "2024-01-15T02:47:23.000Z",
      "status": "triggered",
      "urgency": "high",
      "service": {
        "html_url": "https://mycompany.pagerduty.com/services/PXXXXXX",
        "id": "PXXXXXX",
        "self": "https://api.pagerduty.com/services/PXXXXXX",
        "summary": "payments-api",
        "type": "service_reference"
      },
      "assignments": [
        {
          "at": "2024-01-15T02:47:23.000Z",
          "assignee": {
            "html_url": "https://mycompany.pagerduty.com/users/P3Y1111",
            "id": "P3Y1111",
            "self": "https://api.pagerduty.com/users/P3Y1111",
            "summary": "Jane Doe",
            "type": "user_reference"
          }
        }
      ]
    }
  }
}
```

**Response (Success - Incident Processed)**

```json
{
  "status": "accepted",
  "incident_id": "Q0JBXQZ7T8QXXX",
  "service": "payments-api"
}
```

**Response (Non-Trigger Event)**

```json
{
  "status": "ignored",
  "reason": "not an incident trigger"
}
```

**Status Codes**

| Code | Description |
|------|-------------|
| 200  | Webhook received and processing started |
| 400  | Invalid JSON payload |
| 401  | Invalid signature |

**Notes**

- Context assembly runs in the background; the endpoint returns immediately
- Processing typically takes 3-10 seconds to deliver to Slack
- Non-`incident.triggered` events are acknowledged but not processed

---

### Opsgenie Webhook

#### `POST /webhooks/opsgenie`

Receives Opsgenie webhook events for alert creation.

**Headers**

| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes | `application/json` |
| `X-OpsGenie-Signature` | Recommended | HMAC-SHA256 signature |

**Request Body**

Opsgenie webhook payload. Example for alert creation:

```json
{
  "action": "Create",
  "alert": {
    "alertId": "70413a06-38d6-4c85-92b8-5ebc900d42e2",
    "message": "High Error Rate on payments-api",
    "tags": ["critical", "payments"],
    "tinyId": "1234",
    "entity": "payments-api",
    "alias": "payments-high-error-rate",
    "createdAt": 1705290443000,
    "updatedAt": 1705290443000,
    "username": "System",
    "userId": "",
    "source": "Datadog",
    "status": "open",
    "isSeen": false,
    "acknowledged": false,
    "priority": "P1",
    "teams": ["platform-team"],
    "responders": [
      {
        "type": "user",
        "id": "4513b7ea-3b91-438f-b7e4-e3e54af9147c",
        "name": "Jane Doe"
      }
    ],
    "description": "Error rate exceeded 5% threshold for payments-api"
  },
  "source": {
    "name": "Datadog",
    "type": "api"
  },
  "integrationId": "12345678-1234-1234-1234-123456789012",
  "integrationName": "Incident Copilot Webhook"
}
```

**Response (Success)**

```json
{
  "status": "accepted",
  "alert_id": "70413a06-38d6-4c85-92b8-5ebc900d42e2",
  "service": "payments-api"
}
```

**Response (Non-Create Action)**

```json
{
  "status": "ignored",
  "reason": "not an alert creation"
}
```

**Status Codes**

| Code | Description |
|------|-------------|
| 200  | Webhook received |
| 400  | Invalid JSON payload |
| 401  | Invalid signature |

---

## Data Models

### Incident (Internal)

Represents a parsed incident from PagerDuty or Opsgenie:

```json
{
  "incident_id": "Q0JBXQZ7T8QXXX",
  "incident_number": 42,
  "title": "High Error Rate on payments-api",
  "description": "Error rate exceeded 5% threshold",
  "severity": "high",
  "service_name": "payments-api",
  "service_id": "PXXXXXX",
  "triggered_at": "2024-01-15T02:47:23Z",
  "html_url": "https://mycompany.pagerduty.com/incidents/Q0JBXQZ7T8QXXX",
  "assigned_to": ["Jane Doe"]
}
```

### Severity Levels

| Value | Description |
|-------|-------------|
| `critical` | P1 - Immediate response required |
| `high` | P2 - Urgent, but not critical |
| `medium` | P3 - Standard priority |
| `low` | P4 - Low priority |
| `info` | Informational only |

### Context Card

The assembled context card delivered to Slack:

```json
{
  "incident_id": "Q0JBXQZ7T8QXXX",
  "title": "High Error Rate on payments-api",
  "severity": "high",
  "service_name": "payments-api",
  "triggered_at": "2024-01-15T02:47:23Z",
  "alert_url": "https://mycompany.pagerduty.com/incidents/Q0JBXQZ7T8QXXX",
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
    "logs": [
      {
        "timestamp": "2024-01-15T02:45:00Z",
        "level": "error",
        "message": "ConnectionTimeout to stripe-api after 30s",
        "service": "payments-api",
        "host": "payments-api-7f8d9c-abcde"
      }
    ],
    "log_summaries": [
      {
        "pattern": "ConnectionTimeout to stripe-api",
        "count": 847,
        "level": "error",
        "sample_message": "ConnectionTimeout to stripe-api after 30s",
        "first_seen": "2024-01-15T02:35:00Z",
        "last_seen": "2024-01-15T02:47:00Z"
      }
    ],
    "metrics": {
      "error_rate": 0.087,
      "error_rate_baseline": 0.002,
      "latency_p99_ms": 5420,
      "request_count": 15234,
      "time_range_minutes": 5
    }
  },
  "ai_summary": {
    "top_issues": [
      "ConnectionTimeout to stripe-api (847 occurrences)",
      "Retry limit exceeded (612 occurrences)",
      "Payment processing failed (203 occurrences)"
    ],
    "explanation": "The service is experiencing timeouts when connecting to Stripe's API. This appears to correlate with a recent deployment that modified retry logic.",
    "likely_cause": "Recent deployment abc123d modified Stripe API retry behavior",
    "suggested_actions": [
      "Check Stripe status page for incidents",
      "Review commit abc123d for retry logic changes",
      "Consider rolling back if issue persists"
    ]
  },
  "similar_incidents": [
    {
      "incident_id": "P0JBXQZ7T8QXXX",
      "title": "Stripe API Timeouts",
      "service": "payments-api",
      "occurred_at": "2023-11-20T14:30:00Z",
      "resolved_at": "2023-11-20T15:45:00Z",
      "resolution": "Stripe had a partial outage. Resolved when they fixed it.",
      "similarity_score": 0.92
    }
  ],
  "owners": ["@sarah", "@mike", "@platform-team"],
  "runbook_url": "https://wiki.mycompany.com/runbooks/payments-api",
  "dashboard_url": "https://app.datadoghq.com/dashboard/abc-xyz-123",
  "assembled_at": "2024-01-15T02:47:28Z",
  "assembly_time_ms": 3420,
  "errors": []
}
```

### Deployment

Recent deployment/commit information:

```json
{
  "sha": "abc123def456789",
  "short_sha": "abc123d",
  "author": "Sarah",
  "message": "Fix retry logic for Stripe API calls",
  "timestamp": "2024-01-15T01:30:00Z",
  "url": "https://github.com/mycompany/payments-api/commit/abc123def456789",
  "files_changed": ["src/stripe.py", "tests/test_stripe.py"],
  "additions": 42,
  "deletions": 15
}
```

### Log Entry

Individual log entry from Datadog/CloudWatch:

```json
{
  "timestamp": "2024-01-15T02:45:00Z",
  "level": "error",
  "message": "ConnectionTimeout to stripe-api after 30s",
  "service": "payments-api",
  "host": "payments-api-7f8d9c-abcde",
  "attributes": {
    "trace_id": "abc123",
    "span_id": "def456",
    "error.type": "TimeoutError"
  }
}
```

### AI Summary

AI-generated log analysis:

```json
{
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
}
```

---

## Rate Limiting

### Current Implementation

No rate limiting is currently implemented at the application level. 

### Recommendations for Production

We recommend implementing rate limiting at the infrastructure level:

| Endpoint | Recommended Limit | Notes |
|----------|-------------------|-------|
| `/webhooks/pagerduty` | 60 req/min | Typical alert volume |
| `/webhooks/opsgenie` | 60 req/min | Typical alert volume |
| `/webhooks/health` | 120 req/min | Health checks |
| `/` | 120 req/min | Health checks |

**Example nginx configuration:**

```nginx
limit_req_zone $binary_remote_addr zone=webhooks:10m rate=60r/m;

location /webhooks/ {
    limit_req zone=webhooks burst=10 nodelay;
    proxy_pass http://localhost:8000;
}
```

---

## Error Codes

### HTTP Status Codes

| Code | Meaning | When Returned |
|------|---------|---------------|
| 200 | OK | Request processed successfully |
| 400 | Bad Request | Invalid JSON, malformed payload |
| 401 | Unauthorized | Invalid webhook signature |
| 404 | Not Found | Endpoint doesn't exist |
| 422 | Unprocessable Entity | Valid JSON but invalid data structure |
| 500 | Internal Server Error | Unexpected server error |
| 503 | Service Unavailable | Service temporarily unavailable |

### Error Response Format

```json
{
  "detail": "Invalid signature"
}
```

For validation errors (422):

```json
{
  "detail": [
    {
      "loc": ["body", "event", "data", "id"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Invalid signature` | Webhook secret mismatch | Verify `PAGERDUTY_WEBHOOK_SECRET` matches PagerDuty |
| `Invalid JSON` | Malformed request body | Check webhook payload format |
| `Context fetch timed out` | External APIs slow/down | Check GitHub/Datadog status |
| `slack_not_configured` | Missing Slack token | Set `SLACK_BOT_TOKEN` |

---

## Webhook Payload Formats

### PagerDuty v3 Webhook Format

Full schema: [PagerDuty Webhooks v3 Documentation](https://developer.pagerduty.com/docs/webhooks/v3-overview/)

**Supported Event Types:**

| Event Type | Processed | Notes |
|------------|-----------|-------|
| `incident.triggered` | ✅ Yes | Triggers context assembly |
| `incident.acknowledged` | ❌ No | Acknowledged only |
| `incident.resolved` | ❌ No | Acknowledged only |
| `incident.annotated` | ❌ No | Acknowledged only |
| `incident.escalated` | ❌ No | Acknowledged only |

**Signature Verification:**

PagerDuty signs webhooks using HMAC-SHA256:

```
X-PagerDuty-Signature: v1=<hex-encoded-signature>
```

Signature is computed as:
```
HMAC-SHA256(webhook_secret, request_body)
```

### Opsgenie Webhook Format

Full schema: [Opsgenie Webhook Integration](https://support.atlassian.com/opsgenie/docs/integrate-opsgenie-with-webhook/)

**Supported Actions:**

| Action | Processed | Notes |
|--------|-----------|-------|
| `Create` | ✅ Yes | Triggers context assembly |
| `Acknowledge` | ❌ No | Acknowledged only |
| `Close` | ❌ No | Acknowledged only |
| `AddNote` | ❌ No | Acknowledged only |

**Priority Mapping:**

| Opsgenie Priority | Incident Copilot Severity |
|-------------------|---------------------------|
| P1 | critical |
| P2 | high |
| P3 | medium |
| P4 | low |
| P5 | info |

**Signature Verification:**

Opsgenie signs webhooks using HMAC-SHA256:

```
X-OpsGenie-Signature: <hex-encoded-signature>
```

---

## Webhook Testing

### Testing with curl

**PagerDuty webhook:**

```bash
curl -X POST http://localhost:8000/webhooks/pagerduty \
  -H "Content-Type: application/json" \
  -d '{
    "event": {
      "event_type": "incident.triggered",
      "data": {
        "id": "TEST001",
        "incident_number": 1,
        "title": "Test Incident",
        "urgency": "high",
        "created_at": "2024-01-15T02:47:23Z",
        "html_url": "https://example.pagerduty.com/incidents/TEST001",
        "service": {
          "id": "PSVC001",
          "summary": "test-service"
        },
        "assignments": []
      }
    }
  }'
```

**Expected response:**

```json
{
  "status": "accepted",
  "incident_id": "TEST001",
  "service": "test-service"
}
```

### Testing with PagerDuty

1. Create a test service in PagerDuty
2. Add Generic Webhook v3 integration pointing to your instance
3. Trigger a test incident via the UI or API
4. Check your Slack channel for the context card

---

## OpenAPI Specification

The API automatically generates OpenAPI documentation available at:

- **Swagger UI**: `GET /docs`
- **ReDoc**: `GET /redoc`
- **OpenAPI JSON**: `GET /openapi.json`

---

*API Reference version: 1.0*
*Last updated: January 2026*
