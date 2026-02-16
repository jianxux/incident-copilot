# Architecture

Incident Copilot is a webhook-driven pipeline that assembles incident context and delivers it to your chat tools.

## High-level flow

```mermaid
flowchart TD
  A[Alert fires\nPagerDuty / Opsgenie] -->|Webhook| B[Incident Copilot API\nFastAPI]
  B --> C[Normalize alert\nservice, severity, links]
  C --> D[Context gatherers]
  D --> D1[Deploys\nGitHub / GitLab]
  D --> D2[Logs\nDatadog / CloudWatch / Loki / Splunk]
  D --> D3[On-call\nPagerDuty / Opsgenie]
  D --> E[AI summarizer\nAnthropic]
  E --> F[Context card composer]
  F --> G[Notify\nSlack / Teams]
  B --> H[(Postgres)]
  B --> I[(Redis)]
```

## Components

### API service (FastAPI)

- Receives webhooks from alert providers.
- Authenticates/validates incoming requests (signing secrets).
- Enqueues or executes context gathering.

### Context gatherers

- Source control: recent deploys, commits, PRs
- Observability: relevant logs by time window and service label
- On-call: who’s responsible right now

### Summarization

The AI step turns raw signals into:

- a short incident summary
- suspected root causes
- suggested next checks

### Delivery

- Slack: rich blocks / message formatting
- Teams: incoming webhook card

## Design goals

- **Fast to context**: deliver useful info in <1–2 minutes.
- **Least privilege**: use scoped tokens and secrets.
- **Pluggable providers**: swap log providers and SCM providers.
- **Self-hostable**: run on Docker/Kubernetes/Railway.
