# 🔔 PagerDuty Integration

PagerDuty is the primary alert source for Incident Copilot. When incidents trigger, context cards are automatically generated.

---

## 🔧 Setup

### Step 1: Create API Key

1. Navigate to **Integrations** → **API Access Keys**
2. Click **Create New API Key**
3. Add to `.env`:
   ```bash
   PAGERDUTY_API_KEY=your-api-key
   ```

### Step 2: Configure Webhook

1. Go to **Services** → Select service → **Integrations**
2. Add **Generic Webhook (v3)**
3. Set URL: `https://your-domain.com/webhooks/pagerduty`
4. Copy signing secret to `.env`:
   ```bash
   PAGERDUTY_WEBHOOK_SECRET=your-secret
   ```

---

## ✅ Testing

```bash
incident-copilot test-integration pagerduty
```

---

## 📚 Related Documentation

- [Opsgenie Integration](./opsgenie.md)
- [Getting Started](../getting-started.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
