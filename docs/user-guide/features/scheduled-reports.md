# 📅 Scheduled Reports

Automatically generate and deliver incident reports on a schedule. Get daily, weekly, or monthly summaries delivered to Slack, email, or both.

---

## 🎯 Overview

Scheduled Reports automate incident visibility for stakeholders:

- **Daily Digests** - Quick summary of yesterday's incidents
- **Weekly Reports** - Comprehensive weekly analysis with trends
- **Monthly Reviews** - Full metrics, patterns, and recommendations

Reports include:
- Incident counts and severity breakdown
- MTTR trends and comparisons
- Top affected services
- Pattern detection and insights
- Action item tracking

---

## 📊 Report Types

### Daily Digest

Quick morning briefing on the previous day:

```
📊 Daily Incident Digest - January 15, 2025
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Incidents: 5 (↓2 from previous day)
MTTR: 18 min (↓ 12%)

By Severity:
• Critical: 0
• High: 2
• Medium: 2
• Low: 1

Top Services:
1. payments-api (2 incidents)
2. auth-service (1 incident)

Notable: All incidents resolved within SLA ✅
```

### Weekly Report

Comprehensive weekly analysis:

```
📈 Weekly Incident Report - Jan 8-15, 2025
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Summary
───────
Total Incidents: 23 (↓ 15% vs last week)
MTTR (mean): 22 min (↓ 18%)
MTTR (p90): 45 min (↓ 22%)

Severity Distribution
─────────────────────
Critical: 2 (9%)
High: 6 (26%)
Medium: 10 (43%)
Low: 5 (22%)

Service Breakdown
─────────────────
payments-api    █████████ 8
auth-service    █████ 5
checkout        ████ 4
inventory       ███ 3
notifications   ███ 3

Trend Analysis
──────────────
• MTTR improving for 4 consecutive weeks
• Critical incidents down 50% month-over-month
• payments-api seeing increased errors (investigate)

Action Items Status
───────────────────
Open: 12
Overdue: 3
Completed this week: 8
```

### Monthly Review

Executive-level monthly summary:

```
📊 Monthly Incident Review - January 2025
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Executive Summary
─────────────────
• 92 incidents (↓ 8% vs December)
• MTTR improved 23% month-over-month
• Zero customer-impacting outages

Key Metrics
───────────
Metric          January    December    Change
───────         ───────    ────────    ──────
Incidents       92         100         -8%
MTTR (mean)     19 min     25 min      -24%
MTTR (p90)      38 min     52 min      -27%
TTA (mean)      2.1 min    3.2 min     -34%

Top Issues
──────────
1. Database connection timeouts (18 incidents)
   → Action: Implement connection pooling
2. Third-party API failures (12 incidents)
   → Action: Add circuit breakers
3. Memory leaks in auth-service (8 incidents)
   → Action: Scheduled for v2.3 release

Recommendations
───────────────
1. Prioritize database connection pooling
2. Review auth-service memory management
3. Add monitoring for third-party dependencies
```

---

## ⚙️ Configuration

### Create a Report Schedule

**Via API:**

```bash
curl -X POST http://localhost:8000/api/reports/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Weekly Engineering Report",
    "report_type": "weekly",
    "schedule": "0 9 * * MON",
    "timezone": "America/Los_Angeles",
    "delivery": {
      "slack_channels": ["#incidents", "#engineering-leads"],
      "email_recipients": ["oncall@company.com"]
    },
    "filters": {
      "services": ["payments-api", "auth-service"],
      "min_severity": "medium"
    }
  }'
```

**Via Environment Variables:**

```bash
# Enable default weekly report
REPORTS_WEEKLY_ENABLED=true
REPORTS_WEEKLY_SCHEDULE="0 9 * * MON"
REPORTS_WEEKLY_TIMEZONE=America/Los_Angeles
REPORTS_WEEKLY_SLACK_CHANNEL=#incidents
REPORTS_WEEKLY_EMAIL=oncall@company.com
```

### Schedule Syntax (Cron)

Reports use standard cron syntax:

```
┌─────────── minute (0-59)
│ ┌───────── hour (0-23)
│ │ ┌─────── day of month (1-31)
│ │ │ ┌───── month (1-12)
│ │ │ │ ┌─── day of week (0-6, Sunday=0)
│ │ │ │ │
* * * * *
```

**Common Schedules:**

| Schedule | Cron Expression |
|----------|-----------------|
| Daily at 9am | `0 9 * * *` |
| Weekly Monday 9am | `0 9 * * MON` |
| Monthly 1st at 9am | `0 9 1 * *` |
| Bi-weekly Friday 5pm | `0 17 * * FRI/2` |

---

## 🔑 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REPORTS_ENABLED` | `true` | Enable/disable all scheduled reports |
| `REPORTS_TIMEZONE` | `UTC` | Default timezone for schedules |
| `REPORTS_DAILY_ENABLED` | `false` | Enable daily digest |
| `REPORTS_DAILY_SCHEDULE` | `0 9 * * *` | Daily report cron schedule |
| `REPORTS_WEEKLY_ENABLED` | `true` | Enable weekly report |
| `REPORTS_WEEKLY_SCHEDULE` | `0 9 * * MON` | Weekly report cron schedule |
| `REPORTS_MONTHLY_ENABLED` | `true` | Enable monthly report |
| `REPORTS_MONTHLY_SCHEDULE` | `0 9 1 * *` | Monthly report cron schedule |
| `REPORTS_SLACK_CHANNEL` | - | Default Slack channel for reports |
| `REPORTS_EMAIL_RECIPIENTS` | - | Comma-separated email addresses |

