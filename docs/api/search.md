# Search API

Full-text search and advanced querying across incidents, runbooks, and documentation.

## Overview

The Search API provides:
- Full-text search across all incident data
- Faceted filtering and aggregations
- Saved searches and search history
- Similar incident discovery
- Natural language query support

## Base URL

```
/api/v1/search
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
| Search queries | 60 requests/minute |
| Saved searches | 30 requests/minute |
| Suggestions | 120 requests/minute |

---

## Endpoints

### Search Incidents

Perform a full-text search across incidents.

```
POST /api/v1/search/incidents
```

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | Yes | Search query string |
| `filters` | object | No | Filter criteria |
| `sort` | object | No | Sort configuration |
| `page` | integer | No | Page number (default: 1) |
| `limit` | integer | No | Results per page (default: 20, max: 100) |
| `highlight` | boolean | No | Include text highlights (default: true) |

#### Filter Options

```json
{
  "filters": {
    "status": ["open", "investigating"],
    "priority": ["critical", "high"],
    "severity": [1, 2],
    "assigned_to": ["user_123", "user_456"],
    "team": ["platform", "infrastructure"],
    "tags": ["database", "production"],
    "created_after": "2024-01-01T00:00:00Z",
    "created_before": "2024-01-31T23:59:59Z",
    "resolved": false,
    "has_postmortem": true
  }
}
```

#### Request

```json
{
  "query": "database connection timeout",
  "filters": {
    "status": ["open", "investigating"],
    "priority": ["critical", "high"],
    "created_after": "2024-01-01T00:00:00Z"
  },
  "sort": {
    "field": "created_at",
    "order": "desc"
  },
  "page": 1,
  "limit": 20,
  "highlight": true
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "results": [
      {
        "id": "inc_12345",
        "title": "Database connection pool exhausted",
        "description": "Production database showing connection timeout errors",
        "status": "investigating",
        "priority": "critical",
        "severity": 1,
        "assigned_to": {
          "id": "user_123",
          "name": "Jane Smith"
        },
        "team": "platform",
        "tags": ["database", "production", "postgres"],
        "created_at": "2024-01-25T14:30:00Z",
        "score": 12.5,
        "highlights": {
          "title": ["<em>Database</em> <em>connection</em> pool exhausted"],
          "description": ["Production <em>database</em> showing <em>connection</em> <em>timeout</em> errors"]
        }
      },
      {
        "id": "inc_12340",
        "title": "Connection timeouts to read replicas",
        "description": "Read replica connections timing out under load",
        "status": "open",
        "priority": "high",
        "severity": 2,
        "assigned_to": {
          "id": "user_456",
          "name": "John Doe"
        },
        "team": "infrastructure",
        "tags": ["database", "replication"],
        "created_at": "2024-01-24T09:15:00Z",
        "score": 10.2,
        "highlights": {
          "title": ["<em>Connection</em> <em>timeouts</em> to read replicas"],
          "description": ["Read replica <em>connections</em> <em>timing</em> out under load"]
        }
      }
    ],
    "aggregations": {
      "status": {
        "open": 5,
        "investigating": 8,
        "resolved": 45,
        "closed": 120
      },
      "priority": {
        "critical": 3,
        "high": 12,
        "medium": 28,
        "low": 15
      },
      "team": {
        "platform": 23,
        "infrastructure": 18,
        "backend": 12
      }
    },
    "pagination": {
      "page": 1,
      "limit": 20,
      "total": 58,
      "total_pages": 3
    },
    "query_time_ms": 45
  }
}
```

#### Example

```bash
curl -X POST "https://api.incident-copilot.io/api/v1/search/incidents" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "database connection timeout",
    "filters": {"priority": ["critical", "high"]},
    "limit": 10
  }'
