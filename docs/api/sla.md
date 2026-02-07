# SLA Tracking API

Track and manage Service Level Agreements for incidents, including response times, resolution targets, and breach notifications.

## Overview

The SLA Tracking API enables you to:
- Define SLA policies with response and resolution targets
- Track SLA status for active incidents
- Query SLA breach history
- Configure breach notifications and escalations

## Base URL

```
/api/v1/sla
```

## Authentication

All endpoints require authentication via Bearer token or API key.

```bash
# Bearer Token
Authorization: Bearer <your_jwt_token>

# API Key
X-API-Key: <your_api_key>
```

## Rate Limits

| Endpoint | Rate Limit |
|----------|------------|
| GET endpoints | 100 requests/minute |
| POST/PUT endpoints | 30 requests/minute |
| DELETE endpoints | 10 requests/minute |

---

## Endpoints

### List SLA Policies

Retrieve all configured SLA policies.

```
GET /api/v1/sla/policies
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `page` | integer | No | Page number (default: 1) |
| `limit` | integer | No | Results per page (default: 20, max: 100) |
| `priority` | string | No | Filter by priority: `critical`, `high`, `medium`, `low` |
| `active` | boolean | No | Filter by active status |

#### Response

```json
{
  "success": true,
  "data": {
    "policies": [
      {
        "id": "sla_policy_001",
        "name": "Critical Incident SLA",
        "description": "SLA for P1 critical incidents",
        "priority": "critical",
        "response_target_minutes": 15,
        "resolution_target_minutes": 240,
        "business_hours_only": false,
        "active": true,
        "escalation_policy_id": "esc_001",
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-20T14:30:00Z"
      },
      {
        "id": "sla_policy_002",
        "name": "High Priority SLA",
        "description": "SLA for P2 high priority incidents",
        "priority": "high",
        "response_target_minutes": 60,
        "resolution_target_minutes": 480,
        "business_hours_only": true,
        "active": true,
        "escalation_policy_id": "esc_002",
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-18T09:15:00Z"
      }
    ],
    "pagination": {
      "page": 1,
      "limit": 20,
      "total": 4,
      "total_pages": 1
    }
  }
}
```

#### Example

```bash
curl -X GET "https://api.incident-copilot.io/api/v1/sla/policies?priority=critical" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Create SLA Policy

Create a new SLA policy.

```
POST /api/v1/sla/policies
```

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Policy name (max 100 chars) |
| `description` | string | No | Policy description |
| `priority` | string | Yes | Priority level: `critical`, `high`, `medium`, `low` |
| `response_target_minutes` | integer | Yes | Response time target in minutes |
| `resolution_target_minutes` | integer | Yes | Resolution time target in minutes |
| `business_hours_only` | boolean | No | Count only business hours (default: false) |
| `escalation_policy_id` | string | No | Linked escalation policy |

#### Request

```json
{
  "name": "Medium Priority SLA",
  "description": "SLA for P3 medium priority incidents",
  "priority": "medium",
  "response_target_minutes": 120,
  "resolution_target_minutes": 1440,
  "business_hours_only": true,
  "escalation_policy_id": "esc_003"
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "sla_policy_003",
    "name": "Medium Priority SLA",
    "description": "SLA for P3 medium priority incidents",
    "priority": "medium",
    "response_target_minutes": 120,
    "resolution_target_minutes": 1440,
    "business_hours_only": true,
    "active": true,
    "escalation_policy_id": "esc_003",
    "created_at": "2024-01-25T16:00:00Z",
    "updated_at": "2024-01-25T16:00:00Z"
  }
}
```

#### Example

```bash
curl -X POST "https://api.incident-copilot.io/api/v1/sla/policies" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Medium Priority SLA",
    "priority": "medium",
    "response_target_minutes": 120,
    "resolution_target_minutes": 1440,
    "business_hours_only": true
  }'
```

---

### Get SLA Policy

Retrieve a specific SLA policy by ID.

```
GET /api/v1/sla/policies/{policy_id}
```

#### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `policy_id` | string | Yes | SLA policy ID |

#### Response

```json
{
  "success": true,
  "data": {
    "id": "sla_policy_001",
    "name": "Critical Incident SLA",
    "description": "SLA for P1 critical incidents",
    "priority": "critical",
    "response_target_minutes": 15,
    "resolution_target_minutes": 240,
    "business_hours_only": false,
    "active": true,
    "escalation_policy_id": "esc_001",
    "statistics": {
      "incidents_tracked": 156,
      "response_breaches": 12,
      "resolution_breaches": 8,
      "compliance_rate": 92.3
    },
    "created_at": "2024-01-15T10:00:00Z",
    "updated_at": "2024-01-20T14:30:00Z"
  }
}
```

#### Example

```bash
curl -X GET "https://api.incident-copilot.io/api/v1/sla/policies/sla_policy_001" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Update SLA Policy

Update an existing SLA policy.

```
PUT /api/v1/sla/policies/{policy_id}
```

#### Request Body

All fields are optional. Only provided fields will be updated.

```json
{
  "response_target_minutes": 10,
  "resolution_target_minutes": 180,
  "active": true
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "sla_policy_001",
    "name": "Critical Incident SLA",
    "description": "SLA for P1 critical incidents",
    "priority": "critical",
    "response_target_minutes": 10,
    "resolution_target_minutes": 180,
    "business_hours_only": false,
    "active": true,
    "escalation_policy_id": "esc_001",
    "created_at": "2024-01-15T10:00:00Z",
    "updated_at": "2024-01-26T11:00:00Z"
  }
}
```

#### Example

```bash
curl -X PUT "https://api.incident-copilot.io/api/v1/sla/policies/sla_policy_001" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"response_target_minutes": 10}'
```

---

### Delete SLA Policy

Delete an SLA policy. Active policies cannot be deleted.

```
DELETE /api/v1/sla/policies/{policy_id}
```

#### Response

```json
{
  "success": true,
  "message": "SLA policy deleted successfully"
}
```

#### Example

```bash
curl -X DELETE "https://api.incident-copilot.io/api/v1/sla/policies/sla_policy_003" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Get Incident SLA Status

