# 📅 Incident Timeline

The incident timeline provides a chronological view of all events during an incident, from trigger to resolution.

---

## 🎯 What is the Timeline?

The timeline captures every significant event during an incident:

```
📅 Incident Timeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
02:15  🚀 DEPLOYMENT       abc1234 deployed by @sarah
       │                   "Reduce connection timeout to 5s"
       │
02:30  🔔 ALERT TRIGGERED  High Error Rate detected
       │                   PagerDuty incident #12345
       │
02:32  👁️ ACKNOWLEDGED     @sarah acknowledged
       │
02:35  🔍 INVESTIGATION    Root cause identified
       │                   "Timeout too aggressive for Stripe API"
       │
02:38  🔧 MITIGATION       Config rollback initiated
       │                   @sarah reverted timeout to 30s
       │
02:45  ✅ RESOLVED         Error rate normalized
       │                   Duration: 15 minutes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 🏷️ Event Types

| Event Type | Icon | Description |
|------------|------|-------------|
| `alert_triggered` | 🔔 | Initial alert fired |
| `alert_acknowledged` | 👁️ | Someone acknowledged the alert |
| `investigation_started` | 🔍 | Investigation began |
| `root_cause_identified` | 🎯 | Root cause found |
| `mitigation_started` | 🔧 | Fix/mitigation began |
| `mitigation_completed` | ✅ | Mitigation finished |
| `incident_resolved` | 🏁 | Incident closed |
| `deployment` | 🚀 | Code deployment |
| `configuration_change` | ⚙️ | Config change |
| `escalation` | ⬆️ | Escalated to another team |
| `communication` | 📢 | Status update sent |
| `other` | 📌 | Other significant event |

---

## 📊 Timeline Sources

Events are collected from multiple sources:

### Automatic Sources

| Source | Events Captured |
|--------|-----------------|
| **PagerDuty/Opsgenie** | Trigger, acknowledge, resolve |
| **GitHub/GitLab** | Deployments (commits to main) |
| **Slack** | Acknowledgements, updates |

### Manual Additions

Engineers can add timeline events:
- Via Slack commands (coming soon)
- Via API
- Via postmortem editor

---

## 🔧 How It Works

### Event Collection

```
┌─────────────┐
│  PagerDuty  │──┐
│   Webhook   │  │
└─────────────┘  │
                 │    ┌─────────────────┐
┌─────────────┐  ├───▶│    Timeline     │
│   GitHub    │──┤    │    Builder      │
│   Commits   │  │    └────────┬────────┘
└─────────────┘  │             │
                 │             ▼
┌─────────────┐  │    ┌─────────────────┐
│   Manual    │──┘    │   Chronological │
│   Events    │       │     Timeline    │
└─────────────┘       └─────────────────┘
```

### AI Enhancement

The AI can analyze context and suggest additional events:

```
Based on the logs, it appears:
- 02:33 - First retry failures detected
- 02:34 - Error rate exceeded threshold
- 02:36 - Stripe status page updated
```

---

## 📱 Viewing the Timeline

### In Context Cards

A summary appears in context cards:

```
📅 Timeline
• 02:15 - Deployment (abc1234 by @sarah)
• 02:30 - Alert triggered
• 02:32 - Acknowledged by @sarah
```

### In Postmortems

Full timeline in generated postmortems:

```markdown
## Timeline

| Time (UTC) | Event | Details |
|------------|-------|---------|
| 02:15 | Deployment | abc1234 by @sarah |
| 02:30 | Alert Triggered | PagerDuty #12345 |
| 02:32 | Acknowledged | @sarah |
| 02:35 | Root Cause | Timeout too aggressive |
| 02:45 | Resolved | Duration: 15min |
```

### Via API

```bash
GET /api/incidents/{id}/timeline

Response:
{
  "incident_id": "inc-123",
  "events": [
    {
      "timestamp": "2025-01-15T02:15:00Z",
      "event_type": "deployment",
      "title": "Deployment: abc1234",
      "actor": "sarah",
      "source": "github"
    },
    ...
  ]
}
```

---

## 📝 Adding Events

### Via API

```bash
POST /api/incidents/{id}/timeline
{
  "event_type": "communication",
  "title": "Status update posted",
  "description": "Informed stakeholders of ongoing investigation",
  "actor": "sarah"
}
```

### Via Slack (Coming Soon)

```
/incident timeline add "Root cause identified"
```

---

## 🕐 Time Zones

All timestamps are stored in UTC. Display conversion:

- **Context Cards:** Show UTC with local offset
- **Postmortems:** UTC with timezone noted
- **API:** ISO 8601 format (UTC)

---

## 🔄 Timeline in Postmortems

The timeline is a key component of AI-generated postmortems:

1. **Automatic population** from tracked events
2. **AI gap-filling** based on log analysis
3. **Manual refinement** in postmortem editor

See [Postmortems](./postmortems.md) for more details.

---

## ⏱️ Duration Calculations

### Time to Acknowledge (TTA)

Time from trigger to first acknowledgement:

```
TTA = acknowledged_at - triggered_at
```

### Time to Resolve (TTR/MTTR)

Time from trigger to resolution:

```
TTR = resolved_at - triggered_at
```

### Time to Context

Time from trigger to context card delivery:

```
TTC = context_delivered_at - triggered_at
```

These metrics feed into [Analytics](./analytics.md).

---

## 🐛 Troubleshooting

### Missing Events

**Cause:** Events from unintegrated sources

**Solution:** Add manual events or configure additional integrations

### Out-of-Order Events

**Cause:** Clock skew or delayed webhooks

**Solution:** Events are sorted by timestamp; adjust if needed

### Duplicate Events

**Cause:** Multiple webhook deliveries

**Solution:** De-duplication built in; report if persists

---

## 📚 Related Documentation

- [Context Cards](./context-cards.md) - Timeline in cards
- [Postmortems](./postmortems.md) - Timeline in reports
- [Analytics](./analytics.md) - Duration metrics

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or open an issue on GitHub.*
