# Architecture Overview

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              INCIDENT COPILOT                                │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  PagerDuty  │     │   Datadog   │     │   GitHub    │     │    Slack    │
│  (webhooks) │     │  (logs/     │     │  (deploys)  │     │  (delivery) │
└──────┬──────┘     │   metrics)  │     └──────┬──────┘     └──────┬──────┘
       │            └──────┬──────┘            │                   │
       │                   │                   │                   │
       ▼                   ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           INTEGRATION LAYER                                  │
│  src/integrations/                                                          │
│  ├── pagerduty/    ├── datadog.py    ├── github.py    ├── slack.py        │
│  ├── opsgenie.py   ├── cloudwatch.py ├── gitlab.py    ├── teams.py        │
│  └── ...           └── loki.py       └── ...          └── ...              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ORCHESTRATION LAYER                                │
│  src/orchestrator.py                                                         │
│  ├── process_incident()  → Fan-out to integrations                          │
│  ├── _fetch_*_context()  → Parallel data fetching (8s timeout)              │
│  └── compress_logs()     → Log compression via AI layer                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
┌─────────────────────────┐ ┌─────────────┐ ┌─────────────────────────┐
│      AI LAYER           │ │ DEPENDENCIES│ │      KNOWLEDGE          │
│  src/ai/                │ │ src/depend- │ │  src/runbooks/          │
│  ├── log_compressor.py  │ │ encies/     │ │  src/similarity/        │
│  ├── summarizer.py      │ │ ├── graph.py│ │  src/insights/          │
│  └── copilot.py         │ │ └── service │ │                         │
└─────────────────────────┘ └─────────────┘ └─────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              OUTPUT                                          │
│  models.ContextCard → Slack/Teams message with assembled context            │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Module Dependency Rules

```
┌─────────────────────────────────────────────────────────┐
│                    ALLOWED DEPENDENCIES                  │
├─────────────────────────────────────────────────────────┤
│  api/           → orchestrator, models, integrations    │
│  orchestrator   → ai/, integrations/, dependencies/     │
│  ai/            → models, config (NO integrations)      │
│  integrations/  → models, config (NO orchestrator)      │
│  dependencies/  → models (standalone)                   │
│  eval/          → ai/, models (testing only)            │
└─────────────────────────────────────────────────────────┘

❌ FORBIDDEN:
- integrations/ → orchestrator (circular)
- ai/ → integrations/ (coupling)
- models → anything except stdlib
```

## Key Design Decisions

### 1. Parallel Fan-out with Timeout
```python
# orchestrator.py
async def process_incident(...):
    # All fetches run in parallel with 8s timeout
    scm_ctx, datadog_ctx, oncall = await asyncio.wait_for(
        asyncio.gather(scm_task, datadog_task, oncall_task),
        timeout=8.0
    )
```
**Why**: Context delivery must be fast (<10s). Failed sources gracefully degrade.

### 2. Log Compression Pipeline
```
Raw logs → Parse → Filter → Dedupe → Rank → LLM Summary
100K lines → 5K → 500 → 50 patterns → 2K tokens
```
**Why**: LLM context windows are limited and expensive. Compress before sending.

### 3. Pluggable Integrations
Each integration implements a common interface:
```python
class IntegrationAdapter(ABC):
    async def get_context(self, service_name: str) -> Context
    async def health_check(self) -> bool
```
**Why**: Customers have different stacks. Easy to add new integrations.

### 4. Topology as Shared Knowledge
```python
# Dependencies graph queried by orchestrator
blast_radius = await dependencies.get_blast_radius(service_id)
upstream = await dependencies.get_downstream_services(service_id)
```
**Why**: Understanding service relationships is critical for incident analysis.

## Directory Structure

```
src/
├── ai/                 # AI/LLM components
│   ├── copilot.py      # Interactive assistant
│   ├── log_compressor.py # Log compression pipeline
│   └── summarizer.py   # Log summarization
│
├── api/                # FastAPI routes
│   └── routes.py       # HTTP endpoints
│
├── analytics/          # Metrics and reporting
├── audit/              # Audit logging
├── auth/               # Authentication (SSO, API keys)
├── billing/            # Stripe integration
│
├── dependencies/       # Service topology
│   ├── graph.py        # NetworkX-based graph
│   ├── discovery.py    # Auto-discovery
│   └── service.py      # Service layer
│
├── eval/               # Evaluation framework
│   ├── harness.py      # Test runner
│   ├── rubric.py       # Scoring
│   └── synthetic.py    # Test data generation
│
├── insights/           # AI-powered analysis
│   ├── analyzer.py     # Cross-incident analysis
│   ├── anomaly.py      # Anomaly detection
│   └── detector.py     # Pattern detection
│
├── integrations/       # External services
│   ├── datadog.py
│   ├── github.py
│   ├── pagerduty/
│   ├── slack.py
│   └── ...
│
├── config.py           # Centralized configuration
├── models.py           # Pydantic models
├── orchestrator.py     # Core orchestration logic
└── main.py             # FastAPI app entry point
```

## Data Flow

```
1. INCIDENT RECEIVED
   PagerDuty webhook → api/routes.py → orchestrator.process_incident()

2. CONTEXT GATHERING (parallel, 8s timeout)
   ├── GitHub → recent deploys, CODEOWNERS
   ├── Datadog → logs, metrics
   ├── Dependencies → upstream/downstream services
   └── On-call → who's currently paged

3. AI PROCESSING
   ├── LogCompressor → dedupe, rank, compress logs
   └── Summarizer → LLM generates summary

4. CONTEXT CARD ASSEMBLY
   models.ContextCard with all gathered context

5. DELIVERY
   Slack/Teams → formatted context card
```

## Testing Strategy

```
┌─────────────────────────────────────────────────────────┐
│                    TESTING PYRAMID                       │
├─────────────────────────────────────────────────────────┤
│                    E2E Tests                             │
│               (PagerDuty → Slack flow)                   │
│                        10%                               │
├─────────────────────────────────────────────────────────┤
│              Integration Tests                           │
│         (API endpoints, DB operations)                   │
│                        30%                               │
├─────────────────────────────────────────────────────────┤
│                  Unit Tests                              │
│    (LogCompressor, Rubric, individual modules)           │
│                        60%                               │
└─────────────────────────────────────────────────────────┘
```

## Configuration

All configuration via environment variables + `src/config.py`:

```python
class Settings(BaseSettings):
    # Core
    environment: str = "development"
    debug: bool = False
    
    # Integrations
    pagerduty_api_key: str
    datadog_api_key: str
    github_token: str
    slack_bot_token: str
    
    # AI
    anthropic_api_key: str
    ai_model: str = "claude-3-haiku-20240307"
    
    # Database
    database_url: str
    redis_url: str
```
