# Core Concepts

This guide explains the fundamental concepts behind Incident Copilot and how they work together to reduce your Mean Time To Resolution (MTTR).

## Table of Contents

1. [The Incident Lifecycle](#the-incident-lifecycle)
2. [Alerts and Incidents](#alerts-and-incidents)
3. [Context Assembly](#context-assembly)
4. [The Context Card](#the-context-card)
5. [Integrations](#integrations)
6. [AI Summarization](#ai-summarization)
7. [On-Call Roster](#on-call-roster)
8. [Runbook Linking](#runbook-linking)

---

## The Incident Lifecycle

Incident Copilot participates in the **early response phase** of the incident lifecycle:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          INCIDENT LIFECYCLE                                 │
│                                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌────────┐│
│  │  DETECT  │───▶│  ALERT   │───▶│ RESPOND  │───▶│ RESOLVE  │───▶│ REVIEW ││
│  │          │    │          │    │          │    │          │    │        ││
│  │ Monitor  │    │ PagerDuty│    │ On-call  │    │ Fix &    │    │ Post-  ││
│  │ detects  │    │ triggers │    │ engineer │    │ verify   │    │mortem  ││
│  │ anomaly  │    │ alert    │    │ responds │    │          │    │        ││
│  └──────────┘    └──────────┘    └────┬─────┘    └──────────┘    └────────┘│
│                                       │                                     │
│                                       │                                     │
│                          ┌────────────▼─────────────┐                       │
│                          │    INCIDENT COPILOT      │                       │
│                          │                          │                       │
│                          │  • Assembles context     │                       │
│                          │  • Fetches recent deploys│                       │
│                          │  • Analyzes error logs   │                       │
│                          │  • Delivers context card │                       │
│                          │                          │                       │
│                          │  ⏱️ < 10 seconds          │                       │
│                          └──────────────────────────┘                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### How Incident Copilot Helps

| Phase | Without Copilot | With Copilot |
|-------|-----------------|--------------|
| **Alert received** | Open PagerDuty, read alert | Same |
| **Initial assessment** | 5-10 min: Check dashboards, logs, recent deploys | 10 sec: Context card delivered |
| **Root cause hypothesis** | Manual log analysis | AI-powered summary provided |
| **Find runbooks** | Search documentation | Links auto-attached |
| **Identify owners** | Check CODEOWNERS manually | Owners listed in card |

**Result**: 5-15 minutes saved per incident, reducing MTTR by 30-50%.

---

## Alerts and Incidents

### Understanding Alerts

An **alert** is a notification from your monitoring system that something needs attention. Incident Copilot receives alerts from:

- **PagerDuty** - via webhooks
- **Opsgenie** - via webhooks

### Alert Normalization

Different alert sources use different formats. Incident Copilot normalizes them to a standard model:

```
┌─────────────────────────────────────────────────────────────────┐
│                       ALERT NORMALIZATION                        │
│                                                                 │
│  PagerDuty Webhook              Normalized Incident             │
│  ┌─────────────────────┐        ┌─────────────────────┐         │
│  │ incident_number     │───────▶│ incident_id         │         │
│  │ title               │───────▶│ title               │         │
│  │ urgency             │───────▶│ severity            │         │
│  │ service.name        │───────▶│ service_name        │         │
│  │ created_at          │───────▶│ triggered_at        │         │
│  │ html_url            │───────▶│ alert_url           │         │
│  └─────────────────────┘        └─────────────────────┘         │
│                                                                 │
│  Opsgenie Webhook                                               │
│  ┌─────────────────────┐                                        │
│  │ alertId             │───────▶│ incident_id         │         │
│  │ message             │───────▶│ title               │         │
│  │ priority (P1-P5)    │───────▶│ severity            │         │
│  │ tags[service=...]   │───────▶│ service_name        │         │
│  │ createdAt           │───────▶│ triggered_at        │         │
│  └─────────────────────┘                                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Severity Levels

Incident Copilot uses five severity levels:

| Severity | PagerDuty | Opsgenie | Meaning |
|----------|-----------|----------|---------|
| **CRITICAL** | High (urgent) | P1 | Immediate response required |
| **HIGH** | High | P2 | Urgent attention needed |
| **MEDIUM** | Low | P3 | Standard priority |
| **LOW** | Low | P4 | Can be addressed during business hours |
| **INFO** | Low | P5 | Informational, no action required |

---

## Context Assembly

Context assembly is the core of Incident Copilot. When an alert arrives, the **orchestrator** coordinates fetching data from multiple sources in parallel.

### The Orchestration Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CONTEXT ASSEMBLY                                   │
│                                                                             │
│  Incoming Alert                                                             │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         ORCHESTRATOR                                │    │
│  │                                                                     │    │
│  │  1. Parse and validate alert                                        │    │
│  │  2. Extract service name                                            │    │
│  │  3. Fan-out to data sources (parallel)                              │    │
│  │  4. Wait for results (timeout: 8 seconds)                           │    │
│  │  5. Run AI summarization                                            │    │
│  │  6. Assemble context card                                           │    │
│  │  7. Deliver to Slack/Teams                                          │    │
│  │                                                                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│       │                                                                     │
│       │  Step 3: Parallel Fan-out                                          │
│       │                                                                     │
│       ├─────────────────┬─────────────────┬─────────────────┐               │
│       │                 │                 │                 │               │
│       ▼                 ▼                 ▼                 ▼               │
│  ┌─────────┐      ┌─────────┐      ┌─────────┐      ┌─────────┐            │
│  │ GitHub/ │      │ Datadog/│      │ On-Call │      │ Runbook │            │
│  │ GitLab  │      │CloudWatch│     │ Roster  │      │ Linker  │            │
│  │         │      │         │      │         │      │         │            │
│  │ Commits │      │ Logs    │      │ People  │      │ Links   │            │
│  │ Owners  │      │ Metrics │      │         │      │         │            │
│  └────┬────┘      └────┬────┘      └────┬────┘      └────┬────┘            │
│       │                │                │                │                  │
│       └────────────────┴────────────────┴────────────────┘                  │
│                               │                                             │
│                               ▼                                             │
│                        ┌─────────────┐                                      │
│                        │  AI Summary │ (if logs available)                  │
│                        └──────┬──────┘                                      │
│                               │                                             │
│                               ▼                                             │
│                        ┌─────────────┐                                      │
│                        │Context Card │                                      │
│                        └──────┬──────┘                                      │
│                               │                                             │
│                    ┌──────────┴──────────┐                                  │
│                    ▼                     ▼                                  │
│              ┌───────────┐         ┌───────────┐                            │
│              │   Slack   │         │   Teams   │                            │
│              └───────────┘         └───────────┘                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Timeout Handling

Each data source has a timeout to ensure fast delivery:

| Source | Timeout | On Failure |
|--------|---------|------------|
| GitHub/GitLab | 8 sec | Card delivered without deploy info |
| Datadog/CloudWatch | 8 sec | Card delivered without logs |
| AI Summarization | 5 sec | Card delivered without AI summary |
| Slack Delivery | 5 sec | Error logged, retry queued |

**Key principle**: Partial context is better than no context. If one source fails, the card is still delivered with available data.

### Graceful Degradation

```
┌────────────────────────────────────────────────────────────────┐
│                  GRACEFUL DEGRADATION                          │
│                                                                │
│  Scenario 1: GitHub API down                                   │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ 🟠 payments-api: High Error Rate                        │    │
│  ├────────────────────────────────────────────────────────┤    │
│  │ ⚠️ GitHub: Connection timeout                           │    │
│  │                                                        │    │
│  │ 📋 Log Analysis:                                        │    │
│  │ • ConnectionTimeout to stripe-api (847x)               │    │
│  │ • Retry limit exceeded (612x)                          │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                                │
│  Scenario 2: All sources succeed                               │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ 🟠 payments-api: High Error Rate                        │    │
│  ├────────────────────────────────────────────────────────┤    │
│  │ 🚀 Recent Deployments:                                  │    │
│  │ • abc1234 by @sarah - Fix retry logic (2h ago)         │    │
│  │                                                        │    │
│  │ 📋 Log Analysis:                                        │    │
│  │ • ConnectionTimeout to stripe-api (847x)               │    │
│  │ • Retry limit exceeded (612x)                          │    │
│  │                                                        │    │
│  │ 💡 AI Summary: The service is experiencing timeouts... │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## The Context Card

The context card is the primary output of Incident Copilot—a rich, formatted message delivered to your notification channel.

### Anatomy of a Context Card

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CONTEXT CARD ANATOMY                               │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ 🟠 payments-api: High Error Rate                            ← Header  │  │
│  ├───────────────────────────────────────────────────────────────────────┤  │
│  │ Severity: HIGH  |  Triggered: 02:47 UTC  |  View in PagerDuty        │  │
│  │                                                                 ↑     │  │
│  │                                                          Alert Info   │  │
│  ├───────────────────────────────────────────────────────────────────────┤  │
│  │ 🚀 Recent Deployments:                              ← GitHub Context  │  │
│  │ • abc1234 by @sarah - Fix retry logic (2h ago)                       │  │
│  │ • def5678 by @mike - Update dependencies (8h ago)                    │  │
│  ├───────────────────────────────────────────────────────────────────────┤  │
│  │ 📋 Top Issues (AI Analysis):                        ← Log Analysis   │  │
│  │ • ConnectionTimeout to stripe-api (847x)                             │  │
│  │ • Retry limit exceeded (612x)                                        │  │
│  │ • Payment processing failed (423x)                                   │  │
│  │                                                                       │  │
│  │ 💡 The service is experiencing connection timeouts when calling      │  │
│  │    Stripe's API. This started approximately 2 hours ago, coinciding  │  │
│  │    with the retry logic deployment. The retry configuration may be   │  │
│  │    causing connection pool exhaustion.                               │  │
│  │                                                     ↑ AI Summary      │  │
│  ├───────────────────────────────────────────────────────────────────────┤  │
│  │ 📚 Runbooks:                                        ← Runbook Links  │  │
│  │ • Stripe API Timeout Playbook (95% match)                            │  │
│  │ • Payment System Recovery Guide (78% match)                          │  │
│  ├───────────────────────────────────────────────────────────────────────┤  │
│  │ 👤 On-Call: @alice, @bob                           ← On-Call Roster  │  │
│  │ 👥 Owners: @payments-team                          ← Code Owners     │  │
│  │ 📊 Dashboard  |  📖 Full Runbook                   ← Quick Links     │  │
│  ├───────────────────────────────────────────────────────────────────────┤  │
│  │ Context assembled in 3420ms                        ← Performance     │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Card Components

| Component | Source | Purpose |
|-----------|--------|---------|
| **Header** | Alert | Service name and alert title with severity indicator |
| **Alert Info** | Alert | Severity, timestamp, link to alerting tool |
| **Recent Deployments** | GitHub/GitLab | Last 3-5 commits to identify potential causes |
| **Log Analysis** | Datadog/CloudWatch | Grouped error patterns with counts |
| **AI Summary** | Claude | Intelligent analysis and suggested actions |
| **Runbooks** | Runbook Index | Relevant documentation links |
| **On-Call** | PagerDuty/Opsgenie | Current on-call engineers |
| **Owners** | CODEOWNERS | Service owners from repository |
| **Performance** | Internal | Assembly time for monitoring |

---

## Integrations

Incident Copilot connects to multiple external systems. These are organized by function:

### Integration Categories

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          INTEGRATION CATEGORIES                             │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         ALERT SOURCES                               │    │
│  │                     (Required - choose one)                         │    │
│  │                                                                     │    │
│  │    ┌──────────────┐        ┌──────────────┐                         │    │
│  │    │  PagerDuty   │        │   Opsgenie   │                         │    │
│  │    └──────────────┘        └──────────────┘                         │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                       SOURCE CONTROL                                │    │
│  │                      (Recommended)                                  │    │
│  │                                                                     │    │
│  │    ┌──────────────┐        ┌──────────────┐                         │    │
│  │    │    GitHub    │        │    GitLab    │                         │    │
│  │    └──────────────┘        └──────────────┘                         │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        LOG PROVIDERS                                │    │
│  │                      (Recommended)                                  │    │
│  │                                                                     │    │
│  │  ┌────────┐  ┌──────────┐  ┌──────┐  ┌────────┐  ┌─────────────┐   │    │
│  │  │Datadog │  │CloudWatch│  │ Loki │  │ Splunk │  │Elasticsearch│   │    │
│  │  └────────┘  └──────────┘  └──────┘  └────────┘  └─────────────┘   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      NOTIFICATIONS                                  │    │
│  │                   (Required - choose one+)                          │    │
│  │                                                                     │    │
│  │    ┌──────────────┐        ┌──────────────┐                         │    │
│  │    │    Slack     │        │    Teams     │                         │    │
│  │    └──────────────┘        └──────────────┘                         │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      ISSUE TRACKING                                 │    │
│  │                       (Optional)                                    │    │
│  │                                                                     │    │
│  │    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │    │
│  │    │     Jira     │  │    Linear    │  │  ServiceNow  │             │    │
│  │    └──────────────┘  └──────────────┘  └──────────────┘             │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow Example

```
PagerDuty Alert                  Context Card Delivery
     │                                    ▲
     ▼                                    │
┌─────────┐   service_name   ┌────────────┴────────────┐
│ Webhook │─────────────────▶│                         │
└─────────┘                  │                         │
                             │                         │
GitHub ──── recent commits ──▶                         │
                             │                         │
Datadog ─── error logs ─────▶│    Context Assembler   │────▶ Slack
                             │                         │
Runbooks ── relevant docs ──▶                         │
                             │                         │
PagerDuty ── on-call roster ▶│                         │
                             └─────────────────────────┘
```

---

## AI Summarization

Incident Copilot uses Claude (Anthropic's AI) to analyze logs and provide intelligent summaries.

### What AI Summarization Provides

1. **Top Issues**: Grouped error patterns with occurrence counts
2. **Explanation**: Human-readable description of what's happening
3. **Likely Cause**: Root cause hypothesis based on patterns
4. **Suggested Actions**: Recommended next steps

### How It Works

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          AI SUMMARIZATION                                   │
│                                                                             │
│  Input: Raw Error Logs (up to 100 entries)                                  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ [ERROR] 2024-01-15 02:45:12 ConnectionTimeout to stripe-api          │  │
│  │ [ERROR] 2024-01-15 02:45:13 ConnectionTimeout to stripe-api          │  │
│  │ [WARN]  2024-01-15 02:45:14 Retry attempt 3 of 5                     │  │
│  │ [ERROR] 2024-01-15 02:45:15 Payment processing failed: timeout       │  │
│  │ [ERROR] 2024-01-15 02:45:16 ConnectionTimeout to stripe-api          │  │
│  │ ... (95 more entries)                                                 │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│                                    ▼                                        │
│                          ┌─────────────────┐                                │
│                          │  Claude Prompt  │                                │
│                          │                 │                                │
│                          │ "Analyze these  │                                │
│                          │  error logs..." │                                │
│                          └────────┬────────┘                                │
│                                   │                                         │
│                                   ▼                                         │
│  Output: Structured Analysis                                                │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ Top Issues:                                                           │  │
│  │ • ConnectionTimeout to stripe-api (847 occurrences)                   │  │
│  │ • Retry limit exceeded (612 occurrences)                              │  │
│  │ • Payment processing failed (423 occurrences)                         │  │
│  │                                                                       │  │
│  │ Explanation:                                                          │  │
│  │ The payments-api service is experiencing widespread connection        │  │
│  │ timeouts when attempting to reach Stripe's API. The retry mechanism  │  │
│  │ is being exhausted, leading to payment failures.                     │  │
│  │                                                                       │  │
│  │ Likely Cause:                                                         │  │
│  │ Network connectivity issue or Stripe API rate limiting.              │  │
│  │                                                                       │  │
│  │ Suggested Actions:                                                    │  │
│  │ 1. Check Stripe status page for outages                              │  │
│  │ 2. Verify network connectivity to api.stripe.com                     │  │
│  │ 3. Review retry configuration in recent deploy                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Model Selection

| Model | Speed | Cost | Use Case |
|-------|-------|------|----------|
| claude-3-haiku-20240307 | Fastest | $ | Default, production recommended |
| claude-3-sonnet | Fast | $$ | More detailed analysis |
| claude-3-opus | Slower | $$$ | Complex incidents |

Configure via `AI_MODEL` environment variable.

---

## On-Call Roster

Incident Copilot can fetch and display the current on-call roster from PagerDuty or Opsgenie.

### What's Displayed

- **Primary On-Call**: The main responder
- **Escalation Path**: Secondary responders if configured
- **Contact Info**: Email and Slack mentions (if available)
- **Schedule Link**: Direct link to the schedule

### Service-to-Schedule Mapping

Map services to on-call schedules:

```bash
ONCALL_SCHEDULE_MAP='{"payments-api": "SCHEDULE123", "auth-service": "SCHEDULE456"}'
```

Or set a default:

```bash
ONCALL_SCHEDULE_ID=DEFAULT_SCHEDULE
```

---

## Runbook Linking

Incident Copilot automatically finds and links relevant runbooks to incidents.

### How Matching Works

1. **Text Analysis**: Extract keywords from incident title and description
2. **Service Matching**: Find runbooks tagged for the affected service
3. **Relevance Scoring**: Rank by similarity (0-100%)
4. **Top-K Selection**: Return the 3 most relevant runbooks

### Runbook Sources

Runbooks can come from:
- GitHub markdown files
- Confluence pages
- Notion documents
- Custom sources (via plugin)

### Example Output

```
📚 Runbooks:
• Stripe API Timeout Playbook (95% match)
• Payment System Recovery Guide (78% match)
• Database Connection Issues (45% match)
```

See [Runbooks Documentation](../runbooks.md) for setup details.

---

## Summary

| Concept | Description |
|---------|-------------|
| **Alert** | A notification from PagerDuty/Opsgenie that triggers context assembly |
| **Context Assembly** | Parallel fetch of data from multiple sources (8s timeout) |
| **Context Card** | Rich message delivered to Slack/Teams with all relevant context |
| **AI Summary** | Claude-powered analysis of error logs |
| **Graceful Degradation** | Partial context delivered if some sources fail |

---

*← [Getting Started](./getting-started.md) | [Integrations](./integrations.md) →*
