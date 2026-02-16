# Incident Copilot

Incident Copilot is a context-aware incident assistant for on-call engineers. When an alert triggers, it pulls the most relevant operational context (logs, metrics, runbooks, recent deploys, on-call schedule, ownership) and posts an actionable briefing to your collaboration tool.

## What you get

- **Fast triage**: a single message that answers “what changed?”, “where is it failing?”, and “what should I check next?”.
- **Pluggable integrations**: connect PagerDuty/Opsgenie, Slack/Teams, and your observability + source control systems.
- **Correlation + suppression**: reduce noise by grouping related alerts and suppressing duplicates.
- **Extensible**: add integrations and context sources via a plugin-style architecture.

## Core concepts

- **Incident**: the alert payload normalized into an internal incident model.
- **Context**: enriched data fetched from external systems (logs, metrics, repos, runbooks).
- **Orchestrator**: coordinates context fetching and notification delivery.
- **AI summarization**: converts raw context into a concise incident briefing (optional).

## Next steps

- Start with **[Quickstart](getting-started/quickstart.md)** to get a local instance running.
- Connect your alert source in **[Integrations](integrations/pagerduty.md)**.
- Review **[Configuration](configuration/environment.md)** for required environment variables.

## Support

- For common issues, see Getting Started pages or open an issue with logs + configuration summary.
