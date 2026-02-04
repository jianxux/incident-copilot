# 📈 Analytics & MTTR Metrics

Incident Copilot tracks key metrics to help you understand and improve your incident response performance.

---

## 🎯 Key Metrics

### MTTR (Mean Time to Resolve)

The average time from incident trigger to resolution:

```
MTTR = Σ(resolved_at - triggered_at) / incident_count
```

**Target:** Most teams aim for <1 hour for high-severity incidents.

### TTA (Time to Acknowledge)

Time from trigger to first acknowledgement:

```
TTA = acknowledged_at - triggered_at
```

**Target:** <5 minutes for critical incidents.

### TTC (Time to Context)

Time from trigger to context card delivery:

```
TTC = context_delivered_at - triggered_at
```

**Target:** <10 seconds (Incident Copilot's goal).

---

## 📊 Dashboard Metrics

### Overview Stats

```
┌─────────────────────────────────────────────────────────┐
│  📊 Incident Analytics - Last 30 Days                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Incidents    MTTR (mean)    TTA (mean)    TTC (mean)   │
│  ────────     ──────────     ─────────     ─────────    │
│     47          23 min        2.3 min       6.4 sec     │
│                 ↓ 15%         ↓ 8%          ↓ 2%        │
│                                                         │
│  By Severity:                                           │
│  • Critical (5): MTTR 18 min                            │
│  • High (12): MTTR 25 min                               │
│  • Medium (20): MTTR 28 min                             │
│  • Low (10): MTTR 35 min                                │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Trend Analysis

```
MTTR Trend (Last 12 Weeks)
────────────────────────────────────────────────
45min │      *
      │   *     *
30min │*           *  *
      │               *  *
15min │                     *  *  *  *
      └─────────────────────────────────────────
       W1  W2  W3  W4  W5  W6  W7  W8  W9 W10 W11 W12
```

---

## 📊 Metric Calculations

### Mean MTTR

```python
mttr_values = [incident.time_to_resolve for incident in resolved_incidents]
mean_mttr = sum(mttr_values) / len(mttr_values)
```

### Median MTTR

More robust against outliers:

```python
sorted_values = sorted(mttr_values)
median_mttr = sorted_values[len(sorted_values) // 2]
```

### P90 MTTR

90th percentile - "90% of incidents are resolved faster than this":

```python
p90_mttr = sorted_values[int(len(sorted_values) * 0.9)]
```

---

## 🔍 Filtering & Segmentation

### By Service

Track MTTR per service:

```
GET /api/analytics/mttr?service=payments-api
```

```
Service         MTTR (mean)  Incidents
─────────       ──────────   ─────────
payments-api    18 min       12
auth-service    25 min       8
checkout        32 min       15
```

### By Severity

```
GET /api/analytics/mttr?severity=critical
```

### By Time Period

```
GET /api/analytics/mttr?start=2025-01-01&end=2025-01-31
```

### Period Comparison

Compare to previous period:

```
GET /api/analytics/mttr/compare?days=30
```

```json
{
  "current_period": {
    "mean_mttr_seconds": 1380,
    "incidents_count": 47
  },
  "previous_period": {
    "mean_mttr_seconds": 1620,
    "incidents_count": 52
  },
  "mttr_change_percent": -14.8,
  "incident_count_change_percent": -9.6
}
```

---

## 📱 API Reference

### Get MTTR Stats

```bash
GET /api/analytics/mttr?days=30

Response:
{
  "period": "30d",
  "period_start": "2024-12-16T00:00:00Z",
  "period_end": "2025-01-15T00:00:00Z",
  "mean_mttr_seconds": 1380,
  "median_mttr_seconds": 1200,
  "p90_mttr_seconds": 2400,
  "incidents_count": 47,
  "resolved_count": 45,
  "mean_time_to_acknowledge_seconds": 138,
  "mean_time_to_context_card_seconds": 6.4
}
```

### Compare Periods

```bash
GET /api/analytics/mttr/compare?days=30

Response:
{
  "current_period": { ... },
  "previous_period": { ... },
  "mttr_change_percent": -14.8,
  "incident_count_change_percent": -9.6,
  "trend": "improving"
}
```

### Per-Service Stats

```bash
GET /api/analytics/services

Response:
{
  "services": [
    {
      "service_name": "payments-api",
      "incidents_count": 12,
      "mean_mttr_seconds": 1080,
      "top_error_patterns": ["ConnectionTimeout", "Retry exceeded"]
    }
  ]
}
```

---

## 📊 Events Tracked

### Automatic Tracking

| Event | When Tracked |
|-------|--------------|
| `triggered` | Webhook received |
| `acknowledged` | Ack event from PagerDuty/Opsgenie |
| `resolved` | Resolution event received |
| `context_card_delivered` | Card sent to Slack/Teams |

### How to Track Manually

```bash
POST /api/incidents/{id}/events
{
  "event_type": "acknowledged",
  "timestamp": "2025-01-15T02:32:00Z"
}
```

---

## 🎯 Benchmarks

### Industry Standards

| Metric | Good | Better | Best |
|--------|------|--------|------|
| MTTR (Critical) | <1 hr | <30 min | <15 min |
| MTTR (High) | <2 hr | <1 hr | <30 min |
| TTA (Critical) | <10 min | <5 min | <2 min |
| TTC | <30 sec | <15 sec | <10 sec |

### Improvement Targets

Set realistic improvement goals:

```
Current MTTR: 45 minutes
Target (3 months): 30 minutes (-33%)
Target (6 months): 20 minutes (-56%)
```

---

## 📈 Improving Metrics

### Reduce MTTR

1. **Better context** - Incident Copilot provides immediate context
2. **Runbook automation** - Link relevant runbooks
3. **Similar incidents** - Learn from past resolutions
4. **Clear ownership** - CODEOWNERS and on-call info

### Reduce TTA

1. **Clear escalation** - Know who to notify
2. **Mobile alerts** - PagerDuty/Opsgenie apps
3. **Context cards** - Start investigating immediately

### Reduce TTC

1. **Fast integrations** - Optimize API calls
2. **Caching** - Cache repository data
3. **Parallel fetching** - Concurrent API requests

---

## 📊 Reporting

### Weekly Report (Coming Soon)

Automated weekly summary:

```
📊 Weekly Incident Report (Jan 8-15)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Incidents: 12 (↓ 2 from last week)
MTTR: 22 min (↓ 15%)
TTA: 2.1 min (↓ 8%)

Top Services:
• payments-api: 5 incidents
• auth-service: 3 incidents

Action Items Due: 8
Action Items Overdue: 2
```

### Monthly Review (Coming Soon)

Detailed monthly analysis with trends and recommendations.

---

## 🐛 Troubleshooting

### Missing Metrics

**Cause:** Events not being tracked

**Solutions:**
- Verify webhook integration
- Check event tracking in logs
- Manually add missing events

### Incorrect MTTR

**Cause:** Missing resolution events

**Solutions:**
- Ensure resolution webhooks are configured
- Check resolution event is received
- Manually mark incidents resolved

### No Comparison Data

**Cause:** Not enough historical data

**Solutions:**
- Wait for more incident data
- Import historical incidents

---

## 📚 Related Documentation

- [Context Cards](./context-cards.md) - TTC tracking
- [Incident Timeline](./incident-timeline.md) - Event timestamps
- [Postmortems](./postmortems.md) - Incident analysis

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or open an issue on GitHub.*
