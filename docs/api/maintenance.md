# Maintenance Windows API

Schedule and manage maintenance windows to suppress alerts and track planned downtime.

## Overview

The Maintenance Windows API enables you to:
- Schedule maintenance windows for services
- Suppress alerts during maintenance
- Track maintenance history
- Configure recurring maintenance schedules
- Notify stakeholders of planned maintenance

## Base URL

```
/api/v1/maintenance
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
| DELETE endpoints | 20 requests/minute |

---

## Endpoints

### List Maintenance Windows

Retrieve all maintenance windows.

```
GET /api/v1/maintenance/windows
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `status` | string | No | Filter: `scheduled`, `active`, `completed`, `cancelled` |
| `service_id` | string | No | Filter by service |
| `start_after` | string | No | Windows starting after date |
| `start_before` | string | No | Windows starting before date |
| `page` | integer | No | Page number |
| `limit` | integer | No | Results per page |

#### Response

```json
{
  "success": true,
  "data": {
    "windows": [
      {
        "id": "maint_001",
        "title": "Database Upgrade",
        "description": "Upgrading PostgreSQL from 14 to 15",
        "status": "scheduled",
        "start_time": "2024-01-28T02:00:00Z",
        "end_time": "2024-01-28T06:00:00Z",
        "duration_minutes": 240,
        "services": [
          {"id": "svc_010", "name": "postgres-primary"},
          {"id": "svc_011", "name": "postgres-replica"}
        ],
        "created_by": {
          "id": "user_123",
          "name": "Jane Smith"
        },
        "created_at": "2024-01-20T10:00:00Z"
      },
      {
        "id": "maint_002",
        "title": "Network Maintenance",
        "description": "Core switch firmware update",
        "status": "active",
        "start_time": "2024-01-26T04:00:00Z",
        "end_time": "2024-01-26T06:00:00Z",
        "duration_minutes": 120,
        "services": [
          {"id": "svc_050", "name": "network-core"}
        ],
        "suppressed_alerts": 23,
        "created_by": {
          "id": "user_456",
          "name": "John Doe"
        },
        "created_at": "2024-01-19T15:00:00Z"
      }
    ],
    "pagination": {
      "page": 1,
      "limit": 20,
      "total": 15
    }
  }
}
```

#### Example

```bash
curl -X GET "https://api.incident-copilot.io/api/v1/maintenance/windows?status=scheduled" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Create Maintenance Window

Schedule a new maintenance window.

```
POST /api/v1/maintenance/windows
```

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | Yes | Maintenance title |
| `description` | string | No | Detailed description |
| `start_time` | string | Yes | Start time (ISO 8601) |
| `end_time` | string | Yes | End time (ISO 8601) |
| `services` | array | Yes | Service IDs affected |
| `suppress_alerts` | boolean | No | Suppress alerts (default: true) |
| `notify_stakeholders` | boolean | No | Send notifications (default: true) |
| `notification_lead_time_minutes` | integer | No | Notify before start (default: 60) |
| `tags` | array | No | Maintenance tags |

#### Request

```json
{
  "title": "API Gateway Deployment",
  "description": "Rolling deployment of API gateway v2.5.0 with new rate limiting features",
  "start_time": "2024-01-29T03:00:00Z",
  "end_time": "2024-01-29T04:00:00Z",
  "services": ["svc_001"],
  "suppress_alerts": true,
  "notify_stakeholders": true,
  "notification_lead_time_minutes": 120,
  "tags": ["deployment", "api-gateway"]
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "maint_003",
    "title": "API Gateway Deployment",
    "description": "Rolling deployment of API gateway v2.5.0 with new rate limiting features",
    "status": "scheduled",
    "start_time": "2024-01-29T03:00:00Z",
    "end_time": "2024-01-29T04:00:00Z",
    "duration_minutes": 60,
    "services": [
      {"id": "svc_001", "name": "api-gateway"}
    ],
    "suppress_alerts": true,
    "notify_stakeholders": true,
    "notifications": {
      "scheduled_for": "2024-01-29T01:00:00Z",
      "channels": ["slack", "email"],
      "recipients_count": 45
    },
    "tags": ["deployment", "api-gateway"],
    "created_by": {
      "id": "user_123",
      "name": "Jane Smith"
    },
    "created_at": "2024-01-26T10:00:00Z"
  }
}
```

#### Example

```bash
curl -X POST "https://api.incident-copilot.io/api/v1/maintenance/windows" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Database Maintenance",
    "start_time": "2024-01-29T03:00:00Z",
    "end_time": "2024-01-29T05:00:00Z",
    "services": ["svc_010"]
  }'
