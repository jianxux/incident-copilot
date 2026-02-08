# ADR-004: Evaluation Framework for Quality

## Status
Accepted

## Context

AI-powered analysis can be wrong. We need to:
1. Measure quality before shipping changes
2. Prevent regressions
3. Build confidence in the system

AWS and Datadog both emphasized their eval systems as critical infrastructure.

## Decision

Build a complete eval framework with three components:

### 1. Scoring Rubric
Four dimensions with weights:
- **Root Cause (40%)**: Did it identify correct root cause?
- **Reasoning (25%)**: Did it use correct evidence?
- **Actionability (20%)**: Are recommendations useful?
- **Failure Severity (15%)**: If wrong, how dangerous?

Pass threshold: 0.6 weighted score

### 2. Synthetic Incident Generator
Five scenario templates:
- Database connection exhaustion
- Memory leak / OOM
- Bad deployment
- Upstream timeout
- Configuration error

Each generates: logs, metrics, deploys, ground truth

### 3. Eval Harness
```python
harness = EvalHarness(copilot)
results = await harness.run_eval(synthetic_incidents)
summary = harness.summary()

# summary.passed / summary.failed
# summary.by_scenario (which scenarios we struggle with)
# summary.failure_severities (how bad are our mistakes)
```

## Consequences

### Positive
- Quantified quality (not "seems good")
- Regression detection before merge
- Identifies weak scenarios for improvement
- Builds customer trust ("we measure ourselves")

### Negative
- Synthetic incidents may not reflect real complexity
- Rubric requires tuning (what's "correct"?)
- Maintenance overhead for eval suite

### Mitigation
- Start with synthetic, add real incidents from design partners
- Rubric weights are configurable
- Eval runs in CI on every PR
