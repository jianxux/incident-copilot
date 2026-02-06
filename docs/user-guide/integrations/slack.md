# 💬 Slack Integration

Deliver context cards to Slack channels.

---

## 🔧 Setup

### Create Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Create new app → From scratch
3. Add **Bot Token Scopes**:
   - `chat:write`
   - `chat:write.public`
4. Install to workspace
5. Copy Bot Token to `.env`:
   ```bash
   NOTIFICATION_PROVIDER=slack
   SLACK_BOT_TOKEN=xoxb-your-token
   SLACK_DEFAULT_CHANNEL=#incidents
   ```

---

## 📍 Channel Routing

Route incidents to different channels:

```bash
SLACK_CHANNEL_ROUTING='{
  "payments-api": "#payments-alerts",
  "auth-service": "#auth-alerts",
  "default": "#incidents"
}'
```

---

## ✅ Testing

```bash
incident-copilot test-integration slack
incident-copilot send-test -c "#test-channel"
```

---

## 📚 Related Documentation

- [Teams Integration](./teams.md)
- [Context Cards](../features/context-cards.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
