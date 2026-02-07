# Cost Tracking API

Track and analyze the financial impact of incidents, including direct costs, labor, and business impact.

## Overview

The Cost Tracking API enables you to:
- Record incident-related costs
- Track labor hours and engineer time
- Calculate business impact and revenue loss
- Generate cost reports and analytics
- Set cost budgets and alerts

## Base URL

```
/api/v1/costs
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
| Aggregation endpoints | 20 requests/minute |

---

## Endpoints

### Record Incident Cost

Add a cost entry to an incident.

```
POST /api/v1/costs/incidents/{incident_id}
```

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `category` | string | Yes | Cost category (see below) |
| `amount` | number | Yes | Cost amount |
| `currency` | string | No | Currency code (default: USD) |
| `description` | string | No | Cost description |
| `date` | string | No | Cost date (default: now) |
| `metadata` | object | No | Additional metadata |

#### Cost Categories

| Category | Description |
|----------|-------------|
| `labor` | Engineer time and overtime |
| `infrastructure` | Cloud/hosting costs |
| `third_party` | External services, consultants |
| `customer_credits` | Credits issued to customers |
| `revenue_loss` | Estimated revenue impact |
| `sla_penalty` | SLA breach penalties |
| `other` | Miscellaneous costs |

#### Request

```json
{
  "category": "labor",
  "amount": 450.00,
  "currency": "USD",
  "description": "2 engineers x 3 hours at $75/hr",
  "metadata": {
    "engineers": ["user_123", "user_456"],
    "hours": 6,
    "rate": 75
  }
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "cost_001",
    "incident_id": "inc_12345",
    "category": "labor",
    "amount": 450.00,
    "currency": "USD",
    "description": "2 engineers x 3 hours at $75/hr",
    "metadata": {
      "engineers": ["user_123", "user_456"],
      "hours": 6,
      "rate": 75
    },
    "recorded_by": {
      "id": "user_789",
      "name": "Team Lead"
    },
    "created_at": "2024-01-26T12:00:00Z"
  }
}
```

#### Example

```bash
curl -X POST "https://api.incident-copilot.io/api/v1/costs/incidents/inc_12345" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "category": "labor",
    "amount": 450.00,
    "description": "2 engineers x 3 hours"
  }'
```

---

### Get Incident Costs

Retrieve all costs for an incident.

```
GET /api/v1/costs/incidents/{incident_id}
```

#### Response

```json
{
  "success": true,
  "data": {
    "incident_id": "inc_12345",
    "incident_title": "Database connection failures",
    "costs": [
      {
        "id": "cost_001",
        "category": "labor",
        "amount": 450.00,
        "currency": "USD",
        "description": "2 engineers x 3 hours",
        "created_at": "2024-01-26T12:00:00Z"
      },
      {
        "id": "cost_002",
        "category": "infrastructure",
        "amount": 1200.00,
        "currency": "USD",
        "description": "Emergency scaling of database instances",
        "created_at": "2024-01-26T11:30:00Z"
      },
      {
        "id": "cost_003",
        "category": "customer_credits",
        "amount": 5000.00,
        "currency": "USD",
        "description": "SLA credits for affected enterprise customers",
        "created_at": "2024-01-26T15:00:00Z"
      }
    ],
    "summary": {
      "total": 6650.00,
      "currency": "USD",
      "by_category": {
        "labor": 450.00,
        "infrastructure": 1200.00,
        "customer_credits": 5000.00
      }
    }
  }
}
```

#### Example

```bash
curl -X GET "https://api.incident-copilot.io/api/v1/costs/incidents/inc_12345" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Update Cost Entry

```
PUT /api/v1/costs/{cost_id}
```

#### Request Body

```json
{
  "amount": 525.00,
  "description": "2 engineers x 3.5 hours at $75/hr"
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "cost_001",
    "incident_id": "inc_12345",
    "category": "labor",
    "amount": 525.00,
    "currency": "USD",
    "description": "2 engineers x 3.5 hours at $75/hr",
    "updated_at": "2024-01-26T14:00:00Z"
  }
}
```

---

### Delete Cost Entry

```
DELETE /api/v1/costs/{cost_id}
```

#### Response

```json
{
  "success": true,
  "message": "Cost entry deleted"
}
```

---

### Record Labor Time

Convenience endpoint for tracking engineer time.

```
POST /api/v1/costs/labor
```

#### Request Body

