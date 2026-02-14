# Incident Memory — Learning from Past Incidents

**Author:** Jarvis (internal)
**Last updated:** 2026-02-13
**Status:** Proposed

---

## 1) Overview & Value Proposition

### Problem

When a new alert fires at 3am, the on-call engineer starts from zero. They don't know that an almost identical incident happened two weeks ago, that it took 47 minutes to diagnose, and that the root cause was a misconfigured Redis maxmemory policy after a deploy.

Today's Incident Copilot assembles *live* context (logs, metrics, deploys, alerts) but has no memory of *past* incidents. Every incident is treated as novel. This wastes time and repeats mistakes.

### Solution

**Incident Memory** — a RAG-based system that captures structured knowledge from every resolved incident and retrieves relevant past incidents when new alerts fire. The system gets measurably smarter with every incident your team resolves.

### Why This Matters

- **Cleric** markets "self-learning" as a core differentiator
- **Hawkeye (Neubird)** stores incident embeddings for privacy-preserving similarity search
- **Rootly** has "Ask Rootly AI" that draws on incident history
- We currently have a `PatternDetector` that does title-string matching — functional but shallow

Incident Memory replaces string matching with semantic understanding. It answers: *"What past incidents looked like this, and what fixed them?"*

---

## 2) Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Incident Lifecycle                     │
│                                                          │
│  Alert Fires ──► ContextOrchestrator ──► AI Analysis     │
│       │                                      │           │
│       │         ┌──────────────────┐         │           │
│       └────────►│ Incident Memory  │◄────────┘           │
│    (query)      │                  │   (enrich response)  │
│                 │  ┌────────────┐  │                      │
│                 │  │ Vector DB  │  │                      │
│                 │  │ (pgvector) │  │                      │
│                 │  └────────────┘  │                      │
│                 │  ┌────────────┐  │                      │
│                 │  │ Structured │  │                      │
│                 │  │  Metadata  │  │                      │
│                 │  └────────────┘  │                      │
│                 └──────────────────┘                      │
│                         ▲                                │
│                         │                                │
│  Incident Resolved ─────┘                                │
│    (capture + embed)                                     │
└─────────────────────────────────────────────────────────┘
```

### Components

1. **IncidentMemoryStore** — persistence layer (pgvector + structured metadata)
2. **IncidentCapture** — extracts and embeds knowledge from resolved incidents
3. **IncidentRecall** — retrieves relevant past incidents for active alerts
4. **MemoryEnricher** — injects recalled incidents into ContextOrchestrator's output

---

## 3) Data Model

### 3.1 Incident Record (structured metadata)

```python
class IncidentRecord(BaseModel):
    """Structured knowledge captured from a resolved incident."""

    # Identity
    id: str                          # incident ID (e.g., INC-47)
    title: str                       # original alert/incident title
    created_at: datetime
    resolved_at: datetime
    duration_minutes: float

    # Classification
    severity: str                    # critical / high / medium / low
    services_affected: list[str]     # e.g., ["payment-service", "redis-cluster-3"]
    root_cause_category: str         # deploy / config / capacity / dependency / unknown
    root_cause_summary: str          # 1-2 sentence human-readable root cause

    # Context fingerprint
    error_signatures: list[str]      # normalized error patterns (e.g., "OOMKilled", "connection refused :6379")
    metric_anomalies: list[str]      # which metrics deviated (e.g., "p99_latency > 2s", "error_rate > 5%")
    deploy_involved: bool            # was there a deploy within the incident window?
    deploy_sha: str | None           # if yes, which commit

    # Resolution
    resolution_steps: list[str]      # ordered list of what the team actually did
    resolution_summary: str          # 1-2 sentence summary of the fix
    time_to_diagnose_minutes: float  # from alert to "we know what's wrong"
    time_to_fix_minutes: float       # from diagnosis to resolution
    was_rollback: bool               # did the fix involve rolling back a deploy?
    runbook_used: str | None         # if a runbook was followed, which one

    # Learning
    what_helped: str | None          # what context/tool was most useful during triage
    what_was_missing: str | None     # what would have helped but wasn't available
    tags: list[str]                  # freeform tags for additional classification

    # Embedding
    embedding: list[float] | None    # vector embedding of the full incident narrative
