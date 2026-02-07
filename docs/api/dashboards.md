# Custom Dashboards API

Create and manage custom dashboards for incident monitoring, metrics visualization, and team performance.

## Overview

The Custom Dashboards API enables you to:
- Create custom dashboard layouts
- Add and configure widgets
- Share dashboards with teams
- Set up dashboard-specific alerts
- Export dashboard configurations

## Base URL

```
/api/v1/dashboards
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
| Widget data refresh | 60 requests/minute |

---

## Endpoints

### List Dashboards

Retrieve all accessible dashboards.

```
GET /api/v1/dashboards
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `owner` | string | No | Filter by owner (`me`, `team`, `shared`) |
| `team_id` | string | No | Filter by team |
| `page` | integer | No | Page number |
| `limit` | integer | No | Results per page |

#### Response

```json
{
  "success": true,
  "data": {
    "dashboards": [
      {
        "id": "dash_001",
        "name": "Platform Team Overview",
        "description": "Key metrics and active incidents for Platform team",
        "owner": {
          "id": "user_123",
          "name": "Jane Smith"
        },
        "team": {
          "id": "team_001",
          "name": "Platform"
        },
        "visibility": "team",
        "widgets_count": 8,
        "is_default": true,
        "thumbnail_url": "https://...",
        "created_at": "2024-01-10T00:00:00Z",
        "updated_at": "2024-01-25T14:30:00Z"
      },
      {
        "id": "dash_002",
        "name": "SLA Compliance",
        "description": "SLA metrics and breach tracking",
        "owner": {
          "id": "user_456",
          "name": "John Doe"
        },
        "visibility": "public",
        "widgets_count": 6,
        "is_default": false,
        "created_at": "2024-01-15T00:00:00Z",
        "updated_at": "2024-01-24T10:00:00Z"
      }
    ],
    "pagination": {
      "page": 1,
      "limit": 20,
      "total": 12
    }
  }
}
```

#### Example

```bash
curl -X GET "https://api.incident-copilot.io/api/v1/dashboards?owner=team" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Create Dashboard

```
POST /api/v1/dashboards
```

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Dashboard name |
| `description` | string | No | Dashboard description |
| `visibility` | string | No | `private`, `team`, `public` (default: private) |
| `team_id` | string | No | Team to share with |
| `layout` | object | No | Grid layout configuration |
| `theme` | string | No | `light`, `dark`, `auto` (default: auto) |

#### Request

```json
{
  "name": "Infrastructure Monitoring",
  "description": "Real-time infrastructure health and incident tracking",
  "visibility": "team",
  "team_id": "team_002",
  "layout": {
    "columns": 12,
    "row_height": 80
  },
  "theme": "dark"
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "dash_003",
    "name": "Infrastructure Monitoring",
    "description": "Real-time infrastructure health and incident tracking",
    "owner": {
      "id": "user_123",
      "name": "Jane Smith"
    },
    "team": {
      "id": "team_002",
      "name": "Infrastructure"
    },
    "visibility": "team",
    "layout": {
      "columns": 12,
      "row_height": 80
    },
    "theme": "dark",
    "widgets": [],
    "created_at": "2024-01-26T10:00:00Z"
  }
}
```

---

### Get Dashboard

```
GET /api/v1/dashboards/{dashboard_id}
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `include_data` | boolean | No | Include widget data (default: false) |

#### Response

```json
{
  "success": true,
  "data": {
    "id": "dash_001",
    "name": "Platform Team Overview",
    "description": "Key metrics and active incidents for Platform team",
    "owner": {
      "id": "user_123",
      "name": "Jane Smith"
    },
    "team": {
      "id": "team_001",
      "name": "Platform"
    },
    "visibility": "team",
    "layout": {
      "columns": 12,
      "row_height": 80
    },
    "theme": "auto",
    "widgets": [
      {
        "id": "widget_001",
        "type": "active_incidents",
        "title": "Active Incidents",
        "position": {"x": 0, "y": 0, "w": 6, "h": 4},
        "config": {
          "filters": {"team": ["platform"]},
          "show_priority": true
        }
      },
      {
        "id": "widget_002",
        "type": "metric",
        "title": "MTTR (Last 7 Days)",
        "position": {"x": 6, "y": 0, "w": 3, "h": 2},
        "config": {
          "metric": "mttr",
          "time_range": "7d",
          "comparison": "previous_period"
        }
      },
      {
        "id": "widget_003",
        "type": "chart",
        "title": "Incidents by Priority",
        "position": {"x": 9, "y": 0, "w": 3, "h": 2},
        "config": {
          "chart_type": "pie",
          "metric": "incident_count",
          "group_by": "priority",
          "time_range": "30d"
        }
      },
      {
        "id": "widget_004",
        "type": "sla_status",
        "title": "SLA Compliance",
        "position": {"x": 6, "y": 2, "w": 6, "h": 2},
        "config": {
          "show_breaches": true,
          "policies": ["sla_policy_001", "sla_policy_002"]
        }
      },
      {
        "id": "widget_005",
        "type": "timeline",
        "title": "Recent Activity",
        "position": {"x": 0, "y": 4, "w": 12, "h": 3},
        "config": {
          "event_types": ["incident_created", "incident_resolved", "escalation"],
          "limit": 20
        }
      }
    ],
    "auto_refresh_seconds": 30,
    "created_at": "2024-01-10T00:00:00Z",
    "updated_at": "2024-01-25T14:30:00Z"
  }
}
```

