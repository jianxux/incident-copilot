# Outbound Webhooks API

Configure webhooks to receive real-time notifications about incident events in your external systems.

## Overview

The Outbound Webhooks API enables you to:
- Register webhook endpoints
- Configure event subscriptions
- Manage webhook security
- Monitor delivery status
- Retry failed deliveries

## Base URL

```
/api/v1/webhooks
```

## Authentication

All endpoints require authentication via Bearer token or API key.

```bash
Authorization: Bearer <your_jwt_token>
# or
X-API-Key: <your_api_key>
```

## Rate Limits

| Endpoint | Rate Limit |
|----------|------------|
| GET endpoints | 100 requests/minute |
| POST/PUT endpoints | 30 requests/minute |
| Retry endpoints | 10 requests/minute |

---

## Endpoints

### List Webhooks

Retrieve all configured webhooks.

```
GET /api/v1/webhooks
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `active` | boolean | No | Filter by active status |
| `page` | integer | No | Page number |
| `limit` | integer | No | Results per page |

#### Response

```json
{
  "success": true,
  "data": {
    "webhooks": [
      {
        "id": "wh_001",
        "name": "Slack Notifications",
        "url": "https://hooks.slack.com/services/T00/B00/XXX",
        "active": true,
        "events": ["incident.created", "incident.resolved", "escalation"],
        "delivery_stats": {
          "total_sent": 1250,
          "success_rate": 99.2,
          "last_delivery": "2024-01-26T10:15:00Z",
          "last_status": "success"
        },
        "created_at": "2024-01-01T00:00:00Z"
      },
      {
        "id": "wh_002",
        "name": "JIRA Integration",
        "url": "https://mycompany.atlassian.net/webhook/incidents",
        "active": true,
        "events": ["incident.created", "incident.updated"],
        "delivery_stats": {
          "total_sent": 890,
          "success_rate": 98.7,
          "last_delivery": "2024-01-26T09:45:00Z",
          "last_status": "success"
        },
        "created_at": "2024-01-05T00:00:00Z"
      }
    ],
    "pagination": {
      "page": 1,
      "limit": 20,
      "total": 5
    }
  }
}
```

#### Example

```bash
curl -X GET "https://api.incident-copilot.io/api/v1/webhooks?active=true" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Create Webhook

Register a new webhook endpoint.

```
POST /api/v1/webhooks
```

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Webhook name |
| `url` | string | Yes | Webhook endpoint URL |
| `events` | array | Yes | Events to subscribe to |
| `secret` | string | No | Signing secret for verification |
| `headers` | object | No | Custom headers to include |
| `active` | boolean | No | Active status (default: true) |
| `retry_policy` | object | No | Retry configuration |
| `filters` | object | No | Event filters |

#### Webhook Events

| Event | Description |
|-------|-------------|
| `incident.created` | New incident created |
| `incident.updated` | Incident details changed |
| `incident.acknowledged` | Incident acknowledged |
| `incident.resolved` | Incident resolved |
| `incident.closed` | Incident closed |
| `incident.reopened` | Incident reopened |
| `comment.added` | Comment added to incident |
| `escalation` | Incident escalated |
| `sla.warning` | SLA warning threshold reached |
| `sla.breach` | SLA breached |
| `maintenance.started` | Maintenance window started |
| `maintenance.ended` | Maintenance window ended |

#### Request

```json
{
  "name": "Custom Integration",
  "url": "https://api.example.com/webhook/incidents",
  "events": [
    "incident.created",
    "incident.updated",
    "incident.resolved",
    "escalation"
  ],
  "secret": "whsec_your_signing_secret",
  "headers": {
    "X-Custom-Header": "custom-value",
    "Authorization": "Bearer integration_token"
  },
  "retry_policy": {
    "max_retries": 5,
    "initial_delay_seconds": 10,
    "max_delay_seconds": 300,
    "exponential_backoff": true
  },
  "filters": {
    "priority": ["critical", "high"],
    "team": ["platform", "infrastructure"]
  }
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "wh_003",
    "name": "Custom Integration",
    "url": "https://api.example.com/webhook/incidents",
    "events": [
      "incident.created",
      "incident.updated",
      "incident.resolved",
      "escalation"
    ],
    "headers": {
      "X-Custom-Header": "custom-value",
      "Authorization": "[REDACTED]"
    },
    "retry_policy": {
      "max_retries": 5,
      "initial_delay_seconds": 10,
      "max_delay_seconds": 300,
      "exponential_backoff": true
    },
    "filters": {
      "priority": ["critical", "high"],
      "team": ["platform", "infrastructure"]
    },
    "active": true,
    "signing_secret_set": true,
    "created_at": "2024-01-26T10:00:00Z"
  }
}
```

---

### Get Webhook