```json
{
  "incident_id": "inc_12345",
  "user_id": "user_123",
  "hours": 2.5,
  "hourly_rate": 75.00,
  "description": "Investigation and root cause analysis",
  "date": "2024-01-26"
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "labor_001",
    "incident_id": "inc_12345",
    "user": {
      "id": "user_123",
      "name": "Jane Smith"
    },
    "hours": 2.5,
    "hourly_rate": 75.00,
    "total_cost": 187.50,
    "currency": "USD",
    "description": "Investigation and root cause analysis",
    "date": "2024-01-26",
    "created_at": "2024-01-26T14:30:00Z"
  }
}
```

#### Example

```bash
curl -X POST "https://api.incident-copilot.io/api/v1/costs/labor" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "incident_id": "inc_12345",
    "user_id": "user_123",
    "hours": 2.5,
    "hourly_rate": 75.00
  }'
```

---

### Get Cost Summary

Get aggregated cost metrics.

```
GET /api/v1/costs/summary
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string | No | Start date (ISO 8601) |
| `end_date` | string | No | End date (ISO 8601) |
| `team` | string | No | Filter by team |
| `service` | string | No | Filter by service |
| `priority` | string | No | Filter by incident priority |
| `group_by` | string | No | Group by: `day`, `week`, `month`, `team`, `service`, `category` |

#### Response

```json
{
  "success": true,
  "data": {
    "period": {
      "start": "2024-01-01T00:00:00Z",
      "end": "2024-01-31T23:59:59Z"
    },
    "summary": {
      "total_cost": 125430.00,
      "currency": "USD",
      "incident_count": 45,
      "average_cost_per_incident": 2787.33
    },
    "by_category": {
      "labor": 35200.00,
      "infrastructure": 28500.00,
      "customer_credits": 45000.00,
      "revenue_loss": 12000.00,
      "sla_penalty": 4730.00
    },
    "by_priority": {
      "critical": 78500.00,
      "high": 32000.00,
      "medium": 12430.00,
      "low": 2500.00
    },
    "trend": [
      {
        "period": "2024-01-01",
        "total": 28500.00,
        "incident_count": 12
      },
      {
        "period": "2024-01-08",
        "total": 45200.00,
        "incident_count": 15
      },
      {
        "period": "2024-01-15",
        "total": 31730.00,
        "incident_count": 10
      },
      {
        "period": "2024-01-22",
        "total": 20000.00,
        "incident_count": 8
      }
    ]
  }
}
```

#### Example

```bash
curl -X GET "https://api.incident-copilot.io/api/v1/costs/summary?start_date=2024-01-01&group_by=week" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Configure Cost Rates

Set default hourly rates for teams or roles.

```
PUT /api/v1/costs/config/rates
```

#### Request Body

```json
{
  "default_hourly_rate": 75.00,
  "currency": "USD",
  "rates_by_role": {
    "engineer": 75.00,
    "senior_engineer": 100.00,
    "staff_engineer": 125.00,
    "manager": 110.00,
    "director": 150.00
  },
  "rates_by_team": {
    "platform": 85.00,
    "infrastructure": 90.00,
    "security": 100.00
  },
  "overtime_multiplier": 1.5
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "default_hourly_rate": 75.00,
    "currency": "USD",
    "rates_by_role": {
      "engineer": 75.00,
      "senior_engineer": 100.00,
      "staff_engineer": 125.00,
      "manager": 110.00,
      "director": 150.00
    },
    "rates_by_team": {
      "platform": 85.00,
      "infrastructure": 90.00,
      "security": 100.00
    },
    "overtime_multiplier": 1.5,
    "updated_at": "2024-01-26T10:00:00Z"
  }
}
```

---

### Get Cost Rates

```
GET /api/v1/costs/config/rates
```

#### Response

```json
{
  "success": true,
  "data": {
    "default_hourly_rate": 75.00,
    "currency": "USD",
    "rates_by_role": {
      "engineer": 75.00,
      "senior_engineer": 100.00,
      "staff_engineer": 125.00,
      "manager": 110.00,
      "director": 150.00
    },
    "rates_by_team": {
      "platform": 85.00,
      "infrastructure": 90.00,
      "security": 100.00
    },
    "overtime_multiplier": 1.5
  }
}
```

---

### Set Cost Budget

Configure cost budgets with alerts.

```
POST /api/v1/costs/budgets
```

#### Request Body

```json
{
  "name": "Q1 Incident Budget",
  "amount": 150000.00,
  "currency": "USD",
  "period": {
    "start": "2024-01-01",
    "end": "2024-03-31"
  },
  "scope": {
    "type": "organization"
  },
  "alerts": [
    {
      "threshold_percent": 50,
      "channels": ["email"]
    },
    {
      "threshold_percent": 75,
      "channels": ["email", "slack"]
    },
    {
      "threshold_percent": 90,
      "channels": ["email", "slack", "pagerduty"]
    }
  ]
}
```

