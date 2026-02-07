# Notification Preferences API

Manage user and team notification preferences for incident alerts, updates, and escalations.

## Overview

The Notification Preferences API allows you to:
- Configure notification channels (email, Slack, SMS, push)
- Set quiet hours and do-not-disturb schedules
- Define notification rules based on incident attributes
- Manage team-wide notification policies

## Base URL

```
/api/v1/notifications
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
| GET endpoints | 60 requests/minute |
| POST/PUT endpoints | 30 requests/minute |
| DELETE endpoints | 20 requests/minute |

---

## Endpoints

### Get User Preferences

Retrieve notification preferences for the current user.

```
GET /api/v1/notifications/preferences
```

#### Response

```json
{
  "success": true,
  "data": {
    "user_id": "user_123",
    "channels": {
      "email": {
        "enabled": true,
        "address": "jane@example.com",
        "verified": true
      },
      "slack": {
        "enabled": true,
        "user_id": "U0123456789",
        "dm_enabled": true
      },
      "sms": {
        "enabled": true,
        "phone": "+1-555-123-4567",
        "verified": true
      },
      "push": {
        "enabled": true,
        "devices": ["device_001", "device_002"]
      }
    },
    "preferences": {
      "incident_created": {
        "enabled": true,
        "channels": ["slack", "push"],
        "priority_filter": ["critical", "high"]
      },
      "incident_assigned": {
        "enabled": true,
        "channels": ["email", "slack", "push"]
      },
      "incident_updated": {
        "enabled": true,
        "channels": ["slack"],
        "only_when_assigned": true
      },
      "incident_resolved": {
        "enabled": true,
        "channels": ["email", "slack"]
      },
      "sla_warning": {
        "enabled": true,
        "channels": ["slack", "sms"],
        "warning_threshold_percent": 75
      },
      "sla_breach": {
        "enabled": true,
        "channels": ["email", "slack", "sms", "push"]
      },
      "escalation": {
        "enabled": true,
        "channels": ["sms", "push"]
      },
      "mention": {
        "enabled": true,
        "channels": ["slack", "push"]
      },
      "daily_digest": {
        "enabled": true,
        "channels": ["email"],
        "time": "09:00",
        "timezone": "America/New_York"
      }
    },
    "quiet_hours": {
      "enabled": true,
      "start": "22:00",
      "end": "08:00",
      "timezone": "America/New_York",
      "override_for_critical": true
    },
    "updated_at": "2024-01-25T14:30:00Z"
  }
}
```

#### Example

```bash
curl -X GET "https://api.incident-copilot.io/api/v1/notifications/preferences" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Update User Preferences

Update notification preferences for the current user.

```
PUT /api/v1/notifications/preferences
```

#### Request Body

All fields are optional. Only provided fields will be updated.

```json
{
  "channels": {
    "sms": {
      "enabled": false
    }
  },
  "preferences": {
    "incident_updated": {
      "enabled": true,
      "channels": ["email", "slack"],
      "only_when_assigned": false
    },
    "daily_digest": {
      "enabled": true,
      "time": "08:00"
    }
  },
  "quiet_hours": {
    "enabled": true,
    "start": "23:00",
    "end": "07:00"
  }
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "user_id": "user_123",
    "channels": {
      "email": {
        "enabled": true,
        "address": "jane@example.com",
        "verified": true
      },
      "slack": {
        "enabled": true,
        "user_id": "U0123456789",
        "dm_enabled": true
      },
      "sms": {
        "enabled": false,
        "phone": "+1-555-123-4567",
        "verified": true
      },
      "push": {
        "enabled": true,
        "devices": ["device_001", "device_002"]
      }
    },
    "preferences": {
      "incident_updated": {
        "enabled": true,
        "channels": ["email", "slack"],
        "only_when_assigned": false
      }
    },
    "quiet_hours": {
      "enabled": true,
      "start": "23:00",
      "end": "07:00",
      "timezone": "America/New_York",
      "override_for_critical": true
    },
    "updated_at": "2024-01-26T10:15:00Z"
  }
}
```

#### Example

```bash
curl -X PUT "https://api.incident-copilot.io/api/v1/notifications/preferences" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "quiet_hours": {"enabled": true, "start": "23:00", "end": "07:00"}
  }'
```

---

### Add Notification Channel

Add a new notification channel for the user.

```
POST /api/v1/notifications/channels
```

#### Request Body

```json
{
  "type": "sms",
  "phone": "+1-555-987-6543"
}
```

