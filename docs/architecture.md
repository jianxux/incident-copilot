# Incident Copilot Architecture

> Comprehensive system architecture documentation for the Incident Copilot platform.

## Table of Contents

1. [System Overview](#system-overview)
2. [System Diagram](#system-diagram)
3. [Layer Architecture](#layer-architecture)
4. [Module Dependency Rules](#module-dependency-rules)
5. [Data Flow](#data-flow)
6. [Directory Structure](#directory-structure)
7. [Key Design Decisions](#key-design-decisions)
8. [Configuration](#configuration)
9. [Testing Strategy](#testing-strategy)

---

## System Overview

Incident Copilot is a context-aware assistant for on-call engineers. When an incident is triggered, it automatically assembles relevant context (logs, metrics, recent deploys, service dependencies, similar past incidents) and delivers it to the responder within seconds.

**Core principles:**
- **Speed**: Context delivered in <10 seconds
- **Read-only**: No automated remediation, analysis only
- **Pluggable**: Easy to add new integrations
- **Cost-efficient**: Target $0.02-0.05 per incident via smart compression

---

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                 INCIDENT COPILOT                                     │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                            INGESTION LAYER                                   │    │
│  │                                                                              │    │
│  │    ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │    │
│  │    │PagerDuty │  │Opsgenie  │  │CloudWatch│  │Prometheus│  │ Custom   │    │    │
│  │    │ Webhook  │  │ Webhook  │  │  Alarms  │  │AlertMgr  │  │ Webhook  │    │    │
│  │    └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │    │
│  │         │             │             │             │             │          │    │
│  │         └─────────────┴─────────────┴─────────────┴─────────────┘          │    │
│  │                                     │                                       │    │
│  │                              src/api/webhooks.py                            │    │
│  └─────────────────────────────────────┼───────────────────────────────────────┘    │
│                                        │                                             │
│                                        ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                          ORCHESTRATION LAYER                                 │    │
│  │                                                                              │    │
│  │                         src/orchestrator.py                                  │    │
│  │                                                                              │    │
│  │    ┌─────────────────────────────────────────────────────────────────┐      │    │
│  │    │              process_incident()                                  │      │    │
│  │    │                                                                  │      │    │
│  │    │   ┌───────────┬───────────┬───────────┬───────────┐             │      │    │
│  │    │   │  SCM      │  Logs     │  On-Call  │  Topology │  8s timeout │      │    │
│  │    │   │  Context  │  Context  │  Context  │  Context  │  parallel   │      │    │
│  │    │   └───────────┴───────────┴───────────┴───────────┘             │      │    │
│  │    └─────────────────────────────────────────────────────────────────┘      │    │
│  └─────────────────────────────────────┼───────────────────────────────────────┘    │
│                                        │                                             │
│            ┌───────────────────────────┼───────────────────────────┐                │
│            │                           │                           │                │
│            ▼                           ▼                           ▼                │
│  ┌─────────────────┐       ┌─────────────────────┐       ┌─────────────────┐       │
│  │  INTEGRATION    │       │      AI LAYER       │       │   KNOWLEDGE     │       │
│  │     LAYER       │       │                     │       │     LAYER       │       │
│  │                 │       │  src/ai/            │       │                 │       │
│  │ src/integrations│       │  ├─ log_compressor  │       │ src/runbooks/   │       │
│  │ ├─ datadog.py   │       │  ├─ summarizer.py   │       │ src/similarity/ │       │
│  │ ├─ github.py    │       │  └─ copilot.py      │       │ src/insights/   │       │
│  │ ├─ pagerduty/   │       │                     │       │                 │       │
│  │ ├─ cloudwatch.py│       │  Uses:              │       │ Provides:       │       │
│  │ ├─ loki.py      │       │  - Haiku (compress) │       │ - Past incidents│       │
│  │ └─ slack.py     │       │  - Sonnet (analyze) │       │ - Runbooks      │       │
│  └─────────────────┘       └─────────────────────┘       │ - Patterns      │       │
│            │                           │                 └─────────────────┘       │
│            │                           │                           │                │
│            └───────────────────────────┼───────────────────────────┘                │
│                                        │                                             │
│                                        ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                           DOMAIN LAYER                                       │    │
│  │                                                                              │    │
│  │  src/dependencies/     src/analytics/      src/correlation/                 │    │
│  │  ├─ graph.py           ├─ tracker.py       ├─ engine.py                     │    │
│  │  ├─ service.py         └─ store.py         └─ store.py                      │    │
│  │  └─ discovery.py                                                             │    │
│  │                                                                              │    │
│  │  src/postmortem/       src/escalation/     src/maintenance/                 │    │
│  │  ├─ generator.py       ├─ engine.py        └─ scheduler.py                  │    │
│  │  └─ templates.py       └─ service.py                                         │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                        │                                             │
│                                        ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                            OUTPUT LAYER                                      │    │
│  │                                                                              │    │
│  │     models.ContextCard  ──────►  Slack / Teams / Email / Webhook            │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Layer Architecture

### 1. Ingestion Layer (`src/api/`)
Receives webhooks from alerting platforms and normalizes them into internal events.

| Component | Responsibility |
|-----------|---------------|
| `webhooks.py` | Webhook endpoints for PagerDuty, Opsgenie, etc. |
| `health.py` | Health check, readiness, liveness probes |
| `routes.py` | REST API for UI and integrations |

### 2. Orchestration Layer (`src/orchestrator.py`)
Central coordinator that fans out to integrations and assembles the context card.

- **Parallel fetching** with 8-second timeout
- **Graceful degradation** if any source fails
- **Log compression** before LLM calls

### 3. Integration Layer (`src/integrations/`)
Adapters for external services. Each implements a common interface.

| Integration | Purpose |
|-------------|---------|
| `datadog.py` | Logs, metrics, dashboards |
| `cloudwatch.py` | AWS logs and metrics |
| `loki.py` | Grafana Loki logs |
| `splunk.py` | Splunk logs |
| `github.py` | Recent deploys, CODEOWNERS, PR links |
| `gitlab.py` | GitLab CI/CD, merge requests |
| `pagerduty/` | Incident details, on-call schedule |
| `opsgenie.py` | Opsgenie alerts and schedules |
| `slack.py` | Message delivery |
| `teams.py` | MS Teams delivery |

### 4. AI Layer (`src/ai/`)
LLM-powered intelligence.

| Component | Model | Purpose |
|-----------|-------|---------|
| `log_compressor.py` | Haiku | Compress logs before analysis |
| `summarizer.py` | Sonnet | Generate incident summaries |
| `copilot.py` | Sonnet | Interactive chat assistant |

### 5. Knowledge Layer
Historical and contextual knowledge.

| Component | Purpose |
|-----------|---------|
| `src/runbooks/` | Match runbooks to incidents |
| `src/similarity/` | Find similar past incidents |
| `src/insights/` | Pattern detection across incidents |

### 6. Domain Layer
Core business logic modules.

| Component | Purpose |
|-----------|---------|
| `src/dependencies/` | Service topology graph |
| `src/analytics/` | MTTR, MTTA, metrics |
| `src/correlation/` | Alert deduplication |
| `src/postmortem/` | Post-incident reports |
| `src/escalation/` | Escalation policies |

---

## Module Dependency Rules

### Import Rules Matrix

```
                          CAN IMPORT FROM →
                    ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┐
                    │model│confg│utils│integ│orch │ ai  │ api │
    ┌───────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
    │ models.py     │  -  │  ✗  │  ✗  │  ✗  │  ✗  │  ✗  │  ✗  │
    │ config.py     │  ✓  │  -  │  ✗  │  ✗  │  ✗  │  ✗  │  ✗  │
    │ utils/        │  ✓  │  ✓  │  -  │  ✗  │  ✗  │  ✗  │  ✗  │
I   │ integrations/ │  ✓  │  ✓  │  ✓  │  -  │  ✗  │  ✗  │  ✗  │
M   │ ai/           │  ✓  │  ✓  │  ✓  │  ✗  │  ✗  │  -  │  ✗  │
P   │ dependencies/ │  ✓  │  ✓  │  ✓  │  ✗  │  ✗  │  ✗  │  ✗  │
O   │ analytics/    │  ✓  │  ✓  │  ✓  │  ✗  │  ✗  │  ✗  │  ✗  │
R   │ insights/     │  ✓  │  ✓  │  ✓  │  ✗  │  ✗  │  ✓  │  ✗  │
T   │ orchestrator  │  ✓  │  ✓  │  ✓  │  ✓  │  -  │  ✓  │  ✗  │
    │ api/          │  ✓  │  ✓  │  ✓  │  ✓  │  ✓  │  ✓  │  -  │
    └───────────────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┘
```

### Explicit Rules

```python
# ✓ ALLOWED
from src.models import ContextCard          # Anyone can import models
from src.config import Settings             # Anyone can import config
from src.integrations.datadog import DatadogAdapter  # orchestrator only

# ✗ FORBIDDEN - These create circular dependencies or coupling
from src.orchestrator import ...    # in integrations/ (circular!)
from src.integrations import ...    # in ai/ (coupling!)
from src.api import ...             # in anything except main.py
```

### Why These Rules?

1. **Models are the core** - All layers share models, so they must be dependency-free
2. **Integrations are leaves** - They only produce data, never consume orchestration
3. **AI is isolated** - Can be swapped without touching integrations
4. **Orchestrator is the hub** - Only layer that touches everything
5. **API is the shell** - Entry point only, no business logic

---

## Data Flow

### Happy Path: Incident → Context Card

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ 1. INCIDENT TRIGGER                                                          │
│                                                                              │
│    PagerDuty ──webhook──► POST /webhooks/pagerduty                          │
│                                   │                                          │
│                                   ▼                                          │
│    Validate signature, parse payload, extract incident_id, service          │
└──────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 2. CONTEXT GATHERING (parallel, 8s timeout)                                  │
│                                                                              │
│    orchestrator.process_incident(incident_id, service_name)                 │
│                                                                              │
│    ┌─────────────────┬─────────────────┬─────────────────┬─────────────────┐│
│    │   SCM Context   │   Log Context   │  On-Call Info   │   Topology      ││
│    │                 │                 │                 │                 ││
│    │ - Recent deploys│ - Error logs    │ - Who's paged   │ - Dependencies  ││
│    │ - CODEOWNERS    │ - Metrics       │ - Schedule      │ - Blast radius  ││
│    │ - PR links      │ - Dashboards    │ - Escalation    │ - Risk score    ││
│    └─────────────────┴─────────────────┴─────────────────┴─────────────────┘│
│                                                                              │
│    asyncio.gather() with timeout=8.0, return_exceptions=True                │
└──────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 3. LOG COMPRESSION                                                           │
│                                                                              │
│    Raw logs (100K lines) ──► LogCompressor pipeline                         │
│                                                                              │
│    Parse ──► Filter noise ──► Dedupe ──► Rank by severity ──► Summarize    │
│    100K       50K              5K          500 patterns         2K tokens   │
│                                                                              │
│    Uses Haiku for cost efficiency ($0.001 per compression)                  │
└──────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 4. CONTEXT CARD ASSEMBLY                                                     │
│                                                                              │
│    ContextCard(                                                              │
│        incident_id="INC-123",                                               │
│        service="payment-api",                                                │
│        summary="Connection timeouts to Stripe API after deploy...",        │
│        log_summary=compressed_logs,                                         │
│        recent_deploys=[Deploy(sha="abc123", author="jane", time=...)],     │
│        similar_incidents=[...],                                              │
│        runbooks=[...],                                                       │
│        blast_radius=BlastRadius(affected_services=[...], risk="high"),     │
│    )                                                                         │
└──────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 5. DELIVERY                                                                  │
│                                                                              │
│    SlackAdapter.send_context_card(context_card, channel="#incidents")       │
│                                                                              │
│    ┌─────────────────────────────────────────────────────────────────────┐  │
│    │ 🚨 INC-123: payment-api                                             │  │
│    │                                                                      │  │
│    │ Summary: Connection timeouts to Stripe API after deploy v2.3.4     │  │
│    │                                                                      │  │
│    │ 📦 Recent Deploys:                                                  │  │
│    │ • abc123 by @jane (15 min ago) - "Update Stripe SDK"               │  │
│    │                                                                      │  │
│    │ 📊 Metrics: Error rate 15% ↑ (baseline 0.1%)                       │  │
│    │                                                                      │  │
│    │ 📖 Runbook: stripe-connectivity-issues.md                          │  │
│    └─────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Error Handling Flow

```
Integration fails?
    │
    ├──► Timeout (>8s)? ──► Return partial context, log warning
    │
    ├──► Auth error? ──► Skip integration, add to context card
    │
    └──► Rate limited? ──► Retry with backoff, then skip if still failing

LLM fails?
    │
    ├──► Model timeout? ──► Fall back to rule-based summary
    │
    └──► Token limit? ──► Truncate logs, retry with smaller context
```

---

## Directory Structure

```
incident-copilot/
├── .github/
│   └── workflows/
│       ├── ci.yml              # Lint, test, build on PR
│       └── cd.yml              # Deploy on merge to main
│
├── docs/
│   ├── ARCHITECTURE.md         # This file
│   ├── adr/                    # Architecture Decision Records
│   │   ├── 001-parallel-context-fetching.md
│   │   ├── 002-log-compression-pipeline.md
│   │   └── ...
│   └── api/                    # API documentation
│
├── scripts/
│   ├── dependency_graph.py     # Generate module dependency graph
│   └── ...
│
├── src/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # Settings (env vars)
│   ├── models.py               # Shared Pydantic models
│   ├── orchestrator.py         # Core orchestration logic
│   │
│   ├── api/                    # HTTP layer
│   │   ├── __init__.py
│   │   ├── routes.py           # REST endpoints
│   │   ├── webhooks.py         # Webhook receivers
│   │   └── health.py           # Health checks
│   │
│   ├── ai/                     # AI/LLM components
│   │   ├── __init__.py
│   │   ├── copilot.py          # Interactive chat
│   │   ├── log_compressor.py   # Log compression pipeline
│   │   └── summarizer.py       # Incident summarization
│   │
│   ├── integrations/           # External service adapters
│   │   ├── __init__.py
│   │   ├── datadog.py
│   │   ├── cloudwatch.py
│   │   ├── loki.py
│   │   ├── splunk.py
│   │   ├── github.py
│   │   ├── gitlab.py
│   │   ├── slack.py
│   │   ├── teams.py
│   │   ├── pagerduty/          # Multi-file integration
│   │   │   ├── __init__.py
│   │   │   ├── client.py
│   │   │   └── models.py
│   │   └── ...
│   │
│   ├── dependencies/           # Service topology
│   │   ├── __init__.py
│   │   ├── graph.py            # NetworkX-based graph
│   │   ├── service.py          # Service layer
│   │   └── discovery.py        # Auto-discovery
│   │
│   ├── eval/                   # Evaluation framework
│   │   ├── __init__.py
│   │   ├── harness.py          # Test runner
│   │   ├── rubric.py           # Scoring criteria
│   │   └── synthetic.py        # Test data generation
│   │
│   ├── analytics/              # Metrics & reporting
│   ├── audit/                  # Audit logging
│   ├── auth/                   # Authentication
│   ├── billing/                # Stripe integration
│   ├── correlation/            # Alert grouping
│   ├── costs/                  # Incident cost tracking
│   ├── escalation/             # Escalation policies
│   ├── export/                 # Data export
│   ├── gamification/           # Points & badges
│   ├── insights/               # AI-powered analysis
│   ├── maintenance/            # Maintenance windows
│   ├── notifications/          # Notification routing
│   ├── performance/            # Team performance
│   ├── plugins/                # Plugin system
│   ├── postmortem/             # Post-incident reports
│   ├── rbac/                   # Role-based access
│   ├── runbooks/               # Runbook matching
│   ├── search/                 # Full-text search
│   ├── similarity/             # Similar incident finding
│   ├── sla/                    # SLA tracking
│   ├── status_page/            # Status page integration
│   ├── tagging/                # Incident tagging
│   ├── templates/              # Template engine
│   ├── timeline/               # Incident timeline
│   └── web/                    # Web components
│
├── tests/
│   ├── conftest.py             # Shared fixtures
│   ├── integration/            # Integration tests
│   │   └── test_webhooks.py
│   ├── test_*.py               # Unit tests
│   └── ...
│
├── frontend/                   # Next.js dashboard (optional)
│   ├── src/
│   └── ...
│
├── terraform/                  # Infrastructure as code
│   ├── aws/
│   └── ...
│
├── pyproject.toml              # Python project config
├── Dockerfile
├── docker-compose.yml
├── Makefile                    # Common commands
└── README.md
```

---

## Key Design Decisions

See `docs/adr/` for detailed Architecture Decision Records.

| Decision | Rationale |
|----------|-----------|
| **Parallel fan-out with timeout** | Speed matters. 8s timeout ensures delivery even if one source is slow |
| **Log compression before LLM** | Cost and context window efficiency. 100K logs → 2K tokens |
| **Single investigator (not multi-agent)** | Ship faster, validate PMF first. Can decompose later |
| **Pluggable integrations** | Customers have different stacks. Easy to add/remove |
| **Topology as shared layer** | Service graph is pre-populated, not fetched per-incident |

---

## Configuration

All configuration via environment variables, loaded through `src/config.py`:

```python
class Settings(BaseSettings):
    # Core
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    
    # Database
    database_url: str
    redis_url: str
    
    # Integrations (optional - only needed if integration is used)
    pagerduty_api_key: str | None = None
    datadog_api_key: str | None = None
    github_token: str | None = None
    slack_bot_token: str | None = None
    anthropic_api_key: str | None = None
    
    # AI configuration
    ai_model_compression: str = "claude-3-haiku-20240307"
    ai_model_analysis: str = "claude-3-5-sonnet-20241022"
    
    # Limits
    log_compression_max_lines: int = 100_000
    context_assembly_timeout_seconds: float = 8.0
    
    model_config = SettingsConfigDict(env_file=".env")
```

---

## Testing Strategy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              TESTING PYRAMID                                 │
│                                                                              │
│                            ┌───────────┐                                     │
│                           ╱             ╲                                    │
│                          ╱   E2E Tests   ╲          10%                      │
│                         ╱  (PD→Slack     ╲                                   │
│                        ╱    full flow)    ╲                                  │
│                       ├───────────────────┤                                  │
│                      ╱                     ╲                                 │
│                     ╱   Integration Tests   ╲       30%                      │
│                    ╱   (API, DB, external    ╲                               │
│                   ╱     service mocks)        ╲                              │
│                  ├─────────────────────────────┤                             │
│                 ╱                               ╲                            │
│                ╱         Unit Tests              ╲      60%                  │
│               ╱   (LogCompressor, Rubric, etc.)   ╲                          │
│              └─────────────────────────────────────┘                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

Run tests:
  make test           # All tests
  make test-unit      # Unit only (fast)
  make test-cov       # With coverage report
```

### Eval Framework (`src/eval/`)

For evaluating AI output quality:

```python
from src.eval import SyntheticIncidentGenerator, EvalHarness, Rubric

# Generate synthetic incidents
gen = SyntheticIncidentGenerator(seed=42)
incidents = gen.generate_batch(50)

# Run evaluation
harness = EvalHarness(copilot)
await harness.run_eval(incidents)

# Check results
summary = harness.summary()
print(f"Pass rate: {summary.passed / summary.total_incidents:.1%}")
```

---

## Quick Reference

```bash
# Development
make dev              # Start local dev server
make lint             # Run linters
make test             # Run tests

# Dependencies
make install          # Install dependencies
make update-deps      # Update dependencies

# Docker
make docker-build     # Build image
make docker-run       # Run container

# Utilities
make dependency-graph # Generate module dependency graph
make clean            # Clean build artifacts
```

---

*Last updated: 2026-02-08*
