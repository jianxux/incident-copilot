# 💬 Slack Integration

Slack is the primary notification channel for Incident Copilot. Context cards are delivered to Slack channels when incidents are triggered.

---

## Overview

| Feature | Status |
|---------|--------|
| Context card delivery | ✅ Supported |
| Slash commands | ✅ Supported |
| Interactive buttons | ✅ Supported |
| Thread replies | ✅ Supported |
| Scheduled reports | ✅ Supported |

---

## Prerequisites

- Slack workspace with admin access (to create apps)
- Incident Copilot running and accessible

---

## 🔧 Setup

### Step 1: Create Slack App

1. Go to [Slack API: Your Apps](https://api.slack.com/apps)
2. Click **Create New App**
3. Choose **From scratch**
4. Configure:
   - **App Name**: `Incident Copilot`
   - **Workspace**: Select your workspace
5. Click **Create App**

![Create Slack App](../images/slack-app-create-placeholder.png)
*Screenshot: Creating a new Slack app*

### Step 2: Configure Bot Permissions

1. In your app settings, go to **OAuth & Permissions**
2. Scroll to **Scopes** → **Bot Token Scopes**
3. Add these scopes:

| Scope | Purpose |
|-------|---------|
| `chat:write` | Post context cards to channels |
| `chat:write.public` | Post to channels without joining |
| `users:read` | Look up user info for mentions |
| `channels:read` | List channels for routing |
| `groups:read` | List private channels (if needed) |

![Slack Permissions](../images/slack-permissions-placeholder.png)
*Screenshot: Adding bot token scopes*

### Step 3: Install to Workspace

1. Scroll to **OAuth Tokens for Your Workspace**
2. Click **Install to Workspace**
3. Review permissions and click **Allow**
4. Copy the **Bot User OAuth Token** (starts with `xoxb-`)

![Slack Install](../images/slack-install-placeholder.png)
*Screenshot: Installing app and copying token*

Add to your `.env`:
```bash
SLACK_BOT_TOKEN=xoxb-your-token-here
SLACK_DEFAULT_CHANNEL=#incidents
NOTIFICATION_PROVIDER=slack
```

### Step 4: Invite Bot to Channel

In Slack:
```
/invite @Incident Copilot
```

Or use the bot's `chat:write.public` scope to post without joining.

---

## ⚙️ Configuration Options

### Basic Configuration

```bash
# Required
SLACK_BOT_TOKEN=xoxb-your-token
NOTIFICATION_PROVIDER=slack

# Optional (default shown)
SLACK_DEFAULT_CHANNEL=#incidents
```

### Channel Routing

Route different services to different channels:

```bash
SLACK_CHANNEL_ROUTING='{
  "payments-api": "#payments-alerts",
  "auth-service": "#auth-alerts",
  "checkout": "#checkout-alerts",
  "default": "#incidents"
}'
```

### Severity-Based Routing

Route by severity:

```bash
SLACK_SEVERITY_ROUTING='{
  "critical": "#critical-incidents",
  "high": "#high-priority",
  "default": "#incidents"
}'
```

---

## 🎛️ Slash Commands (Optional)

Enable `/incident` commands in Slack.

### Setup

1. In your Slack app, go to **Slash Commands**
2. Click **Create New Command**
3. Configure:
   - **Command**: `/incident`
   - **Request URL**: `https://your-domain.com/slack/commands`
   - **Short Description**: `Incident Copilot commands`
4. Save

### Available Commands

| Command | Description |
|---------|-------------|
| `/incident status` | Show current active incidents |
| `/incident oncall` | Show current on-call engineer |
| `/incident report daily` | Generate daily report |
| `/incident search <query>` | Search past incidents |

---

## 🔔 Interactive Components (Optional)

Enable buttons and actions in context cards.

### Setup

1. In your Slack app, go to **Interactivity & Shortcuts**
2. Enable **Interactivity**
3. Set **Request URL**: `https://your-domain.com/slack/interactions`
4. Save

### Available Actions

Context cards include interactive buttons:
- **Acknowledge** - Acknowledge the incident in PagerDuty
- **View Logs** - Direct link to log provider
- **View Dashboard** - Link to metrics dashboard
- **Create Postmortem** - Generate AI postmortem

---

## 🔒 Request Verification

Verify incoming Slack requests for security.

### Setup

1. In your Slack app, go to **Basic Information**
2. Scroll to **App Credentials**
3. Copy the **Signing Secret**

Add to your `.env`:
```bash
SLACK_SIGNING_SECRET=your-signing-secret
```

Incident Copilot will verify all incoming Slack requests using this secret.

---

## ✅ Testing

### Validate Configuration

```bash
incident-copilot validate
```

### Test Slack Connection

```bash
incident-copilot test-integration slack
```

### Test Post to Channel

```bash
# Using curl
curl -X POST https://slack.com/api/chat.postMessage \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel": "#incidents", "text": "Test from Incident Copilot"}'
```

---

## 🐛 Troubleshooting

### "channel_not_found" Error

**Cause**: Channel name is wrong or bot isn't in the channel

**Solutions**:
1. Use channel ID instead of name (starts with `C`)
2. Invite bot: `/invite @Incident Copilot`
3. Check channel name spelling (including `#`)

### "not_in_channel" Error

**Solution**: Invite the bot to the channel:
```
/invite @Incident Copilot
```

Or add `chat:write.public` scope to post without joining.

### "invalid_auth" Error

**Causes**:
- Token is expired or revoked
- Token has typo or extra whitespace

**Solution**: Regenerate the Bot User OAuth Token and update `.env`

### "missing_scope" Error

**Solution**: Add the required scope in **OAuth & Permissions**, then reinstall the app.

### Messages Not Appearing

1. Check application logs for errors
2. Verify `NOTIFICATION_PROVIDER=slack`
3. Test with: `incident-copilot test-integration slack`
4. Check bot is in the channel

---

## 📚 Related Documentation

- [Microsoft Teams Integration](./teams.md) - Alternative notification channel
- [Scheduled Reports](../features/scheduled-reports.md) - Report delivery to Slack
- [Configuration Reference](../configuration.md) - All config options
- [Troubleshooting](../troubleshooting.md) - General troubleshooting

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or [FAQ](../faq.md).*
