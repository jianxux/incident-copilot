# 💼 Microsoft Teams Integration

Deliver context cards to Microsoft Teams channels.

---

## 🔧 Setup

### Create Incoming Webhook

1. In Teams, go to the channel
2. Click **...** → **Connectors**
3. Add **Incoming Webhook**
4. Name it "Incident Copilot" and copy URL
5. Add to `.env`:
   ```bash
   NOTIFICATION_PROVIDER=teams
   TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/...
   ```

---

## 📍 Multiple Channels

```bash
TEAMS_CHANNEL_WEBHOOKS='{
  "payments-api": "https://outlook.office.com/.../payments",
  "auth-service": "https://outlook.office.com/.../auth",
  "default": "https://outlook.office.com/.../incidents"
}'
```

---

## 🔄 Use Both Slack and Teams

```bash
NOTIFICATION_PROVIDER=both
SLACK_BOT_TOKEN=xoxb-xxx
TEAMS_WEBHOOK_URL=https://outlook.office.com/...
```

---

## 📚 Related Documentation

- [Slack Integration](./slack.md)
- [Context Cards](../features/context-cards.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