---

## 📬 Delivery Methods

### Slack Delivery

Reports are formatted as rich Slack messages with:
- Expandable sections
- Charts rendered as text art
- Links to detailed dashboards
- Action buttons for drill-down

```bash
REPORTS_SLACK_ENABLED=true
REPORTS_SLACK_CHANNEL=#incident-reports
```

### Email Delivery

Reports sent as formatted HTML emails with:
- Responsive design
- Embedded charts
- CSV attachment option
- One-click unsubscribe

```bash
REPORTS_EMAIL_ENABLED=true
REPORTS_EMAIL_RECIPIENTS=team@company.com,manager@company.com

# SMTP Configuration
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=your-sendgrid-api-key
SMTP_FROM_ADDRESS=reports@incident-copilot.com
```

### Multiple Destinations

Send to multiple channels/emails:

```bash
curl -X POST http://localhost:8000/api/reports/schedules \
  -d '{
    "delivery": {
      "slack_channels": ["#incidents", "#engineering", "#leadership"],
      "email_recipients": ["oncall@company.com", "cto@company.com"]
    }
  }'
```

---

## 📱 API Reference

### List Schedules

```bash
GET /api/reports/schedules

Response:
{
  "schedules": [
    {
      "id": "sched_123",
      "name": "Weekly Engineering Report",
      "report_type": "weekly",
      "schedule": "0 9 * * MON",
      "timezone": "America/Los_Angeles",
      "next_run": "2025-01-20T09:00:00-08:00",
      "last_run": "2025-01-13T09:00:00-08:00",
      "enabled": true
    }
  ]
}
```

### Create Schedule

```bash
POST /api/reports/schedules
{
  "name": "Daily Digest",
  "report_type": "daily",
  "schedule": "0 9 * * *",
  "timezone": "America/New_York",
  "delivery": {
    "slack_channels": ["#incidents"]
  }
}

Response:
{
  "id": "sched_456",
  "name": "Daily Digest",
  "created_at": "2025-01-15T10:00:00Z"
}
```

### Update Schedule

```bash
PATCH /api/reports/schedules/{schedule_id}
{
  "enabled": false
}
```

### Delete Schedule

```bash
DELETE /api/reports/schedules/{schedule_id}
```

### Generate Report On-Demand

```bash
POST /api/reports/generate
{
  "report_type": "weekly",
  "period_start": "2025-01-08",
  "period_end": "2025-01-15",
  "delivery": {
    "slack_channels": ["#incidents"]
  }
}
```

### Get Report History

```bash
GET /api/reports/history?limit=10

Response:
{
  "reports": [
    {
      "id": "rpt_789",
      "schedule_id": "sched_123",
      "report_type": "weekly",
      "generated_at": "2025-01-13T09:00:00Z",
      "period": "2025-01-06 to 2025-01-12",
      "delivery_status": "delivered",
      "destinations": ["#incidents", "oncall@company.com"]
    }
  ]
}
```

---

## 🎛️ Filtering Reports

### By Service

Include only specific services:

```json
{
  "filters": {
    "services": ["payments-api", "auth-service"]
  }
}
```

### By Severity

Minimum severity threshold:

```json
{
  "filters": {
    "min_severity": "high"
  }
}
```

### By Team

Filter by team ownership:

```json
{
  "filters": {
    "teams": ["platform", "payments"]
  }
}
```

---

## 📊 Report Formats

### Slack (Default)

Rich formatted message optimized for Slack:

```
REPORTS_FORMAT=slack
```

### HTML Email

Full HTML report with styling:

```
REPORTS_FORMAT=html
```

### Markdown

Plain markdown (for GitHub, wikis):

```
REPORTS_FORMAT=markdown
```

### JSON

Raw data for custom processing:

```
REPORTS_FORMAT=json
```

---

## 🐛 Troubleshooting

### Reports Not Sending

**Checks:**
1. Verify `REPORTS_ENABLED=true`
2. Check schedule cron syntax
3. Verify timezone is correct
4. Check delivery credentials (Slack/SMTP)

**Debug:**
```bash
# View scheduler logs
docker-compose logs -f | grep reports

# Test delivery manually
curl -X POST http://localhost:8000/api/reports/test-delivery
```

### Empty Reports

**Cause:** No incidents in the reporting period

**Solutions:**
1. Verify incidents exist in the database
2. Check filter criteria aren't too restrictive
3. Review date range calculations

### Slack Delivery Failures

**Checks:**
1. Bot has access to target channel
2. Channel exists (not deleted/archived)
3. Slack token has required scopes

### Email Delivery Failures

**Checks:**
1. SMTP credentials are correct
2. From address is authorized
3. Recipients aren't blocking emails
4. Check spam folders

---

## 📚 Related Documentation

- [Analytics & Metrics](./analytics.md) - Understand report metrics
- [Slack Integration](../integrations/slack.md) - Slack setup
- [API Reference](../api-reference.md) - Full API documentation

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or open an issue on GitHub.*
