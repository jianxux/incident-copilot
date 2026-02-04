# 🚀 Getting Started with Incident Copilot

Get your first context card delivered in 5 minutes! This guide walks you through the minimum setup to see Incident Copilot in action.

---

## 📋 Prerequisites Checklist

Before you begin, make sure you have:

| Requirement | Purpose | How to Get It |
|-------------|---------|---------------|
| ✅ **Alerting Tool** | Trigger incidents | PagerDuty or Opsgenie account |
| ✅ **Notification Channel** | Receive context cards | Slack workspace or Microsoft Teams |
| ✅ **Code Repository** | Show recent deployments | GitHub or GitLab with repos |
| ✅ **Log Provider** | Fetch error logs | Datadog, CloudWatch, Loki, or Splunk |
| ✅ **AI API Key** | Summarize logs | [Anthropic API key](https://console.anthropic.com/) |
| ✅ **Python 3.11+** | Run the application | `python --version` |

---

## ⚡ Quick Start (5 Minutes)

### Step 1: Clone and Configure

```bash
# Clone the repository
git clone https://github.com/your-org/incident-copilot.git
cd incident-copilot

# Create your configuration file
cp .env.example .env
```

### Step 2: Add Your API Keys

Open `.env` in your editor and add these minimum required keys:

```bash
# === MINIMUM REQUIRED CONFIGURATION ===

# Alerting (choose one)
PAGERDUTY_API_KEY=your-pagerduty-api-key
PAGERDUTY_WEBHOOK_SECRET=your-webhook-secret

# Code Repository (choose one)
GITHUB_TOKEN=ghp_your-personal-access-token
GITHUB_ORG=your-organization-name

# Log Provider (choose one)
LOG_PROVIDER=datadog
DATADOG_API_KEY=your-datadog-api-key
DATADOG_APP_KEY=your-datadog-app-key

# Notifications (choose one)
NOTIFICATION_PROVIDER=slack
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token

# AI Summarization
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key
```

📌 **Note:** See individual integration guides for detailed setup instructions.

### Step 3: Run Incident Copilot

**Option A: Docker (Recommended)**

```bash
docker-compose up
```

**Option B: Local Development**

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Run the server
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

✅ **Success!** You should see:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Step 4: Verify the Installation

Open your browser or use curl:

```bash
# Health check
curl http://localhost:8000/health

# Expected response:
# {"status":"healthy","timestamp":"...","version":"0.1.0",...}
```

### Step 5: Validate Configuration

Use the CLI to verify all configuration:

```bash
incident-copilot validate
```

See [CLI Reference](./cli.md) for more commands.

---

## 🔧 Initial Setup Wizard

### Configure PagerDuty Webhook

1. Log into PagerDuty
2. Navigate to **Services** → Select your service → **Integrations**
3. Click **Add Integration** → **Generic Webhook (v3)**
4. Configure:
   - **Name:** `Incident Copilot`
   - **Endpoint URL:** `https://your-domain.com/webhooks/pagerduty`
5. Click **Save**
6. Copy the **Signing Secret** to `PAGERDUTY_WEBHOOK_SECRET` in your `.env`

⚠️ **Important:** For local testing, use a tool like [ngrok](https://ngrok.com/) to expose your local server:

```bash
# In a new terminal
ngrok http 8000

# Use the HTTPS URL ngrok provides (e.g., https://abc123.ngrok.io)
```

### Configure Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App** → **From scratch**
3. Name it `Incident Copilot` and select your workspace
4. Go to **OAuth & Permissions** → **Bot Token Scopes**
5. Add scopes:
   - `chat:write`
   - `chat:write.public`
6. Click **Install to Workspace**
7. Copy the **Bot User OAuth Token** to `SLACK_BOT_TOKEN` in your `.env`

---

## 🧪 First Incident Test

Now let's verify everything works end-to-end!

### Method 1: Trigger a Real Incident

1. Create a test alert in PagerDuty or Opsgenie
2. Watch your Slack channel for the context card
3. Verify it contains:
   - ✅ Incident title and severity
   - ✅ Recent deployments (if any)
   - ✅ Error log summary (if any)
   - ✅ AI analysis

### Method 2: Use the Demo Endpoint

Incident Copilot includes a demo endpoint for testing:

```bash
# Trigger a simulated incident
curl -X POST http://localhost:8000/demo/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "payments-api",
    "title": "High Error Rate",
    "severity": "high"
  }'
```

### Method 3: Use the CLI

```bash
incident-copilot send-test
```

---

## ✅ Verification Checklist

Make sure everything is working:

| Check | Command | Expected Result |
|-------|---------|-----------------|
| App Running | `curl localhost:8000/` | `{"status":"ok"}` |
| Health Check | `curl localhost:8000/health` | `{"status":"healthy",...}` |
| Full Health | `curl 'localhost:8000/health?full=true'` | All components healthy |
| Webhook Health | `curl localhost:8000/webhooks/health` | `{"status":"ok",...}` |
| Config Valid | `incident-copilot validate` | All checks passed |
| Test Integration | `incident-copilot test-all` | All integrations working |

---

## 🚨 Common Setup Issues

### "Connection refused" on localhost:8000

**Cause:** Server isn't running

**Fix:**
```bash
# Check if uvicorn is running
ps aux | grep uvicorn

# If not, start it
uvicorn src.main:app --reload
```

### "Invalid signature" on webhooks

**Cause:** Webhook secret mismatch

**Fix:**
1. Re-copy the signing secret from PagerDuty
2. Make sure there's no extra whitespace in `.env`
3. Restart the server

### "No logs found" in context cards

**Cause:** Service name doesn't match log tags

**Fix:**
1. Check your Datadog service tag matches the PagerDuty service name
2. Or configure explicit mapping:
   ```bash
   SERVICE_REPO_MAP='{"pagerduty-service-name": "org/actual-repo-name"}'
   ```

### "Slack message failed"

**Cause:** Bot not authorized or channel doesn't exist

**Fix:**
1. Verify bot token with:
   ```bash
   curl -X POST https://slack.com/api/auth.test \
     -H "Authorization: Bearer $SLACK_BOT_TOKEN"
   ```
2. Make sure `SLACK_DEFAULT_CHANNEL` exists
3. For private channels, invite the bot: `/invite @Incident Copilot`

See [Troubleshooting](./troubleshooting.md) for more solutions.

---

## 🎯 Next Steps

Now that you have the basics working:

1. **Add More Integrations**
   - [Set up GitLab](./integrations/gitlab.md) if not using GitHub
   - [Configure CloudWatch](./integrations/cloudwatch.md) as an alternative to Datadog
   - [Add Microsoft Teams](./integrations/teams.md) alongside Slack

2. **Explore Features**
   - [Understand Context Cards](./features/context-cards.md)
   - [Enable Similar Incident Search](./features/similar-incidents.md)
   - [Generate AI Postmortems](./features/postmortems.md)
   - [Configure Scheduled Reports](./features/scheduled-reports.md)

3. **Production Deployment**
   - [Deploy with Kubernetes](../../README.md#kubernetes-deployment)
   - [Configure SSO](./admin/sso.md)
   - [Set up Multi-tenancy](./admin/tenant-setup.md)

---

## 📊 Configuration Reference

Here's a complete list of environment variables:

### Required

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key for AI summarization |
| `SLACK_BOT_TOKEN` or `TEAMS_WEBHOOK_URL` | Notification delivery |
| `PAGERDUTY_API_KEY` or `OPSGENIE_API_KEY` | Alerting integration |

### Recommended

| Variable | Description | Default |
|----------|-------------|---------|
| `GITHUB_TOKEN` | GitHub personal access token | - |
| `GITHUB_ORG` | GitHub organization name | - |
| `DATADOG_API_KEY` | Datadog API key | - |
| `DATADOG_APP_KEY` | Datadog application key | - |
| `LOG_PROVIDER` | Log provider: datadog, cloudwatch, loki, splunk | `datadog` |
| `NOTIFICATION_PROVIDER` | Notification: slack, teams, both | `slack` |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `DEBUG` | Enable debug logging | `false` |
| `AI_MODEL` | Claude model for summarization | `claude-3-haiku-20240307` |
| `SLACK_DEFAULT_CHANNEL` | Default Slack channel | `#incidents` |
| `OPENAI_API_KEY` | OpenAI API key for embeddings (similarity search) | - |

See the [full configuration reference](../../README.md#configuration) for all options.

---

## 📚 Related Documentation

- [CLI Reference](./cli.md) - Command line tools
- [API Reference](./api-reference.md) - REST API documentation
- [FAQ](./faq.md) - Frequently asked questions
- [Troubleshooting](./troubleshooting.md) - Common issues and solutions

---

*Need help? Check the [Troubleshooting Guide](./troubleshooting.md) or open an issue on GitHub.*
