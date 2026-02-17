# Incident Copilot

**Incident Copilot** automatically assembles the context you need *when an alert fires*.

When PagerDuty or Opsgenie triggers an incident, Incident Copilot pulls:

- Recent deploys and commits (GitHub / GitLab)
- Relevant logs (Datadog / CloudWatch / Splunk / Loki)
- On-call context (schedule / roster)
- An AI-generated summary and suggested next steps

…and delivers a clean **context card** into Slack and/or Microsoft Teams.

---

## Why

During an incident, the most expensive thing is *time to context*:

- What changed recently?
- Where are the errors coming from?
- Who is on call for this service?
- What should we check first?

Incident Copilot aims to answer those in minutes—automatically.

## What you get

- **FastAPI** service (Python 3.11)
- Docker-first deployment
- Webhooks for alert providers
- Pluggable integrations for source control + logs
- Secure configuration via environment variables

## Quickstart

Go to **Getting started → Quickstart**:

- [`getting-started/quickstart.md`](getting-started/quickstart.md)

## License

This project is licensed under **Business Source License 1.1 (BSL 1.1)**.
