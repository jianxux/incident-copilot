# Integrations API Reference

The Integrations API provides webhooks for receiving alerts from external systems and managing integrations with status pages, notification channels, and plugins.

---

## Webhook Endpoints

### PagerDuty Webhook

Receives PagerDuty v3 webhook events.

```http
POST /webhooks/pagerduty
```

**Headers:**

| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes | `application/json` |
| `X-PagerDuty-Signature` | Recommended | HMAC-SHA256 signature (`v1=<hex>`) |

**Request Body (incident.triggered):**

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
      "summary": "Jane Doe",
      "type": "user_reference"
    },
    "data": {
      "id": "Q0JBXQZ7T8QXXX",
      "type": "incident",
      "html_url": "https://mycompany.pagerduty.com/incidents/Q0JBXQZ7T8QXXX",
      "incident_number": 42,
      "title": "High Error Rate on payments-api",
      "description": "Error rate exceeded 5% threshold",
      "created_at": "2024-01-15T02:47:23.000Z",
      "status": "triggered",
      "urgency": "high",
      "service": {
        "id": "PXXXXXX",
        "summary": "payments-api",
        "type": "service_reference"
      },
      "assignments": [
        {
          "at": "2024-01-15T02:47:23.000Z",
          "assignee": {
            "id": "P3Y1111",
            "summary": "Jane Doe",
            "type": "user_reference"
          }
        }
      ]
    }
  }
}
```

**Response (Success):**

```json
{
  "status": "accepted",
  "incident_id": "Q0JBXQZ7T8QXXX",
  "service": "payments-api"
}
```

**Response (Ignored):**

```json
{
  "status": "ignored",
  "reason": "not an incident trigger"
}
```

**Supported Event Types:**

| Event Type | Processed | Description |
|------------|-----------|-------------|
| `incident.triggered` | ✅ Yes | Triggers context assembly |
| `incident.acknowledged` | ❌ No | Acknowledged only |
| `incident.resolved` | ❌ No | Acknowledged only |
| `incident.escalated` | ❌ No | Acknowledged only |

**Signature Verification:**

```python
import hmac
import hashlib

def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    # signature format: "v1=<hex>"
    provided = signature.split("=")[1] if "=" in signature else signature
    return hmac.compare_digest(expected, provided)
```

---

### Opsgenie Webhook

Receives Opsgenie webhook events.

```http
POST /webhooks/opsgenie
```

**Headers:**

| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes | `application/json` |
| `X-OpsGenie-Signature` | Recommended | HMAC-SHA256 signature |

**Request Body (Create):**

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
    "source": "Datadog",
    "status": "open",
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

**Response (Success):**

```json
{
  "status": "accepted",
  "alert_id": "70413a06-38d6-4c85-92b8-5ebc900d42e2",
  "service": "payments-api"
}
```

**Priority Mapping:**

| Opsgenie Priority | Incident Copilot Severity |
|-------------------|---------------------------|
| P1 | critical |
| P2 | high |
| P3 | medium |
| P4 | low |
| P5 | info |

---

### Webhook Health Check

```http
GET /webhooks/health
```

**Response:**

```json
{
  "status": "healthy"
}
```

---

## Status Page Integration

### List Status Pages

```http
GET /statuspage/pages
```

**Response:**

```json
{
  "pages": [
    {
      "id": "abc123",
      "name": "Company Status",
      "subdomain": "status.company.com",
      "url": "https://status.company.com"
    }
  ],
  "total": 1
}
```

### Get Status Page Details

```http
GET /statuspage/pages/{page_id}
```

### List Components

```http
GET /statuspage/components
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `page_id` | string | Filter by page ID |

**Response:**

```json
{
  "components": [
    {
      "id": "comp_abc123",
      "name": "API Gateway",
      "status": "operational",
      "description": "Main API gateway",
      "group_id": null,
      "position": 1
    }
  ],
  "total": 10
}
```

### Update Component Status

```http
PATCH /statuspage/components/{component_id}/status
```

**Request Body:**

```json
{
  "status": "degraded_performance"
}
```

**Component Statuses:**

| Status | Description |
|--------|-------------|
| `operational` | Fully operational |
| `degraded_performance` | Experiencing issues |
| `partial_outage` | Partial service disruption |
| `major_outage` | Complete service outage |
| `under_maintenance` | Scheduled maintenance |

### Get Component Uptime

```http
GET /statuspage/components/{component_id}/uptime
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | integer | 30 | Period (1-365 days) |
| `page_id` | string | - | Page ID |

**Response:**

```json
{
  "component_id": "comp_abc123",
  "component_name": "API Gateway",
  "uptime_percentage": 99.95,
  "downtime_minutes": 21,
  "total_incidents": 2,
  "avg_resolution_minutes": 10.5,
  "period_start": "2023-12-15T00:00:00Z",
  "period_end": "2024-01-15T00:00:00Z"
}
```

### List Status Incidents

```http
GET /statuspage/incidents
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `page_id` | string | Filter by page ID |
| `status` | string | Filter by status |
| `limit` | integer | Max results (1-200) |

