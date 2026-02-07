# Export API

Export incident data, reports, and analytics in various formats for external processing and compliance.

## Overview

The Export API enables you to:
- Export incidents in JSON, CSV, or PDF formats
- Generate compliance and audit reports
- Schedule recurring exports
- Bulk export historical data
- Track export job status

## Base URL

```
/api/v1/export
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
| Export creation | 10 requests/minute |
| Bulk exports | 5 requests/hour |

---

## Endpoints

### Export Incidents

Create an export job for incidents.

```
POST /api/v1/export/incidents
```

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `format` | string | Yes | Output format: `json`, `csv`, `xlsx`, `pdf` |
| `filters` | object | No | Filter criteria (same as search API) |
| `fields` | array | No | Fields to include (default: all) |
| `date_range` | object | No | Date range filter |
| `include_timeline` | boolean | No | Include incident timeline (default: false) |
| `include_comments` | boolean | No | Include comments (default: false) |
| `include_attachments` | boolean | No | Include attachment URLs (default: false) |

#### Request

```json
{
  "format": "csv",
  "filters": {
    "status": ["resolved", "closed"],
    "priority": ["critical", "high"]
  },
  "date_range": {
    "start": "2024-01-01T00:00:00Z",
    "end": "2024-01-31T23:59:59Z"
  },
  "fields": [
    "id",
    "title",
    "priority",
    "status",
    "created_at",
    "resolved_at",
    "ttd_minutes",
    "ttr_minutes",
    "assigned_to",
    "team"
  ],
  "include_timeline": false,
  "include_comments": false
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "job_id": "export_job_001",
    "status": "pending",
    "format": "csv",
    "estimated_records": 156,
    "created_at": "2024-01-26T10:00:00Z",
    "estimated_completion": "2024-01-26T10:02:00Z"
  }
}
```

#### Example

```bash
curl -X POST "https://api.incident-copilot.io/api/v1/export/incidents" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "format": "csv",
    "date_range": {"start": "2024-01-01T00:00:00Z", "end": "2024-01-31T23:59:59Z"},
    "filters": {"status": ["resolved"]}
  }'
```

---

### Get Export Job Status

Check the status of an export job.

```
GET /api/v1/export/jobs/{job_id}
```

#### Response (In Progress)

```json
{
  "success": true,
  "data": {
    "job_id": "export_job_001",
    "status": "processing",
    "progress": 65,
    "records_processed": 101,
    "total_records": 156,
    "format": "csv",
    "created_at": "2024-01-26T10:00:00Z",
    "started_at": "2024-01-26T10:00:05Z"
  }
}
```

#### Response (Completed)

```json
{
  "success": true,
  "data": {
    "job_id": "export_job_001",
    "status": "completed",
    "format": "csv",
    "records_exported": 156,
    "file_size_bytes": 245890,
    "download_url": "https://exports.incident-copilot.io/export_job_001.csv",
    "download_expires_at": "2024-01-27T10:00:00Z",
    "created_at": "2024-01-26T10:00:00Z",
    "completed_at": "2024-01-26T10:01:45Z"
  }
}
```

#### Status Values

| Status | Description |
|--------|-------------|
| `pending` | Job queued, not started |
| `processing` | Export in progress |
| `completed` | Export finished, ready for download |
| `failed` | Export failed |
| `expired` | Download link expired |

#### Example

```bash
curl -X GET "https://api.incident-copilot.io/api/v1/export/jobs/export_job_001" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Download Export

Download the exported file.

```
GET /api/v1/export/jobs/{job_id}/download
```

#### Response

Binary file download with appropriate Content-Type header.

#### Example

```bash
curl -X GET "https://api.incident-copilot.io/api/v1/export/jobs/export_job_001/download" \
  -H "Authorization: Bearer $TOKEN" \
  -o incidents_export.csv
```

---

### List Export Jobs

List all export jobs for the current user.

