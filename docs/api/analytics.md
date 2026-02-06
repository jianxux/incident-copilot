# Analytics API Reference

The Analytics API provides endpoints for incident metrics, MTTR tracking, AI-powered insights, pattern detection, and cost analysis.

---

## MTTR & Incident Metrics

### Get MTTR Statistics

Retrieve Mean Time To Resolve (MTTR) statistics for a time period.

```http
GET /api/analytics/mttr
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | integer | 7 | Number of days to analyze (1-365) |
| `service` | string | - | Filter by service name |
| `severity` | string | - | Filter by severity level |

**Response:**

```json
{
  "mean_mttr_minutes": 45.2,
  "median_mttr_minutes": 32.0,
  "p90_mttr_minutes": 95.0,
  "p99_mttr_minutes": 180.0,
  "total_incidents": 25,
  "resolved_incidents": 23,
  "period_start": "2024-01-08T00:00:00Z",
  "period_end": "2024-01-15T00:00:00Z"
}
```

### Get Incident Metrics

Retrieve detailed metrics for individual incidents.

```http
GET /api/analytics/incidents
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | integer | 7 | Number of days to fetch (1-365) |
| `service` | string | - | Filter by service name |
| `severity` | string | - | Filter by severity level |
| `limit` | integer | 100 | Maximum incidents (1-1000) |

**Response:**

```json
[
  {
    "incident_id": "INC-12345",
    "service_name": "payments-api",
    "severity": "high",
    "triggered_at": "2024-01-15T10:30:00Z",
    "acknowledged_at": "2024-01-15T10:35:00Z",
    "context_delivered_at": "2024-01-15T10:31:00Z",
    "resolved_at": "2024-01-15T11:15:00Z",
    "mttr_minutes": 45,
    "time_to_acknowledge_minutes": 5,
    "time_to_context_minutes": 1
  }
]
```

### Compare Periods

Compare current period metrics to the previous equivalent period.

```http
GET /api/analytics/comparison
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | integer | 7 | Period length (1-180) |
| `service` | string | - | Filter by service name |
| `severity` | string | - | Filter by severity level |

**Response:**

```json
{
  "current_period": {
    "start": "2024-01-08T00:00:00Z",
    "end": "2024-01-15T00:00:00Z",
    "mean_mttr_minutes": 45.2,
    "incident_count": 25
  },
  "previous_period": {
    "start": "2024-01-01T00:00:00Z",
    "end": "2024-01-08T00:00:00Z",
    "mean_mttr_minutes": 52.8,
    "incident_count": 30
  },
  "mttr_change_percent": -14.4,
  "incident_count_change_percent": -16.7,
  "trend": "improving"
}
```

### Get Analytics Summary

High-level summary for multiple time periods.

```http
GET /api/analytics/summary
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `service` | string | Filter by service name |

**Response:**

```json
{
  "7d": {
    "stats": {
      "mean_mttr_minutes": 45.2,
      "total_incidents": 25
    },
    "comparison": {
      "mttr_change_percent": -14.4,
      "trend": "improving"
    }
  },
  "30d": {
    "stats": {...},
    "comparison": {...}
  },
  "90d": {
    "stats": {...},
    "comparison": {...}
  }
}
```

### Record Incident Events

Manually record incident lifecycle events (for testing or manual entry).

#### Record Triggered

```http
POST /api/analytics/record/triggered
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `incident_id` | string | Yes | Incident identifier |
| `service_name` | string | Yes | Service name |
| `severity` | string | Yes | Severity level |
| `triggered_at` | datetime | No | Trigger time (default: now) |

#### Record Acknowledged

```http
POST /api/analytics/record/acknowledged
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `incident_id` | string | Yes | Incident identifier |
| `acknowledged_at` | datetime | No | Acknowledgement time |

#### Record Resolved

```http
POST /api/analytics/record/resolved
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `incident_id` | string | Yes | Incident identifier |
| `resolved_at` | datetime | No | Resolution time |

#### Record Context Card Delivered

```http
POST /api/analytics/record/context-card
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `incident_id` | string | Yes | Incident identifier |
| `delivered_at` | datetime | No | Delivery time |

---

## AI Insights

### List Insights

Retrieve AI-generated insights about incident patterns and trends.