---

### Update Dashboard

```
PUT /api/v1/dashboards/{dashboard_id}
```

#### Request Body

```json
{
  "name": "Platform Team Overview v2",
  "auto_refresh_seconds": 60,
  "theme": "light"
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "dash_001",
    "name": "Platform Team Overview v2",
    "auto_refresh_seconds": 60,
    "theme": "light",
    "updated_at": "2024-01-26T11:00:00Z"
  }
}
```

---

### Delete Dashboard

```
DELETE /api/v1/dashboards/{dashboard_id}
```

#### Response

```json
{
  "success": true,
  "message": "Dashboard deleted"
}
```

---

### Add Widget

```
POST /api/v1/dashboards/{dashboard_id}/widgets
```

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | Widget type (see below) |
| `title` | string | Yes | Widget title |
| `position` | object | Yes | Grid position {x, y, w, h} |
| `config` | object | No | Widget-specific configuration |

#### Widget Types

| Type | Description |
|------|-------------|
| `active_incidents` | List of active incidents |
| `metric` | Single metric with comparison |
| `chart` | Chart visualization |
| `sla_status` | SLA compliance status |
| `timeline` | Activity timeline |
| `on_call` | Current on-call display |
| `service_health` | Service dependency health |
| `text` | Markdown text block |
| `iframe` | Embedded external content |
| `custom_query` | Custom data query |

#### Request

```json
{
  "type": "chart",
  "title": "Incidents Over Time",
  "position": {"x": 0, "y": 7, "w": 6, "h": 3},
  "config": {
    "chart_type": "line",
    "metric": "incident_count",
    "time_range": "30d",
    "granularity": "day",
    "group_by": "priority",
    "show_trend": true
  }
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "widget_006",
    "type": "chart",
    "title": "Incidents Over Time",
    "position": {"x": 0, "y": 7, "w": 6, "h": 3},
    "config": {
      "chart_type": "line",
      "metric": "incident_count",
      "time_range": "30d",
      "granularity": "day",
      "group_by": "priority",
      "show_trend": true
    },
    "created_at": "2024-01-26T11:30:00Z"
  }
}
```

---

### Update Widget

```
PUT /api/v1/dashboards/{dashboard_id}/widgets/{widget_id}
```

#### Request Body

```json
{
  "title": "Incidents Trend (30 Days)",
  "position": {"x": 0, "y": 7, "w": 8, "h": 3},
  "config": {
    "chart_type": "area",
    "show_trend": true,
    "show_annotations": true
  }
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "widget_006",
    "title": "Incidents Trend (30 Days)",
    "position": {"x": 0, "y": 7, "w": 8, "h": 3},
    "config": {
      "chart_type": "area",
      "metric": "incident_count",
      "time_range": "30d",
      "granularity": "day",
      "group_by": "priority",
      "show_trend": true,
      "show_annotations": true
    },
    "updated_at": "2024-01-26T12:00:00Z"
  }
}
```

---

### Delete Widget

```
DELETE /api/v1/dashboards/{dashboard_id}/widgets/{widget_id}
```

#### Response

```json
{
  "success": true,
  "message": "Widget deleted"
}
```

---

### Get Widget Data

Fetch current data for a widget.

```
GET /api/v1/dashboards/{dashboard_id}/widgets/{widget_id}/data
```

#### Response

```json
{
  "success": true,
  "data": {
    "widget_id": "widget_002",
    "type": "metric",
    "title": "MTTR (Last 7 Days)",
    "value": 42.5,
    "unit": "minutes",
    "comparison": {
      "previous_value": 55.3,
      "change_percent": -23.1,
      "trend": "improving"
    },
    "sparkline": [65, 58, 52, 48, 45, 43, 42],
    "last_updated": "2024-01-26T10:30:00Z"
  }
}
```

---

### Refresh Dashboard Data

Refresh data for all widgets.

