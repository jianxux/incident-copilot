# Incident Copilot — Conversational Slack Bot (Thread Assistant) Product Spec

**Author:** (internal)

**Last updated:** 2026-02-11

## Status
Proposed

---

## 1) Overview & Value Proposition

### Problem
Incident Copilot today posts a **static context card** to Slack when an alert fires. Static cards are valuable for “first look” triage, but they degrade quickly as the incident evolves:

- Engineers ask *follow-up questions* that are not covered by the initial payload (“what changed in the last 24h?”, “what’s the blast radius?”, “show errors for this endpoint”).
- Context needs **refinement** (narrow to a timerange, filter logs, compare a metric before/after deploy).
- The right next action is often **interactive** (runbook link, owner lookup, suggested mitigation steps).

### Solution
Add a **conversational Slack bot** that participates in the *same incident thread* as the context card. Engineers can ask questions in natural language and the bot will:

1. Interpret the question relative to the incident context.
2. Call internal tools (deploys, logs, owners, runbooks, similarity search, metrics) as needed.
3. Respond with formatted, actionable answers (and optional interactive actions).

The bot is **thread-scoped**: it only engages in incident threads started by Incident Copilot.

### Why conversational > static context cards
- **Lower cognitive load:** users don’t need to leave Slack or know which dashboard to open.
- **Higher precision:** the bot can iteratively narrow scope (service, timerange, query) and confirm assumptions.
- **Keeps conversation in one place:** context, decisions, and bot answers are persisted in the incident thread.
- **Actionability:** can draft status updates, surface runbooks/owners, and (later) trigger actions.

### Competitor reference: Rootly
Rootly provides Slack-native incident management with interactive commands (e.g., updating status, assigning roles, incident timeline) and bot-driven prompts inside incident channels/threads.

Incident Copilot’s differentiator should be:
- **Context-first + analysis-first** (deploys/logs/similarity/AI summary already assembled), and
- **Thread-native** conversational Q&A that turns static context into an evolving “incident assistant”.

### Expected impact on MTTR
Primary mechanisms:
- Faster hypothesis generation (deploy diffs, log patterns, metrics deltas).
- Faster routing (ownership + oncall + runbook retrieval).
- Faster comms (status update drafts).

**Targets (initial):**
- 10–20% reduction in “time to first correct hypothesis” for services with good telemetry.
- 5–15% reduction in overall MTTR where incidents are repeatable patterns (via similarity search + runbooks).

---

## 2) User Experience (UX)

### UX flow (end-to-end)
1. **Alert fires** (PagerDuty/Opsgenie webhook → FastAPI).
2. Incident Copilot assembles context (GitHub deploys, Datadog logs, similar incidents, AI summary).
3. Incident Copilot posts a **Slack context card** to the configured channel.
4. The bot starts (or reuses) an **incident thread**:
   - If the card post is not already in a thread, the bot replies to the card to create a thread and pins an instruction message.
   - All interaction happens in that thread.
5. An on-call engineer asks a question by replying in the thread (e.g., “What changed in the last 24h?”).
6. Bot responds within SLA with:
   - A concise answer.
   - Evidence snippets and links (GitHub PRs, Datadog logs, dashboards, runbooks).
   - Follow-up prompts / suggested next questions.

### Entry points
The bot should respond to:
- Any user message in the incident thread that includes either:
  - a direct mention (`@IncidentCopilot`), or
  - a prefix command like `ic:` / `copilot:` / `/ic` (Phase 1 can implement `@mention` only).

### Response behavior (tone, formatting, SLAs)
- **Latency targets**
  - P50: < 2.5s
  - P90: < 6s
  - P99: < 12s
  (Use “typing…” indicator / ephemeral “working on it” message if > 3s.)

- **Tone**
  - Calm, factual, incident-appropriate.
  - No fluff. Prefer short bullets.
  - Ask clarifying questions when required inputs are missing.

- **Formatting**
  - Use Slack mrkdwn.
  - Prefer structured sections:
    - `*Answer*`
    - `*Evidence*`
    - `*Links*`
    - `*Next suggestions*`
  - Provide “copy/paste” blocks for status updates.

