# 📈 Reports & Analytics

Incident Copilot provides comprehensive reporting and analytics to help you track incident trends, measure MTTR improvements, and share insights with stakeholders.

---

## Overview

Reports help you:
- **Track progress** - Monitor MTTR and incident trends over time
- **Identify patterns** - Find recurring issues and problematic services
- **Share insights** - Deliver reports to Slack, email, or dashboards
- **Prove ROI** - Demonstrate the impact of incident management improvements

---

## Report Types

### Automated Reports

Scheduled reports delivered automatically:

| Report | Frequency | Description |
|--------|-----------|-------------|
| **[Daily Digest](./features/scheduled-reports.md#daily-digest)** | Every morning | Summary of yesterday's incidents |
| **[Weekly Report](./features/scheduled-reports.md#weekly-report)** | Weekly | Comprehensive analysis with trends |
| **[Monthly Review](./features/scheduled-reports.md#monthly-review)** | Monthly | Executive summary and recommendations |

### On-Demand Reports

Generate anytime via API or CLI:

```bash
# Generate weekly report for specific period
incident-copilot report generate --type weekly \
  --start 2025-01-01 --end 2025-01-07

# Send immediately to Slack
incident-copilot report send --type daily --channel "#incidents"
```

---

## Quick Start

### 1. Enable Reports

```bash
# .env
REPORTS_ENABLED=true
REPORTS_TIMEZONE=America/Los_Angeles
```

### 2. Configure Delivery

```bash
# Slack delivery
REPORTS_SLACK_CHANNEL=#incident-reports

# Email delivery (optional)
REPORTS_EMAIL_ENABLED=true
REPORTS_EMAIL_RECIPIENTS=team@company.com
```

### 3. Set Schedule

```bash
# Weekly report on Mondays at 9am
REPORTS_WEEKLY_ENABLED=true
REPORTS_WEEKLY_SCHEDULE="0 9 * * MON"

# Daily digest at 8am
REPORTS_DAILY_ENABLED=true
REPORTS_DAILY_SCHEDULE="0 8 * * *"
```

---

## Report Examples

### Daily Digest

```
📊 Daily Incident Digest - January 15, 2025
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Incidents: 5 (↓2 from yesterday)
MTTR: 18 min (↓ 12%)

By Severity:
• Critical: 0  ✅
• High: 2
• Medium: 2
• Low: 1

Top Services:
1. payments-api (2 incidents)
2. auth-service (1 incident)

Notable: All incidents resolved within SLA ✅
```

### Weekly Summary

```
📈 Weekly Incident Report - Jan 8-15, 2025
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Summary
───────
Total Incidents: 23 (↓ 15% vs last week)
MTTR (mean): 22 min (↓ 18%)
MTTR (p90): 45 min (↓ 22%)

Top Issues This Week:
1. Database connection timeouts (8 incidents)
2. Third-party API failures (5 incidents)
3. Memory pressure alerts (3 incidents)

Trend: MTTR improving for 4 consecutive weeks 📉
```

---

## Metrics Tracked

| Metric | Description |
|--------|-------------|
| **MTTR** | Mean Time To Resolve (time from alert to resolution) |
| **MTTA** | Mean Time To Acknowledge (time to first response) |
| **Incident Count** | Total incidents in the period |
| **Severity Distribution** | Breakdown by critical/high/medium/low |
| **Service Breakdown** | Incidents per service |
| **Top Error Patterns** | Most common error types |
| **SLA Compliance** | Percentage meeting SLA targets |

---

## Configuration Reference

See **[Scheduled Reports Configuration](./features/scheduled-reports.md#configuration)** for complete options.

### Key Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REPORTS_ENABLED` | `true` | Enable/disable all reports |
| `REPORTS_TIMEZONE` | `UTC` | Timezone for scheduling |
| `REPORTS_WEEKLY_ENABLED` | `true` | Enable weekly reports |
| `REPORTS_WEEKLY_SCHEDULE` | `0 9 * * MON` | Cron schedule |
| `REPORTS_SLACK_CHANNEL` | - | Default Slack channel |

---

## API Access

Generate reports programmatically:

```bash
# List scheduled reports
GET /api/reports/schedules

# Generate on-demand report
POST /api/reports/generate
{
  "report_type": "weekly",
  "period_start": "2025-01-08",
  "period_end": "2025-01-15"
}

# Get report history
GET /api/reports/history
```

See **[API Reference → Reports](./api-reference.md#reports-api)** for complete documentation.

---

## Customization

### Custom Report Templates

Create custom templates for different stakeholders:

```bash
# Engineering team (detailed technical info)
REPORTS_TEMPLATE_ENGINEERING=detailed

# Leadership (high-level summary)
REPORTS_TEMPLATE_EXECUTIVE=summary
```

### Filtering Reports

Filter reports by service, severity, or team:

```json
{
  "filters": {
    "services": ["payments-api", "checkout"],
    "min_severity": "medium",
    "teams": ["platform"]
  }
}
```

---

## Related Documentation

- **[Scheduled Reports](./features/scheduled-reports.md)** - Detailed configuration guide
- **[Analytics](./features/analytics.md)** - Understanding metrics
- **[API Reference](./api-reference.md#reports-api)** - Report API endpoints
- **[Configuration](./configuration.md)** - All configuration options

---

*Need help with reports? Check the [Troubleshooting Guide](./troubleshooting.md#reports-not-sending).*
