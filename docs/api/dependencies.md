# Service Dependencies API

Manage and query service dependencies for impact analysis and incident correlation.

## Overview

The Service Dependencies API enables you to:
- Define service relationships and dependencies
- Query dependency graphs
- Analyze blast radius for incidents
- Identify affected downstream services
- Track dependency health

## Base URL

```
/api/v1/dependencies
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
| Graph queries | 20 requests/minute |

---

## Endpoints

### List Services

Retrieve all registered services.

```
GET /api/v1/dependencies/services
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `page` | integer | No | Page number (default: 1) |
| `limit` | integer | No | Results per page (default: 50) |
| `team` | string | No | Filter by owning team |
| `tier` | string | No | Filter by tier: `1`, `2`, `3` |
| `status` | string | No | Filter by health status |

#### Response

```json
{
  "success": true,
  "data": {
    "services": [
      {
        "id": "svc_001",
        "name": "api-gateway",
        "display_name": "API Gateway",
        "description": "Main API entry point for all client requests",
        "tier": 1,
        "team": {
          "id": "team_001",
          "name": "Platform"
        },
        "owner": {
          "id": "user_123",
          "name": "Jane Smith"
        },
        "status": "healthy",
        "dependencies_count": 5,
        "dependents_count": 0,
        "metadata": {
          "repository": "https://github.com/org/api-gateway",
          "runbook": "https://wiki.example.com/api-gateway",
          "slack_channel": "#api-gateway-alerts"
        },
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-20T10:00:00Z"
      },
      {
        "id": "svc_002",
        "name": "user-service",
        "display_name": "User Service",
        "description": "User authentication and profile management",
        "tier": 1,
        "team": {
          "id": "team_002",
          "name": "Identity"
        },
        "owner": {
          "id": "user_456",
          "name": "John Doe"
        },
        "status": "healthy",
        "dependencies_count": 3,
        "dependents_count": 8,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-18T15:30:00Z"
      }
    ],
    "pagination": {
      "page": 1,
      "limit": 50,
      "total": 45
    }
  }
}
```

#### Example

```bash
curl -X GET "https://api.incident-copilot.io/api/v1/dependencies/services?tier=1" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Create Service

Register a new service.

```
POST /api/v1/dependencies/services
```

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Service identifier (lowercase, dashes) |
| `display_name` | string | Yes | Human-readable name |
| `description` | string | No | Service description |
| `tier` | integer | Yes | Criticality tier (1-3) |
| `team_id` | string | Yes | Owning team ID |
| `owner_id` | string | No | Primary owner user ID |
| `metadata` | object | No | Additional metadata |

#### Request

```json
{
  "name": "payment-service",
  "display_name": "Payment Service",
  "description": "Handles payment processing and billing",
  "tier": 1,
  "team_id": "team_003",
  "owner_id": "user_789",
  "metadata": {
    "repository": "https://github.com/org/payment-service",
    "runbook": "https://wiki.example.com/payment-service",
    "slack_channel": "#payments-alerts",
    "pagerduty_service": "PXXXXXX"
  }
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "svc_003",
    "name": "payment-service",
    "display_name": "Payment Service",
    "description": "Handles payment processing and billing",
    "tier": 1,
    "team": {
      "id": "team_003",
      "name": "Payments"
    },
    "owner": {
      "id": "user_789",
      "name": "Alice Johnson"
    },
    "status": "unknown",
    "dependencies_count": 0,
    "dependents_count": 0,
    "metadata": {
      "repository": "https://github.com/org/payment-service",
      "runbook": "https://wiki.example.com/payment-service",
      "slack_channel": "#payments-alerts",
      "pagerduty_service": "PXXXXXX"
    },
    "created_at": "2024-01-26T10:00:00Z",
    "updated_at": "2024-01-26T10:00:00Z"
  }
}
```

---

### Get Service

Retrieve a specific service with its dependencies.

```
GET /api/v1/dependencies/services/{service_id}
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `include_dependencies` | boolean | No | Include dependency list (default: true) |
| `include_dependents` | boolean | No | Include dependent services (default: true) |
| `depth` | integer | No | Dependency traversal depth (default: 1, max: 5) |

#### Response