- **Safety / correctness**
  - Never claim actions were executed unless confirmed by an API response.
  - When uncertain, say what is unknown and propose next steps.

### Example conversations (realistic scenarios)

> Assumptions: incident thread is started from a context card for service `payments-api`, severity `critical`.

#### Scenario A — “What changed in the last 24h?”
**Engineer:** `@IncidentCopilot what changed in the last 24h for payments-api?`

**Bot:**
- *Answer*
  - 3 deploys in the last 24h. The most likely relevant change is `a1b2c3d` (2h ago): “Switch fraud check timeout to 750ms”.
- *Evidence*
  - Deploy timeline:
    - 2h ago: `a1b2c3d` by alice — <https://github/...|PR #4821>
    - 9h ago: `d4e5f6g` by bob — <https://github/...|PR #4809>
    - 22h ago: `h7i8j9k` by carol — <https://github/...|PR #4795>
- *Next suggestions*
  - Want a diff of PR #4821 or related log errors since that deploy?

Tool calls:
- `fetch_recent_deploys(service="payments-api", hours=24)`

#### Scenario B — “Show me similar incidents”
**Engineer:** `@IncidentCopilot show me similar incidents`

**Bot:**
- *Answer*
  - Found 2 similar incidents in the last 90 days:
    1) “Payments API latency spike: downstream fraud service timeouts” (2025-12-03)
    2) “5xx surge on /charge due to Redis connection pool exhaustion” (2025-11-14)
- *Evidence*
  - #1 resolution snippet: “Mitigation: rollback deploy + increase fraud timeout; long-term: circuit breaker.”
- *Links*
  - <https://incident-copilot/.../incidents/123|Incident #123>
  - <https://incident-copilot/.../incidents/97|Incident #97>
- *Next suggestions*
  - Should I pull the runbook for fraud-service timeouts or show matching logs for `timeout`?

Tool calls:
- `search_similar_incidents(description=<incident.title + top log patterns>)`

#### Scenario C — “Who owns this service?”
**Engineer:** `@IncidentCopilot who owns payments-api?`

**Bot:**
- *Answer*
  - Primary owners: `@payments-oncall` (Slack group), `@alice`, `@bob`.
- *Links*
  - Runbook: <https://...|payments-api runbook>
  - Team page: <https://...|Payments Platform>

Tool calls:
- `get_service_owners(service="payments-api")`
- `get_runbook(service="payments-api")`

#### Scenario D — “Draft a status page update”
**Engineer:** `@IncidentCopilot draft a status page update for customers`

**Bot:**
- *Draft (copy/paste)*
  ```
  Investigating: We are investigating an issue causing increased error rates and latency for card payments. Some customers may see payment failures.

  Next update: We will provide an update within 30 minutes.
  ```
- *Notes*
  - Based on current impact signals: 5xx up 4.2x and p95 latency +800ms on `/charge`.
  - If you confirm scope (all regions vs us-east only), I can tailor the wording.

Tool calls:
- `get_metrics(service="payments-api", metric="http.5xx_rate", timerange="last_30m")`
- `draft_status_update(incident=<context>, template="statuspage_investigating")`

#### Scenario E — “What’s the blast radius?”
**Engineer:** `@IncidentCopilot what's the blast radius?`

**Bot:**
- *Answer*
  - Likely affected:
    - `checkout-web` (calls `/charge`)
    - `subscriptions-service` (calls `/charge` for renewals)
  - Not currently affected (no correlated error increase):
    - `refunds-api`
- *Evidence*
  - Downstream dependency graph indicates `payments-api` is a critical dependency for checkout.
  - Correlated metric spikes observed for `checkout-web` 5xx starting at 23:41.

Tool calls:
- `get_blast_radius(service="payments-api")`
- `get_metrics(service="checkout-web", metric="http.5xx_rate", timerange="last_30m")`

#### Scenario F — “Run the payments-api runbook”
**Engineer:** `@IncidentCopilot run the payments-api runbook`