```

---

### Get Maintenance Window

```
GET /api/v1/maintenance/windows/{window_id}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "maint_001",
    "title": "Database Upgrade",
    "description": "Upgrading PostgreSQL from 14 to 15",
    "status": "scheduled",
    "start_time": "2024-01-28T02:00:00Z",
    "end_time": "2024-01-28T06:00:00Z",
    "duration_minutes": 240,
    "services": [
      {
        "id": "svc_010",
        "name": "postgres-primary",
        "status": "healthy"
      },
      {
        "id": "svc_011",
        "name": "postgres-replica",
        "status": "healthy"
      }
    ],
    "affected_dependents": [
      {"id": "svc_002", "name": "user-service"},
      {"id": "svc_003", "name": "payment-service"},
      {"id": "svc_020", "name": "order-service"}
    ],
    "suppress_alerts": true,
    "suppression_rules": [
      {"type": "service", "service_id": "svc_010"},
      {"type": "service", "service_id": "svc_011"}
    ],
    "notifications": {
      "pre_maintenance": {
        "sent": true,
        "sent_at": "2024-01-28T01:00:00Z",
        "recipients_count": 45
      },
      "start": {
        "sent": false
      },
      "end": {
        "sent": false
      }
    },
    "checklist": [
      {"task": "Take database backup", "completed": true, "completed_at": "2024-01-27T20:00:00Z"},
      {"task": "Notify on-call team", "completed": true, "completed_at": "2024-01-27T18:00:00Z"},
      {"task": "Verify rollback procedure", "completed": false}
    ],
    "tags": ["database", "upgrade", "postgresql"],
    "created_by": {
      "id": "user_123",
      "name": "Jane Smith"
    },
    "created_at": "2024-01-20T10:00:00Z",
    "updated_at": "2024-01-27T20:00:00Z"
  }
}
```

---

### Update Maintenance Window

```
PUT /api/v1/maintenance/windows/{window_id}
```

#### Request Body

```json
{
  "end_time": "2024-01-28T07:00:00Z",
  "description": "Extended by 1 hour for additional testing"
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "maint_001",
    "title": "Database Upgrade",
    "end_time": "2024-01-28T07:00:00Z",
    "duration_minutes": 300,
    "description": "Extended by 1 hour for additional testing",
    "updated_at": "2024-01-28T05:30:00Z"
  }
}
```

---

### Cancel Maintenance Window

```
POST /api/v1/maintenance/windows/{window_id}/cancel
```

#### Request Body

```json
{
  "reason": "Maintenance postponed due to production incident"
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "maint_001",
    "status": "cancelled",
    "cancelled_at": "2024-01-27T15:00:00Z",
    "cancelled_by": {
      "id": "user_123",
      "name": "Jane Smith"
    },
    "cancellation_reason": "Maintenance postponed due to production incident",
    "notification_sent": true
  }
}
```

---

### Start Maintenance Window

Manually start a maintenance window before its scheduled time.

```
POST /api/v1/maintenance/windows/{window_id}/start
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "maint_001",
    "status": "active",
    "actual_start_time": "2024-01-28T01:45:00Z",
    "started_by": {
      "id": "user_123",
      "name": "Jane Smith"
    },
    "alert_suppression_active": true
  }
}
```

---

### End Maintenance Window

Manually end a maintenance window.

```
POST /api/v1/maintenance/windows/{window_id}/end
```

#### Request Body

```json
{
  "notes": "Upgrade completed successfully. All services verified operational.",
  "success": true
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "maint_001",
    "status": "completed",
    "actual_start_time": "2024-01-28T02:00:00Z",
    "actual_end_time": "2024-01-28T05:15:00Z",
    "actual_duration_minutes": 195,
    "ended_by": {
      "id": "user_123",
      "name": "Jane Smith"
    },
    "success": true,
    "notes": "Upgrade completed successfully. All services verified operational.",
    "suppressed_alerts_count": 45,
    "alert_suppression_active": false
  }
}
```

---

### Extend Maintenance Window

Extend an active maintenance window.

```
POST /api/v1/maintenance/windows/{window_id}/extend
```

#### Request Body

```json
{
  "extend_minutes": 60,
  "reason": "Additional time needed for verification"
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "maint_001",
    "original_end_time": "2024-01-28T06:00:00Z",
    "new_end_time": "2024-01-28T07:00:00Z",
    "extension_minutes": 60,
    "reason": "Additional time needed for verification",
    "extended_by": {
      "id": "user_123",
      "name": "Jane Smith"
    },
    "notification_sent": true
  }
}
```

---

### Create Recurring Maintenance

```
POST /api/v1/maintenance/recurring
```

#### Request Body

```json
{
  "title": "Weekly Database Backup",
  "description": "Full database backup with brief service interruption",
  "schedule": {
    "frequency": "weekly",
    "day_of_week": "sunday",
    "time": "03:00",
    "timezone": "America/New_York",
    "duration_minutes": 30
  },
  "services": ["svc_010"],
  "suppress_alerts": true,
  "notify_stakeholders": true,
  "notification_lead_time_minutes": 30,
  "enabled": true
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "recur_001",
    "title": "Weekly Database Backup",
    "schedule": {
      "frequency": "weekly",
      "day_of_week": "sunday",
      "time": "03:00",
      "timezone": "America/New_York",
      "duration_minutes": 30
    },
    "next_occurrence": "2024-01-28T08:00:00Z",
    "services": [
      {"id": "svc_010", "name": "postgres-primary"}
    ],
    "enabled": true,
    "created_at": "2024-01-26T10:00:00Z"
  }
}
```

---

### List Recurring Maintenance

```
GET /api/v1/maintenance/recurring
```

#### Response

```json
{
  "success": true,
  "data": {
    "recurring_windows": [
      {
        "id": "recur_001",
        "title": "Weekly Database Backup",
        "schedule": {
          "frequency": "weekly",
          "day_of_week": "sunday",
          "time": "03:00",
          "duration_minutes": 30
        },
        "next_occurrence": "2024-01-28T08:00:00Z",
        "last_occurrence": "2024-01-21T08:00:00Z",
        "last_status": "completed",
        "enabled": true
      },
      {
        "id": "recur_002",
        "title": "Monthly Certificate Rotation",
        "schedule": {
          "frequency": "monthly",
          "day_of_month": 1,
          "time": "02:00",
          "duration_minutes": 15
        },
        "next_occurrence": "2024-02-01T07:00:00Z",
        "enabled": true
      }
    ]
  }
}
```

---

### Get Active Maintenance

Check if any maintenance is currently active.

```
GET /api/v1/maintenance/active
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `service_id` | string | No | Filter by service |

