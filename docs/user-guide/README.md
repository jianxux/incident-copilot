# Incident Copilot User Guide

Welcome to Incident Copilot! This documentation will help you set up, configure, and use Incident Copilot to reduce your Mean Time To Resolution (MTTR) by 30-50%.

## What is Incident Copilot?

Incident Copilot is a context-aware assistant for on-call engineers. When an alert fires in PagerDuty or Opsgenie, it automatically:

1. **Fetches recent deployments** from GitHub or GitLab
2. **Pulls error logs** from Datadog, CloudWatch, Loki, Splunk, or Elasticsearch
3. **Summarizes issues** using AI (Claude)
4. **Delivers a context card** to Slack or Microsoft Teams within 10 seconds

![Incident Copilot Overview](./images/overview-placeholder.png)
*Screenshot: Example context card delivered to Slack*

---

## 📚 Documentation Index

### 🚀 Getting Started

| Guide | Description |
|-------|-------------|
| **[Getting Started](./getting-started.md)** | Installation, initial setup, and your first context card |
| **[Core Concepts](./core-concepts.md)** | Understanding incidents, alerts, and context assembly |
| **[Best Practices](./best-practices.md)** | Recommendations for incident response workflows |

### ⚙️ Configuration

| Guide | Description |
|-------|-------------|
| **[Configuration Reference](./configuration.md)** | Complete reference for all environment variables |
| **[CLI Reference](./cli.md)** | Command-line tools for validation and testing |

### 🔌 Integrations

| Guide | Description |
|-------|-------------|
| **[Integrations Guide](./integrations.md)** | Master guide for all integrations |
| **[PagerDuty](./integrations/pagerduty.md)** | Alert source setup |
| **[Opsgenie](./integrations/opsgenie.md)** | Alternative alert source |
| **[GitHub](./integrations/github.md)** | Deployment tracking |
| **[GitLab](./integrations/gitlab.md)** | Alternative source control |
| **[Datadog](./integrations/datadog.md)** | Log provider setup |
| **[CloudWatch](./integrations/cloudwatch.md)** | AWS log provider |
| **[Splunk](./integrations/splunk.md)** | Enterprise log provider |
| **[Slack](./integrations/slack.md)** | Notification channel |
| **[Teams](./integrations/teams.md)** | Microsoft Teams notifications |
| **[Jira](./integrations/jira.md)** | Issue tracking |
| **[Linear](./integrations/linear.md)** | Modern issue tracking |
| **[ServiceNow](./integrations/servicenow.md)** | Enterprise ITSM |

### 📊 Features

| Feature | Description |
|---------|-------------|
| **[Context Cards](./features/context-cards.md)** | Understanding the context card format |
| **[AI Analysis](./features/ai-analysis.md)** | AI-powered log summarization |
| **[Similar Incidents](./features/similar-incidents.md)** | Finding related past incidents |
| **[Incident Timeline](./features/incident-timeline.md)** | Automatic timeline generation |
| **[Reports & Analytics](./reports.md)** | Overview of reporting capabilities |
| **[Scheduled Reports](./features/scheduled-reports.md)** | Daily, weekly, and monthly reports |
| **[Postmortems](./features/postmortems.md)** | AI-generated postmortem documents |
| **[Analytics](./features/analytics.md)** | Metrics and trend analysis |

### 🔐 Administration

| Guide | Description |
|-------|-------------|
| **[User Management](./admin/user-management.md)** | Managing users and permissions |
| **[API Keys](./admin/api-keys.md)** | Creating and managing API keys |
| **[SSO Setup](./admin/sso.md)** | SAML and OIDC configuration |
| **[Tenant Setup](./admin/tenant-setup.md)** | Multi-tenant configuration |
| **[Billing](./admin/billing.md)** | Stripe integration for SaaS |

### 🛠️ Operations

| Guide | Description |
|-------|-------------|
| **[Troubleshooting](./troubleshooting.md)** | Common issues and solutions |
| **[FAQ](./faq.md)** | Frequently asked questions |
| **[API Reference](./api-reference.md)** | REST API documentation |

---

## Quick Start Checklist