```

### 3.2 Database Schema (pgvector)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE incident_memory (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL,
    resolved_at     TIMESTAMPTZ NOT NULL,
    duration_min    REAL NOT NULL,

    severity        TEXT NOT NULL,
    services        TEXT[] NOT NULL,          -- array of service names
    root_cause_cat  TEXT NOT NULL,
    root_cause      TEXT NOT NULL,

    error_sigs      TEXT[] DEFAULT '{}',
    metric_anomalies TEXT[] DEFAULT '{}',
    deploy_involved BOOLEAN DEFAULT FALSE,
    deploy_sha      TEXT,

    resolution_steps JSONB NOT NULL,          -- ordered list
    resolution       TEXT NOT NULL,
    ttd_min         REAL,                     -- time to diagnose
    ttf_min         REAL,                     -- time to fix
    was_rollback    BOOLEAN DEFAULT FALSE,
    runbook_used    TEXT,

    what_helped     TEXT,
    what_missing    TEXT,
    tags            TEXT[] DEFAULT '{}',

    -- Vector embedding (1536 for OpenAI ada-002, 1024 for Cohere, etc.)
    embedding       vector(1536),

    captured_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Similarity search index (IVFFlat for < 100K records, HNSW for larger)
CREATE INDEX idx_incident_memory_embedding
    ON incident_memory USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 50);

-- Structured query indexes
CREATE INDEX idx_incident_memory_services ON incident_memory USING GIN (services);
CREATE INDEX idx_incident_memory_severity ON incident_memory (severity);
CREATE INDEX idx_incident_memory_root_cause ON incident_memory (root_cause_cat);
CREATE INDEX idx_incident_memory_created ON incident_memory (created_at DESC);
```

---

## 4) Capture Pipeline

When an incident is resolved, the capture pipeline runs automatically.

### 4.1 Trigger

```python
# Hook into incident state change
@event_handler("incident.resolved")
async def on_incident_resolved(incident_id: str):
    await incident_capture.capture(incident_id)
```

### 4.2 Extraction (Claude-powered)

The raw incident data (timeline, logs, metrics, chat messages, postmortem if available) is sent to Claude with a structured extraction prompt:

```python
CAPTURE_PROMPT = """
You are analyzing a resolved incident to extract structured knowledge for future reference.

Given the incident timeline, logs, metrics, and resolution notes below, extract:

1. **root_cause_category**: one of [deploy, config, capacity, dependency, network, code_bug, external, unknown]
2. **root_cause_summary**: 1-2 sentences explaining what went wrong
3. **error_signatures**: list of normalized error patterns (strip timestamps/IDs, keep the pattern)
4. **metric_anomalies**: which metrics deviated and how (e.g., "p99 latency > 2s for payment-service")
5. **resolution_steps**: ordered list of actions the team took to fix it
6. **resolution_summary**: 1-2 sentence summary of the fix
7. **time_to_diagnose_minutes**: estimated time from alert to root cause identification
8. **time_to_fix_minutes**: estimated time from root cause ID to resolution
9. **was_rollback**: did the fix involve reverting a deploy?
10. **what_helped**: what context, tool, or data was most useful during triage?
11. **what_was_missing**: what would have sped things up but wasn't available?
12. **tags**: 3-5 freeform tags

Also generate a **narrative summary** (3-5 sentences) that combines the incident context,
root cause, and resolution into a coherent story. This will be embedded for similarity search.

Respond as JSON.
"""
```

### 4.3 Embedding

The narrative summary is embedded using an embedding model:

```python
async def embed_narrative(self, narrative: str) -> list[float]:
    """Generate vector embedding of incident narrative."""
    # Primary: OpenAI text-embedding-3-small (1536 dims, cheap, fast)
    # Fallback: local sentence-transformers if no API key
    response = await self.embedding_client.embeddings.create(
        model="text-embedding-3-small",
        input=narrative,
    )
    return response.data[0].embedding
```