```json
{
  "success": true,
  "data": {
    "id": "svc_002",
    "name": "user-service",
    "display_name": "User Service",
    "description": "User authentication and profile management",
    "tier": 1,
    "team": {
      "id": "team_002",
      "name": "Identity"
    },
    "owner": {
      "id": "user_456",
      "name": "John Doe"
    },
    "status": "healthy",
    "health_checks": {
      "last_check": "2024-01-26T10:29:00Z",
      "uptime_percent": 99.95,
      "avg_latency_ms": 45
    },
    "dependencies": [
      {
        "service": {
          "id": "svc_010",
          "name": "postgres-primary",
          "display_name": "PostgreSQL Primary"
        },
        "type": "database",
        "criticality": "critical",
        "status": "healthy"
      },
      {
        "service": {
          "id": "svc_011",
          "name": "redis-cache",
          "display_name": "Redis Cache"
        },
        "type": "cache",
        "criticality": "degraded",
        "status": "healthy"
      },
      {
        "service": {
          "id": "svc_012",
          "name": "kafka-cluster",
          "display_name": "Kafka Cluster"
        },
        "type": "messaging",
        "criticality": "critical",
        "status": "healthy"
      }
    ],
    "dependents": [
      {
        "service": {
          "id": "svc_001",
          "name": "api-gateway",
          "display_name": "API Gateway"
        },
        "type": "sync",
        "criticality": "critical"
      },
      {
        "service": {
          "id": "svc_020",
          "name": "order-service",
          "display_name": "Order Service"
        },
        "type": "sync",
        "criticality": "critical"
      }
    ],
    "metadata": {
      "repository": "https://github.com/org/user-service",
      "runbook": "https://wiki.example.com/user-service"
    },
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-18T15:30:00Z"
  }
}
```

---

### Update Service

```
PUT /api/v1/dependencies/services/{service_id}
```

#### Request Body

```json
{
  "tier": 2,
  "owner_id": "user_999",
  "metadata": {
    "runbook": "https://wiki.example.com/user-service-v2"
  }
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "svc_002",
    "name": "user-service",
    "tier": 2,
    "owner": {
      "id": "user_999",
      "name": "New Owner"
    },
    "updated_at": "2024-01-26T11:00:00Z"
  }
}
```

---

### Delete Service

```
DELETE /api/v1/dependencies/services/{service_id}
```

#### Response

```json
{
  "success": true,
  "message": "Service deleted"
}
```

---

### Add Dependency

Create a dependency relationship between services.

```
POST /api/v1/dependencies/relationships
```

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source_service_id` | string | Yes | Service that depends on another |
| `target_service_id` | string | Yes | Service being depended on |
| `type` | string | Yes | Dependency type |
| `criticality` | string | Yes | How critical is this dependency |
| `description` | string | No | Relationship description |

#### Dependency Types

| Type | Description |
|------|-------------|
| `sync` | Synchronous API call |
| `async` | Asynchronous messaging |
| `database` | Database dependency |
| `cache` | Cache dependency |
| `messaging` | Message queue dependency |
| `storage` | Object storage dependency |
| `cdn` | CDN dependency |
| `dns` | DNS dependency |

#### Criticality Levels

| Level | Description |
|-------|-------------|
| `critical` | Service cannot function without this |
| `degraded` | Service works but with reduced functionality |
| `optional` | Nice to have, service works without it |

#### Request

```json
{
  "source_service_id": "svc_003",
  "target_service_id": "svc_010",
  "type": "database",
  "criticality": "critical",
  "description": "Primary data store for payment records"
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "rel_001",
    "source_service": {
      "id": "svc_003",
      "name": "payment-service"
    },
    "target_service": {
      "id": "svc_010",
      "name": "postgres-primary"
    },
    "type": "database",
    "criticality": "critical",
    "description": "Primary data store for payment records",
    "created_at": "2024-01-26T10:30:00Z"
  }
}
```

---

### Remove Dependency

```
DELETE /api/v1/dependencies/relationships/{relationship_id}
```

#### Response

```json
{
  "success": true,
  "message": "Dependency relationship removed"
}
```

---

### Get Dependency Graph

Retrieve the full dependency graph for visualization.

```
GET /api/v1/dependencies/graph
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `root_service_id` | string | No | Start from specific service |
| `direction` | string | No | `upstream`, `downstream`, `both` (default: both) |
| `depth` | integer | No | Traversal depth (default: 3, max: 10) |
| `include_health` | boolean | No | Include health status (default: true) |
| `format` | string | No | Response format: `json`, `dot` (Graphviz) |

#### Response

```json
{
  "success": true,
  "data": {
    "nodes": [
      {
        "id": "svc_001",
        "name": "api-gateway",
        "display_name": "API Gateway",
        "tier": 1,
        "status": "healthy",
        "team": "Platform"
      },
      {
        "id": "svc_002",
        "name": "user-service",
        "display_name": "User Service",
        "tier": 1,
        "status": "healthy",
        "team": "Identity"
      },
      {
        "id": "svc_010",
        "name": "postgres-primary",
        "display_name": "PostgreSQL Primary",
        "tier": 1,
        "status": "healthy",
        "team": "Infrastructure"
      }
    ],
    "edges": [
      {
        "id": "rel_001",
        "source": "svc_001",
        "target": "svc_002",
        "type": "sync",
        "criticality": "critical"
      },
      {
        "id": "rel_002",
        "source": "svc_002",
        "target": "svc_010",
        "type": "database",
        "criticality": "critical"
      }
    ],
    "stats": {
      "total_nodes": 45,
      "total_edges": 78,
      "max_depth": 6,
      "critical_paths": 12
    }
  }
}
```