```http
GET /api/insights
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `insight_type` | string | Filter by type |
| `severity` | string | Filter by severity |
| `service` | string | Filter by service name |
| `limit` | integer | Maximum results (1-200) |

**Insight Types:**

| Type | Description |
|------|-------------|
| `pattern` | Recurring incident patterns |
| `anomaly` | Unusual incident behavior |
| `trend` | Trend in metrics |
| `prediction` | Predicted issues |
| `recommendation` | Actionable recommendations |

**Response:**

```json
{
  "total": 15,
  "insights": [
    {
      "insight_id": "ins_abc123",
      "insight_type": "pattern",
      "severity": "high",
      "title": "Recurring deployment failures",
      "description": "Payment API experiences elevated error rates after 30% of deployments",
      "service_names": ["payments-api"],
      "confidence_score": 0.87,
      "detected_at": "2024-01-15T10:00:00Z",
      "acknowledged": false,
      "action_items": [
        "Review deployment pipeline for payments-api",
        "Consider implementing canary deployments"
      ]
    }
  ]
}
```

### Get Insights Summary

```http
GET /api/insights/summary
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | integer | 7 | Number of days (1-90) |

**Response:**

```json
{
  "period_days": 7,
  "total_insights": 15,
  "by_severity": {
    "critical": 2,
    "high": 5,
    "medium": 6,
    "low": 2
  },
  "by_type": {
    "pattern": 5,
    "anomaly": 4,
    "trend": 3,
    "recommendation": 3
  },
  "top_services": [
    {"service": "payments-api", "count": 8},
    {"service": "user-service", "count": 4}
  ],
  "acknowledged_count": 5,
  "unacknowledged_count": 10
}
```

### List Patterns

Retrieve detected incident patterns.

```http
GET /api/insights/patterns
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `service` | string | Filter by service name |
| `limit` | integer | Maximum results (1-200) |

**Response:**

```json
{
  "total": 5,
  "patterns": [
    {
      "pattern_id": "pat_abc123",
      "title": "Database connection exhaustion",
      "description": "Connection pool exhaustion occurs during peak traffic",
      "service_names": ["payments-api", "checkout-service"],
      "incident_count": 12,
      "avg_time_between_occurrences_hours": 72,
      "last_occurrence": "2024-01-14T15:30:00Z",
      "suggested_actions": [
        "Increase connection pool size",
        "Implement connection pooling proxy"
      ]
    }
  ]
}
```

### List Anomalies

Retrieve detected anomalies.

```http
GET /api/insights/anomalies
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `service` | string | Filter by service name |
| `severity` | string | Filter by severity |
| `limit` | integer | Maximum results (1-200) |

**Response:**

```json
{
  "total": 3,
  "anomalies": [
    {
      "anomaly_id": "ano_abc123",
      "anomaly_type": "incident_spike",
      "severity": "high",
      "title": "Unusual incident spike detected",
      "description": "3x normal incident rate in the last 2 hours",
      "service_names": ["payments-api"],
      "detected_at": "2024-01-15T10:00:00Z",
      "baseline_value": 2.0,
      "observed_value": 6.0,
      "deviation_factor": 3.0
    }
  ]
}
```

### List Service Dependencies

Retrieve inferred service dependencies based on incident correlation.

```http
GET /api/insights/dependencies
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `service` | string | Filter by service name |

**Response:**

```json
{
  "total": 8,
  "dependencies": [
    {
      "source_service": "payments-api",
      "target_service": "user-service",
      "correlation_strength": 0.85,
      "incident_count": 15,
      "avg_cascade_time_minutes": 5,
      "inferred_from": "incident_correlation"
    }
  ]
}
```

### Get Incident Digest

Get a comprehensive incident digest.

```http
GET /api/insights/digest
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `period` | string | weekly | Period: `daily`, `weekly`, `monthly` |
| `generate` | boolean | false | Generate if none exists |
| `include_ai` | boolean | true | Include AI summary |

**Response:**

