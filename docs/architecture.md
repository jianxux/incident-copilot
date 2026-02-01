# Incident Copilot Architecture

This document describes the system architecture, data flows, and design decisions behind Incident Copilot.

## System Overview

Incident Copilot is a context-aware assistant for on-call engineers. When an alert fires in PagerDuty or Opsgenie, it automatically assembles relevant context from multiple sources and delivers a rich context card to Slack within 10 seconds.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    INCIDENT COPILOT                                         │
│                                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                              INGESTION LAYER                                        │   │
│   │                                                                                     │   │
│   │    ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐        │   │
│   │    │PagerDuty │   │ Opsgenie │   │CloudWatch│   │  Custom  │   │  Manual  │        │   │
│   │    │ Webhook  │   │ Webhook  │   │  Events  │   │ Webhook  │   │Trigger API│       │   │
│   │    └────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘        │   │
│   │         │              │              │              │              │               │   │
│   │         └──────────────┴──────────────┴──────────────┴──────────────┘               │   │
│   │                                       │                                             │   │
│   │                                       ▼                                             │   │
│   │                         ┌─────────────────────────┐                                 │   │
│   │                         │    Webhook Router       │                                 │   │
│   │                         │  - Signature Verify     │                                 │   │
│   │                         │  - Payload Parse        │                                 │   │
│   │                         │  - Normalize Alert      │                                 │   │
│   │                         └───────────┬─────────────┘                                 │   │
│   └─────────────────────────────────────┼───────────────────────────────────────────────┘   │
│                                         │                                                   │
│   ┌─────────────────────────────────────┼───────────────────────────────────────────────┐   │
│   │                                     │        ORCHESTRATION LAYER                    │   │
│   │                                     ▼                                               │   │
│   │                       ┌─────────────────────────┐                                   │   │
│   │                       │      Orchestrator       │                                   │   │
│   │                       │   - Context Assembly    │                                   │   │
│   │                       │   - Parallel Fan-out    │                                   │   │
│   │                       │   - Result Merging      │                                   │   │
│   │                       └───────────┬─────────────┘                                   │   │
│   │                                   │                                                 │   │
│   │         ┌─────────────────────────┼─────────────────────────┐                       │   │
│   │         │                         │                         │                       │   │
│   │         ▼                         ▼                         ▼                       │   │
│   │   ┌───────────┐            ┌───────────┐            ┌───────────┐                   │   │
│   │   │  GitHub   │            │Log Provider│           │  Runbook  │                   │   │
│   │   │  Adapter  │            │  Adapter   │           │  Linker   │                   │   │
│   │   └─────┬─────┘            └─────┬─────┘            └─────┬─────┘                   │   │
│   │         │                        │                        │                         │   │
│   │         │                  ┌─────┴─────┐                  │                         │   │
│   │         │                  │           │                  │                         │   │
│   │         │            ┌─────┴───┐ ┌─────┴───┐              │                         │   │
│   │         │            │ Datadog │ │CloudWatch│             │                         │   │
│   │         │            └─────────┘ └─────────┘              │                         │   │
│   │         │                  │                              │                         │   │
│   │         │                  ▼                              │                         │   │
│   │         │           ┌───────────┐                         │                         │   │
│   │         │           │    AI     │                         │                         │   │
│   │         │           │Summarizer │                         │                         │   │
│   │         │           │ (Claude)  │                         │                         │   │
│   │         │           └─────┬─────┘                         │                         │   │
│   │         │                 │                               │                         │   │
│   │         └─────────────────┼───────────────────────────────┘                         │   │
│   │                           │                                                         │   │
│   │                           ▼                                                         │   │
│   │                 ┌───────────────────┐                                               │   │
│   │                 │  Context Card     │                                               │   │
│   │                 │  Builder          │                                               │   │
│   │                 └─────────┬─────────┘                                               │   │
│   └───────────────────────────┼─────────────────────────────────────────────────────────┘   │
│                               │                                                             │
│   ┌───────────────────────────┼─────────────────────────────────────────────────────────┐   │
│   │                           │              DELIVERY LAYER                             │   │
│   │                           ▼                                                         │   │
│   │                 ┌───────────────────┐                                               │   │
│   │                 │  Delivery Manager │                                               │   │
│   │                 └─────────┬─────────┘                                               │   │
│   │                           │                                                         │   │
│   │         ┌─────────────────┼─────────────────┐                                       │   │
│   │         │                 │                 │                                       │   │
│   │         ▼                 ▼                 ▼                                       │   │
│   │   ┌───────────┐    ┌───────────┐    ┌───────────┐                                   │   │
│   │   │   Slack   │    │   Teams   │    │  Web UI   │                                   │   │
│   │   │  Adapter  │    │  Adapter  │    │  (Future) │                                   │   │
│   │   └───────────┘    └───────────┘    └───────────┘                                   │   │
│   │                                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                              STORAGE LAYER (Future)                                 │   │
│   │                                                                                     │   │
│   │    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │   │
│   │    │  PostgreSQL  │    │    Redis     │    │Vector Store  │    │ Blob Storage │     │   │
│   │    │  (Incidents) │    │   (Cache)    │    │ (Similarity) │    │  (Artifacts) │     │   │
│   │    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘     │   │
│   │                                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                             │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### 1. Alert Ingestion

