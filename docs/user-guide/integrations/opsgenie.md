# 🔔 Opsgenie Integration

Opsgenie is an alternative alerting platform to PagerDuty. Incident Copilot supports Opsgenie webhooks for triggering context card generation.

---

## 📋 Prerequisites

- [ ] Opsgenie account with Admin access
- [ ] API Integration created or ability to create one
- [ ] Incident Copilot running and accessible via HTTPS

---

## 🔧 Step-by-Step Setup

### Step 1: Create an API Integration

1. Log in to Opsgenie
2. Go to **Settings** → **Integrations**
3. Click **Add Integration** → Select **API**
4. Configure:
   - **Name:** `Incident Copilot API`
   - **Permissions:** Enable **Read** only
5. Click **Save Integration**
6. ⚠️ **Copy the API Key (GenieKey)**
7. Add to your `.env`:
   ```bash
   OPSGENIE_API_KEY=your-geniekey-here
   OPSGENIE_REGION=us  # or 'eu'
   ```

### Step 2: Create a Webhook Integration

1. Go to **Settings** → **Integrations**
2. Click **Add Integration** → Select **Webhook**
3. Configure:
   - **Name:** `Incident Copilot Webhook`
   - **Webhook URL:** `https://your-domain.com/webhooks/opsgenie`
   - **Alert Actions:** Enable **Create**
4. Click **Save Integration**

### Step 3: Restart Incident Copilot

```bash
docker-compose restart
```

---

## ✅ Testing the Integration

### Verify API Key

```bash
# US region
curl -X GET "https://api.opsgenie.com/v2/alerts?limit=1" \
  -H "Authorization: GenieKey $OPSGENIE_API_KEY"

# EU region
curl -X GET "https://api.eu.opsgenie.com/v2/alerts?limit=1" \
  -H "Authorization: GenieKey $OPSGENIE_API_KEY"
```

### Trigger a Test Alert

1. In Opsgenie, go to **Alerts** → **Create Alert**
2. Create a test alert with a service tag
3. Check your Slack/Teams channel for the context card

---

## 🔐 Required Permissions

| Permission | Required | Purpose |
|------------|----------|---------|
| Read | ✅ Yes | Fetch alert details |
| Create/Update/Delete | ❌ No | Not needed |

---

## 🔑 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPSGENIE_API_KEY` | ✅ | GenieKey for API access |
| `OPSGENIE_WEBHOOK_SECRET` | ⚡ Recommended | Webhook signing secret |
| `OPSGENIE_REGION` | ✅ | Region: `us` or `eu` |

---

## 🌍 Region Configuration

| Region | API Endpoint |
|--------|--------------|
| `us` | `api.opsgenie.com` |
| `eu` | `api.eu.opsgenie.com` |

---

## 🏷️ Priority Mapping

| Opsgenie Priority | Incident Copilot Severity |
|-------------------|---------------------------|
| P1 | 🔴 Critical |
| P2 | 🟠 High |
| P3 | 🟡 Medium |
| P4 | 🟢 Low |
| P5 | ℹ️ Info |

---

## 🐛 Troubleshooting

### Authentication Failed

- Verify API key is correct (GenieKey format)
- Check region setting matches your Opsgenie URL
- Ensure API integration has Read permission

### Missing Service Name

- Add `service:name` tags to your alerts
- Configure your monitoring to include service tags

---

## 📚 Additional Resources

- [Opsgenie API Documentation](https://docs.opsgenie.com/docs/api-overview)
- [PagerDuty Integration](./pagerduty.md) (alternative)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md)*