```
GET /api/v1/webhooks/{webhook_id}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "wh_001",
    "name": "Slack Notifications",
    "url": "https://hooks.slack.com/services/T00/B00/XXX",
    "events": ["incident.created", "incident.resolved", "escalation"],
    "headers": {},
    "retry_policy": {
      "max_retries": 3,
      "initial_delay_seconds": 10,
      "max_delay_seconds": 300,
      "exponential_backoff": true
    },
    "filters": {},
    "active": true,
    "signing_secret_set": true,
    "delivery_stats": {
      "total_sent": 1250,
      "successful": 1240,
      "failed": 10,
      "success_rate": 99.2,
      "avg_response_time_ms": 145
    },
    "recent_deliveries": [
      {
        "id": "del_001",
        "event": "incident.created",
        "incident_id": "inc_12345",
        "status": "success",
        "response_code": 200,
        "response_time_ms": 132,
        "delivered_at": "2024-01-26T10:15:00Z"
      },
      {
        "id": "del_002",
        "event": "incident.resolved",
        "incident_id": "inc_12340",
        "status": "success",
        "response_code": 200,
        "response_time_ms": 158,
        "delivered_at": "2024-01-26T09:45:00Z"
      }
    ],
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-20T14:30:00Z"
  }
}
```

---

### Update Webhook

```
PUT /api/v1/webhooks/{webhook_id}
```

#### Request Body

```json
{
  "events": [
    "incident.created",
    "incident.updated",
    "incident.resolved",
    "incident.closed"
  ],
  "active": true
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "wh_001",
    "name": "Slack Notifications",
    "events": [
      "incident.created",
      "incident.updated",
      "incident.resolved",
      "incident.closed"
    ],
    "active": true,
    "updated_at": "2024-01-26T11:00:00Z"
  }
}
```

---

### Delete Webhook

```
DELETE /api/v1/webhooks/{webhook_id}
```

#### Response

```json
{
  "success": true,
  "message": "Webhook deleted"
}
```

---

### Test Webhook

Send a test payload to verify webhook configuration.

```
POST /api/v1/webhooks/{webhook_id}/test
```

#### Request Body

```json
{
  "event": "incident.created"
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "webhook_id": "wh_001",
    "test_event": "incident.created",
    "delivery": {
      "status": "success",
      "response_code": 200,
      "response_time_ms": 145,
      "response_body": "{\"ok\":true}",
      "delivered_at": "2024-01-26T11:30:00Z"
    },
    "payload_sent": {
      "event": "incident.created",
      "test": true,
      "timestamp": "2024-01-26T11:30:00Z",
      "data": {
        "incident": {
          "id": "test_inc_001",
          "title": "Test Incident",
          "priority": "high",
          "status": "open"
        }
      }
    }
  }
}
```

#### Example

```bash
curl -X POST "https://api.incident-copilot.io/api/v1/webhooks/wh_001/test" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"event": "incident.created"}'
```

---

### Get Delivery History

Retrieve webhook delivery history.

```
GET /api/v1/webhooks/{webhook_id}/deliveries
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `status` | string | No | Filter: `success`, `failed`, `pending` |
| `event` | string | No | Filter by event type |
| `start_date` | string | No | Start date (ISO 8601) |
| `end_date` | string | No | End date (ISO 8601) |
| `page` | integer | No | Page number |
| `limit` | integer | No | Results per page |

#### Response

```json
{
  "success": true,
  "data": {
    "deliveries": [
      {
        "id": "del_001",
        "event": "incident.created",
        "incident_id": "inc_12345",
        "status": "success",
        "attempts": 1,
        "response_code": 200,
        "response_time_ms": 132,
        "request_headers": {
          "Content-Type": "application/json",
          "X-Webhook-Signature": "sha256=..."
        },
        "response_body": "{\"ok\":true}",
        "delivered_at": "2024-01-26T10:15:00Z"
      },
      {
        "id": "del_002",
        "event": "incident.resolved",
        "incident_id": "inc_12340",
        "status": "success",
        "attempts": 1,
        "response_code": 200,
        "response_time_ms": 158,
        "delivered_at": "2024-01-26T09:45:00Z"
      },
      {
        "id": "del_003",
        "event": "incident.updated",
        "incident_id": "inc_12335",
        "status": "failed",
        "attempts": 3,
        "last_error": "Connection timeout",
        "last_response_code": null,
        "next_retry": "2024-01-26T10:20:00Z",
        "delivered_at": null,
        "first_attempt_at": "2024-01-26T09:30:00Z"
      }
    ],
    "pagination": {
      "page": 1,
      "limit": 50,
      "total": 1250
    }
  }
}
```

---

### Retry Delivery

Manually retry a failed delivery.

```
POST /api/v1/webhooks/{webhook_id}/deliveries/{delivery_id}/retry
```

#### Response

```json
{
  "success": true,
  "data": {
    "delivery_id": "del_003",
    "retry_status": "success",
    "response_code": 200,
    "response_time_ms": 189,
    "retried_at": "2024-01-26T11:45:00Z"
  }
}
```

---

### Rotate Signing Secret

Generate a new signing secret for webhook verification.

```
POST /api/v1/webhooks/{webhook_id}/rotate-secret
```

#### Response

```json
{
  "success": true,
  "data": {
    "webhook_id": "wh_001",
    "new_secret": "whsec_new_signing_secret_value",
    "old_secret_valid_until": "2024-01-27T11:00:00Z",
    "rotated_at": "2024-01-26T11:00:00Z"
  },
  "message": "New secret generated. Old secret will remain valid for 24 hours."
}
```

---

### Pause/Resume Webhook

```
POST /api/v1/webhooks/{webhook_id}/pause
```

#### Response

```json
{
  "success": true,
  "data": {
    "webhook_id": "wh_001",
    "active": false,
    "paused_at": "2024-01-26T12:00:00Z",
    "paused_by": {
      "id": "user_123",
      "name": "Jane Smith"
    }
  }
}
```

```
POST /api/v1/webhooks/{webhook_id}/resume
```

#### Response

```json
{
  "success": true,
  "data": {
    "webhook_id": "wh_001",
    "active": true,
    "resumed_at": "2024-01-26T13:00:00Z",
    "queued_deliveries": 15
  }
}
```

---

## Webhook Payload Format

### Headers

Every webhook request includes these headers:

| Header | Description |
|--------|-------------|
| `Content-Type` | `application/json` |
| `X-Webhook-ID` | Webhook identifier |
| `X-Webhook-Event` | Event type |
| `X-Webhook-Delivery-ID` | Unique delivery ID |
| `X-Webhook-Timestamp` | Unix timestamp |
| `X-Webhook-Signature` | HMAC-SHA256 signature |

### Signature Verification

```python
import hmac
import hashlib