When an alert fires in PagerDuty or Opsgenie, a webhook is sent to Incident Copilot:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            ALERT INGESTION                                   │
│                                                                              │
│    PagerDuty/Opsgenie                                                        │
│           │                                                                  │
│           │  POST /webhooks/pagerduty                                        │
│           │  {                                                               │
│           │    "event": {                                                    │
│           │      "event_type": "incident.triggered",                         │
│           │      "data": { ... }                                             │
│           │    }                                                             │
│           │  }                                                               │
│           ▼                                                                  │
│    ┌─────────────────┐                                                       │
│    │ Signature Check │ ◄── HMAC-SHA256 verification                          │
│    └────────┬────────┘                                                       │
│             │                                                                │
│             ▼                                                                │
│    ┌─────────────────┐                                                       │
│    │  Parse Payload  │ ◄── Extract incident metadata                         │
│    └────────┬────────┘                                                       │
│             │                                                                │
│             ▼                                                                │
│    ┌─────────────────┐                                                       │
│    │   Normalize     │ ◄── Convert to internal Incident model                │
│    └────────┬────────┘                                                       │
│             │                                                                │
│             │  Incident {                                                    │
│             │    id: "Q0JBXQZ7T8QXXX",                                        │
│             │    service: "payments-api",                                    │
│             │    severity: "high",                                           │
│             │    title: "High Error Rate"                                    │
│             │  }                                                             │
│             │                                                                │
│             ▼                                                                │
│    ┌─────────────────┐                                                       │
│    │ Background Task │ ◄── Returns 200 immediately, processes async          │
│    └─────────────────┘                                                       │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Key Design Decisions:**
- **Async Processing**: Webhook returns 200 immediately, processing happens in background
- **Signature Verification**: All webhooks are verified before processing
- **Normalization**: Different alert sources are converted to a unified internal model

### 2. Context Assembly (Parallel Fan-out)

The orchestrator fetches context from multiple sources in parallel:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         CONTEXT ASSEMBLY                                     │
│                                                                              │
│                         Incident                                             │
│                            │                                                 │
│                            ▼                                                 │
│                    ┌───────────────┐                                         │
│                    │  Orchestrator │                                         │
│                    └───────┬───────┘                                         │
│                            │                                                 │
│          ┌─────────────────┼─────────────────┐                               │
│          │                 │                 │                               │
│          ▼                 ▼                 ▼                               │
│    ┌──────────┐     ┌──────────┐     ┌──────────┐                            │
│    │  GitHub  │     │ Datadog/ │     │ Runbook  │   ◄── Parallel requests    │
│    │   API    │     │CloudWatch│     │  Index   │       (asyncio.gather)     │
│    └────┬─────┘     └────┬─────┘     └────┬─────┘                            │
│         │                │                │                                  │
│     ◄───┼────────────────┼────────────────┼───►  Timeout: 8 seconds          │
│         │                │                │                                  │
│         ▼                ▼                ▼                                  │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐                               │
│   │ Recent   │    │  Error   │    │ Matching │                               │
│   │ Commits  │    │   Logs   │    │ Runbook  │                               │
│   │CODEOWNERS│    │ Metrics  │    │          │                               │
│   └──────────┘    └────┬─────┘    └──────────┘                               │
│                        │                                                     │
│                        ▼                                                     │
│                 ┌──────────────┐                                             │
│                 │      AI      │    ◄── Claude API (streaming)               │
│                 │  Summarizer  │        Timeout: 5 seconds                   │
│                 └──────────────┘                                             │
│                        │                                                     │
│                        ▼                                                     │
│                 ┌──────────────┐                                             │
│                 │    Merge     │    ◄── Combine all results                  │
│                 │   Results    │        Handle partial failures              │
│                 └──────────────┘                                             │
│                        │                                                     │
│                        ▼                                                     │
│                  Context Card                                                │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Key Design Decisions:**
- **Parallel Execution**: All external calls happen concurrently using `asyncio.gather`
- **Timeout Handling**: Each source has a timeout; partial results are still useful
- **Graceful Degradation**: If one source fails, the card is still delivered with available data