#### Channel Types

| Type | Required Fields |
|------|----------------|
| `email` | `address` |
| `sms` | `phone` |
| `slack` | `user_id` or `webhook_url` |
| `push` | `device_token`, `platform` (`ios`, `android`, `web`) |
| `webhook` | `url`, optional `secret` |

#### Response

```json
{
  "success": true,
  "data": {
    "channel_id": "ch_001",
    "type": "sms",
    "phone": "+1-555-987-6543",
    "verified": false,
    "verification_sent_at": "2024-01-26T10:20:00Z",
    "created_at": "2024-01-26T10:20:00Z"
  },
  "message": "Verification code sent to +1-555-987-6543"
}
```

#### Example

```bash
curl -X POST "https://api.incident-copilot.io/api/v1/notifications/channels" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type": "sms", "phone": "+1-555-987-6543"}'
```

---

### Verify Channel

Verify a notification channel with the verification code.

```
POST /api/v1/notifications/channels/{channel_id}/verify
```

#### Request Body

```json
{
  "code": "123456"
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "channel_id": "ch_001",
    "type": "sms",
    "phone": "+1-555-987-6543",
    "verified": true,
    "verified_at": "2024-01-26T10:25:00Z"
  }
}
```

#### Example

```bash
curl -X POST "https://api.incident-copilot.io/api/v1/notifications/channels/ch_001/verify" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"code": "123456"}'
```

---

### Remove Notification Channel

Remove a notification channel.

```
DELETE /api/v1/notifications/channels/{channel_id}
```

#### Response

```json
{
  "success": true,
  "message": "Notification channel removed"
}
```

#### Example

```bash
curl -X DELETE "https://api.incident-copilot.io/api/v1/notifications/channels/ch_001" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Create Notification Rule

Create a custom notification rule based on incident attributes.

```
POST /api/v1/notifications/rules
```

#### Request Body

```json
{
  "name": "Database Critical Alerts",
  "description": "Get notified for all critical database incidents",
  "conditions": {
    "match": "all",
    "rules": [
      {
        "field": "priority",
        "operator": "equals",
        "value": "critical"
      },
      {
        "field": "tags",
        "operator": "contains",
        "value": "database"
      }
    ]
  },
  "channels": ["sms", "push"],
  "enabled": true
}
```

#### Operators

| Operator | Description | Applicable Fields |
|----------|-------------|-------------------|
| `equals` | Exact match | priority, status, severity |
| `not_equals` | Not equal | priority, status, severity |
| `contains` | Contains value | tags, title, description |
| `not_contains` | Does not contain | tags, title, description |
| `in` | In list | team, service, assigned_to |
| `not_in` | Not in list | team, service, assigned_to |
| `regex` | Regex match | title, description |

#### Response

```json
{
  "success": true,
  "data": {
    "id": "rule_001",
    "name": "Database Critical Alerts",
    "description": "Get notified for all critical database incidents",
    "conditions": {
      "match": "all",
      "rules": [
        {
          "field": "priority",
          "operator": "equals",
          "value": "critical"
        },
        {
          "field": "tags",
          "operator": "contains",
          "value": "database"
        }
      ]
    },
    "channels": ["sms", "push"],
    "enabled": true,
    "created_at": "2024-01-26T10:30:00Z"
  }
}
```

#### Example

```bash
curl -X POST "https://api.incident-copilot.io/api/v1/notifications/rules" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Database Critical Alerts",
    "conditions": {
      "match": "all",
      "rules": [
        {"field": "priority", "operator": "equals", "value": "critical"},
        {"field": "tags", "operator": "contains", "value": "database"}
      ]
    },
    "channels": ["sms", "push"]
  }'
```

---

### List Notification Rules

Get all notification rules for the current user.

```
GET /api/v1/notifications/rules
```

#### Response

```json
{
  "success": true,
  "data": {
    "rules": [
      {
        "id": "rule_001",
        "name": "Database Critical Alerts",
        "description": "Get notified for all critical database incidents",
        "conditions": {
          "match": "all",
          "rules": [
            {"field": "priority", "operator": "equals", "value": "critical"},
            {"field": "tags", "operator": "contains", "value": "database"}
          ]
        },
        "channels": ["sms", "push"],
        "enabled": true,
        "trigger_count": 12,
        "last_triggered": "2024-01-25T18:45:00Z",
        "created_at": "2024-01-20T10:00:00Z"
      }
    ]
  }
}
```

#### Example

```bash
curl -X GET "https://api.incident-copilot.io/api/v1/notifications/rules" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Update Notification Rule