```json
{
  "digest_id": "dig_abc123",
  "period": "weekly",
  "period_start": "2024-01-08T00:00:00Z",
  "period_end": "2024-01-15T00:00:00Z",
  "statistics": {
    "total_incidents": 25,
    "by_severity": {...},
    "by_service": {...},
    "mttr_minutes": 45
  },
  "patterns": [...],
  "anomalies": [...],
  "ai_summary": "This week saw a 15% reduction in incidents compared to last week...",
  "generated_at": "2024-01-15T08:00:00Z"
}
```

### Generate Digest

Generate a fresh incident digest.

```http
POST /api/insights/digest/generate
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `period` | string | weekly | Period type |
| `include_ai` | boolean | true | Include AI summary |

### Trigger Analysis

Run comprehensive incident data analysis.

```http
POST /api/insights/analyze
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `service` | string | - | Service to analyze |
| `days` | integer | 30 | Days of data (1-365) |
| `include_patterns` | boolean | true | Detect patterns |
| `include_anomalies` | boolean | true | Detect anomalies |
| `include_dependencies` | boolean | true | Analyze dependencies |
| `generate_ai` | boolean | true | Generate AI summaries |

**Response:**

```json
{
  "analysis_id": "ana_abc123",
  "started_at": "2024-01-15T10:00:00Z",
  "completed_at": "2024-01-15T10:02:30Z",
  "incidents_analyzed": 150,
  "patterns_detected": 5,
  "anomalies_detected": 3,
  "dependencies_inferred": 8,
  "insights_generated": 15
}
```

### Acknowledge Insight

Mark an insight as acknowledged.

```http
POST /api/insights/{insight_id}/acknowledge
```

**Request Body:**

```json
{
  "acknowledged_by": "jane.doe@example.com"
}
```

### Get Insight

Retrieve a specific insight.

```http
GET /api/insights/{insight_id}
```

---

## Cost Tracking

### Calculate Incident Cost

Calculate the total cost of an incident.

```http
POST /api/costs/calculate
```

**Request Body:**

```json
{
  "incident_id": "INC-12345",
  "service_name": "payments-api",
  "severity": "high",
  "incident_started_at": "2024-01-15T10:00:00Z",
  "incident_resolved_at": "2024-01-15T11:30:00Z",
  "responders": [
    {
      "id": "U001",
      "name": "Jane Doe",
      "team": "platform",
      "role": "sre",
      "time_minutes": 90
    },
    {
      "id": "U002",
      "name": "John Smith",
      "team": "engineering",
      "role": "engineer",
      "time_minutes": 45
    }
  ],
  "affected_users": 5000,
  "affected_transactions": 250
}
```

**Response:**

```json
{
  "cost": {
    "incident_id": "INC-12345",
    "service_name": "payments-api",
    "severity": "high",
    "total_cost": "8750.00",
    "responder_costs": [
      {
        "responder_id": "U001",
        "name": "Jane Doe",
        "hourly_rate": "150.00",
        "time_minutes": 90,
        "cost": "225.00"
      }
    ],
    "opportunity_cost": "2500.00",
    "revenue_impact": "5000.00",
    "custom_costs": [],
    "calculated_at": "2024-01-15T12:00:00Z"
  },
  "message": "Incident cost calculated successfully"
}
```

### List Incident Costs

```http
GET /api/costs
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `start_date` | datetime | Filter by start date |
| `end_date` | datetime | Filter by end date |
| `service` | string | Filter by service |
| `team` | string | Filter by team |
| `severity` | string | Filter by severity |
| `finalized` | boolean | Filter by finalized status |
| `limit` | integer | Maximum results (1-500) |

### Get Incident Cost

```http
GET /api/costs/{incident_id}
```

### Update Incident Cost

```http
PUT /api/costs/{incident_id}
```

**Request Body:**

```json
{
  "affected_users": 6000,
  "affected_transactions": 300,
  "notes": "Updated impact assessment",
  "responders": [...],
  "custom_costs": [
    {
      "description": "Emergency contractor",
      "amount": "500.00"
    }
  ]
}
```

### Add SLA Penalty

```http
POST /api/costs/{incident_id}/sla-penalty
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `sla_id` | string | Yes | SLA identifier |
| `sla_name` | string | Yes | SLA name |
| `breach_type` | string | Yes | Type of breach |
| `target_value` | string | Yes | SLA target |
| `actual_value` | string | Yes | Actual achieved |
| `customer_id` | string | No | Customer ID |
| `customer_name` | string | No | Customer name |
| `customer_tier` | string | No | Customer tier |

