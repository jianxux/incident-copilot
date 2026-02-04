# 🔔 PagerDuty Integration

PagerDuty is the primary alert source for Incident Copilot. When incidents are triggered in PagerDuty, context cards are automatically generated and delivered to your notification channel.

---

## 📋 Prerequisites

- [ ] PagerDuty account with Admin or Manager role
- [ ] Access to the service(s) you want to monitor
- [ ] Incident Copilot running and accessible via HTTPS

---

## 🔧 Step-by-Step Setup

### Step 1: Create a PagerDuty API Key

1. Log in to your PagerDuty account
2. Navigate to **Integrations** → **API Access Keys**
3. Click **Create New API Key**
4. Configure:
   - **Description:** `Incident Copilot`
   - **API Key Type:** Select **Read-only** (recommended)
5. Click **Create Key**
6. ⚠️ **Copy the API key immediately** - you won't see it again!
7. Add to your `.env`:
   ```bash
   PAGERDUTY_API_KEY=your-api-key-here
   ```

### Step 2: Configure the Webhook

1. Go to **Services** → Select the service you want to monitor
2. Click the **Integrations** tab
3. Click **Add Integration**
4. Search for **Generic Webhook (v3)** and select it
5. Configure the webhook:
   - **Name:** `Incident Copilot`
   - **Endpoint URL:** `https://your-domain.com/webhooks/pagerduty`
6. Under **Event Subscriptions**, enable:
   - ✅ `incident.triggered` (required)
   - ☐ `incident.acknowledged` (optional)
   - ☐ `incident.resolved` (optional)
7. Click **Save Integration**
8. ⚠️ **Copy the Signing Secret** shown after saving
9. Add to your `.env`:
   ```bash
   PAGERDUTY_WEBHOOK_SECRET=your-signing-secret
   ```

### Step 3: Restart Incident Copilot

```bash
docker-compose restart
```

---

## ✅ Testing the Integration

### Verify API Key

```bash
curl -X GET "https://api.pagerduty.com/abilities" \
  -H "Authorization: Token token=$PAGERDUTY_API_KEY" \
  -H "Accept: application/vnd.pagerduty+json;version=2"
```

### Trigger a Test Incident

1. In PagerDuty, go to your service
2. Click **New Incident**
3. Fill in a test title and create
4. Check your Slack/Teams channel for the context card
5. **Resolve the incident** when done

---

## 🔐 Required Permissions

| Permission | Required | Purpose |
|------------|----------|---------|
| Read | ✅ Yes | Fetch incident details |
| Write | ❌ No | Not needed |

---

## 🔑 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `PAGERDUTY_API_KEY` | ✅ | API key for fetching details |
| `PAGERDUTY_WEBHOOK_SECRET` | ✅ | Webhook signing secret |

---

## 🐛 Troubleshooting

### Webhook Not Receiving Events

- Verify webhook URL is correct and HTTPS
- Check PagerDuty webhook delivery logs
- Ensure server is publicly accessible
- Check firewall/IP whitelist settings

### Invalid Signature Errors

- Re-copy the signing secret from PagerDuty
- Ensure no extra whitespace in `.env`
- Restart the application after changes

---

## 📚 Additional Resources

- [PagerDuty Webhook Documentation](https://developer.pagerduty.com/docs/webhooks/v3-overview/)
- [Opsgenie Integration](./opsgenie.md) (alternative)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md)*
