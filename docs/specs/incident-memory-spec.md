# Incident Memory — Learning from Past Incidents

**Author:** Jarvis (internal)
**Last updated:** 2026-02-13
**Status:** Phase 1 Implemented · Phases 2–4 Planned

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

| Component | Module | Status |
|-----------|--------|--------|
| **IncidentMemoryStore** | `src/memory/store.py` | ✅ Phase 1 |
| **IncidentCapture** | `src/memory/capture.py` | ✅ Phase 1 |
| **IncidentRecall** | `src/memory/recall.py` | ✅ Phase 1 |
| **IncidentMemoryConfig** | `src/memory/config.py` | ✅ Phase 1 |
| **MemoryEnricher** | `src/orchestrator.py` (planned) | 🔲 Phase 2 |
| **Conversational Tool** | `search_past_incidents` | 🔲 Phase 2 |
| **Feedback Loop** | feedback storage + weight adjustment | 🔲 Phase 3 |

---

## 3) Data Model

### 3.1 Incident Record

Defined in `src/memory/models.py`:

```python
class IncidentRecord(BaseModel):
    """Structured memory representation of a resolved incident."""

    # Identity
    id: str                              # incident ID (e.g., INC-47)
    title: str                           # original alert/incident title
    created_at: datetime
    resolved_at: datetime | None = None
    duration_minutes: int | None = None

    # Classification
    severity: str | None = None          # critical / high / medium / low / info / unknown
    services_affected: list[str] = []    # e.g., ["payment-service", "redis-cluster-3"]
    root_cause_category: str | None = None   # deploy / config / capacity / dependency / unknown
    root_cause_summary: str | None = None    # 1-2 sentence human-readable root cause

    # Context fingerprint
    error_signatures: list[str] = []     # normalized error patterns ("OOMKilled", "connection refused :6379")
    metric_anomalies: list[str] = []     # which metrics deviated ("p99_latency > 2s", "error_rate > 5%")
    deploy_involved: bool = False        # was there a deploy within the incident window?
    deploy_sha: str | None = None        # if yes, which commit

    # Resolution
    resolution_steps: list[str] = []     # ordered list of what the team actually did
    resolution_summary: str | None = None    # 1-2 sentence summary of the fix
    time_to_diagnose_minutes: int | None = None  # from alert to "we know what's wrong"
    time_to_fix_minutes: int | None = None       # from diagnosis to resolution
    was_rollback: bool | None = None     # did the fix involve rolling back a deploy?
    runbook_used: str | None = None      # if a runbook was followed, which one

    # Learning
    what_helped: str | None = None       # what context/tool was most useful during triage
    what_was_missing: str | None = None  # what would have helped but wasn't available
    tags: list[str] = []                 # freeform tags for additional classification

    # Embedding
    embedding: list[float] = []          # vector embedding of the full incident narrative
```

**Recall result model:**

```python
class IncidentRecallResult(BaseModel):
    """Scored recall match for a past incident."""
    record: IncidentRecord
    score: float                # final composite score
    vector_similarity: float    # raw cosine similarity
    temporal_decay: float       # decay multiplier applied
```

### 3.2 Database Schema (pgvector)

Migration: `supabase/migrations/20260213000002_incident_memory_phase1.sql`

```sql
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS incident_memory (
    id                        TEXT PRIMARY KEY,
    title                     TEXT NOT NULL,
    created_at                TIMESTAMPTZ NOT NULL,
    resolved_at               TIMESTAMPTZ,
    duration_minutes          INTEGER,
    severity                  TEXT,
    services_affected         TEXT[] NOT NULL DEFAULT '{}',
    root_cause_category       TEXT,
    root_cause_summary        TEXT,
    error_signatures          TEXT[] NOT NULL DEFAULT '{}',
    metric_anomalies          TEXT[] NOT NULL DEFAULT '{}',
    deploy_involved           BOOLEAN NOT NULL DEFAULT FALSE,
    deploy_sha                TEXT,
    resolution_steps          TEXT[] NOT NULL DEFAULT '{}',
    resolution_summary        TEXT,
    time_to_diagnose_minutes  INTEGER,
    time_to_fix_minutes       INTEGER,
    was_rollback              BOOLEAN,
    runbook_used              TEXT,
    what_helped               TEXT,
    what_was_missing          TEXT,
    tags                      TEXT[] NOT NULL DEFAULT '{}',
    embedding                 vector(1536) NOT NULL,
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Vector index (IVFFlat for < 100K records, HNSW for larger)
CREATE INDEX idx_incident_memory_embedding
    ON incident_memory USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Structured filter indexes
CREATE INDEX idx_incident_memory_services_affected ON incident_memory USING gin(services_affected);
CREATE INDEX idx_incident_memory_tags              ON incident_memory USING gin(tags);
CREATE INDEX idx_incident_memory_error_signatures  ON incident_memory USING gin(error_signatures);
CREATE INDEX idx_incident_memory_created_at        ON incident_memory(created_at DESC);
CREATE INDEX idx_incident_memory_severity          ON incident_memory(severity);
```

