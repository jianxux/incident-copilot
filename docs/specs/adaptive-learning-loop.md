# Adaptive Learning Loop — Feature Design Document

**Module:** Incident Copilot · Adaptive Learning Loop
**Status:** Draft · v1.0
**Date:** 2026-02-13
**Review:** Engineering Implementation + Investor/Customer Design Review

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Goals / Non-Goals](#2-goals--non-goals)
3. [Architecture Overview](#3-architecture-overview)
4. [Pillar 1 — Resolution Capture](#4-pillar-1--resolution-capture)
5. [Pillar 2 — Resolution-Weighted Verdicts](#5-pillar-2--resolution-weighted-verdicts)
6. [Pillar 3 — Confidence Scoring & Calibration](#6-pillar-3--confidence-scoring--calibration)
7. [Pillar 4 — Runbook Staleness Detection](#7-pillar-4--runbook-staleness-detection)
8. [Data Model](#8-data-model)
9. [API Endpoints](#9-api-endpoints)
10. [AI Pipeline Details](#10-ai-pipeline-details)
11. [Feedback Loops](#11-feedback-loops)
12. [Migration Strategy](#12-migration-strategy)
13. [Privacy & Security](#13-privacy--security)
14. [Metrics for Success](#14-metrics-for-success)
15. [Implementation Phases](#15-implementation-phases)
16. [Cost Analysis](#16-cost-analysis)
17. [Competitive Differentiation](#17-competitive-differentiation)

---

## 1. Problem Statement

Today's Incident Copilot retrieves similar past incidents and links runbooks, but it **does not learn from outcomes**. Every incident is treated as if the organization has never resolved anything like it before — even when engineers fixed the exact same issue last week.

### Customer Pain Points

| Pain Point | Impact |
|---|---|
| **Resolutions vanish into Slack threads.** The actual fix — commands, rollbacks, config changes — lives in ephemeral chat, not structured knowledge. | New on-callers repeat the same discovery from scratch. |
| **Verdicts lack historical grounding.** The AI Verdict Engine synthesizes from pattern matching but doesn't know "the last 3 times this fired on auth-service, the fix was rolling back the deploy." | Recommendations feel generic. Trust erodes. |
| **No feedback loop on accuracy.** The system has no idea whether its recommendations were followed or worked. No mechanism for self-improvement. | Engineers can't distinguish a 90%-reliable suggestion from a coin flip. |
| **Runbooks rot silently.** Engineers deviate from documented steps because the runbook is stale, but nobody flags it. | Responders follow outdated steps, wasting critical minutes. |

### The Gap

```
Current:   Incident → Similarity Search → Verdict → (end)
                                                ↑
                                            No feedback

Desired:   Incident → Similarity Search → Verdict → Resolution
               ↑           ↑                            │
               │           │                            ▼
               └───────────┴──── Learning Loop ←── Outcome Data
```

Without closing this loop, the system is a **static retrieval tool**, not an **adaptive copilot**. The pitch: *"Your 100th incident resolves faster than your 10th."*

---

## 2. Goals / Non-Goals

### Goals

| # | Goal | Success Criteria |
|---|---|---|
| G1 | Capture structured resolution data from every resolved incident | ≥80% of resolved incidents have structured resolution within 48h |
| G2 | Weight verdicts by historically successful resolutions | Verdict acceptance rate increases ≥20% within 3 months |
| G3 | Display calibrated confidence scores on every recommendation | Brier score deviation ≤0.10 from actual outcomes |
| G4 | Detect stale runbooks and surface update suggestions | ≥90% of runbooks with >30% deviation rate flagged within 2 weeks |
| G5 | Maintain cost efficiency | New features add ≤$0.015/incident to the $0.02–0.05 baseline |

### Non-Goals

- **Automated runbook editing.** We suggest updates; humans approve.
- **Real-time mid-incident capture.** Too noisy, privacy-sensitive. We capture post-resolution.
- **Replacing human judgment.** Confidence scores inform; they don't auto-resolve.
- **Cross-tenant learning.** All learning is tenant-scoped. No shared model across customers.
- **Conversational bot.** This is a background learning system, not a chatbot.

---

## 3. Architecture Overview

### System Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                         INCIDENT COPILOT                              │
│                                                                       │
│  ┌───────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  EXISTING  │
│  │ Similarity│  │    AI    │  │ Runbook  │  │Postmortem│            │
│  │  Search   │  │ Insights │  │ Linking  │  │ Module   │            │
│  └─────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘            │
│        │              │              │              │                  │
│  ┌─────┴──────────────┴──────────────┴──────────────┴──────┐         │
│  │                  AI Verdict Engine                        │         │
│  │            (Haiku compress → Sonnet synthesize)           │         │
│  └──────────────────────────┬──────────────────────────────┘         │
│                              │                                        │
│  ════════════════════════════╪════════════════════════════════  NEW   │
│                              │                                        │
│  ┌───────────────────────────┴────────────────────────────┐          │
│  │              ADAPTIVE LEARNING LOOP                     │          │
│  │              src/learning/                              │          │
│  │                                                         │          │
│  │  ┌──────────────┐ ┌─────────────┐ ┌────────────────┐  │          │
│  │  │  Resolution  │ │ Confidence  │ │   Runbook      │  │          │
│  │  │  Capture     │ │ Calibration │ │   Staleness    │  │          │
│  │  │  Engine      │ │ Engine      │ │   Detector     │  │          │
│  │  └──────┬───────┘ └──────┬──────┘ └───────┬────────┘  │          │
│  │         │                │                 │           │          │
│  │  ┌──────┴────────────────┴─────────────────┴────────┐  │          │
│  │  │        Resolution Knowledge Store                 │  │          │
│  │  │       (Postgres + pgvector embeddings)            │  │          │
│  │  └──────────────────────────────────────────────────┘  │          │
│  └────────────────────────────────────────────────────────┘          │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘

External Sources:
  ┌───────┐  ┌──────┐  ┌──────────┐  ┌──────────┐
  │ Slack │  │ Git  │  │ Deploy   │  │ PagerDuty│
  │  API  │  │ API  │  │ Pipeline │  │ / Ops    │
  └───────┘  └──────┘  └──────────┘  └──────────┘
```

### New Module Layout

```
src/learning/
├── __init__.py
├── router.py                  # FastAPI routes
├── capture/
│   ├── __init__.py
│   ├── orchestrator.py        # Coordinates all capture sources
│   ├── slack_collector.py     # Extracts resolution from Slack threads
│   ├── git_analyzer.py        # Finds commits/deploys in incident window
│   ├── postmortem_parser.py   # Structured fields from postmortems
│   └── annotation_api.py     # Engineer manual input endpoint
├── resolution/
│   ├── __init__.py
│   ├── store.py               # Resolution Knowledge Store CRUD
│   ├── embeddings.py          # Resolution embedding generation
│   └── ranker.py              # Recency + success rate ranking
├── confidence/
│   ├── __init__.py
│   ├── tracker.py             # Tracks verdict outcomes
│   ├── calibrator.py          # Bayesian calibration engine
│   └── scorer.py              # Generates confidence % for new verdicts
└── staleness/
    ├── __init__.py
    ├── detector.py            # Compares actual steps vs runbook steps
    ├── adherence_tracker.py   # Step-by-step deviation tracking
    └── suggester.py           # Generates runbook update suggestions
```

---

## 4. Pillar 1 — Resolution Capture

### Overview

When an incident resolves, the Resolution Capture Engine automatically collects what actually fixed it from multiple sources and produces a structured resolution record.

### Sources & Extraction

| Source | Signal | Extraction Method |
|---|---|---|
| **Slack thread** | Messages in incident channel between alert-fire and resolution | Haiku summarization: "Extract the specific actions that resolved this incident" |
| **Git commits** | Commits to affected service(s) during incident window ±30min | Diff analysis + commit message extraction |
| **Deploy pipeline** | Rollbacks, hotfixes, config changes deployed during window | Deploy event correlation from CI/CD webhooks |
| **Postmortem** | Root cause, mitigation, and resolution fields | Direct field extraction from postmortem module |
| **Engineer annotation** | Manual input via Slack button or API | Structured form: action type, commands, notes |

### Resolution Capture Flow

```
Incident status → "resolved"
        │
        ├──▶ Slack Collector ──────▶ ┐
        ├──▶ Git Analyzer ─────────▶ ├──▶ Capture Orchestrator
        ├──▶ Deploy Correlator ────▶ │         │
        └──▶ Postmortem Parser ────▶ ┘         │
                                               ▼
                                    Haiku: Merge & Deduplicate
                                               │
                                               ▼
                                    Structured Resolution Record
                                    + text-embedding-3-small vector
                                               │
                                               ▼
                                    Resolution Knowledge Store
```

### Structured Resolution Record

```json
{
  "resolution_id": "res-abc123",
  "incident_id": "INC-456",
  "service": "auth-service",
  "resolved_at": "2026-02-13T08:30:00Z",
  "resolution_type": "rollback|config_change|hotfix|restart|scaling|manual",
  "summary": "Rolled back auth-service from v2.3.1 to v2.3.0 due to memory leak in JWT validation",
  "actions": [
    {
      "type": "rollback",
      "target": "auth-service",
      "detail": "kubectl rollout undo deployment/auth-service -n production",
      "source": "slack_thread",
      "confidence": 0.92
    }
  ],
  "root_cause": "Memory leak introduced in v2.3.1 JWT validation refactor",
  "commits": ["abc123f", "def456a"],
  "time_to_resolve_min": 23,
  "sources_used": ["slack", "git", "postmortem"],
  "embedding": [0.012, -0.034, ...],  // 1536-dim vector
  "verified": false,
  "verified_by": null
}
```

### Engineer Annotation (Slack Integration)

When an incident resolves, post a Slack message with interactive buttons:

```
✅ INC-456 resolved (23 min)

How was this fixed?
[🔄 Rollback] [⚙️ Config Change] [🔥 Hotfix] [🔁 Restart] [📝 Other]

Or describe it: /copilot resolve "rolled back auth-service to v2.3.0"
```

This supplements automatic extraction and serves as ground truth validation.

---

## 5. Pillar 2 — Resolution-Weighted Verdicts

### Overview

Enhance the AI Verdict Engine to incorporate past resolutions when generating recommendations. Instead of generic pattern matching, the system says: *"Based on 3 similar incidents in the last 90 days, the most effective resolution was rolling back the deploy (resolved in avg 15 min)."*

### Resolution Ranking Algorithm

```python
def resolution_score(resolution, current_incident):
    """Score a past resolution for relevance to current incident."""

    # Semantic similarity (existing vector search)
    similarity = cosine_similarity(
        current_incident.embedding,
        resolution.embedding
    )

    # Recency decay: half-life of 90 days
    days_ago = (now() - resolution.resolved_at).days
    recency = 0.5 ** (days_ago / 90)

    # Success rate: was this resolution type effective for this service?
    success_rate = get_success_rate(
        service=resolution.service,
        resolution_type=resolution.resolution_type
    )

    # Verification bonus
    verified_bonus = 1.2 if resolution.verified else 1.0

    return (
        0.40 * similarity +
        0.25 * recency +
        0.25 * success_rate +
        0.10 * verified_bonus
    )
```

### Enhanced Verdict Prompt

The Sonnet synthesis prompt is augmented with resolution context:

```
Current incident: {incident_summary}
Similar incidents: {top_5_similar}

RESOLUTION HISTORY (ranked by relevance):
1. INC-312 (14 days ago, auth-service) — Rolled back deploy v2.3.1→v2.3.0
   Resolution time: 15 min | Success: verified ✓ | Similarity: 0.94
2. INC-287 (32 days ago, auth-service) — Rolled back deploy v2.2.8→v2.2.7
   Resolution time: 22 min | Success: verified ✓ | Similarity: 0.89
3. INC-201 (78 days ago, auth-service) — Restarted pods (did NOT resolve, required rollback)
   Resolution time: 45 min | Success: failed then escalated | Similarity: 0.85

Based on this context, generate a verdict with:
- Recommended action (weighted by historical success)
- Confidence percentage
- Supporting evidence from past resolutions
- What NOT to try (based on failed past attempts)
```

### Slack Card Enhancement

```
🔍 Incident Copilot — INC-456: auth-service high latency

📊 Confidence: 87% (based on 3 similar resolutions)

🎯 Recommended Action: Roll back auth-service deploy
   "Last 3 times this pattern occurred, rollback resolved it in avg 15 min"

⚠️ Skip: Pod restart (failed for INC-201, required escalation to rollback)

📋 Past Resolutions:
  • INC-312 (14d ago): Rollback v2.3.1→v2.3.0 — ✅ 15 min
  • INC-287 (32d ago): Rollback v2.2.8→v2.2.7 — ✅ 22 min

🔗 Runbook: auth-service-high-latency.md
```

---

## 6. Pillar 3 — Confidence Scoring & Calibration

### Overview

Track whether verdicts were followed and whether they worked. Use this feedback to calibrate confidence scores over time so that "87% confidence" actually means the recommendation is correct ~87% of the time.

### Outcome Tracking

After an incident resolves, the system compares:
1. **What was recommended** (the verdict)
2. **What was actually done** (from resolution capture)
3. **Whether it worked** (incident resolved within SLA? escalated?)

```python
class VerdictOutcome(BaseModel):
    verdict_id: str
    incident_id: str
    recommended_action: str
    actual_action: str
    recommendation_followed: bool    # Did they do what we suggested?
    incident_resolved: bool          # Did the incident resolve?
    time_to_resolve_min: int
    escalated: bool
    outcome: Literal["correct", "partially_correct", "incorrect", "not_followed"]
```

### Bayesian Calibration Engine

Confidence scores are calibrated using a Beta distribution per (service, pattern) pair:

```python
class ConfidenceCalibrator:
    """
    Maintains Beta(α, β) distributions per pattern.
    α = successful predictions, β = failed predictions.
    Prior: Beta(2, 2) — slight uncertainty, centered at 50%.
    """

    def update(self, pattern_key: str, was_correct: bool):
        if was_correct:
            self.distributions[pattern_key].alpha += 1
        else:
            self.distributions[pattern_key].beta += 1

    def get_confidence(self, pattern_key: str) -> float:
        dist = self.distributions[pattern_key]
        return dist.alpha / (dist.alpha + dist.beta)

    def get_confidence_interval(self, pattern_key: str) -> tuple[float, float]:
        """95% credible interval — shown when sample size is small."""
        return beta.ppf(0.025, α, β), beta.ppf(0.975, α, β)
```

### Calibration Levels

| Level | Key | Example |
|---|---|---|
| **Global** | `global` | Overall system accuracy |
| **Per-service** | `svc:{service_name}` | Accuracy for auth-service incidents |
| **Per-pattern** | `pat:{service}:{error_class}` | Accuracy for auth-service + OOM pattern |
| **Per-resolution-type** | `res:{service}:{resolution_type}` | Accuracy of rollback recommendations for auth-service |

The displayed confidence is the **most specific available level** with ≥5 data points, falling back to broader levels.

### Confidence Display Rules

| Data Points | Display |
|---|---|
| < 5 for any level | "Confidence: Low (insufficient history)" — no percentage |
| 5–15 at service level | "Confidence: 73% ± 15% (based on 8 similar incidents)" |
| > 15 at pattern level | "Confidence: 87% (based on 22 similar incidents)" |

---

## 7. Pillar 4 — Runbook Staleness Detection

### Overview

Track step-by-step adherence to runbooks during incident resolution. When engineers consistently deviate from documented steps, flag the runbook as stale and generate update suggestions.

### Adherence Tracking

When a runbook is linked to an incident, the system:
1. Extracts the runbook's numbered steps
2. After resolution, compares actual actions (from Resolution Capture) against runbook steps
3. Records which steps were followed, skipped, or substituted

```python
class RunbookAdherence(BaseModel):
    runbook_id: str
    incident_id: str
    total_steps: int
    steps_followed: list[int]       # Step numbers that were followed
    steps_skipped: list[int]        # Steps that were skipped
    steps_substituted: list[dict]   # {step: 3, instead: "ran X instead of Y"}
    additional_actions: list[str]   # Actions not in runbook
    adherence_rate: float           # steps_followed / total_steps
```

### Staleness Detection Algorithm

```python
def detect_stale_runbook(runbook_id: str, window_days: int = 90):
    recent = get_adherence_records(runbook_id, days=window_days)

    if len(recent) < 3:
        return None  # Insufficient data

    avg_adherence = mean(r.adherence_rate for r in recent)
    common_skips = find_commonly_skipped_steps(recent, threshold=0.5)
    common_substitutions = find_common_substitutions(recent, threshold=0.4)

    if avg_adherence < 0.70 or len(common_skips) > 0:
        return StalenessReport(
            runbook_id=runbook_id,
            staleness_score=1.0 - avg_adherence,
            incidents_analyzed=len(recent),
            commonly_skipped=common_skips,
            common_substitutions=common_substitutions,
            suggested_updates=generate_suggestions(common_skips, common_substitutions)
        )
```

### Staleness Notification

```
⚠️ Runbook Alert: auth-service-high-latency.md may be stale

📊 Adherence: 45% (across 8 recent incidents)

Commonly skipped steps:
  • Step 3: "Check connection pool settings" — skipped 6/8 times
  • Step 5: "Restart sidecar proxy" — skipped 7/8 times

Common substitutions:
  • Step 4: Instead of "scale up to 10 replicas", engineers ran
    "kubectl rollout undo" (5/8 times)

💡 Suggested updates:
  1. Remove steps 3 and 5 (consistently skipped, not relevant)
  2. Replace step 4 with: "Roll back to previous deploy version"
  3. Add new step: "Check deploy diff for memory-related changes"

[✅ Accept Suggestions] [📝 Edit Manually] [❌ Dismiss]
```

---

## 8. Data Model

### New Tables

```sql
-- Resolution records with embeddings
CREATE TABLE resolutions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    incident_id     VARCHAR(255) NOT NULL,
    service         VARCHAR(255) NOT NULL,
    resolved_at     TIMESTAMPTZ NOT NULL,
    resolution_type VARCHAR(50) NOT NULL,  -- rollback|config_change|hotfix|restart|scaling|manual
    summary         TEXT NOT NULL,
    actions         JSONB NOT NULL DEFAULT '[]',
    root_cause      TEXT,
    commits         JSONB DEFAULT '[]',
    time_to_resolve_min INTEGER,
    sources_used    JSONB DEFAULT '[]',
    verified        BOOLEAN DEFAULT FALSE,
    verified_by     VARCHAR(255),
    embedding       vector(1536),          -- pgvector
    created_at      TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT fk_incident FOREIGN KEY (incident_id)
        REFERENCES incidents(id)
);

CREATE INDEX idx_resolutions_embedding ON resolutions
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_resolutions_service ON resolutions(tenant_id, service);
CREATE INDEX idx_resolutions_type ON resolutions(tenant_id, resolution_type);

-- Verdict outcome tracking
CREATE TABLE verdict_outcomes (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,
    verdict_id              UUID NOT NULL,
    incident_id             VARCHAR(255) NOT NULL,
    recommended_action      TEXT NOT NULL,
    actual_action           TEXT,
    recommendation_followed BOOLEAN,
    incident_resolved       BOOLEAN,
    time_to_resolve_min     INTEGER,
    escalated               BOOLEAN DEFAULT FALSE,
    outcome                 VARCHAR(30),  -- correct|partially_correct|incorrect|not_followed
    recorded_at             TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_verdict_outcomes_tenant ON verdict_outcomes(tenant_id);

-- Confidence calibration state
CREATE TABLE confidence_calibrations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL,
    pattern_key VARCHAR(500) NOT NULL,   -- e.g. "svc:auth-service" or "pat:auth-service:oom"
    level       VARCHAR(30) NOT NULL,    -- global|service|pattern|resolution_type
    alpha       FLOAT NOT NULL DEFAULT 2.0,
    beta        FLOAT NOT NULL DEFAULT 2.0,
    sample_size INTEGER NOT NULL DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT now(),

    UNIQUE(tenant_id, pattern_key)
);

-- Runbook adherence tracking
CREATE TABLE runbook_adherence (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    runbook_id          VARCHAR(255) NOT NULL,
    incident_id         VARCHAR(255) NOT NULL,
    total_steps         INTEGER NOT NULL,
    steps_followed      JSONB DEFAULT '[]',
    steps_skipped       JSONB DEFAULT '[]',
    steps_substituted   JSONB DEFAULT '[]',
    additional_actions  JSONB DEFAULT '[]',
    adherence_rate      FLOAT NOT NULL,
    recorded_at         TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_adherence_runbook ON runbook_adherence(tenant_id, runbook_id);

-- Staleness reports
CREATE TABLE runbook_staleness_reports (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    runbook_id          VARCHAR(255) NOT NULL,
    staleness_score     FLOAT NOT NULL,
    incidents_analyzed  INTEGER NOT NULL,
    commonly_skipped    JSONB DEFAULT '[]',
    common_substitutions JSONB DEFAULT '[]',
    suggested_updates   JSONB DEFAULT '[]',
    status              VARCHAR(30) DEFAULT 'open',  -- open|accepted|dismissed
    created_at          TIMESTAMPTZ DEFAULT now()
);
```

---

## 9. API Endpoints

### Resolution Capture

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/learning/resolutions` | Create resolution record (auto or manual) |
| `GET` | `/api/v1/learning/resolutions/{incident_id}` | Get resolution for an incident |
| `PUT` | `/api/v1/learning/resolutions/{id}/verify` | Engineer verifies/corrects resolution |
| `GET` | `/api/v1/learning/resolutions/search` | Search resolutions by service, type, similarity |
| `POST` | `/api/v1/learning/resolutions/capture/{incident_id}` | Trigger auto-capture for a resolved incident |

### Confidence & Outcomes

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/learning/outcomes` | Record verdict outcome |
| `GET` | `/api/v1/learning/confidence/{pattern_key}` | Get confidence for a pattern |
| `GET` | `/api/v1/learning/confidence/report` | Calibration report across all patterns |
| `GET` | `/api/v1/learning/outcomes/stats` | Aggregate outcome stats |

### Runbook Staleness

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/learning/adherence` | Record runbook adherence for an incident |
| `GET` | `/api/v1/learning/staleness/{runbook_id}` | Get staleness report for a runbook |
| `GET` | `/api/v1/learning/staleness` | List all stale runbooks (filterable) |
| `POST` | `/api/v1/learning/staleness/{id}/accept` | Accept suggested updates |
| `POST` | `/api/v1/learning/staleness/{id}/dismiss` | Dismiss staleness report |

---

## 10. AI Pipeline Details

### Models & Usage

| Step | Model | Input | Output | Cost/call |
|---|---|---|---|---|
| Slack thread summarization | Haiku 3.5 | ~2K tokens (thread) | ~300 tokens (resolution summary) | ~$0.001 |
| Git diff analysis | Haiku 3.5 | ~1K tokens (diffs) | ~200 tokens (change summary) | ~$0.0005 |
| Resolution merging & dedup | Haiku 3.5 | ~1K tokens (multi-source) | ~400 tokens (structured record) | ~$0.001 |
| Resolution embedding | text-embedding-3-small | ~300 tokens | 1536-dim vector | ~$0.00001 |
| Enhanced verdict (with resolution context) | Sonnet 3.5 | ~4K tokens (incident + resolutions) | ~800 tokens (verdict) | ~$0.01 |
| Runbook adherence comparison | Haiku 3.5 | ~1.5K tokens (runbook + actions) | ~300 tokens (adherence record) | ~$0.001 |
| Staleness suggestion generation | Sonnet 3.5 | ~2K tokens (adherence history) | ~500 tokens (suggestions) | ~$0.005 |

### Cost Per Incident (Learning Loop Addition)

| Component | Per Incident | Frequency |
|---|---|---|
| Resolution capture (Haiku x3) | $0.0025 | Every resolved incident |
| Resolution embedding | $0.00001 | Every resolved incident |
| Enhanced verdict (already using Sonnet) | +$0.002 | Every new incident (additional context) |
| Adherence check (Haiku) | $0.001 | Incidents with linked runbooks (~60%) |
| Staleness report (Sonnet) | $0.005 | Weekly batch per stale runbook |
| **Total additional per-incident** | **~$0.006** | |

**New all-in cost: $0.026–$0.056/incident** — within the $0.02–0.05 target with minor overage on the high end.

---

## 11. Feedback Loops

```
                    ┌──────────────────────────────────┐
                    │         FEEDBACK LOOPS            │
                    └──────────────────────────────────┘

Loop 1: Resolution → Verdict Quality
─────────────────────────────────────
  Incident resolves → Resolution captured → Stored with embedding
       ↓
  Next similar incident → Resolution retrieved → Verdict enriched
       ↓
  Better verdict → Higher acceptance → More outcome data
       ↓
  Confidence calibration improves → Trust increases

Loop 2: Outcome → Confidence Calibration
─────────────────────────────────────────
  Verdict delivered → Engineer acts → Incident resolves (or not)
       ↓
  Outcome recorded → Bayesian update → Confidence adjusted
       ↓
  Next verdict shows calibrated confidence → Engineers trust scores

Loop 3: Adherence → Runbook Quality
────────────────────────────────────
  Runbook linked → Incident resolved → Actions compared to runbook
       ↓
  Deviations tracked → Pattern detected → Staleness flagged
       ↓
  Runbook updated → Adherence improves → Faster resolution

Loop 4: Meta-Learning (Monthly)
───────────────────────────────
  Aggregate all outcomes → Identify weak services/patterns
       ↓
  Adjust ranking weights → Retune resolution scoring
       ↓
  Overall system accuracy improves quarter-over-quarter
```

---

## 12. Migration Strategy

### Phase 0: Shadow Mode (Week 1–2)
- Deploy Resolution Capture Engine alongside existing pipeline
- Capture resolutions but **don't display** them in verdicts
- Validate extraction quality manually on 50+ incidents
- No user-facing changes

### Phase 1: Enriched Verdicts (Week 3–4)
- Add resolution context to Verdict Engine prompt
- Display past resolutions in Slack cards as "supplementary info"
- Confidence shown as "Beta — based on N incidents"
- Feature flag: `LEARNING_LOOP_ENABLED=true`

### Phase 2: Confidence Scoring (Week 5–8)
- Enable outcome tracking (auto + Slack button feedback)
- Begin calibration with Beta(2,2) prior
- Show confidence percentages once ≥5 data points per pattern
- Runbook adherence tracking begins silently

### Phase 3: Full Loop (Week 9–12)
- Resolution-weighted ranking fully active
- Confidence scores shown on all verdicts
- Staleness reports generated and surfaced
- Engineer feedback buttons on all resolution captures

### Rollback Plan
Each phase is behind a feature flag. Rollback = disable flag. No data migration needed for rollback; learning data accumulates regardless.

---

## 13. Privacy & Security

| Concern | Mitigation |
|---|---|
| **Slack thread content may contain secrets** | Haiku extraction prompt instructs: "Extract resolution actions only. Do not include credentials, tokens, secrets, or PII." Post-processing regex strips common secret patterns. |
| **Git diffs may contain sensitive code** | Only commit messages and file paths are stored by default. Full diff analysis is opt-in per tenant. |
| **Cross-tenant data isolation** | All queries include `tenant_id` filter. Vector search is tenant-scoped. No shared embeddings. |
| **Resolution data retention** | Configurable per tenant (default: 2 years). Automated purge job. |
| **Engineer attribution** | Resolution capture stores "who resolved" only if tenant enables it. Default: anonymous. |
| **Audit trail** | All learning loop operations logged to existing audit module (`src/audit/`). |

---

## 14. Metrics for Success

### Primary KPIs

| Metric | Baseline | Target (3 months) | Target (6 months) |
|---|---|---|---|
| **Verdict acceptance rate** | ~35% (estimated) | 50% | 65% |
| **Mean time to resolve (MTTR)** | Varies by service | -15% | -25% |
| **Resolution capture rate** | 0% (new feature) | 60% | 80% |
| **Confidence calibration (Brier score)** | N/A | ≤0.15 | ≤0.10 |
| **Stale runbooks detected** | 0 (no detection) | Flag 80% of stale runbooks | Flag 90%+ |
| **Engineer feedback rate** | 0% | 30% verify/correct | 50% |

### Secondary Metrics

- Resolutions per source type (Slack vs Git vs Postmortem vs Manual)
- Runbook adherence rate trend (should increase as runbooks improve)
- Confidence interval width (should narrow as data accumulates)
- Cost per incident (should stay within $0.06 ceiling)

---

## 15. Implementation Phases

| Phase | Duration | Deliverables | Dependencies |
|---|---|---|---|
| **Phase 1: Resolution Capture** | 3 weeks | Slack collector, Git analyzer, Postmortem parser, Resolution store, Engineer annotation API | Slack API access, Git webhooks |
| **Phase 2: Enhanced Verdicts** | 2 weeks | Resolution ranker, Enhanced verdict prompt, Updated Slack card template | Phase 1 |
| **Phase 3: Confidence Engine** | 3 weeks | Outcome tracker, Bayesian calibrator, Confidence scorer, Feedback UI | Phase 2 |
| **Phase 4: Runbook Staleness** | 2 weeks | Adherence tracker, Staleness detector, Suggestion generator, Notification UI | Phase 1 |
| **Phase 5: Tuning & Polish** | 2 weeks | Weight tuning, calibration validation, dashboard, documentation | Phases 1–4 |
| **Total** | **12 weeks** | | |

### Team Requirements

- 1 backend engineer (full-time, 12 weeks)
- 0.5 ML/AI engineer (embedding tuning, calibration validation)
- 0.5 frontend engineer (Slack card updates, dashboard)

---

## 16. Cost Analysis

### Infrastructure

| Component | Monthly Cost | Notes |
|---|---|---|
| pgvector storage (resolutions) | ~$5–20 | Scales with incident volume |
| Additional Haiku calls | ~$15–50 | At 1000 incidents/month |
| Additional Sonnet context | ~$20–60 | Larger prompts for verdicts |
| Embedding generation | ~$0.50 | Negligible |
| **Total additional** | **~$40–130/month** | For 1000 incidents/month |

### Per-Incident Breakdown

| Tier | Incidents/month | Current Cost | Learning Loop Add | New Total |
|---|---|---|---|---|
| Startup | 50 | $1.50 | $0.30 | $1.80 |
| Mid-market | 500 | $15 | $3 | $18 |
| Enterprise | 5000 | $150 | $30 | $180 |

### ROI Justification

If Learning Loop reduces MTTR by 15% (conservative):
- **Enterprise with 30-min avg MTTR**: Saves ~5 min/incident × 5000 incidents = 417 engineer-hours/month
- At $75/hr loaded cost: **$31,250/month saved** for $180/month in AI costs
- **ROI: 173x**

---

## 17. Competitive Differentiation

### Landscape Comparison

| Capability | Incident Copilot (with Learning Loop) | Rootly | FireHydrant | PagerDuty AIOps |
|---|---|---|---|---|
| **Similar incident matching** | ✅ Vector embeddings | ✅ Basic keyword | ✅ Basic | ✅ Pattern matching |
| **Resolution capture (structured)** | ✅ Multi-source auto-extraction | ❌ Manual postmortem only | ⚠️ Retro fields only | ❌ None |
| **Resolution-weighted verdicts** | ✅ Ranked by recency + success | ❌ No verdict engine | ❌ No verdict engine | ⚠️ "Likely cause" (no resolution weighting) |
| **Calibrated confidence scores** | ✅ Bayesian, per-service/pattern | ❌ | ❌ | ❌ |
| **Runbook staleness detection** | ✅ Auto-detect + suggest updates | ❌ | ⚠️ Manual review | ❌ |
| **Learns from every incident** | ✅ Continuous feedback loop | ❌ Static | ❌ Static | ⚠️ Limited |
| **Cost per incident** | $0.03–0.06 | N/A (manual) | N/A (manual) | ~$0.10+ (estimated) |

### Defensible Moat

The Learning Loop creates a **data flywheel** that competitors cannot replicate without:
1. Multi-source resolution extraction (Slack + Git + Deploy + Postmortem)
2. Outcome tracking with Bayesian calibration
3. Months of accumulated resolution data per customer

**The longer a customer uses it, the smarter it gets.** This is the strongest retention mechanism in incident management — switching costs increase with every resolved incident.

### Key Differentiator Messaging

> *"Other tools show you similar past incidents. We show you exactly what fixed them, how confident we are, and whether your runbooks are still accurate. Your 100th incident resolves faster than your 10th."*

---

## Appendix A: Open Questions

1. **Should resolution capture be opt-in or opt-out per source?** (Recommendation: opt-out, with Slack thread capture requiring explicit Slack app permission)
2. **Minimum incidents before showing confidence?** (Current proposal: 5, but may need tuning)
3. **Should staleness reports auto-create Jira/Linear tickets?** (Recommendation: Phase 2, behind integration flag)
4. **Cross-service resolution transfer?** (e.g., "rollback fixed auth-service, might fix payment-service too") — deferred to v2

## Appendix B: Related Existing Modules

| Module | Integration Point |
|---|---|
| `src/similarity/` | Resolution embeddings stored alongside incident embeddings; ranker extends similarity search |
| `src/ai/` | Verdict Engine prompt augmented with resolution context + confidence |
| `src/runbooks/` | Adherence tracker compares runbook steps vs actual actions |
| `src/postmortem/` | Resolution capture pulls from postmortem structured fields |
| `src/insights/` | Monthly meta-learning aggregates feed into pattern detection |
| `src/analytics/` | New dashboards for resolution rates, confidence calibration, runbook health |
| `src/integrations/slack.py` | New Slack blocks for resolution annotation + staleness alerts |
