# ADR-001: Parallel Context Fetching with Timeout

## Status
Accepted

## Context

When an incident is triggered, we need to gather context from multiple sources:
- GitHub/GitLab (recent deploys)
- Datadog/CloudWatch (logs, metrics)
- On-call schedules
- Service dependencies

The target is to deliver a context card to Slack within 10 seconds of the incident firing.

Sequential fetching would be too slow (each source takes 2-5s).

## Decision

Use `asyncio.gather()` with a hard timeout to fetch all sources in parallel:

```python
scm_ctx, logs_ctx, oncall = await asyncio.wait_for(
    asyncio.gather(
        fetch_scm_context(service),
        fetch_logs_context(service),
        fetch_oncall_roster(service),
        return_exceptions=True  # Don't fail if one source fails
    ),
    timeout=8.0  # Leave 2s for AI summarization + Slack delivery
)
```

Key aspects:
1. **8 second timeout** for data fetching (leaves room for processing)
2. **`return_exceptions=True`** so one slow/failed source doesn't block others
3. **Graceful degradation** - context card shows what we got, notes what failed

## Consequences

### Positive
- Context delivery within 10s target
- Failed sources don't block the entire flow
- Easy to add new sources (just add to gather)

### Negative
- Debugging timing issues is harder (parallel execution)
- Must handle partial failures in context card rendering
- Rate limits can be hit if many incidents fire simultaneously

### Mitigation
- Structured logging with correlation IDs
- Caching layer for repeated queries
- Rate limit awareness in each adapter