#### Response

```json
{
  "success": true,
  "data": {
    "active_windows": [
      {
        "id": "maint_002",
        "title": "Network Maintenance",
        "status": "active",
        "start_time": "2024-01-26T04:00:00Z",
        "end_time": "2024-01-26T06:00:00Z",
        "remaining_minutes": 45,
        "services": [
          {"id": "svc_050", "name": "network-core"}
        ],
        "alert_suppression_active": true
      }
    ],
    "is_any_active": true
  }
}
```

---

### Get Suppressed Alerts

List alerts suppressed during a maintenance window.

```
GET /api/v1/maintenance/windows/{window_id}/suppressed-alerts
```

#### Response

```json
{
  "success": true,
  "data": {
    "window_id": "maint_002",
    "alerts": [
      {
        "id": "alert_001",
        "title": "High CPU Usage - network-core",
        "severity": "warning",
        "source": "prometheus",
        "suppressed_at": "2024-01-26T04:15:00Z"
      },
      {
        "id": "alert_002",
        "title": "Connection Timeout - network-core",
        "severity": "critical",
        "source": "pingdom",
        "suppressed_at": "2024-01-26T04:18:00Z"
      }
    ],
    "total_suppressed": 23,
    "pagination": {
      "page": 1,
      "limit": 50
    }
  }
}
```

---

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| 400 | `INVALID_TIME_RANGE` | End time must be after start time |
| 400 | `PAST_START_TIME` | Cannot schedule maintenance in the past |
| 400 | `EMPTY_SERVICES` | At least one service required |
| 400 | `INVALID_SCHEDULE` | Invalid recurring schedule configuration |
| 404 | `WINDOW_NOT_FOUND` | Maintenance window not found |
| 409 | `ALREADY_STARTED` | Maintenance window already started |
| 409 | `ALREADY_ENDED` | Maintenance window already ended |
| 409 | `OVERLAPPING_WINDOW` | Conflicts with existing maintenance |
| 422 | `SERVICE_NOT_FOUND` | One or more services not found |

### Error Response Format

```json
{
  "success": false,
  "error": {
    "code": "OVERLAPPING_WINDOW",
    "message": "Maintenance conflicts with existing scheduled maintenance",
    "details": {
      "conflicting_window_id": "maint_001",
      "conflicting_window_title": "Database Upgrade",
      "overlap_start": "2024-01-28T02:00:00Z",
      "overlap_end": "2024-01-28T04:00:00Z"
    }
  }
}
```
