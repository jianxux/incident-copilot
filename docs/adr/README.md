# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records for the Incident Copilot project.

## What is an ADR?

An ADR is a document that captures an important architectural decision made along with its context and consequences.

## Template

Use this template for new ADRs:

```markdown
# ADR-XXX: Title

## Status
Proposed | Accepted | Deprecated | Superseded by ADR-YYY

## Context
What is the issue that we're seeing that is motivating this decision or change?

## Decision
What is the change that we're proposing and/or doing?

## Consequences
What becomes easier or more difficult to do because of this change?
```

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [001](001-parallel-context-fetching.md) | Parallel Context Fetching with Timeout | Accepted |
| [002](002-log-compression-pipeline.md) | Multi-stage Log Compression Pipeline | Accepted |
| [003](003-pluggable-integrations.md) | Pluggable Integration Architecture | Accepted |
| [004](004-eval-framework.md) | Evaluation Framework for Quality | Accepted |
