# 💬 Slack Integration

Slack is the primary notification channel for Incident Copilot. Context cards are delivered as rich Block Kit messages.

---

## 📋 Prerequisites

- [ ] Slack workspace with permission to install apps
- [ ] Admin access to create a Slack app
- [ ] Incident Copilot running and configured

---

## 🔧 Step-by-Step Setup

### Step 1: Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App** → **From scratch**
3. Configure:
   - **App Name:** `Incident Copilot`
   - **Workspace:** Select your workspace
4. Click **Create App**

### Step 2: Configure Bot Permissions

1. Go to **OAuth & Permissions**
2. Under **Bot Token Scopes**, add:
   - `chat:write` - Send messages
   - `chat:write.public` - Send to public channels without invite
3. Click **Install to Workspace**
4. ⚠️ **Copy the Bot User OAuth Token** (starts with `xoxb-`)

### Step 3: Configure Environment Variables

```bash
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_DEFAULT_CHANNEL=#incidents
NOTIFICATION_PROVIDER=slack
```

### Step 4: Restart Incident Copilot

```bash
docker-compose restart
```

---

## ✅ Testing the Integration

### Verify Bot Token

```bash
curl -X POST "https://slack.com/api/auth.test" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN"
```

### Test Message Delivery

```bash
curl -X POST "https://slack.com/api/chat.postMessage" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel": "#incidents", "text": "🧪 Test from Incident Copilot"}'
```

---

## 🔐 Required Scopes

| Scope | Purpose |
|-------|---------|
| `chat:write` | Send messages to channels bot is in |
| `chat:write.public` | Send to public channels without invite |

---

## 🔑 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SLACK_BOT_TOKEN` | ✅ | Bot OAuth token |
| `SLACK_SIGNING_SECRET` | ⚡ Optional | For slash commands |
| `SLACK_DEFAULT_CHANNEL` | ✅ | Default channel |
| `NOTIFICATION_PROVIDER` | ✅ | Set to `slack` or `both` |

---

## 🐛 Troubleshooting

### channel_not_found

- Verify channel name (including `#`)
- Use channel ID instead of name

### not_in_channel

- Add `chat:write.public` scope, OR
- Invite bot: `/invite @Incident Copilot`

### invalid_auth

- Regenerate bot token
- Check token starts with `xoxb-`

---

## 📚 Additional Resources

- [Slack API Documentation](https://api.slack.com/docs)
- [Microsoft Teams Integration](./teams.md) (alternative)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md)*