**Design notes:**
- Fields are nullable where the spec originally required NOT NULL — pragmatic choice for real-world data where extraction may be partial.
- `resolution_steps` stored as `TEXT[]` (not JSONB) — simpler for pgvector queries. The original spec proposed JSONB.
- IVFFlat lists bumped from 50 → 100 for better recall at moderate scale.
- Added GIN indexes on `tags` and `error_signatures` (beyond original spec) for richer structured filtering.

---

## 4) Capture Pipeline

When an incident is resolved, the capture pipeline runs automatically.

### 4.1 Implementation (`src/memory/capture.py`)

**IncidentCapture** orchestrates three steps:

1. **Extract** — Send raw incident payload to Claude with a structured extraction prompt
2. **Embed** — Generate vector embedding of the incident narrative via OpenAI embeddings API
3. **Store** — Persist the `IncidentRecord` + embedding to pgvector

```python
class IncidentCapture:
    async def capture(self, incident_payload: dict) -> IncidentRecord:
        """Full capture pipeline: extract → embed → store."""
        fields = await self._extract(incident_payload)
        narrative = self._build_narrative(fields)
        embedding = await self._embed(narrative)
        record = IncidentRecord(id=str(uuid.uuid4()), embedding=embedding, **fields)
        return await self.store.store(record)
```

### 4.2 Claude Extraction Prompt

The capture prompt instructs Claude to return structured JSON matching the `IncidentRecord` schema. Key rules:
- Use `null` when unknown
- Keep summaries concise and factual
- No extra keys

**Model:** Configurable via `capture_model` (default: `claude-3-haiku-20240307` for speed/cost).

### 4.3 Embedding

```python
async def _embed(self, text: str) -> list[float]:
    """Generate embedding via OpenAI API."""
    # Default: text-embedding-3-small (1536 dims, $0.02/1M tokens)
    # Configurable via embedding_model setting
```

**Embedding model options:**
| Model | Dims | Cost | Use Case |
|-------|------|------|----------|
| `text-embedding-3-small` (default) | 1536 | $0.02/1M tokens | Production |
| `text-embedding-3-large` | 3072 | $0.13/1M tokens | High-precision |
| Local `all-MiniLM-L6-v2` | 384 | Free | Air-gapped deployments |

### 4.4 Upsert Semantics

Store uses `ON CONFLICT (id) DO UPDATE` — re-capturing an incident (e.g., after postmortem is added) updates the record and re-embeds the narrative.

---

## 5) Recall Pipeline

When a new alert fires, the recall pipeline finds relevant past incidents.

### 5.1 Query Model (`src/memory/recall.py`)

```python
class RecallQuery(BaseModel):
    narrative: str                          # natural language description of current alert
    services: list[str] = []               # affected services (for structured boost)
    severity: str | None = None            # current alert severity
    start_time: datetime | None = None     # time window start
    end_time: datetime | None = None       # time window end
    lookback_days: int | None = None       # alternative to start/end
    limit: int = 5                         # max results (1-50)
    candidate_limit: int | None = None     # broader initial fetch for reranking (1-200)
    min_similarity: float | None = None    # override config threshold
    rerank_with_claude: bool | None = None # override config rerank setting
    embedding: list[float] = []            # filled by recall service before store call
```

### 5.2 Hybrid Search (Semantic + Structured)

The recall pipeline uses a two-stage approach:

1. **Vector search** — pgvector cosine similarity on the embedded narrative
2. **Structured boost** — service overlap and severity match add to the score
3. **Temporal decay** — exponential decay based on incident age (half-life: 30 days configurable)