### 3. AI Summarization

Logs are processed by Claude to extract actionable insights:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         AI SUMMARIZATION                                     │
│                                                                              │
│   Raw Logs (up to 100 entries)                                               │
│   ┌────────────────────────────────────────┐                                 │
│   │ [ERROR] ConnectionTimeout to stripe... │                                 │
│   │ [ERROR] ConnectionTimeout to stripe... │                                 │
│   │ [WARN] Retry attempt 3 of 5...         │                                 │
│   │ [ERROR] Payment processing failed...   │                                 │
│   │ ...                                    │                                 │
│   └────────────────────────────────────────┘                                 │
│                     │                                                        │
│                     ▼                                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐    │
│   │                    Prompt Construction                              │    │
│   │                                                                     │    │
│   │   "Analyze these error logs from {service}. Identify:               │    │
│   │    1. Top 3-5 error patterns with counts                            │    │
│   │    2. Brief explanation of what's happening                         │    │
│   │    3. Most likely cause                                             │    │
│   │    4. Suggested actions (2-3 bullets)                               │    │
│   │                                                                     │    │
│   │    Keep response concise for Slack."                                │    │
│   └─────────────────────────────────────────────────────────────────────┘    │
│                     │                                                        │
│                     ▼                                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐    │
│   │                    Claude API (Haiku)                               │    │
│   │                    - Streaming response                             │    │
│   │                    - ~500 token output                              │    │
│   │                    - Timeout: 5 seconds                             │    │
│   └─────────────────────────────────────────────────────────────────────┘    │
│                     │                                                        │
│                     ▼                                                        │
│   ┌────────────────────────────────────────┐                                 │
│   │ AI Summary:                            │                                 │
│   │ - top_issues: [...]                    │                                 │
│   │ - explanation: "..."                   │                                 │
│   │ - likely_cause: "..."                  │                                 │
│   │ - suggested_actions: [...]             │                                 │
│   └────────────────────────────────────────┘                                 │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Key Design Decisions:**
- **Model Choice**: Claude 3 Haiku for speed and cost efficiency
- **Prompt Engineering**: Structured output for consistent parsing
- **Token Limits**: Input truncated to fit context window, output limited for Slack

### 4. Delivery

The assembled context card is formatted and delivered to Slack:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              DELIVERY                                        │
│                                                                              │
│   Context Card                                                               │
│        │                                                                     │
│        ▼                                                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐    │
│   │                    Block Kit Builder                                │    │
│   │                                                                     │    │
│   │   Convert ContextCard → Slack Block Kit format                      │    │
│   │   - Header with severity emoji                                      │    │
│   │   - Sections for deploys, logs, AI summary                          │    │
│   │   - Context with owners, runbook links                              │    │
│   │   - Footer with timing metadata                                     │    │
│   └─────────────────────────────────────────────────────────────────────┘    │
│        │                                                                     │
│        ▼                                                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐    │
│   │                    Slack API                                        │    │
│   │                                                                     │    │
│   │   POST chat.postMessage                                             │    │
│   │   - channel: #incidents (or service-specific)                       │    │
│   │   - blocks: [...]                                                   │    │
│   │   - unfurl_links: false                                             │    │
│   └─────────────────────────────────────────────────────────────────────┘    │
│        │                                                                     │
│        ▼                                                                     │
│   ┌────────────────────────────────────────────────────────────────┐         │
│   │ 🟠 payments-api: High Error Rate                               │         │
│   ├────────────────────────────────────────────────────────────────┤         │
│   │ Severity: HIGH  |  Triggered: 02:47  |  View in PagerDuty      │         │
│   ├────────────────────────────────────────────────────────────────┤         │
│   │ 🚀 Recent Deployments:                                         │         │
│   │ • abc1234 by @sarah - Fix retry logic                          │         │
│   ├────────────────────────────────────────────────────────────────┤         │
│   │ 📋 Top Issues (AI Analysis):                                   │         │
│   │ • ConnectionTimeout to stripe-api (847x)                       │         │
│   │ • Retry limit exceeded (612x)                                  │         │
│   │                                                                │         │
│   │ The service is experiencing timeouts when connecting to        │         │
│   │ Stripe's API...                                                │         │
│   ├────────────────────────────────────────────────────────────────┤         │
│   │ Owners: @sarah, @mike  |  📖 Runbook  |  📊 Dashboard          │         │
│   │ Context assembled in 3420ms                                    │         │
│   └────────────────────────────────────────────────────────────────┘         │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Descriptions

