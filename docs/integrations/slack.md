# Slack

Incident Copilot posts incident context cards to Slack and can optionally support OAuth-based “Connect Slack”.

## Create a Slack App

1. Go to <https://api.slack.com/apps>
2. **Create New App** → “From scratch”
3. Choose your workspace

## Configure OAuth & Permissions

### Bot token scopes

Recommended scopes (adjust to your features):

- `chat:write`
- `chat:write.public` (if posting to channels the bot isn’t a member of)
- `channels:read` / `groups:read` (optional)

Install the app to your workspace to generate a **Bot User OAuth Token** (`xoxb-...`).

### Signing secret

Slack → **Basic Information** → **Signing Secret**.

## Set environment variables

```bash
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
SLACK_DEFAULT_CHANNEL=#incidents

# Optional OAuth connect
SLACK_OAUTH_CLIENT_ID=...
SLACK_OAUTH_CLIENT_SECRET=...
APP_URL=https://<your-app>
```

## Events / Interactivity (optional)

Depending on your deployment, you may want:

- **Interactivity & Shortcuts**: enable and set a Request URL
- **Event Subscriptions**: enable and set a Request URL

Example request URL:

```
https://<your-app>/webhooks/slack
```

!!! note
    If you only need outgoing notifications (no Slack events), you can keep Events disabled.

## Troubleshooting

- `invalid_auth`: wrong token or app not installed to the workspace.
- `channel_not_found`: bot not invited to channel, or missing `chat:write.public`.