```
GET /api/v1/export/jobs
```

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `status` | string | No | Filter by status |
| `limit` | integer | No | Max results (default: 20) |
| `page` | integer | No | Page number |

#### Response

```json
{
  "success": true,
  "data": {
    "jobs": [
      {
        "job_id": "export_job_002",
        "status": "completed",
        "format": "pdf",
        "records_exported": 45,
        "file_size_bytes": 1245890,
        "created_at": "2024-01-26T11:00:00Z",
        "completed_at": "2024-01-26T11:03:00Z",
        "download_expires_at": "2024-01-27T11:00:00Z"
      },
      {
        "job_id": "export_job_001",
        "status": "completed",
        "format": "csv",
        "records_exported": 156,
        "file_size_bytes": 245890,
        "created_at": "2024-01-26T10:00:00Z",
        "completed_at": "2024-01-26T10:01:45Z",
        "download_expires_at": "2024-01-27T10:00:00Z"
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
curl -X GET "https://api.incident-copilot.io/api/v1/export/jobs?status=completed" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Cancel Export Job

Cancel a pending or processing export job.

```
POST /api/v1/export/jobs/{job_id}/cancel
```

#### Response

```json
{
  "success": true,
  "data": {
    "job_id": "export_job_003",
    "status": "cancelled",
    "cancelled_at": "2024-01-26T11:15:00Z"
  }
}
```

#### Example

```bash
curl -X POST "https://api.incident-copilot.io/api/v1/export/jobs/export_job_003/cancel" \
  -H "Authorization: Bearer $TOKEN"
```

---

### Generate Report

Generate a formatted report.

```
POST /api/v1/export/reports
```

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | Report type (see below) |
| `format` | string | Yes | Output format: `pdf`, `html`, `xlsx` |
| `date_range` | object | Yes | Report date range |
| `options` | object | No | Report-specific options |

#### Report Types

| Type | Description |
|------|-------------|
| `summary` | Executive summary with key metrics |
| `detailed` | Detailed incident breakdown |
| `sla_compliance` | SLA compliance report |
| `team_performance` | Team metrics and performance |
| `trend_analysis` | Incident trends over time |
| `postmortem_summary` | Summary of postmortems |
| `audit` | Compliance audit report |

#### Request

```json
{
  "type": "sla_compliance",
  "format": "pdf",
  "date_range": {
    "start": "2024-01-01T00:00:00Z",
    "end": "2024-01-31T23:59:59Z"
  },
  "options": {
    "include_charts": true,
    "group_by": "team",
    "include_breach_details": true
  }
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "job_id": "report_job_001",
    "type": "sla_compliance",
    "status": "pending",
    "format": "pdf",
    "created_at": "2024-01-26T12:00:00Z",
    "estimated_completion": "2024-01-26T12:05:00Z"
  }
}
```

#### Example

```bash
curl -X POST "https://api.incident-copilot.io/api/v1/export/reports" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "summary",
    "format": "pdf",
    "date_range": {"start": "2024-01-01", "end": "2024-01-31"}
  }'