**Embedding model choice:**
- **OpenAI text-embedding-3-small** — $0.02/1M tokens, 1536 dims, excellent quality. Default.
- **Local fallback** — sentence-transformers `all-MiniLM-L6-v2` (384 dims) for air-gapped deployments. Adjust `vector(1536)` → `vector(384)` in schema.
- **Config-driven** — customers choose based on their security/cost requirements.

### 4.4 Storage

```python
async def store(self, record: IncidentRecord) -> None:
    """Persist incident record with embedding to pgvector."""
    await self.db.execute(
        """
        INSERT INTO incident_memory (
            id, title, created_at, resolved_at, duration_min,
            severity, services, root_cause_cat, root_cause,
            error_sigs, metric_anomalies, deploy_involved, deploy_sha,
            resolution_steps, resolution, ttd_min, ttf_min,
            was_rollback, runbook_used,
            what_helped, what_missing, tags, embedding
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                  $11, $12, $13, $14, $15, $16, $17, $18, $19,
                  $20, $21, $22, $23)
        ON CONFLICT (id) DO UPDATE SET
            root_cause = EXCLUDED.root_cause,
            resolution = EXCLUDED.resolution,
            resolution_steps = EXCLUDED.resolution_steps,
            embedding = EXCLUDED.embedding,
            captured_at = NOW()
        """,
        record.values()
    )
```

---

## 5) Recall Pipeline

When a new alert fires, the recall pipeline finds relevant past incidents.

### 5.1 Query Construction

The current alert context is used to build both a semantic query and structured filters:

```python
class RecallQuery(BaseModel):
    """Query for finding similar past incidents."""

    # Semantic (embedding similarity)
    narrative: str              # natural language description of current alert
    embedding: list[float]      # embedded version of the narrative

    # Structured filters (narrow the search space)
    services: list[str]         # affected services
    severity_min: str | None    # minimum severity to consider
    time_window_days: int = 90  # how far back to look

    # Tuning
    top_k: int = 5              # max results
    min_similarity: float = 0.7 # cosine similarity threshold
```

### 5.2 Hybrid Search (semantic + structured)

```python
async def recall(self, query: RecallQuery) -> list[RecalledIncident]:
    """Find similar past incidents using hybrid search."""

    results = await self.db.fetch(
        """
        SELECT
            id, title, severity, services, root_cause_cat, root_cause,
            resolution, resolution_steps, duration_min, ttd_min, ttf_min,
            was_rollback, tags, created_at,
            1 - (embedding <=> $1::vector) AS similarity
        FROM incident_memory
        WHERE
            created_at > NOW() - INTERVAL '$2 days'
            AND ($3::text[] IS NULL OR services && $3)  -- overlap filter
        ORDER BY embedding <=> $1::vector
        LIMIT $4
        """,
        query.embedding,
        query.time_window_days,
        query.services or None,
        query.top_k,
    )

    return [
        RecalledIncident(**row)
        for row in results
        if row["similarity"] >= query.min_similarity
    ]
```

### 5.3 Re-ranking

After initial retrieval, optionally re-rank using Claude for relevance:

```python
RERANK_PROMPT = """
Given this current alert:
{current_context}

And these past incidents:
{candidates}

Rank them by relevance to the current situation. Consider:
- Same services/infrastructure involved?
- Similar error patterns?
- Similar timing (time of day, day of week)?
- Similar recent deploys or config changes?

Return the incident IDs in order of relevance, with a brief explanation of why each is relevant.
"""
```

This is optional and only triggered when:
- Initial retrieval returns > 3 results above threshold
- The incident is severity `critical` or `high` (worth the extra API call)

---

## 6) Integration with ContextOrchestrator

### 6.1 Where It Plugs In

The `ContextOrchestrator` currently assembles: alerts → logs → metrics → deploys → AI summary.

Incident Memory becomes a new context source, inserted before the AI summary step:

```python
class ContextOrchestrator:
    async def build_context(self, alert: Alert) -> IncidentContext:
        # Existing steps
        logs = await self.fetch_logs(alert)
        metrics = await self.fetch_metrics(alert)
        deploys = await self.fetch_deploys(alert)

        # NEW: Recall similar past incidents
        similar = await self.incident_memory.recall(
            RecallQuery(
                narrative=self._build_narrative(alert, logs, metrics, deploys),
                embedding=await self.embed(narrative),
                services=alert.affected_services,
            )
        )

        # AI summary now includes past incident context
        summary = await self.ai_summarize(
            alert=alert,
            logs=logs,
            metrics=metrics,
            deploys=deploys,
            similar_incidents=similar,  # NEW
        )

        return IncidentContext(
            alert=alert,
            logs=logs,
            metrics=metrics,
            deploys=deploys,
            similar_incidents=similar,  # NEW
            summary=summary,
        )
```

