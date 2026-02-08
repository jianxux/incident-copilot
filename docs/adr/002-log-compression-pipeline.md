# ADR-002: Multi-stage Log Compression Pipeline

## Status
Accepted

## Context

During incidents, we may have 10K-100K+ log lines to analyze. LLM context windows are limited (200K tokens for Claude) and expensive (~$0.01/1K tokens for Opus).

Raw logs are:
- Verbose (health checks, debug noise)
- Redundant (same error repeated 1000x)
- Unranked (critical errors mixed with warnings)

## Decision

Implement a 5-stage compression pipeline:

```
Raw logs (100K lines)
    │
    ├── 1. PARSE
    │   Extract: timestamp, level, service, message
    │   Handle: JSON, ISO, syslog formats
    │
    ├── 2. FILTER
    │   Remove: health checks, debug, INFO
    │   Keep: ERROR, WARN, FATAL
    │   Result: ~5K lines
    │
    ├── 3. DEDUPLICATE
    │   Normalize: IPs, UUIDs, timestamps → placeholders
    │   Group: by signature hash
    │   Result: ~200 unique patterns
    │
    ├── 4. RANK
    │   Score: severity × frequency × recency × blast_radius
    │   Boost: OOM, panic, timeout keywords
    │   Result: Top 50 patterns
    │
    └── 5. SUMMARIZE
        LLM: Generate human-readable summary
        Result: ~2K tokens
```

## Consequences

### Positive
- 100K → 2K tokens (98% reduction)
- Preserves signal (ranked by importance)
- Cheap (Haiku for compression, Sonnet for reasoning)
- Fast (~100ms for 10K logs)

### Negative
- May miss edge cases filtered as "noise"
- Normalization could over-group distinct errors
- Requires tuning noise patterns per customer

### Mitigation
- Keep sample_raw in each pattern for verification
- Configurable noise patterns
- Fall back to raw logs if compression fails