### Core Components

| Component | Location | Responsibility |
|-----------|----------|----------------|
| **FastAPI App** | `src/main.py` | HTTP server, routing, middleware |
| **Webhook Router** | `src/api/webhooks.py` | Receive and validate webhooks |
| **Orchestrator** | `src/orchestrator.py` | Coordinate context assembly |
| **AI Summarizer** | `src/ai/summarizer.py` | Log analysis with Claude |
| **Config** | `src/config.py` | Environment-based settings |
| **Models** | `src/models.py` | Pydantic data models |

### Integration Adapters

| Adapter | Location | External Service |
|---------|----------|------------------|
| **PagerDutyAdapter** | `src/integrations/pagerduty.py` | PagerDuty webhooks & API |
| **OpsgenieAdapter** | `src/integrations/opsgenie.py` | Opsgenie webhooks & API |
| **GitHubAdapter** | `src/integrations/github.py` | GitHub REST API |
| **DatadogAdapter** | `src/integrations/datadog.py` | Datadog Logs & Metrics API |
| **CloudWatchAdapter** | `src/integrations/cloudwatch.py` | AWS CloudWatch Logs |
| **SlackAdapter** | `src/integrations/slack.py` | Slack Web API |

### Data Models

```python
# Core models (src/models.py)

class PagerDutyIncident:
    """Normalized incident from PagerDuty webhook."""
    incident_id: str
    title: str
    severity: Severity
    service_name: str
    triggered_at: datetime

class ContextCard:
    """Assembled context delivered to Slack."""
    incident_id: str
    github: GitHubContext | None
    datadog: DatadogContext | None
    ai_summary: AILogSummary | None
    assembly_time_ms: int

class AILogSummary:
    """AI-generated log analysis."""
    top_issues: list[str]
    explanation: str
    likely_cause: str | None
    suggested_actions: list[str]
```

---

## Performance Targets

| Operation | Target | Budget |
|-----------|--------|--------|
| **End-to-end latency** | <10s | Total time from webhook to Slack message |
| Webhook handling | <100ms | Validate, parse, queue for background |
| GitHub API | <2s | Fetch commits + CODEOWNERS |
| Datadog/CloudWatch API | <5s | Fetch logs + metrics |
| AI Summarization | <3s | Claude API call |
| Slack delivery | <1s | Post message |
| **Total assembly** | <8s | Sum of parallel + sequential steps |

### Timeout Strategy

```python
# Orchestrator timeouts
CONTEXT_FETCH_TIMEOUT = 8.0  # seconds for GitHub + Datadog in parallel
AI_SUMMARIZE_TIMEOUT = 5.0   # seconds for Claude API
SLACK_SEND_TIMEOUT = 5.0     # seconds for Slack API
```

---

## Scalability Considerations

### Current Architecture (MVP)

- **Single process**: Uvicorn with async handlers
- **Stateless**: No persistent state between requests
- **In-memory**: No caching layer
- **SQLite**: Local database for incident history

**Suitable for**: Small teams, <100 alerts/day

### Scaling to Production

#### Horizontal Scaling

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         LOAD BALANCER                                   │
│                     (nginx / ALB / Traefik)                             │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
           ┌─────────────────┼─────────────────┐
           │                 │                 │
      ┌────▼────┐       ┌────▼────┐       ┌────▼────┐
      │  API 1  │       │  API 2  │       │  API 3  │
      │(Uvicorn)│       │(Uvicorn)│       │(Uvicorn)│
      └────┬────┘       └────┬────┘       └────┬────┘
           │                 │                 │
           └─────────────────┼─────────────────┘
                             │
           ┌─────────────────┼─────────────────┐
           │                 │                 │
      ┌────▼────┐       ┌────▼────┐       ┌────▼────┐
      │  Redis  │       │Postgres │       │ Vector  │
      │ (Cache) │       │ (Data)  │       │ (Search)│
      └─────────┘       └─────────┘       └─────────┘
```

#### Caching Strategy

| Cache | Key | TTL | Purpose |
|-------|-----|-----|---------|
| GitHub commits | `github:{repo}:commits` | 5 min | Reduce API calls |
| CODEOWNERS | `github:{repo}:codeowners` | 1 hour | Rarely changes |
| Runbook index | `runbooks:index` | 15 min | Search performance |
| Rate limit counters | `ratelimit:{api}:{key}` | 1 min | API rate limiting |

#### Queue-Based Processing

For high volume (>1000 alerts/day):

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Webhook   │────▶│   Redis     │────▶│   Worker    │
│   Handler   │     │   Queue     │     │   Process   │
└─────────────┘     └─────────────┘     └─────────────┘
       │                                       │
       ▼                                       ▼
   Return 200                          Process incident
   immediately                         Send to Slack
```