**Bot (Phase 1/2 behavior):**
- Phase 1 (read-only):
  - *Runbook link:* <https://...|payments-api runbook>
  - *Quick checks:*
    - Check p95 latency and 5xx rate
    - Check fraud-service dependency health
    - Check last deploy and consider rollback if errors started after deploy

- Phase 2 (actions):
  - “I can run the *‘collect diagnostics’* step (Datadog log queries + key metrics) and post results here. Proceed?”
  - (Upon confirmation) executes the defined action and posts results.

Tool calls:
- `get_runbook(service="payments-api")`
- (Phase 2) `fetch_logs(...)`, `get_metrics(...)` etc.

---

## 3) Architecture

### Slack transport: Events API vs Socket Mode
**Recommendation:** Support **Slack Events API** as primary; allow **Socket Mode** as optional dev mode.

- **Events API** (recommended for production)
  - Pros: simple infra, standard Slack app setup, works well behind HTTPS.
  - Cons: requires public URL + signature verification.

- **Socket Mode** (optional)
  - Pros: easier local dev without exposing a public endpoint.
  - Cons: long-lived websocket connection, extra operational surface.

**Decision:**
- Phase 1: Events API only (FastAPI routes).
- Phase 2+: optionally add Socket Mode behind a feature flag for local/dev.

### Receiving thread replies
Slack sends message events to the Events API subscription endpoint.

Key details:
- A reply in a thread has:
  - `event.type == "message"`
  - `event.thread_ts` set to the root message timestamp
  - `event.ts` is the message timestamp
- Messages from bots also appear; we must ignore self-messages to avoid loops.

We must subscribe to:
- `message.channels`, `message.groups`, (optionally `message.im`, `message.mpim`)

### Thread → Incident context mapping
Incident Copilot already posts a context card. We must capture identifiers:

- `channel_id`
- root message `ts` (used as `thread_ts`)
- incident id (internal)

Store mapping:
- Key: `(slack_team_id, channel_id, thread_ts)`
- Value: `incident_id`, `service_name`, `created_at`, cached context snapshot, token budget counters.

Where to get `thread_ts`:
- When posting the initial context card, Slack returns `ts`.
- We should immediately post a “bot instructions” reply in the thread with `thread_ts=<card_ts>` to ensure a thread exists and to publish usage.

### LLM integration (Claude) with tool-use pattern
Implement an **agent loop** that:
1. Creates a structured prompt including:
   - incident context snapshot
   - latest thread messages (limited)
   - list of available tools and schemas
2. Calls Claude.
3. If Claude requests a tool call, execute tool(s) and feed results back.
4. Repeat until model returns a final answer.

Guidelines:
- Use **bounded loops** (max tool iterations: 3–6).
- Use **per-incident budgets** (tokens + tool calls).
- Cache tool results per incident thread.

#### Tools available to the bot
The LLM may call these tools (implemented as Python async functions/services):
- `fetch_recent_deploys(service, hours)`
- `fetch_logs(service, timerange, query)`
- `search_similar_incidents(description)`
- `get_service_owners(service)`
- `get_runbook(service)`
- `draft_status_update(incident, template)`
- `get_blast_radius(service)`
- `get_metrics(service, metric, timerange)`

### Rate limiting and cost controls
Controls should exist at three layers:
1. **Slack event ingestion**: dedupe + ignore bot messages + drop non-incident threads.
2. **LLM calls**: per-thread token budget & per-minute rate limiting.
3. **Tool calls**: cache results, enforce bounds (timerange, max log lines).

Proposed budgets (initial defaults):
- Per incident thread:
  - Max 20 LLM requests / 6 hours
  - Max 80k input tokens + 20k output tokens cumulative
  - Max 40 tool calls
- Per user per minute:
  - Max 6 queries/minute (return “rate limited” message)

---

## 4) Data Model

### Thread context object schema
Persist as a row (SQL/Supabase) or Redis document.

