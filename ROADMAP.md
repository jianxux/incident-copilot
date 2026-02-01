# Incident Copilot Roadmap 🗺️

> Building the context-aware copilot for on-call engineers.

## Current Status: **MVP Complete** ✅

The core product is functional and deployed. Engineers can receive context cards within seconds of an alert firing.

---

## Phase 1: MVP (Complete) ✅

| Feature | Status | Notes |
|---------|--------|-------|
| PagerDuty webhook integration | ✅ Done | Receives alerts, verifies signatures |
| GitHub deployment fetcher | ✅ Done | Recent commits + deployments |
| Datadog log integration | ✅ Done | Fetches relevant error logs |
| AI log summarization | ✅ Done | Claude-powered analysis |
| Slack context card delivery | ✅ Done | Rich formatted cards |
| Docker deployment | ✅ Done | Production-ready container |

## Phase 2: Multi-Platform (Complete) ✅

| Feature | Status | Notes |
|---------|--------|-------|
| Opsgenie integration | ✅ Done | Full webhook + API support |
| CloudWatch logs | ✅ Done | AWS log group mapping |
| Microsoft Teams | ✅ Done | Adaptive cards delivery |
| Past incident similarity | ✅ Done | Vector similarity search |
| Runbook auto-linking | ✅ Done | Automatic detection + linking |

## Phase 3: Enterprise Ready (In Progress) 🚧

| Feature | Status | Notes |
|---------|--------|-------|
| Multi-tenant auth | ✅ Done | JWT + API keys, tenant isolation |
| Usage-based billing | ✅ Done | Stripe integration |
| Self-serve onboarding | ✅ Done | Landing page + signup flow |
| Web dashboard | ✅ Done | Incident timeline, analytics |
| Analytics & insights | ✅ Done | MTTR tracking, trends |
| Helm chart (K8s) | 🚧 PR Open | Production K8s deployment |
| CD pipeline | 🚧 PR Open | Auto-deploy on merge |
| CLI tools | ✅ Done | Config validation, testing |
| Demo mode | ✅ Done | Sales/onboarding demos |

## Phase 4: Advanced Features (Planned) 📋

| Feature | Priority | Description |
|---------|----------|-------------|
| Jira integration | High | Auto-create incident tickets |
| Prometheus metrics | High | /metrics endpoint for observability |
| GitLab support | Medium | Alternative to GitHub |
| Grafana/Loki logs | Medium | Alternative log provider |
| Linear integration | Medium | Modern issue tracking |
| Incident timeline | Medium | Visual incident progression |
| Postmortem generator | Low | AI-generated incident reports |
| Mobile app | Low | On-call notifications + context |

## Phase 5: Enterprise Scale (Future) 🔮

| Feature | Description |
|---------|-------------|
| Splunk integration | Enterprise log aggregation |
| ServiceNow ITSM | Enterprise incident management |
| SSO/SAML | Enterprise authentication |
| Audit logging | Compliance requirements |
| Custom integrations | Webhook + plugin system |
| On-premise deployment | Air-gapped environments |

---

## How to Contribute

1. Check the [issues](https://github.com/jianxux/incident-copilot/issues) for current tasks
2. Comment on an issue to claim it
3. Create a feature branch and submit a PR
4. Ensure CI passes before requesting review

## Feedback

Building something you'd use? Have feature requests? Open an issue or reach out!

---

*Last updated: 2026-02-01*
