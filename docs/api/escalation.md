# Escalation Policies API

Define and manage escalation policies for incident response and on-call management.

## Overview

The Escalation Policies API enables you to:
- Create multi-level escalation policies
- Define escalation rules and conditions
- Configure notification channels per level
- Integrate with on-call schedules
- Track escalation history

## Base URL

```
/api/v1/escalation
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
| Escalation triggers | 20 requests/minute |

---

## Endpoints

### List Escalation Policies

Retrieve all escalation policies.

```
GET /api/v1/escalation/policies
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team` | string | No | Filter by team |
| `active` | boolean | No | Filter by active status |
| `page` | integer | No | Page number |
| `limit` | integer | No | Results per page |

#### Response

```json
{
  "success": true,
  "data": {
    "policies": [
      {
        "id": "esc_001",
        "name": "Critical Incident Escalation",
        "description": "Escalation policy for P1 critical incidents",
        "team": {
          "id": "team_001",
          "name": "Platform"
        },
        "levels_count": 4,
        "active": true,
        "linked_services": ["svc_001", "svc_002", "svc_003"],
        "created_at": "2024-01-10T00:00:00Z",
        "updated_at": "2024-01-20T14:30:00Z"
      }
    ],
    "pagination": {
      "page": 1,
      "limit": 20,
      "total": 8
    }
  }
}
```

#### Example

```bash
curl -X GET "https://api.incident-copilot.io/api/v1/escalation/policies?active=true" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Create Escalation Policy

Create a new escalation policy.

```
POST /api/v1/escalation/policies
```

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Policy name |
| `description` | string | No | Policy description |
| `team_id` | string | Yes | Owning team ID |
| `levels` | array | Yes | Escalation levels |
| `repeat` | object | No | Repeat configuration |
| `active` | boolean | No | Active status (default: true) |

#### Escalation Level Structure

```json
{
  "level": 1,
  "delay_minutes": 15,
  "targets": [
    {
      "type": "schedule",
      "schedule_id": "sched_001"
    }
  ],
  "channels": ["push", "sms"],
  "repeat_count": 2,
  "repeat_interval_minutes": 5
}
```

#### Target Types

| Type | Required Fields | Description |
|------|----------------|-------------|
| `user` | `user_id` | Specific user |
| `schedule` | `schedule_id` | On-call schedule |
| `team` | `team_id` | Entire team |
| `channel` | `channel_id`, `channel_type` | Slack/Teams channel |

#### Request

```json
{
  "name": "Critical Incident Escalation",
  "description": "Multi-level escalation for P1 incidents",
  "team_id": "team_001",
  "levels": [
    {
      "level": 1,
      "delay_minutes": 0,
      "targets": [
        {"type": "schedule", "schedule_id": "oncall_primary"}
      ],
      "channels": ["push", "slack"],
      "repeat_count": 3,
      "repeat_interval_minutes": 5
    },
    {
      "level": 2,
      "delay_minutes": 15,
      "targets": [
        {"type": "schedule", "schedule_id": "oncall_secondary"},
        {"type": "user", "user_id": "user_lead"}
      ],
      "channels": ["push", "sms", "phone"]
    },
    {
      "level": 3,
      "delay_minutes": 30,
      "targets": [
        {"type": "user", "user_id": "user_manager"}
      ],
      "channels": ["phone", "sms"]
    },
    {
      "level": 4,
      "delay_minutes": 60,
      "targets": [
        {"type": "user", "user_id": "user_director"}
      ],
      "channels": ["phone"]
    }
  ],
  "repeat": {
    "enabled": true,
    "max_repeats": 3,
    "repeat_interval_minutes": 30
  }
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "esc_003",
    "name": "Critical Incident Escalation",
    "description": "Multi-level escalation for P1 incidents",
    "team": {
      "id": "team_001",
      "name": "Platform"
    },
    "levels": [
      {
        "level": 1,
        "delay_minutes": 0,
        "targets": [
          {"type": "schedule", "schedule_id": "oncall_primary", "schedule_name": "Primary On-Call"}
        ],
        "channels": ["push", "slack"],
        "repeat_count": 3,
        "repeat_interval_minutes": 5
      }
    ],
    "repeat": {
      "enabled": true,
      "max_repeats": 3,
      "repeat_interval_minutes": 30
    },
    "active": true,
    "created_at": "2024-01-26T10:00:00Z"
  }
}
```

---

### Get Escalation Policy