```json
{
  "tenant_id": "...",
  "slack": {
    "team_id": "T123",
    "channel_id": "C123",
    "thread_ts": "1707522345.1234",
    "root_message_ts": "1707522345.1234",
    "context_card_ts": "1707522345.1234"
  },
  "incident": {
    "incident_id": "inc_abc",
    "provider": "pagerduty",
    "external_id": "PD-XYZ",
    "service": "payments-api",
    "severity": "critical",
    "title": "5xx spike on /charge",
    "triggered_at": "2026-02-11T07:41:00Z",
    "alert_url": "https://..."
  },
  "context_snapshot": {
    "github": {"recent_deploys": []},
    "datadog": {"top_patterns": []},
    "similar_incidents": [],
    "ai_summary": {"top_issues": [], "explanation": "..."}
  },
  "conversation": {
    "history": [
      {"ts": "...", "user": "U123", "role": "user", "text": "..."},
      {"ts": "...", "user": "B123", "role": "assistant", "text": "..."}
    ],
    "last_seen_event_id": "Ev123",
    "last_user_message_ts": "..."
  },
  "budgets": {
    "llm_requests": 0,
    "tool_calls": 0,
    "input_tokens": 0,
    "output_tokens": 0
  },
  "cache": {
    "tool_results": {
      "fetch_recent_deploys:payments-api:24": {
        "created_at": "...",
        "ttl_seconds": 600,
        "value": {"...": "..."}
      }
    }
  },
  "created_at": "...",
  "updated_at": "..."
}
```

### Conversation history storage
Store a bounded transcript:
- Last **N messages** (e.g., 25) and last **M minutes** (e.g., 180).
- Include only relevant fields (user id, text, timestamps).
- Optionally store “summaries” of longer threads.

### Tool result caching
- Cache key should include tool name + normalized args.
- TTL suggestions:
  - deploys: 5–10 minutes
  - logs: 1–3 minutes (often expensive)
  - owners/runbook: 1 day
  - similar incidents: 1 day (or until incident resolved)
  - metrics: 1–3 minutes

---

## 5) Implementation Plan

### Phase 1 (1 week): Basic Q&A in thread
Scope:
- Receive Slack message events for incident threads.
- Basic Q&A for:
  - deploys (`fetch_recent_deploys`)
  - logs (`fetch_logs`)
  - owners/runbook (`get_service_owners`, `get_runbook`)
- Minimal budgets + caching.

Deliverables:
- Slack Events API endpoint with signature verification.
- Thread context store & mapping from context card post → thread.
- LLM tool-use loop for read-only tools.

### Phase 2 (1 week): “Actions”
Scope:
- Draft status update (`draft_status_update`) with templates.
- “Run runbook” as guided execution:
  - Phase 2 should be **confirm-first**: bot proposes actions and asks for explicit confirmation.
  - For safety, “runbook execution” is limited to:
    - fetching diagnostics (logs/metrics)
    - posting a checklist
    - opening links
  - No destructive actions in Phase 2.

### Phase 3 (1 week): Proactive suggestions
Scope:
- Bot identifies patterns:
  - errors started right after deploy
  - known incident match found
  - dependency outage detected
- Posts a proactive message in thread:
  - “This resembles incident #123; mitigation was rollback + increase timeout. Want details?”

### File-by-file breakdown (what to build)
This spec assumes the repository layout:
- `incident-copilot/src/` (FastAPI backend)

**New modules (proposed):**
- `src/integrations/slack_events.py`
  - Verify Slack signature
  - Parse events payloads
  - Route message events to handler

- `src/bots/slack_thread_bot.py`
  - High-level orchestration: event → load context → call agent → post reply

- `src/bots/context_store.py`
  - Thread context persistence interface
  - Implementations:
    - `InMemoryContextStore` (dev)
    - `RedisContextStore` or `SupabaseContextStore` (prod)

- `src/bots/tools/` (tool implementations)
  - `deploys.py`, `logs.py`, `owners.py`, `runbooks.py`, `similarity.py`, `metrics.py`, `status_update.py`, `blast_radius.py`

