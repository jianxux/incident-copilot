# Incident Copilot Roadmap 🗺️

> Building the context-aware copilot for on-call engineers.

## Current Status: **Enterprise Ready** ✅

All core features complete. The platform supports multi-tenant SaaS deployment with enterprise authentication, compliance logging, and comprehensive integrations.

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

## Phase 3: Enterprise Ready (Complete) ✅

| Feature | Status | Notes |
|---------|--------|-------|
| Multi-tenant auth | ✅ Done | JWT + API keys, tenant isolation |
| Usage-based billing | ✅ Done | Stripe integration |
| Self-serve onboarding | ✅ Done | Landing page + signup flow |
| Web dashboard | ✅ Done | Incident timeline, analytics |
| Analytics & insights | ✅ Done | MTTR tracking, trends |
| Helm chart (K8s) | ✅ Done | Production K8s deployment (PR #5) |
| CD pipeline | ✅ Done | Auto-deploy on merge (PR #6) |
| CLI tools | ✅ Done | Config validation, testing |
| Demo mode | ✅ Done | Sales/onboarding demos |
| Health checks | ✅ Done | K8s liveness/readiness probes (PR #9) |

## Phase 4: Advanced Features (Complete) ✅

| Feature | Status | Notes |
|---------|--------|-------|
| Jira integration | ✅ Done | Auto-create incident tickets (PR #8) |
| Prometheus metrics | ✅ Done | /metrics endpoint for observability (PR #7) |
| GitLab support | ✅ Done | Alternative to GitHub (PR #12) |
| Grafana/Loki logs | ✅ Done | Alternative log provider (PR #11) |
| Linear integration | ✅ Done | Modern issue tracking (PR #10) |
| Postmortem generator | ✅ Done | AI-generated incident reports (PR #13) |

## Phase 5: Enterprise Scale (Complete) ✅

| Feature | Status | Notes |
|---------|--------|-------|
| Splunk integration | ✅ Done | Enterprise log aggregation (PR #13) |
| ServiceNow ITSM | ✅ Done | Enterprise incident management (PR #13) |
| SSO/SAML | ✅ Done | SAML 2.0 + OIDC, provider presets (PR #13) |
| Audit logging | ✅ Done | SOC2/HIPAA compliance (PR #13) |
| Custom integrations | 📋 Planned | Webhook + plugin system |
| On-premise deployment | 📋 Planned | Air-gapped environments |

## Phase 6: Growth & Scale (Planned) 📋

| Feature | Priority | Description |
|---------|----------|-------------|
| Incident timeline UI | High | Visual incident progression in dashboard |
| Mobile app | Medium | On-call notifications + context |
| AI insights | Medium | Pattern detection across incidents |
| Multi-region deployment | Medium | Global edge deployment |
| Custom integration SDK | Low | Build your own integrations |
| White-label | Low | Enterprise branding options |

---

## Integration Matrix

### Alert Sources
| Source | Status |
|--------|--------|
| PagerDuty | ✅ Full |
| Opsgenie | ✅ Full |
| DataDog Alerts | ✅ Full |
| Custom Webhook | ✅ Full |

### Log Providers
| Provider | Status |
|----------|--------|
| Datadog | ✅ Full |
| CloudWatch | ✅ Full |
| Grafana Loki | ✅ Full |
| Splunk | ✅ Full |

### Code/Deploy
| Provider | Status |
|----------|--------|
| GitHub | ✅ Full |
| GitLab | ✅ Full |

### Notification
| Provider | Status |
|----------|--------|
| Slack | ✅ Full |
| Microsoft Teams | ✅ Full |

### ITSM
| Provider | Status |
|----------|--------|
| Jira | ✅ Full |
| Linear | ✅ Full |
| ServiceNow | ✅ Full |

### Authentication
| Provider | Status |
|----------|--------|
| Email/Password | ✅ Full |
| GitHub OAuth | ✅ Full |
| Google OAuth | ✅ Full |
| SAML 2.0 | ✅ Full |
| OIDC | ✅ Full |

---

## PRs Merged (13 Total)

1. PR #1: Phase 1 Complete - Core features
2. PR #2: Demo Mode
3. PR #3: CLI Tools
4. PR #4: Multi-tenant Auth & Billing
5. PR #5: Kubernetes Helm Chart
6. PR #6: CD Pipeline
7. PR #7: Prometheus Metrics
8. PR #8: Jira Integration
9. PR #9: Health Check Endpoints
10. PR #10: Linear Integration
11. PR #11: Grafana Loki Integration
12. PR #12: GitLab Integration
13. PR #13: Enterprise Features (SSO, Audit, Postmortem, Splunk, ServiceNow)

---

## How to Contribute

1. Check the [issues](https://github.com/jianxux/incident-copilot/issues) for current tasks
2. Comment on an issue to claim it
3. Create a feature branch and submit a PR
4. Ensure CI passes before requesting review

## Feedback

Building something you'd use? Have feature requests? Open an issue or reach out!

---

*Last updated: 2026-02-02*