Get SLA tracking status for a specific incident.

```
GET /api/v1/sla/incidents/{incident_id}
```

#### Response

```json
{
  "success": true,
  "data": {
    "incident_id": "inc_12345",
    "policy_id": "sla_policy_001",
    "policy_name": "Critical Incident SLA",
    "status": "at_risk",
    "response": {
      "target_minutes": 15,
      "elapsed_minutes": 12,
      "remaining_minutes": 3,
      "status": "on_track",
      "responded_at": null,
      "breached": false
    },
    "resolution": {
      "target_minutes": 240,
      "elapsed_minutes": 180,
      "remaining_minutes": 60,
      "status": "at_risk",
      "resolved_at": null,
      "breached": false
    },
    "started_at": "2024-01-26T10:00:00Z",
    "business_hours_elapsed": null
  }
}
```

#### Status Values

| Status | Description |
|--------|-------------|
| `on_track` | SLA targets will likely be met |
| `at_risk` | Less than 25% time remaining |
| `breached` | SLA target has been exceeded |
| `met` | SLA target was met |
| `paused` | SLA timer is paused |

#### Example

```bash
curl -X GET "https://api.incident-copilot.io/api/v1/sla/incidents/inc_12345" \
  -H "Authorization: Bearer $TOKEN"
```

---

### List SLA Breaches

Query SLA breach history.

```
GET /api/v1/sla/breaches
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string | No | Start date (ISO 8601) |
| `end_date` | string | No | End date (ISO 8601) |
| `policy_id` | string | No | Filter by policy ID |
| `breach_type` | string | No | `response` or `resolution` |
| `page` | integer | No | Page number |
| `limit` | integer | No | Results per page |

#### Response

```json
{
  "success": true,
  "data": {
    "breaches": [
      {
        "id": "breach_001",
        "incident_id": "inc_10234",
        "incident_title": "Database connection failures",
        "policy_id": "sla_policy_001",
        "breach_type": "response",
        "target_minutes": 15,
        "actual_minutes": 23,
        "exceeded_by_minutes": 8,
        "breached_at": "2024-01-24T14:23:00Z"
      },
      {
        "id": "breach_002",
        "incident_id": "inc_10198",
        "incident_title": "API latency degradation",
        "policy_id": "sla_policy_002",
        "breach_type": "resolution",
        "target_minutes": 480,
        "actual_minutes": 612,
        "exceeded_by_minutes": 132,
        "breached_at": "2024-01-23T22:12:00Z"
      }
    ],
    "summary": {
      "total_breaches": 20,
      "response_breaches": 12,
      "resolution_breaches": 8
    },
    "pagination": {
      "page": 1,
      "limit": 20,
      "total": 20,
      "total_pages": 1
    }
  }
}
```

#### Example

```bash
curl -X GET "https://api.incident-copilot.io/api/v1/sla/breaches?start_date=2024-01-01&breach_type=response" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Pause SLA Timer

Pause the SLA timer for an incident (e.g., waiting on customer).

```
POST /api/v1/sla/incidents/{incident_id}/pause
```

#### Request Body

```json
{
  "reason": "Waiting for customer response"
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "incident_id": "inc_12345",
    "paused": true,
    "paused_at": "2024-01-26T11:30:00Z",
    "pause_reason": "Waiting for customer response",
    "total_paused_minutes": 0
  }
}
```

#### Example

```bash
curl -X POST "https://api.incident-copilot.io/api/v1/sla/incidents/inc_12345/pause" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Waiting for customer response"}'
```

---

### Resume SLA Timer

Resume a paused SLA timer.

```
POST /api/v1/sla/incidents/{incident_id}/resume
```

#### Response

```json
{
  "success": true,
  "data": {
    "incident_id": "inc_12345",
    "paused": false,
    "resumed_at": "2024-01-26T12:45:00Z",
    "total_paused_minutes": 75
  }
}
```

#### Example

```bash
curl -X POST "https://api.incident-copilot.io/api/v1/sla/incidents/inc_12345/resume" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| 400 | `INVALID_PRIORITY` | Invalid priority level specified |
| 400 | `INVALID_TARGET_TIME` | Target time must be positive integer |
| 404 | `POLICY_NOT_FOUND` | SLA policy does not exist |
| 404 | `INCIDENT_NOT_FOUND` | Incident does not exist |
| 409 | `POLICY_ACTIVE` | Cannot delete active policy |
| 409 | `ALREADY_PAUSED` | SLA timer is already paused |
| 409 | `NOT_PAUSED` | SLA timer is not paused |
| 422 | `DUPLICATE_PRIORITY` | Policy for this priority already exists |

### Error Response Format

```json
{
  "success": false,
  "error": {
    "code": "POLICY_NOT_FOUND",
    "message": "SLA policy with ID 'sla_policy_999' not found",
    "details": {
      "policy_id": "sla_policy_999"
    }
  }
}
```