```python
# Composite scoring
final_score = (vector_similarity * temporal_decay) + service_boost + severity_boost
```

Config parameters (from `IncidentMemoryConfig`):
- `recall_min_similarity: 0.15` — low threshold to cast a wide net before reranking
- `recall_temporal_half_life_days: 30` — recent incidents weighted higher
- `recall_service_boost: 0.08` — bonus for matching affected services
- `recall_severity_boost: 0.05` — bonus for matching severity level

### 5.3 Optional Claude Re-ranking

For high-severity incidents (configurable via `recall_rerank_severity_threshold`), Claude re-ranks the initial candidates by practical relevance:

```
Consider: same symptoms, same services, successful fast resolution, high confidence root cause.
Return ranked IDs as JSON.
```

- Only triggered when `recall_enable_rerank: true` (default) and severity ≥ threshold
- Uses `claude-3-haiku-20240307` for speed (configurable via `recall_rerank_model`)

---

## 6) Configuration

All configuration via environment variables with `INCIDENT_MEMORY_` prefix. Defined in `src/memory/config.py`:

```python
class IncidentMemoryConfig(BaseSettings):
    enabled: bool = True

    # Storage
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/incident_copilot"
    table_name: str = "incident_memory"

    # Embeddings
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Capture pipeline
    capture_model: str = "claude-3-haiku-20240307"
    capture_max_tokens: int = 1200
    capture_temperature: float = 0.0

    # Recall pipeline
    recall_default_limit: int = 5
    recall_candidate_limit: int = 50
    recall_min_similarity: float = 0.15
    recall_temporal_half_life_days: int = 30
    recall_service_boost: float = 0.08
    recall_severity_boost: float = 0.05

    # Claude reranking
    recall_enable_rerank: bool = True
    recall_rerank_model: str = "claude-3-haiku-20240307"
    recall_rerank_max_tokens: int = 800
    recall_rerank_severity_threshold: str = "high"

    # Index tuning
    ivfflat_lists: int = 100
```

---

## 7) Integration with ContextOrchestrator (Phase 2)

### 7.1 Where It Plugs In

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
        narrative = self._build_narrative(alert, logs, metrics, deploys)
        similar = await self.incident_memory.recall(
            RecallQuery(narrative=narrative, services=alert.affected_services)
        )

        # AI summary now includes past incident context
        summary = await self.ai_summarize(
            alert=alert, logs=logs, metrics=metrics,
            deploys=deploys, similar_incidents=similar,
        )

        return IncidentContext(
            alert=alert, logs=logs, metrics=metrics,
            deploys=deploys, similar_incidents=similar, summary=summary,
        )
```

### 7.2 AI Summary Prompt Enhancement

```
## Similar Past Incidents

{% for incident in similar_incidents %}
### {{ incident.title }} ({{ incident.created_at | date }}, {{ incident.severity }})
- **Root cause:** {{ incident.root_cause_summary }}
- **Resolution:** {{ incident.resolution_summary }}
- **Time to resolve:** {{ incident.duration_minutes }} minutes
- **Similarity:** {{ incident.score | percent }}
{% if incident.was_rollback %}- ⚠️ Required rollback{% endif %}
{% endfor %}

Based on these similar incidents, assess:
1. Is this likely the same root cause? If so, which one and why?
2. What resolution steps should be tried first?
3. What's different that might require a different approach?
```

### 7.3 Output to Slack / Web UI

The context card gains a new section:

```
🧠 Similar Past Incidents

1. INC-47 (Jan 15, high) — 91% match
   Root cause: Redis maxmemory config changed in deploy abc123
   Fixed by: Rolling back Redis config, then deploying corrected values
   Resolved in: 47 min

💡 Suggested first action: Check if a recent deploy changed Redis configuration
```

---

## 8) Conversational Integration (Phase 2)

The Copilot conversational bot gains a new tool:

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

## 9) Feedback Loop & Active Learning (Phase 3)

### 9.1 Resolution Feedback

After the engineer resolves an incident with Memory suggestions:

```
Was the suggested resolution helpful?
  👍 Yes, it matched    → boost similarity weight for that pair
  👎 No, different issue → reduce similarity weight
  📝 Partially          → capture what was different
