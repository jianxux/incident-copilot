# 💼 Microsoft Teams Integration

Microsoft Teams is supported as an alternative or addition to Slack for delivering context cards via Incoming Webhooks.

---

## 📋 Prerequisites

- [ ] Microsoft Teams workspace
- [ ] Permission to add connectors to channels
- [ ] Incident Copilot running and configured

---

## 🔧 Step-by-Step Setup

### Step 1: Create an Incoming Webhook

1. Open Microsoft Teams
2. Navigate to the channel for incident notifications
3. Click `...` → **Connectors** (or **Manage channel** → **Connectors**)
4. Find **Incoming Webhook** and click **Configure**
5. Configure:
   - **Name:** `Incident Copilot`
   - **Icon:** Upload custom icon (optional)
6. Click **Create**
7. ⚠️ **Copy the Webhook URL** (very long!)

### Step 2: Configure Environment Variables

```bash
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/your-long-url
NOTIFICATION_PROVIDER=teams  # or 'both' for Slack + Teams
```

### Step 3: Restart Incident Copilot

```bash
docker-compose restart
```

---

## ✅ Testing the Integration

### Test Webhook

```bash
curl -X POST "$TEAMS_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"@type":"MessageCard","summary":"Test","text":"🧪 Test from Incident Copilot"}'
```

---

## 🔑 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TEAMS_WEBHOOK_URL` | ✅ | Incoming Webhook URL |
| `NOTIFICATION_PROVIDER` | ✅ | Set to `teams` or `both` |

---

## 🔄 Using Both Slack and Teams

```bash
NOTIFICATION_PROVIDER=both
SLACK_BOT_TOKEN=xoxb-your-token
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/...
```

---

## 🐛 Troubleshooting

### Webhook Not Responding

- Test webhook URL manually
- Verify URL hasn't expired/been deleted
- Check URL is complete (very long)

### Message Format Error

- Check server logs for payload details
- Verify Adaptive Card JSON is valid

---

## 📚 Additional Resources

- [Teams Webhooks Documentation](https://docs.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/)
- [Slack Integration](./slack.md) (alternative)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md)*