- `src/llm/claude_agent.py`
  - Tool schema definitions
  - Tool execution loop
  - Budget accounting

**Touch existing files:**
- `src/integrations/slack.py`
  - Add `chat_postMessage(..., thread_ts=...)` support
  - Add helper to post “instructions” message in the thread

- `src/config.py`
  - Add Slack signing secret, events enabled flag, optional socket mode configs
  - Add bot mention name/id config

- `src/main.py` (or app router assembly)
  - Include new Slack events router

- `tests/`
  - Slack signature verification tests
  - Event handler unit tests
  - Tool caching/budget tests

---

## 6) API Design

### New FastAPI routes
Proposed endpoints (tenant-aware if applicable):

- `POST /api/integrations/slack/events`
  - Slack Events API receiver
  - Must handle:
    - URL verification (`type=url_verification`)
    - Event callbacks (`type=event_callback`)
  - Must verify Slack request signature using signing secret.

- `POST /api/integrations/slack/interactions` (Phase 2+)
  - For interactive components (buttons/selects) if we add “Confirm” actions.

- (Optional) `GET /api/incidents/{incident_id}/slack/thread`
  - Debug endpoint to retrieve mapping to Slack thread.

### Slack event subscription details
- **Request verification**
  - Use `X-Slack-Signature` and `X-Slack-Request-Timestamp`.
  - Reject if timestamp too old (e.g., > 5 minutes).

- **Deduplication**
  - Use `event_id` from payload to dedupe.

- **Ignoring bot loops**
  - Ignore events where `event.bot_id` is set or `event.user` == bot user.

### WebSocket considerations
- Not required for Events API.
- If Socket Mode is added:
  - Run a separate worker process that maintains Slack socket connection and forwards events internally (e.g., to an internal queue) to avoid mixing with HTTP server lifecycles.

---

## 7) Cost Analysis

### Claude API cost per incident (rough estimate)
Assumptions:
- Average incident has 6 user questions.
- Each question triggers 1–2 tool calls and 1–2 Claude calls.
- Prompt includes:
  - context snapshot (compressed): ~2k tokens
  - thread history (bounded): ~1k tokens
  - tool schemas: ~500 tokens

Estimated tokens:
- Per question: ~3.5k input + ~400 output
- 6 questions: ~21k input + ~2.4k output

If incidents are heavier (15 questions), budgets must kick in.

**Recommendation:** enforce budgets and add summarization when history grows.

### Slack API rate limits
Slack Web API is rate limited per method/workspace (varies by plan).
Mitigations:
- Post 1 response per user query.
- Use “typing…” message sparingly.
- Prefer updating a single “working” message rather than posting multiple updates.

### Caching strategy to minimize LLM calls
- Cache tool results aggressively with TTLs.
- Avoid re-sending full context snapshot every time; create:
  - a stable incident “facts” block
  - incremental “new tool results” appended
- When thread history grows > N messages, summarize and replace history with summary + last 5 turns.

---

## Appendix A — Key code patterns (snippets)

> Note: snippets are representative and may need adaptation to existing project structure.

### A1) Slack Events handler (FastAPI)

```python
from __future__ import annotations

import hmac
import hashlib
import time

import structlog
from fastapi import APIRouter, Header, HTTPException, Request

logger = structlog.get_logger()
router = APIRouter(prefix="/api/integrations/slack", tags=["slack"])


def verify_slack_signature(signing_secret: str, body: bytes, timestamp: str, signature: str) -> None:
    # Protect against replay
    now = int(time.time())
    ts = int(timestamp)
    if abs(now - ts) > 60 * 5:
        raise HTTPException(status_code=401, detail="stale slack request")

    basestring = f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8")
    expected = "v0=" + hmac.new(
        signing_secret.encode("utf-8"),
        basestring,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="invalid slack signature")


@router.post("/events")
async def slack_events(
    request: Request,
    x_slack_request_timestamp: str = Header(default=""),
    x_slack_signature: str = Header(default=""),
):
    settings = request.app.state.settings
    body = await request.body()

    verify_slack_signature(
        signing_secret=settings.slack_signing_secret,
        body=body,
        timestamp=x_slack_request_timestamp,
        signature=x_slack_signature,
    )

    payload = await request.json()

    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    if payload.get("type") != "event_callback":
        return {"ok": True}

    event = payload.get("event", {})

    # Dedupe by event_id (persist in store)
    event_id = payload.get("event_id")

    # Ignore bot messages to prevent loops
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return {"ok": True}

    # Only handle thread messages
    if event.get("type") == "message" and event.get("thread_ts"):
        await request.app.state.slack_thread_bot.handle_message_event(
            team_id=payload.get("team_id"),
            event_id=event_id,
            channel_id=event.get("channel"),
            thread_ts=event.get("thread_ts"),
            user_id=event.get("user"),
            text=event.get("text", ""),
            message_ts=event.get("ts"),
        )

    return {"ok": True}
```

