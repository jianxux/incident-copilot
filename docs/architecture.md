# Incident Copilot Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              INCIDENT COPILOT                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│   │  PagerDuty  │    │  Opsgenie   │    │  CloudWatch │    │   Custom    │     │
│   │   Webhook   │    │   Webhook   │    │   Events    │    │   Webhook   │     │
│   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘     │
│          │                  │                  │                  │             │
│          └──────────────────┴─────────┬────────┴──────────────────┘             │
│                                       │                                         │
│                                       ▼                                         │
│                          ┌────────────────────────┐                             │
│                          │    Webhook Handler     │                             │
│                          │   (FastAPI Router)     │                             │
│                          └───────────┬────────────┘                             │
│                                      │                                          │
│                                      ▼                                          │
│                          ┌────────────────────────┐                             │
│                          │     Orchestrator       │                             │
│                          │  (Context Assembly)    │                             │
│                          └───────────┬────────────┘                             │
│                                      │                                          │
│          ┌───────────────────────────┼───────────────────────────┐              │
│          │                           │                           │              │
│          ▼                           ▼                           ▼              │
│  ┌───────────────┐         ┌───────────────┐          ┌───────────────┐         │
│  │ GitHub Client │         │  Log Fetcher  │          │  AI Summarizer │        │
│  │ (Deployments) │         │(Datadog/CW/etc)│         │   (Claude)     │        │
│  └───────────────┘         └───────────────┘          └───────────────┘         │
│          │                           │                           │              │
│          └───────────────────────────┼───────────────────────────┘              │
│                                      │                                          │
│          ┌───────────────────────────┼───────────────────────────┐              │
│          │                           │                           │              │
│          ▼                           ▼                           ▼              │
│  ┌───────────────┐         ┌───────────────┐          ┌───────────────┐         │
│  │Similar Incident│        │    Runbook    │          │   Context     │         │
│  │    Search     │         │    Linker     │          │   Card Fmt    │         │
│  └───────────────┘         └───────────────┘          └───────────────┘         │
│                                      │                                          │
│                                      ▼                                          │
│                          ┌────────────────────────┐                             │
│                          │   Delivery Manager     │                             │
│                          │  (Slack/Teams/etc)     │                             │
│                          └────────────────────────┘                             │
│                                      │                                          │
│          ┌───────────────────────────┼───────────────────────────┐              │
│          │                           │                           │              │
│          ▼                           ▼                           ▼              │
│     ┌─────────┐               ┌─────────┐                 ┌─────────┐           │
│     │  Slack  │               │  Teams  │                 │ Web UI  │           │
│     └─────────┘               └─────────┘                 └─────────┘           │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Alert Ingestion

```
PagerDuty/Opsgenie Alert
         │
         ▼
   ┌───────────┐
   │ Validate  │  ← Verify webhook signature
   │ Signature │
   └─────┬─────┘
         │
         ▼
   ┌───────────┐
   │  Parse    │  ← Extract alert metadata
   │  Payload  │    (service, severity, description)
   └─────┬─────┘
         │
         ▼
   ┌───────────┐
   │ Trigger   │  ← Start context assembly
   │ Assembly  │
   └───────────┘
```

### 2. Context Assembly (Parallel)

```
                    ┌──────────────────────┐
                    │    Orchestrator      │
                    └──────────┬───────────┘
                               │
       ┌───────────────────────┼───────────────────────┐
       │                       │                       │
       ▼                       ▼                       ▼
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│    GitHub    │       │   Datadog/   │       │   Incident   │
│   Deploys    │       │  CloudWatch  │       │    Index     │
│   <2s        │       │    <5s       │       │    <2s       │
└──────┬───────┘       └──────┬───────┘       └──────┬───────┘
       │                      │                      │
       │                      ▼                      │
       │               ┌──────────────┐              │
       │               │     AI       │              │
       │               │  Summarize   │              │
       │               │    <3s       │              │
       │               └──────┬───────┘              │
       │                      │                      │
       └───────────────────────┼──────────────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  Merge Results &     │
                    │  Build Context Card  │
                    └──────────────────────┘
```

### 3. Delivery

```
Context Card
     │
     ▼
┌────────────────┐
│ Format for     │  ← Rich formatting for Slack
│ Target Channel │    Markdown for others
└───────┬────────┘
        │
        ▼
┌────────────────┐
│ Send via API   │
│ (async)        │
└───────┬────────┘
        │
        ▼
┌────────────────┐
│ Store in DB    │  ← For history/similarity
│ (async)        │
└────────────────┘
```

## Component Details

### Orchestrator (`src/orchestrator.py`)