### List Unresolved Incidents

```http
GET /statuspage/incidents/unresolved
```

### Create Status Incident

```http
POST /statuspage/incidents
```

**Request Body:**

```json
{
  "name": "API Performance Degradation",
  "status": "investigating",
  "impact": "minor",
  "body": "We are investigating reports of slow API responses.",
  "component_ids": ["comp_abc123", "comp_def456"],
  "deliver_notifications": true
}
```

**Incident Statuses:**

| Status | Description |
|--------|-------------|
| `investigating` | Actively investigating |
| `identified` | Root cause identified |
| `monitoring` | Fix deployed, monitoring |
| `resolved` | Fully resolved |

**Impact Levels:**

| Impact | Description |
|--------|-------------|
| `none` | No user impact |
| `minor` | Small subset affected |
| `major` | Significant impact |
| `critical` | Service-wide outage |

### Update Status Incident

```http
PATCH /statuspage/incidents/{incident_id}
```

**Request Body:**

```json
{
  "status": "identified",
  "body": "We have identified the issue with our payment processor.",
  "component_statuses": {
    "comp_abc123": "partial_outage"
  },
  "deliver_notifications": true
}
```

### Resolve Status Incident

```http
POST /statuspage/incidents/{incident_id}/resolve
```

**Request Body:**

```json
{
  "body": "The issue has been fully resolved. All systems are operational.",
  "deliver_notifications": true
}
```

### Delete Status Incident

```http
DELETE /statuspage/incidents/{incident_id}
```

---

## Component Mappings

Map internal services to status page components.

### List Mappings

```http
GET /statuspage/mappings
```

**Response:**

```json
{
  "mappings": [
    {
      "internal_service": "payments-api",
      "component_id": "comp_abc123",
      "page_id": "page_xyz",
      "severity_threshold": "high",
      "auto_update": true
    }
  ],
  "total": 5
}
```

### Add Mapping

```http
POST /statuspage/mappings
```

**Request Body:**

```json
{
  "internal_service": "payments-api",
  "component_id": "comp_abc123",
  "page_id": "page_xyz",
  "severity_threshold": "high",
  "auto_update": true
}
```

### Remove Mapping

```http
DELETE /statuspage/mappings/{internal_service}
```

---

## Status Page Automation

### Set Manual Override

Prevent automatic status updates during manual incident management.

```http
POST /statuspage/automation/override/{internal_incident_id}
```

**Request Body:**

```json
{
  "enabled": true
}
```

### Check Manual Override

```http
GET /statuspage/automation/override/{internal_incident_id}
```

### Post Custom Update

Post a custom update to a synced status incident.

```http
POST /statuspage/automation/custom-update/{internal_incident_id}
```

**Request Body:**

```json
{
  "status": "identified",
  "body": "We have identified the root cause...",
  "deliver_notifications": true
}
```

### Get Automation Config

```http
GET /statuspage/automation/config
```

**Response:**

```json
{
  "enabled": true,
  "auto_create_for_severities": ["critical", "high"],
  "auto_update_enabled": true,
  "auto_resolve_enabled": true,
  "notification_delay_seconds": 300,
  "require_acknowledgement": false,
  "group_related_incidents": true,
  "grouping_window_minutes": 15
}
```

---

## Templates

### List Templates

```http
GET /statuspage/templates
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `category` | string | Filter by category |

**Response:**

```json
{
  "templates": [
    {
      "id": "investigating-default",
      "name": "Investigation Started",
      "category": "investigating",
      "description": "Default investigating template",
      "variables": ["service_name", "issue_description"],
      "is_default": true
    }
  ],
  "total": 15
}
```

### Get Template

```http
GET /statuspage/templates/{template_id}
```

### Render Template

```http
POST /statuspage/templates/render
```

**Request Body:**

```json
{
  "template_id": "investigating-default",
  "variables": {
    "service_name": "Payment API",
    "issue_description": "elevated error rates"
  }
}
```

**Response:**

```json
{
  "rendered": "We are investigating reports of elevated error rates affecting the Payment API. We will provide updates as we learn more.",
  "template_id": "investigating-default"
}
```

---

## Plugin System

### Create Plugin

```http
POST /plugins
```

**Request Body:**

```json
{
  "name": "Custom Notification",
  "description": "Send notifications to custom endpoint",
  "plugin_type": "webhook",
  "url": "https://example.com/webhook",
  "events": ["incident.triggered", "incident.resolved"],
  "headers": {
    "X-Custom-Header": "value"
  },
  "payload_template": "default"
}
```

**Plugin Types:**

| Type | Description |
|------|-------------|
| `webhook` | HTTP POST to URL |
| `slack` | Slack incoming webhook |
| `teams` | Microsoft Teams webhook |
| `script` | Custom script execution |

**Response:**

```json
{
  "id": "plg_abc123",
  "name": "Custom Notification",
  "plugin_type": "webhook",
  "status": "active",
  "created_at": "2024-01-15T10:00:00Z"
}
```

### List Plugins

```http
GET /plugins
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `type` | string | Filter by plugin type |
| `status` | string | Filter by status: `active`, `disabled`, `error` |
| `event` | string | Filter by event subscription |