```
PUT /api/v1/notifications/rules/{rule_id}
```

#### Request Body

```json
{
  "enabled": false
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "rule_001",
    "name": "Database Critical Alerts",
    "enabled": false,
    "updated_at": "2024-01-26T11:00:00Z"
  }
}
```

#### Example

```bash
curl -X PUT "https://api.incident-copilot.io/api/v1/notifications/rules/rule_001" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

---

### Delete Notification Rule

```
DELETE /api/v1/notifications/rules/{rule_id}
```

#### Response

```json
{
  "success": true,
  "message": "Notification rule deleted"
}
```

---

### Get Notification History

Retrieve notification delivery history.

```
GET /api/v1/notifications/history
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Max results (default: 50) |
| `channel` | string | No | Filter by channel type |
| `status` | string | No | `delivered`, `failed`, `pending` |
| `start_date` | string | No | Start date (ISO 8601) |
| `end_date` | string | No | End date (ISO 8601) |

#### Response

```json
{
  "success": true,
  "data": {
    "notifications": [
      {
        "id": "notif_001",
        "type": "incident_created",
        "incident_id": "inc_12345",
        "incident_title": "Database connection failures",
        "channel": "slack",
        "status": "delivered",
        "delivered_at": "2024-01-26T10:30:15Z",
        "created_at": "2024-01-26T10:30:12Z"
      },
      {
        "id": "notif_002",
        "type": "sla_warning",
        "incident_id": "inc_12345",
        "incident_title": "Database connection failures",
        "channel": "sms",
        "status": "delivered",
        "delivered_at": "2024-01-26T10:45:03Z",
        "created_at": "2024-01-26T10:45:00Z"
      },
      {
        "id": "notif_003",
        "type": "escalation",
        "incident_id": "inc_12340",
        "incident_title": "API latency spike",
        "channel": "push",
        "status": "failed",
        "error": "Device token expired",
        "created_at": "2024-01-26T09:15:00Z"
      }
    ],
    "pagination": {
      "page": 1,
      "limit": 50,
      "total": 156
    }
  }
}
```

#### Example

```bash
curl -X GET "https://api.incident-copilot.io/api/v1/notifications/history?channel=sms&limit=20" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Test Notification Channel

Send a test notification to verify channel configuration.

```
POST /api/v1/notifications/test
```

#### Request Body

```json
{
  "channel": "slack"
}
```

#### Response

```json
{
  "success": true,
  "message": "Test notification sent successfully",
  "data": {
    "channel": "slack",
    "sent_at": "2024-01-26T11:00:00Z",
    "message_id": "msg_test_001"
  }
}
```

#### Example

```bash
curl -X POST "https://api.incident-copilot.io/api/v1/notifications/test" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel": "slack"}'
```

---

## Notification Types

| Type | Description |
|------|-------------|
| `incident_created` | New incident created |
| `incident_assigned` | Incident assigned to user |
| `incident_updated` | Incident status or details changed |
| `incident_resolved` | Incident marked as resolved |
| `incident_reopened` | Resolved incident reopened |
| `sla_warning` | SLA approaching breach threshold |
| `sla_breach` | SLA has been breached |
| `escalation` | Incident escalated to user |
| `mention` | User mentioned in incident |
| `comment` | New comment on assigned incident |
| `daily_digest` | Daily summary of incidents |
| `weekly_report` | Weekly incident report |

---

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| 400 | `INVALID_CHANNEL_TYPE` | Unknown notification channel type |
| 400 | `INVALID_PHONE_FORMAT` | Phone number format invalid |
| 400 | `INVALID_EMAIL_FORMAT` | Email address format invalid |
| 400 | `INVALID_RULE_CONDITION` | Invalid rule condition syntax |
| 404 | `CHANNEL_NOT_FOUND` | Notification channel not found |
| 404 | `RULE_NOT_FOUND` | Notification rule not found |
| 409 | `CHANNEL_EXISTS` | Channel already configured |
| 422 | `VERIFICATION_FAILED` | Invalid verification code |
| 422 | `VERIFICATION_EXPIRED` | Verification code expired |

### Error Response Format

```json
{
  "success": false,
  "error": {
    "code": "VERIFICATION_FAILED",
    "message": "Invalid verification code",
    "details": {
      "attempts_remaining": 2,
      "expires_at": "2024-01-26T11:00:00Z"
    }
  }
}
```