```
GET /api/v1/escalation/policies/{policy_id}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "esc_001",
    "name": "Critical Incident Escalation",
    "description": "Multi-level escalation for P1 incidents",
    "team": {
      "id": "team_001",
      "name": "Platform"
    },
    "levels": [
      {
        "level": 1,
        "delay_minutes": 0,
        "targets": [
          {
            "type": "schedule",
            "schedule_id": "oncall_primary",
            "schedule_name": "Primary On-Call",
            "current_oncall": {
              "id": "user_123",
              "name": "Jane Smith"
            }
          }
        ],
        "channels": ["push", "slack"],
        "repeat_count": 3,
        "repeat_interval_minutes": 5
      },
      {
        "level": 2,
        "delay_minutes": 15,
        "targets": [
          {
            "type": "user",
            "user_id": "user_lead",
            "user_name": "Team Lead"
          }
        ],
        "channels": ["push", "sms", "phone"]
      }
    ],
    "repeat": {
      "enabled": true,
      "max_repeats": 3,
      "repeat_interval_minutes": 30
    },
    "statistics": {
      "total_escalations": 45,
      "avg_acknowledgment_time_minutes": 8.5,
      "level_2_escalation_rate": 0.22
    },
    "linked_services": [
      {"id": "svc_001", "name": "api-gateway"},
      {"id": "svc_002", "name": "user-service"}
    ],
    "active": true,
    "created_at": "2024-01-10T00:00:00Z",
    "updated_at": "2024-01-20T14:30:00Z"
  }
}
```

---

### Update Escalation Policy

```
PUT /api/v1/escalation/policies/{policy_id}
```

#### Request Body

```json
{
  "levels": [
    {
      "level": 1,
      "delay_minutes": 0,
      "targets": [
        {"type": "schedule", "schedule_id": "oncall_primary"}
      ],
      "channels": ["push", "slack", "sms"]
    }
  ]
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "esc_001",
    "name": "Critical Incident Escalation",
    "levels": [...],
    "updated_at": "2024-01-26T11:00:00Z"
  }
}
```

---

### Delete Escalation Policy

```
DELETE /api/v1/escalation/policies/{policy_id}
```

#### Response

```json
{
  "success": true,
  "message": "Escalation policy deleted"
}
```

---

### Trigger Escalation

Manually trigger escalation for an incident.

```
POST /api/v1/escalation/trigger
```

#### Request Body

```json
{
  "incident_id": "inc_12345",
  "reason": "No response from on-call after 20 minutes",
  "target_level": 2
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "escalation_id": "esc_evt_001",
    "incident_id": "inc_12345",
    "policy_id": "esc_001",
    "current_level": 2,
    "reason": "No response from on-call after 20 minutes",
    "triggered_by": {
      "id": "user_789",
      "name": "Incident Commander"
    },
    "notified_targets": [
      {
        "type": "user",
        "user_id": "user_lead",
        "user_name": "Team Lead",
        "channels": ["push", "sms", "phone"]
      }
    ],
    "triggered_at": "2024-01-26T10:30:00Z"
  }
}
```

#### Example

```bash
curl -X POST "https://api.incident-copilot.io/api/v1/escalation/trigger" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "inc_12345",
    "reason": "Manual escalation - need additional support"
  }'
```

---

### Acknowledge Escalation

Acknowledge an escalation to stop further notifications.

```
POST /api/v1/escalation/{escalation_id}/acknowledge
```

#### Request Body

```json
{
  "message": "I'm looking into this now"
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "escalation_id": "esc_evt_001",
    "incident_id": "inc_12345",
    "acknowledged_by": {
      "id": "user_123",
      "name": "Jane Smith"
    },
    "acknowledged_at": "2024-01-26T10:35:00Z",
    "time_to_acknowledge_minutes": 5,
    "message": "I'm looking into this now"
  }
}
```

---

### Get Escalation History

Get escalation history for an incident.

```
GET /api/v1/escalation/incidents/{incident_id}/history
```

#### Response

```json
{
  "success": true,
  "data": {
    "incident_id": "inc_12345",
    "policy": {
      "id": "esc_001",
      "name": "Critical Incident Escalation"
    },
    "current_level": 2,
    "acknowledged": true,
    "events": [
      {
        "id": "esc_evt_001",
        "type": "escalation_started",
        "level": 1,
        "targets": [
          {"type": "schedule", "name": "Primary On-Call", "user": "Jane Smith"}
        ],
        "timestamp": "2024-01-26T10:00:00Z"
      },
      {
        "id": "esc_evt_002",
        "type": "notification_sent",
        "level": 1,
        "target": {"user": "Jane Smith"},
        "channel": "push",
        "timestamp": "2024-01-26T10:00:01Z"
      },
      {
        "id": "esc_evt_003",
        "type": "notification_sent",
        "level": 1,
        "target": {"user": "Jane Smith"},
        "channel": "slack",
        "timestamp": "2024-01-26T10:00:02Z"
      },
      {
        "id": "esc_evt_004",
        "type": "level_escalated",
        "from_level": 1,
        "to_level": 2,
        "reason": "No acknowledgment within 15 minutes",
        "timestamp": "2024-01-26T10:15:00Z"
      },
      {
        "id": "esc_evt_005",
        "type": "acknowledged",
        "level": 2,
        "acknowledged_by": {"id": "user_lead", "name": "Team Lead"},
        "timestamp": "2024-01-26T10:18:00Z"
      }
    ]
  }
}
```