Benefits:
- Webhook response time <50ms
- Retry failed jobs automatically
- Scale workers independently
- Handle burst traffic

### Database Schema (Production)

```sql
-- Incidents table
CREATE TABLE incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id TEXT NOT NULL,
    source TEXT NOT NULL,              -- 'pagerduty', 'opsgenie'
    service TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    triggered_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    context_card_json JSONB,           -- Full card for replay
    embedding vector(1536),            -- For similarity search
    created_at TIMESTAMPTZ DEFAULT now(),
    
    CONSTRAINT unique_external_incident UNIQUE (source, external_id)
);

CREATE INDEX idx_incidents_service ON incidents(service);
CREATE INDEX idx_incidents_triggered ON incidents(triggered_at DESC);

-- Context cards (for audit/replay)
CREATE TABLE context_cards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID REFERENCES incidents(id),
    version INT DEFAULT 1,
    card_json JSONB NOT NULL,
    assembly_time_ms INT,
    delivered_at TIMESTAMPTZ,
    delivery_channel TEXT,             -- 'slack', 'teams'
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Runbook index
CREATE TABLE runbooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,              -- 'github', 'confluence', 'notion'
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    services TEXT[],
    keywords TEXT[],
    content_hash TEXT,                 -- For change detection
    updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_runbooks_services ON runbooks USING GIN(services);
CREATE INDEX idx_runbooks_keywords ON runbooks USING GIN(keywords);
```

---

## Security Considerations

### Authentication & Authorization

| Layer | Mechanism | Notes |
|-------|-----------|-------|
| Webhooks | HMAC signature | Verify source authenticity |
| API Keys | Environment variables | Never logged or exposed |
| Internal APIs | Network isolation | Deploy in private subnet |
| Slack | Bot OAuth token | Minimal required scopes |

### Secrets Management

```yaml
# Production: Use secrets manager
# AWS Secrets Manager / HashiCorp Vault / GCP Secret Manager

secrets:
  pagerduty_webhook_secret:
    source: aws_secrets_manager
    name: incident-copilot/pagerduty
    
  github_token:
    source: aws_secrets_manager
    name: incident-copilot/github
```

### Data Handling

| Data Type | Sensitivity | Handling |
|-----------|-------------|----------|
| Log messages | Medium-High | Truncate, don't persist raw |
| API keys | Critical | Encrypt at rest, rotate regularly |
| Incident titles | Low-Medium | OK to log and display |
| User emails | Medium | Minimize collection |

### Network Security

```
┌─────────────────────────────────────────────────────────────────────┐
│                         VPC / Private Network                       │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │                    Public Subnet                            │   │
│   │                                                             │   │
│   │   ┌─────────────┐                                           │   │
│   │   │    ALB      │ ◄── HTTPS only, WAF rules                 │   │
│   │   └──────┬──────┘                                           │   │
│   │          │                                                  │   │
│   └──────────┼──────────────────────────────────────────────────┘   │
│              │                                                      │
│   ┌──────────┼──────────────────────────────────────────────────┐   │
│   │          │          Private Subnet                          │   │
│   │          ▼                                                  │   │
│   │   ┌─────────────┐                                           │   │
│   │   │ API Servers │ ◄── No public IP                          │   │
│   │   └──────┬──────┘                                           │   │
│   │          │                                                  │   │
│   │          ▼                                                  │   │
│   │   ┌─────────────┐                                           │   │
│   │   │  Database   │ ◄── Private subnet only                   │   │
│   │   └─────────────┘                                           │   │
│   │                                                             │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│   Outbound: NAT Gateway → External APIs                             │
│   (GitHub, Datadog, Slack, Anthropic)                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Future Architecture Considerations

### Multi-Tenant SaaS

For a hosted SaaS version:

- **Tenant isolation**: Separate databases or schema-per-tenant
- **API authentication**: OAuth2 / API keys for each tenant
- **Rate limiting**: Per-tenant quotas
- **Data residency**: Region-specific deployments

### Real-Time Updates

For live incident tracking:

- **WebSocket connections**: Stream updates to web UI
- **Event sourcing**: Append-only incident events
- **SSE (Server-Sent Events)**: Alternative to WebSockets

### ML Enhancements

- **Similarity search**: Vector embeddings for past incident matching
- **Anomaly detection**: Baseline metrics, alert on deviations
- **Auto-remediation**: Suggested actions → one-click execution

---

*Architecture version: 2.0*
*Last updated: January 2026*
