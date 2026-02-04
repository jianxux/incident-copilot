# 🃏 Context Cards

Context Cards are the core output of Incident Copilot — a rich summary delivered to your notification channel when an incident fires.

---

## 📋 What's in a Context Card?

When an incident triggers, you receive a card containing:

```
┌─────────────────────────────────────────┐
│ 🟠 payments-api: High Error Rate        │
├─────────────────────────────────────────┤
│ Severity: HIGH  |  Triggered: 02:47 AM  │
├─────────────────────────────────────────┤
│ 🚀 Recent Deployments:                  │
│ • abc1234 by @sarah - Fix retry logic   │
│ • def5678 by @mike - Update deps        │
├─────────────────────────────────────────┤
│ 📋 Top Issues (AI Analysis):            │
│ • ConnectionTimeout to stripe-api (847x)│
│ • Retry limit exceeded (612x)           │
│                                         │
│ The service is experiencing timeouts    │
│ when connecting to Stripe's API. This   │
│ started after the recent deployment...  │
├─────────────────────────────────────────┤
│ 🔍 Similar Past Incidents:              │
│ • Stripe outage (2024-01-10) - 92% match│
├─────────────────────────────────────────┤
│ 👥 On-Call: @sarah | 📖 Runbook         │
│ Context assembled in 3420ms             │
└─────────────────────────────────────────┘
```

---

## 📊 Card Sections

### Header
- **Service name** and incident title
- **Severity** level with color indicator
- **Trigger time**

### Recent Deployments
- Last 3-5 commits/deployments
- Author and commit message
- Links to commits

### Error Analysis (AI)
- Top error patterns with counts
- AI-generated summary
- Likely root cause hypothesis

### Similar Incidents
- Past incidents with similar patterns
- Similarity score
- How they were resolved

### Quick Actions
- On-call contact
- Runbook link
- Service dashboard

---

## ⚙️ Customization

### Configure Sections

```bash
# Show/hide sections
CONTEXT_CARD_SHOW_DEPLOYMENTS=true
CONTEXT_CARD_SHOW_AI_SUMMARY=true
CONTEXT_CARD_SHOW_SIMILAR=true
CONTEXT_CARD_SHOW_RUNBOOK=true
```

### Deployment Count

```bash
DEPLOYMENTS_TO_SHOW=5  # Default: 3
```

### Time Window

```bash
LOG_LOOKBACK_MINUTES=30  # Default: 15
DEPLOYMENT_LOOKBACK_HOURS=24  # Default: 12
```

---

## ⏱️ Performance

Target delivery time: **<10 seconds**

Typical breakdown:
| Component | Time |
|-----------|------|
| Webhook receipt | <100ms |
| Fetch deployments | 500-1500ms |
| Fetch logs | 1000-2000ms |
| AI summarization | 2000-4000ms |
| Slack delivery | 200-500ms |

---

## 📚 Related Documentation

- [AI Analysis](./ai-analysis.md)
- [Similar Incidents](./similar-incidents.md)
- [Slack Integration](../integrations/slack.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
