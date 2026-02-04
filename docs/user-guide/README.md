# 📚 Incident Copilot User Guide

Welcome to the Incident Copilot User Guide! This documentation will help you set up, configure, and get the most value from Incident Copilot.

## What is Incident Copilot?

Incident Copilot is a context-aware assistant for on-call engineers. When an alert fires, it automatically:

1. 🚀 **Fetches recent deployments** from GitHub or GitLab
2. 📊 **Pulls error logs** from Datadog, CloudWatch, Loki, or Splunk
3. 🤖 **Summarizes issues** using AI (Claude)
4. 📬 **Delivers a context card** to Slack or Teams within 10 seconds

**Result:** Engineers get actionable context immediately, reducing MTTR by 30-50%.

---

## 📖 Table of Contents

### Getting Started
- [🚀 Quick Start Guide](./getting-started.md) - Get your first context card in 5 minutes
- [💻 CLI Reference](./cli.md) - Command line tools
- [🔌 API Reference](./api-reference.md) - REST API documentation
- [❓ FAQ](./faq.md) - Frequently asked questions
- [🔧 Troubleshooting](./troubleshooting.md) - Common issues and solutions

### Integrations
Set up your alerting, code, logging, and notification tools:

| Category | Integrations |
|----------|--------------|
| **Alerting** | [PagerDuty](./integrations/pagerduty.md) • [Opsgenie](./integrations/opsgenie.md) |
| **Code & Deploys** | [GitHub](./integrations/github.md) • [GitLab](./integrations/gitlab.md) |
| **Logs & Metrics** | [Datadog](./integrations/datadog.md) • [CloudWatch](./integrations/cloudwatch.md) • [Splunk](./integrations/splunk.md) |
| **Notifications** | [Slack](./integrations/slack.md) • [Microsoft Teams](./integrations/teams.md) |
| **Issue Tracking** | [Jira](./integrations/jira.md) • [Linear](./integrations/linear.md) • [ServiceNow](./integrations/servicenow.md) |

### Features
Learn how to use Incident Copilot's key features:

- [🃏 Context Cards](./features/context-cards.md) - Understanding the information delivered to you
- [🤖 AI Analysis](./features/ai-analysis.md) - How AI summarization works
- [📅 Incident Timeline](./features/incident-timeline.md) - Using the timeline view
- [🔍 Similar Incidents](./features/similar-incidents.md) - Finding related past incidents
- [📝 Postmortems](./features/postmortems.md) - Generating AI-powered postmortems
- [📈 Analytics](./features/analytics.md) - Understanding MTTR and metrics
- [📅 Scheduled Reports](./features/scheduled-reports.md) - Automated incident reports

### Administration
Configure and manage your Incident Copilot deployment:

- [🏢 Tenant Setup](./admin/tenant-setup.md) - Multi-tenant configuration
- [👥 User Management](./admin/user-management.md) - Adding users and roles
- [🔐 SSO Configuration](./admin/sso.md) - SAML and OIDC setup
- [💳 Billing](./admin/billing.md) - Understanding plans and usage
- [🔑 API Keys](./admin/api-keys.md) - Managing programmatic access

---

## 🎯 Quick Start

Want to get started immediately? Here's the fastest path:

### 1. Prerequisites
- A PagerDuty or Opsgenie account
- A Slack workspace (or Microsoft Teams)
- GitHub or GitLab for your code
- Datadog, CloudWatch, or another log provider

### 2. Minimum Configuration

```bash
# Copy the example config
cp .env.example .env

# Edit with your minimum required keys:
PAGERDUTY_API_KEY=your-key
PAGERDUTY_WEBHOOK_SECRET=your-secret
GITHUB_TOKEN=ghp_xxxx
GITHUB_ORG=your-org
DATADOG_API_KEY=your-key
DATADOG_APP_KEY=your-key
SLACK_BOT_TOKEN=xoxb-xxxx
ANTHROPIC_API_KEY=sk-ant-xxxx
```

### 3. Run It

```bash
# Using Docker
docker-compose up

# Or locally
pip install -e ".[dev]"
uvicorn src.main:app --reload
```

### 4. Configure Webhook

In PagerDuty, add a webhook pointing to:
```
https://your-domain.com/webhooks/pagerduty
```

That's it! Trigger a test incident and watch the context card appear in Slack.

---

## 📊 Context Card Preview

Here's what you'll see when an incident fires:

```
┌─────────────────────────────────────────┐
│ 🟠 payments-api: High Error Rate        │
├─────────────────────────────────────────┤
│ Severity: HIGH  |  Triggered: 02:47     │
├─────────────────────────────────────────┤
│ 🚀 Recent Deployments:                  │
│ • abc1234 by @sarah - Fix retry logic   │
│ • def5678 by @mike - Update deps        │
├─────────────────────────────────────────┤
│ 📋 Top Issues (AI Analysis):            │
│ • ConnectionTimeout to stripe-api (847x)│
│ • Retry limit exceeded (612x)           │
│                                         │
│ The service is experiencing timeouts    │
│ when connecting to Stripe's API...      │
├─────────────────────────────────────────┤
│ 🔍 Similar Past Incidents:              │
│ • Stripe outage (2024-01-10) - 92% match│
├─────────────────────────────────────────┤
│ 👥 On-Call: @sarah | 📖 Runbook         │
│ Context assembled in 3420ms             │
└─────────────────────────────────────────┘
```

---

## 🆘 Getting Help

- **Documentation Issues?** Open an issue on GitHub
- **Feature Requests?** Check the [Roadmap](../../ROADMAP.md)
- **Bug Reports?** Include logs with `DEBUG=true`

---

*Documentation version: 1.0 | Last updated: February 2025*
