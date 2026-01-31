# Incident Copilot 🚨

Context-aware incident copilot for on-call engineers. Automatically assembles relevant context when alerts fire, reducing MTTR by 30-50%.

## What It Does

When a PagerDuty alert fires, Incident Copilot:

1. **Fetches recent deployments** from GitHub
2. **Pulls error logs** from Datadog
3. **Summarizes issues** using AI (Claude)
4. **Delivers a context card** to Slack within 10 seconds

## Quick Start

### 1. Clone and configure

```bash
cd incident-copilot
cp .env.example .env
# Edit .env with your API keys
```

### 2. Run locally

```bash
# Install dependencies
pip install -e ".[dev]"

# Run the server
uvicorn src.main:app --reload

# Or with Docker
docker-compose up
```

### 3. Configure PagerDuty webhook

In PagerDuty:
1. Go to **Services** → Select your service → **Integrations**
2. Add a **Generic Webhook (v3)**
3. Set URL to: `https://your-domain.com/webhooks/pagerduty`
4. Copy the signing secret to your `.env`

### 4. Create Slack App

1. Create a new Slack app at https://api.slack.com/apps
2. Add Bot Token Scopes: `chat:write`, `chat:write.public`
3. Install to workspace and copy Bot OAuth Token to `.env`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/webhooks/pagerduty` | POST | PagerDuty webhook receiver |
| `/webhooks/health` | GET | Webhook health check |

## Project Structure

```
incident-copilot/
├── src/
│   ├── api/           # FastAPI routes
│   ├── integrations/  # PagerDuty, GitHub, Datadog, Slack adapters
│   ├── ai/            # Log summarization with Claude
│   ├── config.py      # Settings management
│   ├── models.py      # Pydantic models
│   ├── orchestrator.py # Core context assembly logic
│   └── main.py        # FastAPI app entry point
├── tests/
├── docker-compose.yml
└── pyproject.toml
```

## Context Card Example

```
┌─────────────────────────────────────────┐
│ 🟠 payments-api: High Error Rate        │
├─────────────────────────────────────────┤
│ Severity: HIGH  |  Triggered: 02:47     │
├─────────────────────────────────────────┤
│ 🚀 Recent Deployments:                  │
│ • abc1234 by @sarah - Fix retry logic   │
├─────────────────────────────────────────┤
│ 📋 Top Issues (AI Analysis):            │
│ • ConnectionTimeout to stripe-api (847x)│
│ • Retry limit exceeded (612x)           │
│                                         │
│ The service is experiencing timeouts    │
│ when connecting to Stripe's API...      │
├─────────────────────────────────────────┤
│ Owners: @sarah, @mike  |  📖 Runbook    │
│ Context assembled in 3420ms             │
└─────────────────────────────────────────┘
```

## Configuration

All configuration via environment variables:

| Variable | Description |
|----------|-------------|
| `PAGERDUTY_API_KEY` | PagerDuty API key |
| `PAGERDUTY_WEBHOOK_SECRET` | Webhook signing secret |
| `GITHUB_TOKEN` | GitHub personal access token |
| `GITHUB_ORG` | GitHub organization name |
| `DATADOG_API_KEY` | Datadog API key |
| `DATADOG_APP_KEY` | Datadog application key |
| `SLACK_BOT_TOKEN` | Slack bot OAuth token |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude |

## Roadmap

- [x] PagerDuty webhook integration
- [x] GitHub recent deploys
- [x] Datadog logs fetching
- [x] AI log summarization
- [x] Slack context card delivery
- [ ] Past incident similarity search
- [ ] Runbook auto-linking
- [ ] Opsgenie support
- [ ] CloudWatch support
- [ ] Web UI

## License

MIT
