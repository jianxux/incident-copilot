# 📅 Incident Timeline

View the complete history of an incident from trigger to resolution.

---

## 📋 Timeline Events

The timeline tracks:

| Event | Description |
|-------|-------------|
| `triggered` | Alert fired |
| `context_card_sent` | Context card delivered |
| `acknowledged` | Responder acknowledged |
| `escalated` | Incident escalated |
| `resolved` | Incident resolved |

---

## 📊 Example Timeline

```
02:47:00  🔴 Incident triggered
          payments-api: High Error Rate

02:47:06  📬 Context card delivered
          Sent to #incidents (3.4s assembly time)

02:49:12  ✋ Acknowledged by @sarah
          Via PagerDuty mobile

02:52:00  🔍 Investigation note added
          "Checking Stripe status page"

03:05:00  ✅ Resolved by @sarah
          Resolution: "Stripe API recovered"
```

---

## 🔧 API Access

```bash
GET /api/incidents/{incident_id}/timeline

Response:
{
  "events": [
    {
      "timestamp": "2025-01-15T02:47:00Z",
      "event_type": "triggered",
      "actor": "pagerduty"
    },
    {
      "timestamp": "2025-01-15T02:47:06Z",
      "event_type": "context_card_sent",
      "details": {"channel": "#incidents", "assembly_time_ms": 3420}
    }
  ]
}
```

---

## 📚 Related Documentation

- [Context Cards](./context-cards.md)
- [Postmortems](./postmortems.md)
- [Analytics](./analytics.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