def verify_signature(payload, signature, secret):
    expected = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)

# Usage
signature = request.headers.get('X-Webhook-Signature')
is_valid = verify_signature(request.body, signature, webhook_secret)
```

### Example Payloads

#### incident.created

```json
{
  "event": "incident.created",
  "timestamp": "2024-01-26T10:15:00Z",
  "delivery_id": "del_001",
  "data": {
    "incident": {
      "id": "inc_12345",
      "title": "Database connection failures",
      "description": "Multiple services reporting database connection errors",
      "priority": "critical",
      "severity": 1,
      "status": "open",
      "team": {
        "id": "team_001",
        "name": "Platform"
      },
      "services": [
        {"id": "svc_010", "name": "postgres-primary"}
      ],
      "created_by": {
        "id": "user_123",
        "name": "Jane Smith"
      },
      "created_at": "2024-01-26T10:15:00Z",
      "url": "https://app.incident-copilot.io/incidents/inc_12345"
    }
  }
}
```

#### incident.resolved

```json
{
  "event": "incident.resolved",
  "timestamp": "2024-01-26T11:00:00Z",
  "delivery_id": "del_002",
  "data": {
    "incident": {
      "id": "inc_12345",
      "title": "Database connection failures",
      "priority": "critical",
      "status": "resolved",
      "resolution_summary": "Increased connection pool size and restarted affected services",
      "resolved_by": {
        "id": "user_123",
        "name": "Jane Smith"
      },
      "resolved_at": "2024-01-26T11:00:00Z",
      "duration_minutes": 45,
      "url": "https://app.incident-copilot.io/incidents/inc_12345"
    }
  }
}
```

#### escalation

```json
{
  "event": "escalation",
  "timestamp": "2024-01-26T10:30:00Z",
  "delivery_id": "del_003",
  "data": {
    "incident": {
      "id": "inc_12345",
      "title": "Database connection failures",
      "priority": "critical",
      "url": "https://app.incident-copilot.io/incidents/inc_12345"
    },
    "escalation": {
      "from_level": 1,
      "to_level": 2,
      "reason": "No acknowledgment within 15 minutes",
      "escalated_to": [
        {"id": "user_456", "name": "John Doe", "role": "Team Lead"}
      ],
      "escalated_at": "2024-01-26T10:30:00Z"
    }
  }
}
```

---

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| 400 | `INVALID_URL` | Webhook URL is invalid |
| 400 | `INVALID_EVENTS` | Unknown event types specified |
| 400 | `EMPTY_EVENTS` | At least one event required |
| 404 | `WEBHOOK_NOT_FOUND` | Webhook does not exist |
| 404 | `DELIVERY_NOT_FOUND` | Delivery record not found |
| 409 | `URL_EXISTS` | Webhook URL already registered |
| 422 | `UNREACHABLE_URL` | Cannot reach webhook URL |

### Error Response Format

```json
{
  "success": false,
  "error": {
    "code": "UNREACHABLE_URL",
    "message": "Cannot reach webhook URL",
    "details": {
      "url": "https://api.example.com/webhook",
      "error": "Connection refused",
      "tested_at": "2024-01-26T10:00:00Z"
    }
  }
}
```