#### Scope Options

| Type | Description |
|------|-------------|
| `organization` | Entire organization |
| `team` | Specific team (include `team_id`) |
| `service` | Specific service (include `service_id`) |

#### Response

```json
{
  "success": true,
  "data": {
    "id": "budget_001",
    "name": "Q1 Incident Budget",
    "amount": 150000.00,
    "currency": "USD",
    "period": {
      "start": "2024-01-01",
      "end": "2024-03-31"
    },
    "scope": {
      "type": "organization"
    },
    "current_spend": 0,
    "remaining": 150000.00,
    "percent_used": 0,
    "alerts": [
      {
        "threshold_percent": 50,
        "channels": ["email"],
        "triggered": false
      }
    ],
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

---

### Get Budget Status

```
GET /api/v1/costs/budgets/{budget_id}
```

#### Response

```json
{
  "success": true,
  "data": {
    "id": "budget_001",
    "name": "Q1 Incident Budget",
    "amount": 150000.00,
    "currency": "USD",
    "period": {
      "start": "2024-01-01",
      "end": "2024-03-31"
    },
    "current_spend": 78500.00,
    "remaining": 71500.00,
    "percent_used": 52.33,
    "projected_total": 142000.00,
    "on_track": true,
    "days_remaining": 65,
    "daily_average": 2854.55,
    "alerts": [
      {
        "threshold_percent": 50,
        "channels": ["email"],
        "triggered": true,
        "triggered_at": "2024-01-26T10:00:00Z"
      },
      {
        "threshold_percent": 75,
        "channels": ["email", "slack"],
        "triggered": false
      }
    ]
  }
}
```

---

### List Budgets

```
GET /api/v1/costs/budgets
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `active` | boolean | No | Filter active budgets only |
| `scope_type` | string | No | Filter by scope type |

#### Response

```json
{
  "success": true,
  "data": {
    "budgets": [
      {
        "id": "budget_001",
        "name": "Q1 Incident Budget",
        "amount": 150000.00,
        "current_spend": 78500.00,
        "percent_used": 52.33,
        "period": {
          "start": "2024-01-01",
          "end": "2024-03-31"
        },
        "on_track": true
      }
    ]
  }
}
```

---

### Calculate Revenue Impact

Estimate revenue loss from an incident.

```
POST /api/v1/costs/incidents/{incident_id}/revenue-impact
```

#### Request Body

```json
{
  "calculation_method": "transaction_based",
  "parameters": {
    "avg_transaction_value": 45.00,
    "transactions_per_minute": 150,
    "impact_percentage": 100,
    "duration_minutes": 45
  }
}
```

#### Calculation Methods

| Method | Required Parameters |
|--------|---------------------|
| `transaction_based` | `avg_transaction_value`, `transactions_per_minute`, `impact_percentage`, `duration_minutes` |
| `hourly_revenue` | `hourly_revenue`, `impact_percentage`, `duration_minutes` |
| `user_based` | `revenue_per_user`, `affected_users`, `duration_minutes` |
| `fixed` | `amount` |

#### Response

```json
{
  "success": true,
  "data": {
    "incident_id": "inc_12345",
    "calculation_method": "transaction_based",
    "estimated_revenue_loss": 303750.00,
    "currency": "USD",
    "parameters": {
      "avg_transaction_value": 45.00,
      "transactions_per_minute": 150,
      "impact_percentage": 100,
      "duration_minutes": 45
    },
    "breakdown": {
      "total_transactions_affected": 6750,
      "revenue_per_minute": 6750.00
    },
    "recorded_as_cost": true,
    "cost_id": "cost_004",
    "calculated_at": "2024-01-26T15:00:00Z"
  }
}
```

---

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| 400 | `INVALID_CATEGORY` | Unknown cost category |
| 400 | `INVALID_AMOUNT` | Amount must be positive |
| 400 | `INVALID_CURRENCY` | Unsupported currency code |
| 400 | `INVALID_DATE_RANGE` | End date before start date |
| 404 | `INCIDENT_NOT_FOUND` | Incident does not exist |
| 404 | `COST_NOT_FOUND` | Cost entry not found |
| 404 | `BUDGET_NOT_FOUND` | Budget not found |
| 409 | `BUDGET_OVERLAP` | Budget periods overlap |

### Error Response Format

```json
{
  "success": false,
  "error": {
    "code": "INVALID_AMOUNT",
    "message": "Cost amount must be a positive number",
    "details": {
      "provided": -100,
      "field": "amount"
    }
  }
}
```
