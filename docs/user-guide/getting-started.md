# Getting Started with Incident Copilot

This guide walks you through installing, configuring, and running Incident Copilot for the first time.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
   - [Docker (Recommended)](#docker-recommended)
   - [Local Development](#local-development)
   - [Kubernetes](#kubernetes)
3. [Quick Configuration](#quick-configuration)
4. [Your First Context Card](#your-first-context-card)
5. [Next Steps](#next-steps)

---

## Prerequisites

Before you begin, ensure you have:

### Required
- **Python 3.11+** (if running locally)
- **Docker & Docker Compose** (if using Docker)
- **A PagerDuty or Opsgenie account** with webhook access
- **A Slack workspace** with admin access to create apps

### Recommended
- **GitHub access** to the repositories for your services
- **Datadog account** or AWS CloudWatch access for logs
- **Anthropic API key** for AI-powered log summarization

### Accounts & API Keys

You'll need API keys from:

| Service | Required | Purpose |
|---------|----------|---------|
| PagerDuty or Opsgenie | ✅ Yes | Receive alert webhooks |
| Slack | ✅ Yes | Deliver context cards |
| GitHub or GitLab | Recommended | Fetch recent deployments |
| Datadog or CloudWatch | Recommended | Fetch error logs |
| Anthropic (Claude) | Recommended | AI log summarization |

---

## Installation

### Docker (Recommended)

The fastest way to get started is with Docker Compose.

#### 1. Clone the Repository

```bash
git clone https://github.com/your-org/incident-copilot.git
cd incident-copilot
```

#### 2. Create Configuration

```bash
cp .env.example .env
```

Edit `.env` with your API keys (see [Quick Configuration](#quick-configuration)).

#### 3. Start the Application

```bash
docker-compose up -d
```

#### 4. Verify It's Running

```bash
# Check container status
docker-compose ps

# Check health endpoint
curl http://localhost:8000/health
```

Expected output:
```json
{
  "status": "healthy",
  "checks": {
    "api": "ok",
    "database": "ok"
  }
}
```

![Docker Compose Running](./images/docker-compose-placeholder.png)
*Screenshot: Docker Compose showing healthy containers*

---

### Local Development

For development or testing without Docker.

#### 1. Clone and Set Up

```bash
git clone https://github.com/your-org/incident-copilot.git
cd incident-copilot

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"
```

#### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

#### 3. Run the Server

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

#### 4. Access the API

- **API Docs (Swagger)**: http://localhost:8000/docs
- **API Docs (ReDoc)**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

![Swagger UI](./images/swagger-ui-placeholder.png)
*Screenshot: Interactive API documentation at /docs*

---

### Kubernetes

For production deployments, use the included Helm chart.

#### 1. Add Required Secrets

Create a Kubernetes secret with your API keys:

```bash
kubectl create secret generic incident-copilot-secrets \
  --from-literal=pagerduty-api-key=xxx \
  --from-literal=pagerduty-webhook-secret=xxx \
  --from-literal=slack-bot-token=xoxb-xxx \
  --from-literal=github-token=ghp_xxx \
  --from-literal=datadog-api-key=xxx \
  --from-literal=datadog-app-key=xxx \
  --from-literal=anthropic-api-key=sk-ant-xxx
```

#### 2. Install with Helm

```bash
helm install incident-copilot ./helm/incident-copilot \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host=incident-copilot.example.com
```

#### 3. Verify Deployment

```bash
kubectl get pods -l app=incident-copilot
kubectl logs -l app=incident-copilot --tail=50
```

See [Kubernetes Deployment Guide](../deployment.md) for advanced configuration.

---

## Quick Configuration

The minimum configuration requires:

1. **An alerting source** (PagerDuty or Opsgenie)
2. **A notification destination** (Slack)

### Minimal `.env` Configuration

```bash
# =============================================================================
# REQUIRED: Alert Source (choose one)
# =============================================================================

# Option A: PagerDuty
PAGERDUTY_API_KEY=your-api-key
PAGERDUTY_WEBHOOK_SECRET=your-webhook-secret

# Option B: Opsgenie
# OPSGENIE_API_KEY=your-geniekey
# OPSGENIE_WEBHOOK_SECRET=your-webhook-secret
# OPSGENIE_REGION=us

# =============================================================================
# REQUIRED: Notification Destination
# =============================================================================

SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_DEFAULT_CHANNEL=#incidents
NOTIFICATION_PROVIDER=slack

# =============================================================================
# RECOMMENDED: Source Control
# =============================================================================

GITHUB_TOKEN=ghp_your-personal-access-token
GITHUB_ORG=your-organization

# =============================================================================
# RECOMMENDED: Log Provider
# =============================================================================

LOG_PROVIDER=datadog
DATADOG_API_KEY=your-api-key
DATADOG_APP_KEY=your-application-key
DATADOG_SITE=datadoghq.com

# =============================================================================
# RECOMMENDED: AI Summarization
# =============================================================================

ANTHROPIC_API_KEY=sk-ant-your-api-key
AI_MODEL=claude-3-haiku-20240307
```

### Service-to-Repository Mapping

By default, Incident Copilot assumes your GitHub repository name matches your service name:

- Service: `payments-api` → Repository: `your-org/payments-api`

For custom mappings:

```bash
SERVICE_REPO_MAP='{"payments-api": "myorg/payment-service", "auth": "myorg/identity-platform"}'
```

---

## Your First Context Card

Let's verify everything is working by triggering a test incident.

### Step 1: Set Up PagerDuty Webhook

1. Go to **PagerDuty** → **Services** → Select your service
2. Click **Integrations** → **Add Integration**
3. Select **Generic Webhook (v3)**
4. Set the endpoint URL: `https://your-domain.com/webhooks/pagerduty`
5. Copy the **Signing Secret** to your `.env` as `PAGERDUTY_WEBHOOK_SECRET`

![PagerDuty Webhook Setup](./images/pagerduty-webhook-placeholder.png)
*Screenshot: Adding webhook integration in PagerDuty*

### Step 2: Restart the Application

After updating `.env`:

```bash
# Docker
docker-compose restart

# Local
# Ctrl+C and restart uvicorn
```

### Step 3: Trigger a Test Incident

In PagerDuty:
1. Go to your service
2. Click **+ New Incident**
3. Fill in:
   - **Title**: Test incident for Copilot
   - **Description**: Testing context card delivery

### Step 4: Check Slack

Within 10 seconds, you should see a context card in your configured Slack channel:

```
┌─────────────────────────────────────────────────────────────────┐
│ 🟠 payments-api: Test incident for Copilot                     │
├─────────────────────────────────────────────────────────────────┤
│ Severity: MEDIUM  |  Triggered: 14:32 UTC  |  View in PagerDuty│
├─────────────────────────────────────────────────────────────────┤
│ 🚀 Recent Deployments:                                         │
│ • abc1234 by @engineer - Add retry logic (2 hours ago)         │
│ • def5678 by @dev - Fix timeout handling (5 hours ago)         │
├─────────────────────────────────────────────────────────────────┤
│ 📋 Log Analysis:                                                │
│ No recent errors found in logs.                                │
├─────────────────────────────────────────────────────────────────┤
│ 📖 Runbooks  |  📊 Dashboard  |  Owners: @oncall               │
│ Context assembled in 2450ms                                    │
└─────────────────────────────────────────────────────────────────┘
```

![Context Card in Slack](./images/slack-context-card-placeholder.png)
*Screenshot: Context card delivered to Slack*

### Troubleshooting First Setup

If you don't see a context card:

1. **Check application logs**:
   ```bash
   docker-compose logs -f incident-copilot
   ```

2. **Verify webhook delivery** in PagerDuty:
   - Go to your webhook integration
   - Click **Recent Deliveries**
   - Check for successful (200) responses

3. **Test Slack connection**:
   ```bash
   curl -X POST https://slack.com/api/auth.test \
     -H "Authorization: Bearer $SLACK_BOT_TOKEN"
   ```

4. **Check the health endpoint**:
   ```bash
   curl http://localhost:8000/health
   ```

See [Troubleshooting Guide](./troubleshooting.md) for more help.

---

## Next Steps

Congratulations! You've set up Incident Copilot. Here's what to do next:

### 1. Add More Integrations

Enhance your context cards by connecting more sources:

- **[GitHub/GitLab](./integrations.md#github)**: Show recent deployments and code owners
- **[Datadog/CloudWatch](./integrations.md#datadog)**: Include error logs and metrics
- **[AI Summarization](./integrations.md#ai)**: Get intelligent log analysis

### 2. Configure for Production

- Set up [Kubernetes deployment](../deployment.md) for high availability
- Configure [rate limiting](./configuration.md#rate-limiting) for external APIs
- Enable [audit logging](./configuration.md#audit-logging) for compliance

### 3. Optimize Your Workflow

- Read [Best Practices](./best-practices.md) for incident response
- Set up [runbook linking](../runbooks.md) for faster resolution
- Configure [SLA tracking](./configuration.md#sla-tracking) for metrics

### 4. Learn Core Concepts

Understand how Incident Copilot works:

- [How context assembly works](./core-concepts.md#context-assembly)
- [Understanding the context card](./core-concepts.md#context-card)
- [AI summarization explained](./core-concepts.md#ai-summarization)

---

## Quick Reference

### Useful Commands

```bash
# View logs
docker-compose logs -f incident-copilot

# Restart after config changes
docker-compose restart

# Check health
curl http://localhost:8000/health

# View API documentation
open http://localhost:8000/docs
```

### Useful URLs

| URL | Description |
|-----|-------------|
| `/health` | Health check endpoint |
| `/health/ready` | Kubernetes readiness probe |
| `/health/live` | Kubernetes liveness probe |
| `/docs` | Swagger UI |
| `/redoc` | ReDoc documentation |
| `/webhooks/pagerduty` | PagerDuty webhook endpoint |
| `/webhooks/opsgenie` | Opsgenie webhook endpoint |

---

*Next: [Core Concepts](./core-concepts.md) →*
