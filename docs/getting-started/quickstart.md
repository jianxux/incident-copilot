# Quickstart

Get Incident Copilot running locally with Docker Compose.

## Prerequisites

- Docker + Docker Compose
- A Slack workspace (optional, but recommended)
- At least one alert source (PagerDuty or Opsgenie)

## 1) Configure environment variables

Create a `.env` file at the repo root:

```bash
cp .env.example .env 2>/dev/null || true
```

Minimum recommended variables:

```bash
# Core
APP_URL=http://localhost:8000
SECRET_KEY=change-me

# Notifications (Slack)
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
SLACK_DEFAULT_CHANNEL=#incidents

# Alert source (pick one)
PAGERDUTY_WEBHOOK_SECRET=...
# or
OPSGENIE_WEBHOOK_SECRET=...

# Logs (pick one)
DATADOG_API_KEY=...
DATADOG_APP_KEY=...
# or set LOG_PROVIDER=cloudwatch/loki/splunk and configure that provider

# AI summary
ANTHROPIC_API_KEY=...
AI_MODEL=claude-3-haiku-20240307
```

!!! tip
    You can run without AI by leaving `ANTHROPIC_API_KEY` empty, but summaries will be limited/disabled depending on your deployment configuration.

## 2) Start services

```bash
docker compose up --build
```

The API should be available at:

- `http://localhost:8000`

## 3) Verify health

```bash
curl -s http://localhost:8000/health || true
curl -s http://localhost:8000/healthz || true
```

## 4) Add an alert webhook

- **PagerDuty** → see [PagerDuty integration](../integrations/pagerduty.md)
- **Opsgenie** → configure an Opsgenie alert webhook and set `OPSGENIE_WEBHOOK_SECRET`

## 5) Confirm notifications

Trigger a test alert and ensure the Slack/Teams message shows:

- service name
- recent deploy info
- log links/snippets
- AI summary

---

## Next

- [Installation (Python)](installation.md)
- [Configuration](../configuration.md)
- [Architecture](../architecture.md)