### A2) Thread context manager (store + cache)

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC


@dataclass
class ToolCacheEntry:
    value: dict
    created_at: datetime
    ttl_seconds: int

    def is_valid(self, now: datetime) -> bool:
        age = (now - self.created_at).total_seconds()
        return age < self.ttl_seconds


@dataclass
class ThreadContext:
    tenant_id: str
    team_id: str
    channel_id: str
    thread_ts: str
    incident_id: str
    service: str

    history: list[dict] = field(default_factory=list)
    tool_cache: dict[str, ToolCacheEntry] = field(default_factory=dict)
    budgets: dict[str, int] = field(default_factory=lambda: {
        "llm_requests": 0,
        "tool_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
    })


class ContextStore:
    async def get(self, team_id: str, channel_id: str, thread_ts: str) -> ThreadContext | None:
        raise NotImplementedError

    async def upsert(self, ctx: ThreadContext) -> None:
        raise NotImplementedError

    async def dedupe_event(self, event_id: str) -> bool:
        """Return True if event is new, False if duplicate."""
        raise NotImplementedError


async def cached_tool_call(ctx: ThreadContext, cache_key: str, ttl: int, fn):
    now = datetime.now(UTC)
    entry = ctx.tool_cache.get(cache_key)
    if entry and entry.is_valid(now):
        return entry.value

    value = await fn()
    ctx.tool_cache[cache_key] = ToolCacheEntry(value=value, created_at=now, ttl_seconds=ttl)
    ctx.budgets["tool_calls"] += 1
    return value
```

### A3) Claude tool-use loop (bounded)

```python
from __future__ import annotations

import structlog

logger = structlog.get_logger()


MAX_ITERATIONS = 5


async def run_agent(claude_client, ctx, user_text: str, tools: dict[str, callable]) -> str:
    messages = build_messages(ctx, user_text)

    for i in range(MAX_ITERATIONS):
        ctx.budgets["llm_requests"] += 1

        resp = await claude_client.messages.create(
            model="claude-3-7-sonnet-latest",
            max_tokens=600,
            messages=messages,
            tools=tool_schemas(),
        )

        # pseudo-code: depends on anthropic SDK response format
        if resp.stop_reason == "tool_use":
            tool_name, tool_args = extract_tool_call(resp)
            tool_fn = tools.get(tool_name)
            if not tool_fn:
                messages.append({"role": "assistant", "content": f"Tool not found: {tool_name}"})
                break

            tool_result = await tool_fn(ctx, **tool_args)
            messages = append_tool_result(messages, tool_name, tool_args, tool_result)
            continue

        final_text = extract_final_text(resp)
        return final_text

    return "I couldn't complete that within the tool budget. Try narrowing the question (service/timerange) or ask for one specific artifact (deploys/logs/owners)."
```

---

## Open questions / follow-ups
- Multi-tenancy: confirm how Slack team/workspace mapping to `tenant_id` is stored and retrieved for Events API requests.
- Persistence: choose Redis vs Supabase for thread contexts.
- Permissions: decide if bot responds without mention (in incident threads only) or requires explicit mention.
- Action safety: define explicit allow-list for Phase 2 actions.
