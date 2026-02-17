# Incident Copilot Roadmap

## Current Status (Feb 17, 2026)

Core platform and enterprise feature set are in place. Phase 6 has moved from planning into active delivery, with several previously planned items now completed in code.

---

## Phase 1: MVP (Complete) ✅

- PagerDuty webhook ingestion
- GitHub change/deploy context
- Datadog log context
- AI log summarization
- Slack context-card delivery
- Dockerized local/dev deployment

## Phase 2: Multi-Platform (Complete) ✅

- Opsgenie integration
- CloudWatch log support
- Microsoft Teams delivery
- Similar incident search
- Runbook auto-linking

## Phase 3: Enterprise Foundation (Complete) ✅

- Multi-tenant auth and tenant isolation
- Usage/billing module
- Self-serve onboarding flows
- Dashboard + analytics experience
- Helm chart and deployment docs
- CLI/demo/health endpoints

## Phase 4: Advanced Integrations (Complete) ✅

- Jira integration
- Prometheus metrics
- GitLab support
- Grafana/Loki support
- Linear integration
- AI postmortem generation

## Phase 5: Enterprise Controls (Complete) ✅

- Splunk integration
- ServiceNow integration
- SSO/SAML/OIDC
- Audit logging

## Phase 6: Growth & Scale (In Progress) 🚧

### Completed in code

- Incident timeline UI (web + Next.js dashboard surfaces)
- AI insights and pattern-detection APIs (`src/insights/`, `/api/insights`)
- On-call roster/handoff workflows
- API rate limiting middleware + admin routes
- Incident tagging system
- Webhook plugin framework
- Slack command handling (`/api/slack/...`, slash command adapters)
- Alert correlation engine
- Email notification pipeline

### Still in progress / planned

- Mobile app experience (API groundwork exists under `src/api/mobile/`)
- Multi-region deployment strategy
- White-label branding controls
- Public custom integration SDK packaging

---

## Integration Matrix

### Alert Sources
| Source | Status |
|--------|--------|
| PagerDuty | ✅ Full |
| Opsgenie | ✅ Full |
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

### Notification Channels
| Channel | Status |
|---------|--------|
| Slack | ✅ Full |
| Microsoft Teams | ✅ Full |
| Email | ✅ Full |

### ITSM / Ticketing
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

## How to Contribute

1. Check [issues](https://github.com/jianxux/incident-copilot/issues)
2. Claim a task in comments
3. Open a focused feature branch + PR
4. Ensure CI checks pass before review request

---

*Last updated: 2026-02-17*