### 6.2 AI Summary Prompt Enhancement

```python
SUMMARY_PROMPT_WITH_MEMORY = """
{existing_prompt}

## Similar Past Incidents

The following past incidents were found to be similar to the current alert:

{% for incident in similar_incidents %}
### {{ incident.title }} ({{ incident.created_at.strftime('%Y-%m-%d') }}, {{ incident.severity }})
- **Root cause:** {{ incident.root_cause }}
- **Resolution:** {{ incident.resolution }}
- **Time to resolve:** {{ incident.duration_min }} minutes
- **Similarity:** {{ "%.0f"|format(incident.similarity * 100) }}%
{% if incident.was_rollback %}- ⚠️ Required rollback{% endif %}
{% endfor %}

Based on these similar incidents, assess:
1. Is this likely the same root cause as a past incident? If so, which one and why?
2. What resolution steps should be tried first, based on what worked before?
3. What's different about this occurrence that might require a different approach?
"""
```

### 6.3 Output to Slack / Web UI

The context card and copilot thread gain a new section:

```
🧠 Similar Past Incidents

1. INC-47 (Jan 15, high) — 91% match
   Root cause: Redis maxmemory config changed in deploy abc123
   Fixed by: Rolling back Redis config, then deploying corrected values
   Resolved in: 47 min

2. INC-31 (Dec 28, medium) — 78% match
   Root cause: Connection pool exhaustion after traffic spike
   Fixed by: Increasing pool size from 20→50, adding circuit breaker
   Resolved in: 23 min

💡 Suggested first action: Check if a recent deploy changed Redis configuration
   (based on INC-47 resolution)
```

---

## 7) Conversational Integration

The Copilot conversational bot (per conversational-bot-spec.md) gains a new tool:

```python
MEMORY_TOOL = {
    "name": "search_past_incidents",
    "description": "Search past resolved incidents for similar patterns, root causes, or resolutions",
    "parameters": {
        "query": "Natural language description of what to search for",
        "services": "Optional: filter by service names",
        "root_cause_category": "Optional: filter by root cause type",
        "time_range_days": "Optional: how far back to search (default 90)"
    }
}
```

Engineers can ask:
- *"Have we seen this Redis timeout before?"*
- *"What usually causes OOMKilled on payment-service?"*
- *"Show me incidents that required rollbacks last month"*

---

## 8) Feedback Loop (Active Learning)

### 8.1 Resolution Feedback

After the engineer resolves an incident with Memory suggestions:

```
Was the suggested resolution helpful?
  👍 Yes, it matched    → boost similarity weight for that pair
  👎 No, different issue → reduce similarity weight
  📝 Partially          → capture what was different
```

### 8.2 Embedding Refinement

Over time, feedback signals can be used to:
- Fine-tune the embedding model (if using a local model)
- Adjust similarity thresholds per service/category
- Weight recent incidents higher (temporal decay)

```python
# Temporal decay: recent incidents get a similarity boost
def apply_temporal_decay(similarity: float, days_ago: int) -> float:
    """Recent incidents are more relevant."""
    decay = 0.95 ** (days_ago / 30)  # ~5% decay per month
    return similarity * decay
```

---

## 9) Privacy & Security

| Concern | Mitigation |
|---------|-----------|
| Incident data contains sensitive info | All data stays in customer's own Postgres (self-hosted). No data leaves the deployment. |
| Embedding API sends text externally | Offer local embedding model option (sentence-transformers). Config flag: `EMBEDDING_PROVIDER=local\|openai` |
| Access control | Incident Memory respects existing RBAC. Users only see incidents from services they have access to. |
| Data retention | Configurable retention period. Default: 365 days. `INCIDENT_MEMORY_RETENTION_DAYS=365` |
| PII in incident narratives | Capture prompt instructs Claude to strip PII (names, IPs, credentials) from narratives before embedding. |