The central coordination point. Responsibilities:
- Receive parsed alerts from webhook handlers
- Dispatch parallel data fetching tasks
- Merge results into a unified ContextCard
- Trigger delivery

```python
async def assemble_context(alert: Alert) -> ContextCard:
    # Parallel fetch
    deploys, logs, similar = await asyncio.gather(
        github.fetch_deployments(alert.service),
        datadog.fetch_logs(alert.service, time_window),
        index.find_similar(alert),
    )
    
    # AI summarization
    summary = await ai.summarize_logs(logs)
    
    # Build card
    return ContextCard(
        alert=alert,
        deployments=deploys,
        log_summary=summary,
        similar_incidents=similar,
        runbooks=await runbooks.find_relevant(alert),
    )
```

### Integrations (`src/integrations/`)

Each integration follows a standard interface:

```python
class IntegrationClient(Protocol):
    async def health_check(self) -> bool: ...
    async def fetch_data(self, params: dict) -> Any: ...
```

Implementations:
- `pagerduty.py` - Webhook parsing, API enrichment
- `opsgenie.py` - Webhook parsing, API enrichment
- `github.py` - Deployment and commit fetching
- `datadog.py` - Log and metric fetching
- `cloudwatch.py` - AWS log fetching
- `slack.py` - Context card delivery

### AI Summarizer (`src/ai/summarizer.py`)

Uses Claude to:
1. Identify top error patterns in logs
2. Group by error type with counts
3. Generate human-readable summary
4. Highlight anomalies vs baseline

```python
async def summarize_logs(logs: list[LogEntry]) -> LogSummary:
    prompt = build_log_analysis_prompt(logs)
    response = await claude.complete(prompt)
    return parse_summary_response(response)
```

### Similarity Search (`src/similarity/`)

Vector-based incident matching:
1. **Index**: Store incidents with embeddings (OpenAI ada-002)
2. **Query**: On new incident, embed alert + top logs
3. **Match**: Cosine similarity against index
4. **Return**: Top 3 matches with resolution info

Storage: SQLite with numpy arrays for MVP, Pinecone/Weaviate for scale.

## Database Schema

### Incidents Table

```sql
CREATE TABLE incidents (
    id TEXT PRIMARY KEY,
    source TEXT,              -- pagerduty, opsgenie
    source_id TEXT,           -- external alert ID
    service TEXT,
    severity TEXT,
    title TEXT,
    description TEXT,
    triggered_at TIMESTAMP,
    resolved_at TIMESTAMP,
    resolution_notes TEXT,
    context_card_json TEXT,   -- full card for replay
    embedding BLOB,           -- vector for similarity
    created_at TIMESTAMP
);
```

### Deployments Table

```sql
CREATE TABLE deployments (
    id TEXT PRIMARY KEY,
    repo TEXT,
    sha TEXT,
    author TEXT,
    message TEXT,
    deployed_at TIMESTAMP,
    service TEXT
);
```

### Runbooks Table

```sql
CREATE TABLE runbooks (
    id TEXT PRIMARY KEY,
    title TEXT,
    url TEXT,
    source TEXT,           -- github, notion, confluence
    content TEXT,          -- for keyword matching
    keywords TEXT[],
    services TEXT[],
    updated_at TIMESTAMP
);
```

## Performance Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| End-to-end latency | <10s | From webhook to Slack |
| GitHub API | <2s | Uses GraphQL for efficiency |
| Datadog API | <5s | Largest variable |
| AI summarization | <3s | Claude streaming |
| Similarity search | <2s | Local index |
| Slack delivery | <1s | Async |

## Deployment

### Single-Tenant (MVP)

```yaml
# docker-compose.yml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    volumes:
      - ./data:/app/data  # SQLite storage
  
  redis:
    image: redis:alpine
    # For rate limiting, caching
```

### Multi-Tenant (Future)

```
┌─────────────────────────────────────────┐
│            Load Balancer                │
└────────────────┬────────────────────────┘
                 │
     ┌───────────┼───────────┐
     │           │           │
┌────▼────┐ ┌────▼────┐ ┌────▼────┐
│  API 1  │ │  API 2  │ │  API 3  │
└────┬────┘ └────┬────┘ └────┬────┘
     │           │           │
     └───────────┼───────────┘
                 │
         ┌───────▼───────┐
         │  PostgreSQL   │
         └───────────────┘
```

## Security Considerations

1. **Webhook Authentication**: Always verify signatures
2. **API Keys**: Store encrypted, never log
3. **Log Data**: May contain PII, handle carefully
4. **AI**: Option to self-host or use sanitized data
5. **Multi-tenant**: Strict tenant isolation

---

*Architecture version: 1.0*
*Last updated: January 2026*
