# 🔔 Opsgenie Integration

Opsgenie is an alternative alert source for Incident Copilot.

---

## 🔧 Setup

### Step 1: Create API Key

1. Go to **Settings** → **API key management**
2. Create new API integration
3. Add to `.env`:
   ```bash
   OPSGENIE_API_KEY=your-api-key
   ```

### Step 2: Configure Webhook

1. Go to **Settings** → **Integrations**
2. Add **Webhook** integration
3. Set URL: `https://your-domain.com/webhooks/opsgenie`
4. Add signing secret to `.env`:
   ```bash
   OPSGENIE_WEBHOOK_SECRET=your-secret
   ```

---

## ✅ Testing

```bash
incident-copilot test-integration opsgenie
```

---

## 📚 Related Documentation

- [PagerDuty Integration](./pagerduty.md)
- [Getting Started](../getting-started.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