```

---

### Schedule Recurring Export

Create a scheduled recurring export.

```
POST /api/v1/export/schedules
```

#### Request Body

```json
{
  "name": "Weekly Incident Report",
  "type": "incidents",
  "format": "xlsx",
  "schedule": {
    "frequency": "weekly",
    "day_of_week": "monday",
    "time": "08:00",
    "timezone": "America/New_York"
  },
  "filters": {
    "status": ["resolved", "closed"]
  },
  "delivery": {
    "method": "email",
    "recipients": ["team@example.com", "manager@example.com"]
  },
  "enabled": true
}
```

#### Schedule Frequency Options

| Frequency | Additional Fields |
|-----------|------------------|
| `daily` | `time` |
| `weekly` | `day_of_week`, `time` |
| `monthly` | `day_of_month`, `time` |
| `quarterly` | `time` |

#### Delivery Methods

| Method | Required Fields |
|--------|----------------|
| `email` | `recipients` (array of email addresses) |
| `slack` | `channel` (Slack channel ID) |
| `webhook` | `url`, optional `headers` |
| `s3` | `bucket`, `prefix`, `credentials_id` |

#### Response

```json
{
  "success": true,
  "data": {
    "schedule_id": "sched_001",
    "name": "Weekly Incident Report",
    "type": "incidents",
    "format": "xlsx",
    "schedule": {
      "frequency": "weekly",
      "day_of_week": "monday",
      "time": "08:00",
      "timezone": "America/New_York"
    },
    "next_run": "2024-01-29T13:00:00Z",
    "enabled": true,
    "created_at": "2024-01-26T12:30:00Z"
  }
}
```

#### Example

```bash
curl -X POST "https://api.incident-copilot.io/api/v1/export/schedules" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Weekly Incident Report",
    "type": "incidents",
    "format": "xlsx",
    "schedule": {"frequency": "weekly", "day_of_week": "monday", "time": "08:00"},
    "delivery": {"method": "email", "recipients": ["team@example.com"]}
  }'
```

---

### List Scheduled Exports

```
GET /api/v1/export/schedules
```

#### Response

```json
{
  "success": true,
  "data": {
    "schedules": [
      {
        "schedule_id": "sched_001",
        "name": "Weekly Incident Report",
        "type": "incidents",
        "format": "xlsx",
        "schedule": {
          "frequency": "weekly",
          "day_of_week": "monday",
          "time": "08:00",
          "timezone": "America/New_York"
        },
        "next_run": "2024-01-29T13:00:00Z",
        "last_run": "2024-01-22T13:00:00Z",
        "last_status": "completed",
        "enabled": true
      }
    ]
  }
}
```

---

### Update Scheduled Export

```
PUT /api/v1/export/schedules/{schedule_id}
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
    "schedule_id": "sched_001",
    "enabled": false,
    "updated_at": "2024-01-26T13:00:00Z"
  }
}
```

---

### Delete Scheduled Export

```
DELETE /api/v1/export/schedules/{schedule_id}
```

#### Response

```json
{
  "success": true,
  "message": "Scheduled export deleted"
}
```

---

## Export Fields Reference

### Incident Fields

| Field | Description |
|-------|-------------|
| `id` | Incident ID |
| `title` | Incident title |
| `description` | Full description |
| `priority` | Priority level |
| `severity` | Severity level |
| `status` | Current status |
| `created_at` | Creation timestamp |
| `acknowledged_at` | Acknowledgment timestamp |
| `resolved_at` | Resolution timestamp |
| `closed_at` | Closure timestamp |
| `ttd_minutes` | Time to detect |
| `ttr_minutes` | Time to resolve |
| `assigned_to` | Assignee name |
| `team` | Team name |
| `service` | Affected service |
| `tags` | Comma-separated tags |
| `root_cause` | Root cause summary |
| `resolution` | Resolution summary |
| `customer_impact` | Customer impact description |

---

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| 400 | `INVALID_FORMAT` | Unsupported export format |
| 400 | `INVALID_DATE_RANGE` | Invalid or missing date range |
| 400 | `INVALID_SCHEDULE` | Invalid schedule configuration |
| 404 | `JOB_NOT_FOUND` | Export job not found |
| 404 | `SCHEDULE_NOT_FOUND` | Schedule not found |
| 409 | `JOB_NOT_CANCELLABLE` | Job already completed or failed |
| 410 | `DOWNLOAD_EXPIRED` | Download link has expired |
| 429 | `EXPORT_LIMIT_EXCEEDED` | Too many concurrent exports |

### Error Response Format

```json
{
  "success": false,
  "error": {
    "code": "DOWNLOAD_EXPIRED",
    "message": "Export download link has expired",
    "details": {
      "job_id": "export_job_001",
      "expired_at": "2024-01-27T10:00:00Z"
    }
  }
}
```