```

### 9.2 Refinement Over Time

Feedback signals can be used to:
- Adjust similarity thresholds per service/category
- Weight recent incidents higher (temporal decay already built into Phase 1)
- Build a "Memory Stats" dashboard (total records, avg similarity, hit rate)

---

## 10) Privacy & Security

| Concern | Mitigation |
|---------|-----------|
| Incident data contains sensitive info | All data stays in customer's own Postgres. No data leaves the deployment. |
| Embedding API sends text externally | Offer local embedding model option. Config: `INCIDENT_MEMORY_EMBEDDING_MODEL` |
| Access control | Respects existing RBAC. Users only see incidents from services they have access to. |
| Data retention | Configurable. Default: 365 days. |
| PII in narratives | Capture prompt instructs Claude to strip PII before embedding. |

---

## 11) Implementation Plan

### Phase 1 — Core Memory ✅ COMPLETE
- [x] pgvector extension + schema migration (`supabase/migrations/20260213000002_incident_memory_phase1.sql`)
- [x] `IncidentMemoryStore` — CRUD + vector search (`src/memory/store.py`, 278 lines)
- [x] `IncidentCapture` — Claude extraction + embedding (`src/memory/capture.py`, 269 lines)
- [x] `IncidentRecall` — hybrid search + Claude reranking (`src/memory/recall.py`, 211 lines)
- [x] Config model + feature flags (`src/memory/config.py`, 57 lines)
- [x] Data models (`src/memory/models.py`, 42 lines)
- [x] Unit tests (`tests/test_incident_memory.py`, 273 lines)
- **Total: 1,202 lines across 8 files**

### Phase 2 — ContextOrchestrator Integration
- [ ] Wire `IncidentRecall` into `ContextOrchestrator.build_context()`
- [ ] Enhance AI summary prompt with past incident context
- [ ] Add "Similar Past Incidents" section to Slack/Web context cards
- [ ] Add `search_past_incidents` tool to conversational bot
- [ ] API endpoint: `GET /api/memory/recall` for direct queries

### Phase 3 — Feedback & Refinement
- [ ] Resolution feedback UI (Slack interactive message + Web UI)
- [ ] Feedback storage + similarity weight adjustment
- [ ] Dashboard: "Incident Memory Stats" (total records, avg similarity, hit rate)

### Phase 4 — Advanced
- [ ] Local embedding model support (sentence-transformers for air-gapped)
- [ ] Cross-service correlation ("when A fails, B usually follows")
- [ ] Auto-generated runbooks from recurring resolution patterns
- [ ] Memory health alerts ("3 incidents with no similar matches — memory may need seeding")
- [ ] Cold start: import from existing postmortems / Jira tickets

---

## 12) Metrics & Observability

```python
# Prometheus metrics
incident_memory_records_total      # gauge: total records in memory
incident_memory_capture_seconds    # histogram: capture pipeline latency
incident_memory_recall_seconds     # histogram: recall pipeline latency
incident_memory_recall_results     # histogram: results per query
incident_memory_similarity_scores  # histogram: similarity score distribution
incident_memory_feedback_total     # counter: feedback responses by type
incident_memory_recall_hit_rate    # gauge: % of alerts with ≥1 similar match
```

---

## 13) Marketing Angle

> **"Gets smarter with every incident your team resolves."**

Supporting claims:
- *"Incident #47 took 47 minutes. Incident #63 — same root cause — took 12 minutes, because Incident Copilot remembered."*
- *"Your team's tribal knowledge, captured and searchable. No more 'ask Sarah, she fixed this last time.'"*
- *"Every resolved incident makes the next one faster. Compounding returns on your incident response investment."*

---

## 14) Open Questions

1. **Cold start** — New deployments have empty memory. Options: import from postmortems/Jira, seed from runbooks, or graceful degradation ("No similar incidents found yet").

2. **Multi-tenant** — Each customer's memory must be strictly isolated. Enforce `org_id` column + row-level security.

3. **Embedding model upgrades** — When better models ship, re-embed everything via batch job (embeddings from different models aren't comparable).

4. **HNSW vs IVFFlat** — Current migration uses IVFFlat (lists=100). For >100K records, migrate to HNSW for better recall. Phase 4 consideration.

---

*End of spec.*