```
POST /api/v1/dashboards/{dashboard_id}/refresh
```

#### Response

```json
{
  "success": true,
  "data": {
    "dashboard_id": "dash_001",
    "widgets_refreshed": 8,
    "refresh_time_ms": 245,
    "refreshed_at": "2024-01-26T10:35:00Z"
  }
}
```

---

### Clone Dashboard

```
POST /api/v1/dashboards/{dashboard_id}/clone
```

#### Request Body

```json
{
  "name": "Platform Overview (Copy)",
  "visibility": "private"
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "dash_004",
    "name": "Platform Overview (Copy)",
    "cloned_from": "dash_001",
    "widgets_count": 8,
    "visibility": "private",
    "created_at": "2024-01-26T13:00:00Z"
  }
}
```

---

### Export Dashboard

Export dashboard configuration as JSON.

```
GET /api/v1/dashboards/{dashboard_id}/export
```

#### Response

```json
{
  "success": true,
  "data": {
    "version": "1.0",
    "exported_at": "2024-01-26T13:00:00Z",
    "dashboard": {
      "name": "Platform Team Overview",
      "description": "Key metrics and active incidents for Platform team",
      "layout": {
        "columns": 12,
        "row_height": 80
      },
      "theme": "auto",
      "widgets": [
        {
          "type": "active_incidents",
          "title": "Active Incidents",
          "position": {"x": 0, "y": 0, "w": 6, "h": 4},
          "config": {
            "filters": {"team": ["platform"]},
            "show_priority": true
          }
        }
      ]
    }
  }
}
```

---

### Import Dashboard

Import a dashboard from exported JSON.

```
POST /api/v1/dashboards/import
```

#### Request Body

```json
{
  "version": "1.0",
  "dashboard": {
    "name": "Imported Dashboard",
    "description": "Dashboard imported from export",
    "layout": {
      "columns": 12,
      "row_height": 80
    },
    "widgets": [...]
  }
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "dash_005",
    "name": "Imported Dashboard",
    "widgets_count": 8,
    "created_at": "2024-01-26T13:30:00Z"
  }
}
```

---

### Set Default Dashboard

```
POST /api/v1/dashboards/{dashboard_id}/set-default
```

#### Response

```json
{
  "success": true,
  "data": {
    "dashboard_id": "dash_001",
    "is_default": true,
    "scope": "user"
  }
}
```

---

## Widget Configuration Reference

### Metric Widget

```json
{
  "type": "metric",
  "config": {
    "metric": "mttr|mttd|incident_count|sla_compliance",
    "time_range": "24h|7d|30d|90d|custom",
    "filters": {
      "team": ["platform"],
      "priority": ["critical", "high"]
    },
    "comparison": "previous_period|none",
    "show_sparkline": true,
    "thresholds": {
      "warning": 60,
      "critical": 120
    }
  }
}
```

### Chart Widget

```json
{
  "type": "chart",
  "config": {
    "chart_type": "line|bar|pie|area|stacked_bar",
    "metric": "incident_count|resolution_time|cost",
    "time_range": "7d|30d|90d",
    "granularity": "hour|day|week|month",
    "group_by": "priority|team|service|status",
    "filters": {},
    "show_legend": true,
    "show_annotations": false,
    "colors": ["#4CAF50", "#FFC107", "#F44336"]
  }
}
```

### Active Incidents Widget

```json
{
  "type": "active_incidents",
  "config": {
    "filters": {
      "team": ["platform"],
      "priority": ["critical", "high"],
      "status": ["open", "investigating"]
    },
    "sort_by": "created_at|priority|sla_status",
    "show_priority": true,
    "show_assignee": true,
    "show_sla": true,
    "max_items": 10
  }
}
```

---

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| 400 | `INVALID_WIDGET_TYPE` | Unknown widget type |
| 400 | `INVALID_POSITION` | Widget position out of bounds |
| 400 | `INVALID_CONFIG` | Widget configuration invalid |
| 403 | `NOT_OWNER` | Not dashboard owner |
| 404 | `DASHBOARD_NOT_FOUND` | Dashboard not found |
| 404 | `WIDGET_NOT_FOUND` | Widget not found |
| 409 | `POSITION_CONFLICT` | Widget position overlaps |
| 422 | `IMPORT_VERSION_MISMATCH` | Unsupported export version |

### Error Response Format

```json
{
  "success": false,
  "error": {
    "code": "POSITION_CONFLICT",
    "message": "Widget position overlaps with existing widget",
    "details": {
      "conflicting_widget_id": "widget_003",
      "overlap_area": {"x": 6, "y": 0, "w": 2, "h": 2}
    }
  }
}
```