### Finalize Incident Cost

Lock the cost record from further modifications.

```http
POST /api/costs/{incident_id}/finalize
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `finalized_by` | string | Yes | User finalizing |

### Delete Incident Cost

```http
DELETE /api/costs/{incident_id}
```

---

## Cost Reports

### Generate Cost Report

```http
POST /api/costs/reports/generate
```

**Request Body:**

```json
{
  "period": "monthly",
  "services": ["payments-api", "checkout-service"],
  "include_roi": true,
  "compare_previous": true,
  "top_incidents_limit": 10
}
```

**Period Types:**

| Period | Description |
|--------|-------------|
| `daily` | Last 24 hours |
| `weekly` | Last 7 days |
| `monthly` | Last 30 days |
| `quarterly` | Last 90 days |
| `yearly` | Last 365 days |

**Response:**

```json
{
  "report": {
    "report_id": "rpt_abc123",
    "period": "monthly",
    "period_start": "2023-12-15T00:00:00Z",
    "period_end": "2024-01-15T00:00:00Z",
    "total_incidents": 75,
    "total_cost": "125000.00",
    "average_cost_per_incident": "1666.67",
    "cost_change_percent": -12.5,
    "cost_by_severity": {
      "critical": "45000.00",
      "high": "55000.00",
      "medium": "20000.00",
      "low": "5000.00"
    },
    "cost_by_service": {...},
    "service_summaries": [...],
    "top_incidents": [...],
    "generated_at": "2024-01-15T10:00:00Z"
  },
  "message": "Cost report generated successfully"
}
```

### Get Cost Summary

Quick cost summary without full report.

```http
GET /api/costs/reports/summary
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `period` | string | monthly | Report period |

### Export Report as CSV

```http
GET /api/costs/reports/export/csv
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `period` | string | monthly | Report period |

Returns raw CSV content with `Content-Disposition: attachment` header.

### Export for Finance Systems

```http
GET /api/costs/reports/finance-export
```

Returns structured data suitable for accounting integration.

---

## ROI Analysis

### Get ROI Analysis

```http
GET /api/costs/roi/analysis
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `start_date` | datetime | Analysis period start |
| `end_date` | datetime | Analysis period end |
| `investment_cost` | float | Total investment for ROI calculation |

**Response:**

```json
{
  "period_start": "2024-01-01T00:00:00Z",
  "period_end": "2024-01-15T00:00:00Z",
  "total_incidents": 50,
  "total_cost_without_tool": "175000.00",
  "total_cost_with_tool": "125000.00",
  "savings": "50000.00",
  "savings_percentage": 28.6,
  "mttr_improvement_percentage": 35.0,
  "investment_cost": "10000.00",
  "roi_percentage": 400.0,
  "payback_period_days": 30,
  "breakdown": {
    "time_savings": "25000.00",
    "revenue_protected": "15000.00",
    "reduced_escalations": "10000.00"
  }
}
```

---

## Cost Configuration

### Get Cost Configuration

```http
GET /api/costs/config
```

**Response:**

```json
{
  "config": {
    "config_id": "default",
    "name": "Default Cost Factors",
    "hourly_rates": {
      "sre": 150,
      "engineer": 125,
      "manager": 175,
      "executive": 300
    },
    "revenue_factors": {
      "per_affected_user": 0.10,
      "per_affected_transaction": 5.00
    },
    "sla_factors": {
      "professional": 1.0,
      "enterprise": 2.0,
      "premium": 5.0
    }
  },
  "message": "Current cost configuration"
}
```

### Update Cost Configuration

```http
PUT /api/costs/config
```

**Request Body:**

```json
{
  "config_id": "custom",
  "name": "Custom Cost Factors",
  "hourly_rates": {
    "sre": 175,
    "engineer": 150,
    "manager": 200,
    "executive": 350
  },
  "revenue_factors": {
    "per_affected_user": 0.15,
    "per_affected_transaction": 7.50
  }
}
```

### Reset Cost Configuration

```http
POST /api/costs/config/reset
```

Restores default cost factors.

---

*See also: [Incidents API](incidents.md) | [Admin API](admin.md)*