### Get Plugin

```http
GET /plugins/{plugin_id}
```

### Update Plugin

```http
PUT /plugins/{plugin_id}
```

### Delete Plugin

```http
DELETE /plugins/{plugin_id}
```

### Test Plugin

Test a plugin without triggering actual events.

```http
POST /plugins/{plugin_id}/test
```

**Request Body:**

```json
{
  "sample_data": {
    "incident_id": "INC-12345",
    "title": "Test incident",
    "severity": "high",
    "service_name": "test-service"
  },
  "dry_run": true
}
```

**Response:**

```json
{
  "success": true,
  "response_status": 200,
  "response_body": "OK",
  "execution_time_ms": 150
}
```

### Enable/Disable Plugin

```http
POST /plugins/{plugin_id}/enable
POST /plugins/{plugin_id}/disable
```

### List Payload Templates

```http
GET /plugins/templates/list
```

### Get Payload Template

```http
GET /plugins/templates/{name}
```

---

## WebSocket API

Real-time updates via WebSocket connection.

### Connection

```
wss://your-domain.com/api/realtime/ws?token=<access_token>
```

**Alternative Authentication:**

```javascript
const ws = new WebSocket('wss://your-domain.com/api/realtime/ws');

ws.onopen = () => {
  ws.send(JSON.stringify({
    type: 'auth',
    token: '<access_token>'
  }));
};
```

### Subscribe to Incident

```json
{
  "type": "subscribe",
  "incident_id": "INC-12345"
}
```

### Unsubscribe from Incident

```json
{
  "type": "unsubscribe",
  "incident_id": "INC-12345"
}
```

### Typing Indicator

```json
{
  "type": "typing",
  "incident_id": "INC-12345",
  "is_typing": true
}
```

### Incoming Events

**Event Types:**

| Event | Description |
|-------|-------------|
| `incident.created` | New incident created |
| `incident.updated` | Incident details updated |
| `incident.resolved` | Incident resolved |
| `comment.added` | Comment added to incident |
| `comment.updated` | Comment edited |
| `comment.deleted` | Comment deleted |
| `timeline.event` | Timeline event added |
| `assignment.changed` | Assignment changed |
| `user.joined` | User joined incident room |
| `user.left` | User left incident room |
| `user.typing` | User typing indicator |
| `system.connected` | Connection established |
| `system.heartbeat` | Keep-alive ping |
| `system.error` | Error notification |

**Example Event:**

```json
{
  "event_id": "evt_abc123",
  "event_type": "incident.updated",
  "tenant_id": "tenant_xyz",
  "incident_id": "INC-12345",
  "timestamp": "2024-01-15T10:30:00Z",
  "actor_id": "user_123",
  "actor_name": "Jane Doe",
  "payload": {
    "field": "status",
    "old_value": "investigating",
    "new_value": "identified"
  }
}
```

### WebSocket Stats

```http
GET /api/realtime/stats
```

**Response:**

```json
{
  "total_connections": 150,
  "connections_by_tenant": {
    "tenant_xyz": 45
  },
  "active_rooms": 25
}
```

### WebSocket Health

```http
GET /api/realtime/health
```

**Response:**

```json
{
  "status": "ok",
  "connections": 150
}
```

---

## Server-Sent Events (SSE)

For simpler real-time updates without WebSocket.

### Dashboard Events

```http
GET /dashboard/events
```

**Connection:**

```javascript
const eventSource = new EventSource('/dashboard/events');

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data);
};

eventSource.addEventListener('incident_updated', (event) => {
  const data = JSON.parse(event.data);
  console.log('Incident updated:', data);
});
```

**Event Types:**

| Event | Description |
|-------|-------------|
| `connected` | Connection established |
| `incident_created` | New incident |
| `incident_updated` | Incident updated |
| `incident_completed` | Processing completed |
| `incident_failed` | Processing failed |

---

*See also: [Incidents API](incidents.md) | [Analytics API](analytics.md)*