---

### List On-Call Schedules

```
GET /api/v1/escalation/schedules
```

#### Response

```json
{
  "success": true,
  "data": {
    "schedules": [
      {
        "id": "sched_001",
        "name": "Primary On-Call",
        "team": {
          "id": "team_001",
          "name": "Platform"
        },
        "timezone": "America/New_York",
        "rotation_type": "weekly",
        "current_oncall": {
          "id": "user_123",
          "name": "Jane Smith",
          "until": "2024-01-29T09:00:00Z"
        },
        "next_oncall": {
          "id": "user_456",
          "name": "John Doe",
          "from": "2024-01-29T09:00:00Z"
        }
      }
    ]
  }
}
```

---

### Get On-Call Schedule

```
GET /api/v1/escalation/schedules/{schedule_id}
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string | No | Schedule view start date |
| `end_date` | string | No | Schedule view end date |

#### Response

```json
{
  "success": true,
  "data": {
    "id": "sched_001",
    "name": "Primary On-Call",
    "description": "Primary on-call rotation for Platform team",
    "team": {
      "id": "team_001",
      "name": "Platform"
    },
    "timezone": "America/New_York",
    "rotation": {
      "type": "weekly",
      "handoff_time": "09:00",
      "handoff_day": "monday"
    },
    "participants": [
      {"id": "user_123", "name": "Jane Smith", "order": 1},
      {"id": "user_456", "name": "John Doe", "order": 2},
      {"id": "user_789", "name": "Alice Johnson", "order": 3}
    ],
    "current_shift": {
      "user": {"id": "user_123", "name": "Jane Smith"},
      "start": "2024-01-22T09:00:00Z",
      "end": "2024-01-29T09:00:00Z"
    },
    "upcoming_shifts": [
      {
        "user": {"id": "user_456", "name": "John Doe"},
        "start": "2024-01-29T09:00:00Z",
        "end": "2024-02-05T09:00:00Z"
      },
      {
        "user": {"id": "user_789", "name": "Alice Johnson"},
        "start": "2024-02-05T09:00:00Z",
        "end": "2024-02-12T09:00:00Z"
      }
    ],
    "overrides": [
      {
        "id": "ovr_001",
        "user": {"id": "user_999", "name": "Backup Engineer"},
        "start": "2024-01-27T18:00:00Z",
        "end": "2024-01-28T10:00:00Z",
        "reason": "Original on-call unavailable"
      }
    ]
  }
}
```

---

### Create Schedule Override

```
POST /api/v1/escalation/schedules/{schedule_id}/overrides
```

#### Request Body

```json
{
  "user_id": "user_999",
  "start": "2024-01-27T18:00:00Z",
  "end": "2024-01-28T10:00:00Z",
  "reason": "Covering for team member on PTO"
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "ovr_002",
    "schedule_id": "sched_001",
    "user": {
      "id": "user_999",
      "name": "Backup Engineer"
    },
    "start": "2024-01-27T18:00:00Z",
    "end": "2024-01-28T10:00:00Z",
    "reason": "Covering for team member on PTO",
    "created_by": {
      "id": "user_123",
      "name": "Jane Smith"
    },
    "created_at": "2024-01-26T15:00:00Z"
  }
}
```

---

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| 400 | `INVALID_LEVEL_ORDER` | Escalation levels must be sequential |
| 400 | `EMPTY_TARGETS` | Each level must have at least one target |
| 400 | `INVALID_DELAY` | Delay minutes must be non-negative |
| 404 | `POLICY_NOT_FOUND` | Escalation policy not found |
| 404 | `SCHEDULE_NOT_FOUND` | On-call schedule not found |
| 404 | `INCIDENT_NOT_FOUND` | Incident not found |
| 409 | `ALREADY_ACKNOWLEDGED` | Escalation already acknowledged |
| 409 | `OVERRIDE_CONFLICT` | Override conflicts with existing override |
| 422 | `INVALID_SCHEDULE_REF` | Referenced schedule does not exist |

### Error Response Format

```json
{
  "success": false,
  "error": {
    "code": "OVERRIDE_CONFLICT",
    "message": "Override conflicts with existing override",
    "details": {
      "conflicting_override_id": "ovr_001",
      "overlap_start": "2024-01-27T18:00:00Z",
      "overlap_end": "2024-01-28T06:00:00Z"
    }
  }
}
```