---

## 10) Configuration

```python
class IncidentMemoryConfig(BaseModel):
    """Configuration for Incident Memory feature."""

    enabled: bool = True
    embedding_provider: str = "openai"         # openai | local
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    similarity_threshold: float = 0.70
    max_recall_results: int = 5
    time_window_days: int = 90
    retention_days: int = 365
    rerank_enabled: bool = False               # Claude re-ranking (costs extra)
    rerank_min_severity: str = "high"          # only re-rank for high/critical
    auto_capture: bool = True                  # capture on incident resolve
    temporal_decay: bool = True                # weight recent incidents higher
    feedback_enabled: bool = True              # resolution feedback loop
```

---

## 11) Implementation Plan

### Phase 1 — Core Memory (1-2 weeks)
- [ ] pgvector extension + schema migration
- [ ] `IncidentMemoryStore` — CRUD + vector search
- [ ] `IncidentCapture` — Claude extraction + embedding on resolve
- [ ] `IncidentRecall` — hybrid search (embedding + structured filters)
- [ ] Unit tests + integration tests with test Postgres
- [ ] Config model + feature flag

### Phase 2 — ContextOrchestrator Integration (1 week)
- [ ] Wire `IncidentRecall` into `ContextOrchestrator.build_context()`
- [ ] Enhance AI summary prompt with past incident context
- [ ] Add "Similar Past Incidents" section to Slack/Web context cards
- [ ] Add `search_past_incidents` tool to conversational bot

### Phase 3 — Feedback & Refinement (1 week)
- [ ] Resolution feedback UI (Slack interactive message + Web UI)
- [ ] Feedback storage + similarity weight adjustment
- [ ] Temporal decay scoring
- [ ] Dashboard: "Incident Memory Stats" (total records, avg similarity, feedback scores)

### Phase 4 — Advanced (future)
- [ ] Local embedding model support (sentence-transformers)
- [ ] Cross-service correlation ("when service A has this issue, service B usually follows")
- [ ] Auto-generated runbooks from recurring resolution patterns
- [ ] "Incident Memory Health" alerts (e.g., "3 incidents this week with no similar matches — your memory may need seeding")

---

## 12) Metrics & Observability

```python
# Prometheus metrics for Incident Memory
incident_memory_records_total      # gauge: total records in memory
incident_memory_capture_seconds    # histogram: time to capture an incident
incident_memory_recall_seconds     # histogram: time to recall similar incidents
incident_memory_recall_results     # histogram: number of results returned per query
incident_memory_similarity_scores  # histogram: distribution of similarity scores
incident_memory_feedback_total     # counter: feedback responses (label: helpful/not/partial)
incident_memory_recall_hit_rate    # gauge: % of alerts that found at least one similar incident
```

---

## 13) Marketing Angle

> **"Gets smarter with every incident your team resolves."**

This is the one-liner. It's true, it's measurable, and it directly counters the "dumb static tool" perception.

Supporting claims:
- *"Incident #47 took 47 minutes. Incident #63 — same root cause — took 12 minutes, because Incident Copilot remembered."*
- *"Your team's tribal knowledge, captured and searchable. No more 'ask Sarah, she fixed this last time.'"*
- *"Every resolved incident makes the next one faster. That's compounding returns on your incident response investment."*

---

## 14) Open Questions

1. **Embedding model cost at scale** — At ~$0.02/1M tokens, a 500-word narrative costs ~$0.00001 to embed. Even 10,000 incidents/year is negligible. But should we default to local for self-hosted?

2. **Cold start** — New deployments have empty memory. Options:
   - Import from existing postmortems/Jira tickets
   - Seed with synthetic incidents from runbooks
   - Graceful degradation: "No similar incidents found yet. Memory builds automatically as incidents are resolved."

3. **Multi-tenant** — Each customer's memory must be strictly isolated. Enforce `org_id` column and row-level security.

4. **Embedding model upgrades** — When a better model comes out, do we re-embed everything? Probably yes (batch job), since embeddings from different models aren't comparable.

---

*End of spec.*