#### Example

```bash
curl -X GET "https://api.incident-copilot.io/api/v1/dependencies/graph?root_service_id=svc_002&direction=downstream&depth=2" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Analyze Blast Radius

Analyze the impact of a service failure.

```
GET /api/v1/dependencies/services/{service_id}/blast-radius
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `failure_mode` | string | No | `complete`, `degraded`, `latency` (default: complete) |
| `include_indirect` | boolean | No | Include indirect impacts (default: true) |

#### Response

```json
{
  "success": true,
  "data": {
    "source_service": {
      "id": "svc_010",
      "name": "postgres-primary",
      "display_name": "PostgreSQL Primary"
    },
    "failure_mode": "complete",
    "impact_summary": {
      "total_affected_services": 12,
      "tier_1_affected": 4,
      "tier_2_affected": 5,
      "tier_3_affected": 3,
      "critical_dependencies": 6,
      "estimated_user_impact": "high"
    },
    "affected_services": [
      {
        "service": {
          "id": "svc_002",
          "name": "user-service",
          "display_name": "User Service",
          "tier": 1
        },
        "impact_type": "critical",
        "path_length": 1,
        "dependency_path": ["postgres-primary → user-service"],
        "expected_behavior": "Complete service failure"
      },
      {
        "service": {
          "id": "svc_001",
          "name": "api-gateway",
          "display_name": "API Gateway",
          "tier": 1
        },
        "impact_type": "critical",
        "path_length": 2,
        "dependency_path": ["postgres-primary → user-service → api-gateway"],
        "expected_behavior": "Authentication failures, partial API availability"
      },
      {
        "service": {
          "id": "svc_020",
          "name": "order-service",
          "display_name": "Order Service",
          "tier": 1
        },
        "impact_type": "critical",
        "path_length": 2,
        "dependency_path": ["postgres-primary → user-service → order-service"],
        "expected_behavior": "Cannot process orders requiring user context"
      }
    ],
    "recommended_actions": [
      {
        "action": "Activate database failover",
        "priority": "immediate",
        "runbook": "https://wiki.example.com/db-failover"
      },
      {
        "action": "Enable cached user data fallback",
        "priority": "high",
        "services": ["user-service", "api-gateway"]
      }
    ]
  }
}
```

---

### Get Dependency Health

Check health status across dependencies.

```
GET /api/v1/dependencies/health
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `service_id` | string | No | Filter by specific service |
| `status` | string | No | Filter by status: `healthy`, `degraded`, `unhealthy`, `unknown` |

#### Response

```json
{
  "success": true,
  "data": {
    "overall_health": "degraded",
    "summary": {
      "healthy": 42,
      "degraded": 2,
      "unhealthy": 1,
      "unknown": 0
    },
    "issues": [
      {
        "service": {
          "id": "svc_011",
          "name": "redis-cache",
          "display_name": "Redis Cache"
        },
        "status": "degraded",
        "reason": "High latency (avg 150ms)",
        "since": "2024-01-26T09:45:00Z",
        "affected_services_count": 8
      },
      {
        "service": {
          "id": "svc_025",
          "name": "email-service",
          "display_name": "Email Service"
        },
        "status": "unhealthy",
        "reason": "Service not responding",
        "since": "2024-01-26T10:15:00Z",
        "affected_services_count": 3,
        "active_incident": "inc_12345"
      }
    ],
    "last_updated": "2024-01-26T10:30:00Z"
  }
}
```

---

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| 400 | `INVALID_SERVICE_NAME` | Service name format invalid |
| 400 | `INVALID_TIER` | Tier must be 1, 2, or 3 |
| 400 | `CIRCULAR_DEPENDENCY` | Would create circular dependency |
| 404 | `SERVICE_NOT_FOUND` | Service does not exist |
| 404 | `RELATIONSHIP_NOT_FOUND` | Dependency relationship not found |
| 409 | `SERVICE_EXISTS` | Service name already registered |
| 409 | `DEPENDENCY_EXISTS` | Relationship already exists |
| 409 | `HAS_DEPENDENTS` | Cannot delete service with dependents |

### Error Response Format

```json
{
  "success": false,
  "error": {
    "code": "CIRCULAR_DEPENDENCY",
    "message": "Adding this dependency would create a circular reference",
    "details": {
      "path": ["svc_001", "svc_002", "svc_003", "svc_001"]
    }
  }
}
```
