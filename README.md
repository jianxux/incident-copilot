# Incident Copilot 🚨

Context-aware incident copilot for on-call engineers. Automatically assembles relevant context when alerts fire, reducing MTTR by 30-50%.

## What It Does

When a PagerDuty alert fires, Incident Copilot:

1. **Fetches recent deployments** from GitHub
2. **Pulls error logs** from Datadog or CloudWatch
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

### 3b. Configure Opsgenie webhook (alternative)

In Opsgenie:
1. Go to **Settings** → **Integrations** → **Add Integration**
2. Select **Webhook** integration
3. Configure the webhook:
   - **Webhook URL**: `https://your-domain.com/webhooks/opsgenie`
   - **Add Header**: `X-OpsGenie-Signature` for signature verification
4. Select alert actions to trigger: **Create** (required)
5. Copy the **API Key** (GenieKey) from your Opsgenie API Integration

#### Required Opsgenie API Scopes

If using the Opsgenie API for enrichment (recommended):
- `Read` scope on Alerts
- `Read` scope on Alert Notes (optional)

#### Environment Variables

```bash
OPSGENIE_API_KEY=your-geniekey-here
OPSGENIE_WEBHOOK_SECRET=your-webhook-secret
OPSGENIE_REGION=us  # or 'eu' for EU region
```

### 4. Create Slack App

1. Create a new Slack app at https://api.slack.com/apps
2. Add Bot Token Scopes: `chat:write`, `chat:write.public`
3. Install to workspace and copy Bot OAuth Token to `.env`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/webhooks/pagerduty` | POST | PagerDuty webhook receiver |
| `/webhooks/opsgenie` | POST | Opsgenie webhook receiver |
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
| `LOG_PROVIDER` | Log provider: `datadog` (default) or `cloudwatch` |
| `PAGERDUTY_API_KEY` | PagerDuty API key |
| `PAGERDUTY_WEBHOOK_SECRET` | Webhook signing secret |
| `OPSGENIE_API_KEY` | Opsgenie API key (GenieKey) |
| `OPSGENIE_WEBHOOK_SECRET` | Opsgenie webhook signing secret |
| `OPSGENIE_REGION` | Opsgenie region (`us` or `eu`) |
| `GITHUB_TOKEN` | GitHub personal access token |
| `GITHUB_ORG` | GitHub organization name |
| `DATADOG_API_KEY` | Datadog API key |
| `DATADOG_APP_KEY` | Datadog application key |
| `AWS_REGION` | AWS region for CloudWatch |
| `AWS_ACCESS_KEY_ID` | AWS access key (optional, uses boto3 defaults) |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key |
| `CLOUDWATCH_LOG_GROUP_MAP` | JSON mapping of service to log groups |
| `SLACK_BOT_TOKEN` | Slack bot OAuth token |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude |

## AWS CloudWatch Integration

Incident Copilot supports AWS CloudWatch Logs as an alternative to Datadog.

### Setup

1. Set `LOG_PROVIDER=cloudwatch` in your `.env`
2. Configure AWS credentials:

```bash
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
```

Or use IAM roles/instance profiles (boto3 will auto-detect).

3. (Optional) Map services to specific log groups:

```bash
CLOUDWATCH_LOG_GROUP_MAP='{"payments-api": "/aws/lambda/payments,/ecs/payments"}'
```

Without explicit mapping, it tries common conventions:
- `/aws/lambda/{service-name}`
- `/ecs/{service-name}`
- `/aws/ecs/{service-name}`
- `/application/{service-name}`

### Required IAM Permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:FilterLogEvents",
        "logs:DescribeLogGroups",
        "logs:StartQuery",
        "logs:GetQueryResults"
      ],
      "Resource": "arn:aws:logs:*:*:log-group:*"
    }
  ]
}
```

### Features

- Fetch recent error/warning logs from multiple log groups
- Filter by time window (default: last 15 minutes)
- CloudWatch Logs Insights queries for structured searches
- Same output format as Datadog for seamless AI summarization

## Roadmap

- [x] PagerDuty webhook integration
- [x] GitHub recent deploys
- [x] Datadog logs fetching
- [x] AI log summarization
- [x] Slack context card delivery
- [x] CloudWatch support
- [ ] Past incident similarity search
- [ ] Runbook auto-linking
- [x] Opsgenie support
- [ ] Web UI

## License

MIT