```
□ Step 1: Install Incident Copilot
    └── See: Getting Started → Installation

□ Step 2: Configure alert source (PagerDuty or Opsgenie)
    └── See: Integrations → PagerDuty or Opsgenie

□ Step 3: Set up notification channel (Slack or Teams)
    └── See: Integrations → Slack or Teams

□ Step 4: Connect source control (GitHub or GitLab)
    └── See: Integrations → GitHub or GitLab

□ Step 5: Configure log provider (Datadog, CloudWatch, etc.)
    └── See: Integrations → Your Log Provider

□ Step 6: Add AI key for log summarization
    └── See: Configuration → AI Configuration

□ Step 7: Trigger a test incident
    └── See: Getting Started → Your First Context Card

□ Step 8: Configure scheduled reports (optional)
    └── See: Features → Scheduled Reports
```

---

## Quick Links by Task

| I want to... | Go to... |
|--------------|----------|
| Install Incident Copilot | [Getting Started → Installation](./getting-started.md#installation) |
| Set up PagerDuty webhooks | [Integrations → PagerDuty](./integrations/pagerduty.md) |
| Configure Slack notifications | [Integrations → Slack](./integrations/slack.md) |
| Connect GitHub for deployments | [Integrations → GitHub](./integrations/github.md) |
| Set up scheduled reports | [Features → Scheduled Reports](./features/scheduled-reports.md) |
| Debug webhook issues | [Troubleshooting → Webhooks](./troubleshooting.md#webhook-issues) |
| View all config options | [Configuration Reference](./configuration.md) |
| Use the CLI | [CLI Reference](./cli.md) |
| Call the API | [API Reference](./api-reference.md) |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                       INCIDENT COPILOT                          │
│                                                                 │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐   │
│   │  PagerDuty   │     │   Opsgenie   │     │   Manual     │   │
│   │   Webhook    │     │   Webhook    │     │   Trigger    │   │
│   └──────┬───────┘     └──────┬───────┘     └──────┬───────┘   │
│          │                    │                    │            │
│          └────────────────────┴────────────────────┘            │
│                               │                                 │
│                               ▼                                 │
│                    ┌─────────────────────┐                      │
│                    │    Orchestrator     │                      │
│                    │  (Context Assembly) │                      │
│                    └──────────┬──────────┘                      │
│                               │                                 │
│         ┌─────────────────────┼─────────────────────┐           │
│         │                     │                     │           │
│         ▼                     ▼                     ▼           │
│   ┌───────────┐        ┌───────────┐        ┌───────────┐       │
│   │  GitHub/  │        │  Datadog/ │        │    AI     │       │
│   │  GitLab   │        │ CloudWatch│        │ Summarizer│       │
│   │           │        │  /Loki    │        │ (Claude)  │       │
│   └─────┬─────┘        └─────┬─────┘        └─────┬─────┘       │
│         │                    │                    │             │
│         └────────────────────┴────────────────────┘             │
│                               │                                 │
│                               ▼                                 │
│                    ┌─────────────────────┐                      │
│                    │   Context Card      │                      │
│                    └──────────┬──────────┘                      │
│                               │                                 │
│                    ┌──────────┴──────────┐                      │
│                    ▼                     ▼                      │
│             ┌───────────┐         ┌───────────┐                 │
│             │   Slack   │         │   Teams   │                 │
│             └───────────┘         └───────────┘                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## What's New

### v0.2.0 (Latest)
- ✨ **Elasticsearch support** - Connect to Elastic for logs
- ✨ **ServiceNow integration** - Create incidents in ServiceNow
- ✨ **Alert correlation** - Group related alerts automatically
- ✨ **Scheduled reports** - Daily, weekly, monthly reports
- 🔧 **CLI improvements** - Better validation and testing
- 📚 **Documentation refresh** - Comprehensive user guides

### v0.1.0
- 🎉 Initial release
- PagerDuty and Opsgenie support
- Slack and Teams notifications
- GitHub and GitLab integration
- Datadog and CloudWatch logs
- AI-powered log summarization

---

## Getting Help

- **[FAQ](./faq.md)**: Check common questions first
- **[Troubleshooting](./troubleshooting.md)**: Diagnose and fix issues
- **[GitHub Issues](https://github.com/your-org/incident-copilot/issues)**: Report bugs or request features
- **[Architecture Docs](../architecture.md)**: Technical deep-dive

---

## Version

This documentation is for **Incident Copilot v0.2.0**.

*Last updated: February 2025*