```

---

### Search All Resources

Search across multiple resource types.

```
POST /api/v1/search
```

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | Yes | Search query string |
| `types` | array | No | Resource types: `incidents`, `runbooks`, `postmortems`, `services` |
| `limit_per_type` | integer | No | Max results per type (default: 5) |

#### Request

```json
{
  "query": "kubernetes pod crash",
  "types": ["incidents", "runbooks", "postmortems"],
  "limit_per_type": 5
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "incidents": {
      "total": 23,
      "results": [
        {
          "id": "inc_11234",
          "title": "Kubernetes pods crashing in production",
          "status": "resolved",
          "score": 15.3
        }
      ]
    },
    "runbooks": {
      "total": 8,
      "results": [
        {
          "id": "rb_045",
          "title": "Kubernetes Pod CrashLoopBackOff Recovery",
          "category": "kubernetes",
          "score": 14.1
        }
      ]
    },
    "postmortems": {
      "total": 5,
      "results": [
        {
          "id": "pm_089",
          "title": "Pod OOM Kills Due to Memory Leak",
          "incident_id": "inc_10890",
          "score": 12.8
        }
      ]
    },
    "query_time_ms": 62
  }
}
```

#### Example

```bash
curl -X POST "https://api.incident-copilot.io/api/v1/search" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "kubernetes pod crash", "types": ["incidents", "runbooks"]}'
```

---

### Find Similar Incidents

Find incidents similar to a given incident.

```
GET /api/v1/search/incidents/{incident_id}/similar
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Max results (default: 10, max: 50) |
| `min_score` | float | No | Minimum similarity score (0-1, default: 0.5) |
| `include_resolved` | boolean | No | Include resolved incidents (default: true) |

#### Response

```json
{
  "success": true,
  "data": {
    "reference_incident": {
      "id": "inc_12345",
      "title": "Database connection pool exhausted"
    },
    "similar": [
      {
        "id": "inc_10234",
        "title": "Connection pool limits reached during traffic spike",
        "status": "resolved",
        "similarity_score": 0.89,
        "matching_factors": ["symptoms", "affected_service", "tags"],
        "resolution_summary": "Increased connection pool size and added circuit breaker",
        "resolved_at": "2024-01-10T16:45:00Z"
      },
      {
        "id": "inc_09876",
        "title": "Database connections exhausted after deploy",
        "status": "resolved",
        "similarity_score": 0.82,
        "matching_factors": ["symptoms", "root_cause"],
        "resolution_summary": "Rolled back deployment with connection leak",
        "resolved_at": "2023-12-15T11:20:00Z"
      }
    ]
  }
}
```

#### Example

```bash
curl -X GET "https://api.incident-copilot.io/api/v1/search/incidents/inc_12345/similar?limit=5" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Get Search Suggestions

Get autocomplete suggestions for search queries.

```
GET /api/v1/search/suggest
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `q` | string | Yes | Partial query string (min 2 chars) |
| `type` | string | No | Resource type to search |
| `limit` | integer | No | Max suggestions (default: 10) |

#### Response

```json
{
  "success": true,
  "data": {
    "suggestions": [
      {
        "text": "database connection",
        "type": "query",
        "frequency": 156
      },
      {
        "text": "database timeout",
        "type": "query",
        "frequency": 89
      },
      {
        "text": "database replication lag",
        "type": "query",
        "frequency": 45
      }
    ],
    "recent_searches": [
      "database connection pool",
      "postgres replication"
    ]
  }
}
```

#### Example

```bash
curl -X GET "https://api.incident-copilot.io/api/v1/search/suggest?q=datab&limit=5" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Save Search

Save a search for quick access.

```
POST /api/v1/search/saved
```

#### Request Body

```json
{
  "name": "Critical Database Issues",
  "query": "database",
  "filters": {
    "priority": ["critical"],
    "tags": ["database", "postgres"]
  },
  "notify_on_new": true,
  "notification_channel": "slack"
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "saved_001",
    "name": "Critical Database Issues",
    "query": "database",
    "filters": {
      "priority": ["critical"],
      "tags": ["database", "postgres"]
    },
    "notify_on_new": true,
    "notification_channel": "slack",
    "created_at": "2024-01-26T10:00:00Z",
    "last_run": null,
    "result_count": 0
  }
}
```

#### Example

```bash
curl -X POST "https://api.incident-copilot.io/api/v1/search/saved" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Critical Database Issues",
    "query": "database",
    "filters": {"priority": ["critical"]}
  }'
