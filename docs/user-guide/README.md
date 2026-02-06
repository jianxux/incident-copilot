# Incident Copilot User Guide

Welcome to Incident Copilot! This documentation will help you set up, configure, and use Incident Copilot to reduce your Mean Time To Resolution (MTTR) by 30-50%.

## What is Incident Copilot?

Incident Copilot is a context-aware assistant for on-call engineers. When an alert fires in PagerDuty or Opsgenie, it automatically:

1. **Fetches recent deployments** from GitHub or GitLab
2. **Pulls error logs** from Datadog, CloudWatch, Loki, or other log providers
3. **Summarizes issues** using AI (Claude)
4. **Delivers a context card** to Slack or Microsoft Teams within 10 seconds

![Incident Copilot Overview](./images/overview-placeholder.png)
*Screenshot: Example context card delivered to Slack*

---

## 📚 Documentation Index

### Getting Started
- **[Getting Started](./getting-started.md)** - Installation, configuration, and your first context card

### Core Concepts
- **[Core Concepts](./core-concepts.md)** - Understanding incidents, alerts, integrations, and context assembly

### Integrations
- **[Integrations Guide](./integrations.md)** - Step-by-step setup for all supported integrations:
  - Alert Sources: PagerDuty, Opsgenie
  - Source Control: GitHub, GitLab
  - Log Providers: Datadog, CloudWatch, Loki, Splunk, New Relic, Elasticsearch
  - Notifications: Slack, Microsoft Teams
  - Issue Tracking: Jira, Linear, ServiceNow

### Configuration
- **[Configuration Reference](./configuration.md)** - Complete reference for all environment variables

### Operations
- **[Troubleshooting](./troubleshooting.md)** - Common issues and how to resolve them
- **[Best Practices](./best-practices.md)** - Recommendations for incident response workflows

---

## Quick Links

| Task | Documentation |
|------|---------------|
| Install Incident Copilot | [Getting Started → Installation](./getting-started.md#installation) |
| Set up PagerDuty webhooks | [Integrations → PagerDuty](./integrations.md#pagerduty) |
| Configure Slack notifications | [Integrations → Slack](./integrations.md#slack) |
| Connect GitHub for deployments | [Integrations → GitHub](./integrations.md#github) |
| Debug webhook issues | [Troubleshooting → Webhooks](./troubleshooting.md#webhooks-not-arriving) |
| View all config options | [Configuration Reference](./configuration.md) |

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
│                    └──────────┬──────────┘                      │
│                               │                                 │
│         ┌─────────────────────┼─────────────────────┐           │
│         │                     │                     │           │
│         ▼                     ▼                     ▼           │
│   ┌───────────┐        ┌───────────┐        ┌───────────┐       │
│   │  GitHub/  │        │  Datadog/ │        │    AI     │       │
│   │  GitLab   │        │ CloudWatch│        │ Summarizer│       │
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

## Getting Help

- **GitHub Issues**: [Report bugs or request features](https://github.com/your-org/incident-copilot/issues)
- **Architecture Docs**: [Technical architecture](../architecture.md)
- **API Reference**: [Full API documentation](../API.md)

---

## Version

This documentation is for **Incident Copilot v0.1.0**.

*Last updated: February 2025*
