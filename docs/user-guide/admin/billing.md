# 💳 Billing & Usage

Understand Incident Copilot plans and usage tracking.

---

## 📊 Plans

### Self-Hosted (Free)

Incident Copilot is **open source** and free to self-host. You pay for:
- Your infrastructure (hosting, database)
- Third-party API costs (Anthropic, OpenAI)

### API Costs

Approximate costs per incident:

| Service | Cost per Incident |
|---------|-------------------|
| Claude API (AI summary) | ~$0.01-0.05 |
| OpenAI Embeddings | ~$0.001 (optional) |

For 100 incidents/month: **~$1-5** in API costs.

---

## 📈 Usage Tracking

View your usage at **Settings** → **Usage**:

```
┌─────────────────────────────────────┐
│  📊 Usage - January 2025            │
├─────────────────────────────────────┤
│  Incidents processed: 147           │
│  Context cards sent: 145            │
│  AI summaries generated: 142        │
│  Postmortems created: 23            │
│                                     │
│  API Costs (estimated):             │
│  • Anthropic: $4.20                 │
│  • OpenAI: $0.15                    │
└─────────────────────────────────────┘
```

---

## 📚 Related Documentation

- [Tenant Setup](./tenant-setup.md)
- [Analytics](../features/analytics.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