```

---

### List Saved Searches

Get all saved searches for the current user.

```
GET /api/v1/search/saved
```

#### Response

```json
{
  "success": true,
  "data": {
    "saved_searches": [
      {
        "id": "saved_001",
        "name": "Critical Database Issues",
        "query": "database",
        "filters": {
          "priority": ["critical"]
        },
        "notify_on_new": true,
        "created_at": "2024-01-26T10:00:00Z",
        "last_run": "2024-01-26T14:30:00Z",
        "result_count": 3
      },
      {
        "id": "saved_002",
        "name": "My Team's Open Incidents",
        "query": "*",
        "filters": {
          "team": ["platform"],
          "status": ["open", "investigating"]
        },
        "notify_on_new": false,
        "created_at": "2024-01-20T09:00:00Z",
        "last_run": "2024-01-26T14:30:00Z",
        "result_count": 7
      }
    ]
  }
}
```

#### Example

```bash
curl -X GET "https://api.incident-copilot.io/api/v1/search/saved" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Delete Saved Search

```
DELETE /api/v1/search/saved/{search_id}
```

#### Response

```json
{
  "success": true,
  "message": "Saved search deleted successfully"
}
```

#### Example

```bash
curl -X DELETE "https://api.incident-copilot.io/api/v1/search/saved/saved_001" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Get Search History

Retrieve recent search history.

```
GET /api/v1/search/history
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Max results (default: 20) |
| `days` | integer | No | History days to include (default: 7) |

#### Response

```json
{
  "success": true,
  "data": {
    "history": [
      {
        "query": "kubernetes pod crash",
        "filters": {},
        "result_count": 23,
        "searched_at": "2024-01-26T14:30:00Z"
      },
      {
        "query": "database timeout",
        "filters": {"priority": ["critical"]},
        "result_count": 8,
        "searched_at": "2024-01-26T14:15:00Z"
      }
    ]
  }
}
```

#### Example

```bash
curl -X GET "https://api.incident-copilot.io/api/v1/search/history?limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Search Query Syntax

### Basic Queries

| Query | Description |
|-------|-------------|
| `database` | Search for "database" |
| `database connection` | Search for both terms |
| `"connection pool"` | Search exact phrase |

### Boolean Operators

| Query | Description |
|-------|-------------|
| `database AND timeout` | Both terms required |
| `database OR redis` | Either term |
| `database NOT test` | Exclude term |
| `database -staging` | Exclude term (shorthand) |

### Field-Specific Search

| Query | Description |
|-------|-------------|
| `title:database` | Search in title only |
| `description:timeout` | Search in description |
| `tags:production` | Search by tag |
| `team:platform` | Search by team |

### Wildcards and Fuzzy

| Query | Description |
|-------|-------------|
| `data*` | Prefix wildcard |
| `databse~` | Fuzzy match (typo tolerance) |
| `connection~2` | Fuzzy with edit distance 2 |

---

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| 400 | `QUERY_REQUIRED` | Search query is required |
| 400 | `QUERY_TOO_SHORT` | Query must be at least 2 characters |
| 400 | `INVALID_FILTER` | Unknown filter field specified |
| 400 | `INVALID_SORT_FIELD` | Unknown sort field |
| 404 | `SAVED_SEARCH_NOT_FOUND` | Saved search does not exist |
| 404 | `INCIDENT_NOT_FOUND` | Reference incident not found |
| 422 | `QUERY_SYNTAX_ERROR` | Invalid search query syntax |

### Error Response Format

```json
{
  "success": false,
  "error": {
    "code": "QUERY_SYNTAX_ERROR",
    "message": "Invalid search query syntax",
    "details": {
      "query": "title:(unclosed",
      "position": 7,
      "expected": "closing parenthesis"
    }
  }
}
```
