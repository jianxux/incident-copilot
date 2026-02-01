# Runbook Auto-Linking Guide

This document explains how Incident Copilot automatically links relevant runbooks to incidents, helping on-call engineers quickly find resolution procedures.

## Overview

When an incident is triggered, Incident Copilot searches for relevant runbooks based on:

1. **Service name** - Exact match to the alerting service
2. **Alert keywords** - Terms from the alert title/description
3. **Error patterns** - Common error types detected in logs
4. **Historical matches** - Runbooks used for similar past incidents

The best matching runbook URL is included in the context card delivered to Slack.

## How Runbook Auto-Linking Works

### Matching Algorithm

```
┌─────────────────────────────────────────────────────────────────┐
│                     RUNBOOK MATCHING                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Incident Alert                                                │
│   ├── service: "payments-api"                                   │
│   ├── title: "High Error Rate"                                  │
│   └── logs: ["ConnectionTimeout", "Stripe API"]                 │
│                                                                 │
│         │                                                       │
│         ▼                                                       │
│   ┌─────────────────────────────────────────┐                   │
│   │         Runbook Index                   │                   │
│   │  ┌─────────────────────────────────┐    │                   │
│   │  │ payments-api-runbook.md         │    │                   │
│   │  │ services: [payments-api]        │◄───┼── Service Match   │
│   │  │ keywords: [payment, stripe]     │◄───┼── Keyword Match   │
│   │  └─────────────────────────────────┘    │                   │
│   │                                         │                   │
│   │  ┌─────────────────────────────────┐    │                   │
│   │  │ stripe-troubleshooting.md       │    │                   │
│   │  │ keywords: [stripe, timeout]     │◄───┼── Keyword Match   │
│   │  └─────────────────────────────────┘    │                   │
│   └─────────────────────────────────────────┘                   │
│                                                                 │
│         │                                                       │
│         ▼                                                       │
│   ┌─────────────────────────────────────────┐                   │
│   │  Scoring & Ranking                      │                   │
│   │  1. payments-api-runbook.md (0.95)      │                   │
│   │  2. stripe-troubleshooting.md (0.72)    │                   │
│   └─────────────────────────────────────────┘                   │
│                                                                 │
│         │                                                       │
│         ▼                                                       │
│   Best Match: payments-api-runbook.md                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Scoring Weights

| Factor | Weight | Description |
|--------|--------|-------------|
| Service exact match | 0.5 | Runbook explicitly tagged for the service |
| Title keyword match | 0.3 | Keywords from runbook appear in alert title |
| Log pattern match | 0.15 | Error patterns mentioned in runbook |
| Historical usage | 0.05 | Runbook was used for similar past incidents |

A runbook is linked if the total score exceeds **0.6** (configurable).

---

## Supported Runbook Formats

Incident Copilot can index runbooks from multiple sources and formats.

### Markdown Files (Recommended)

Standard Markdown with optional YAML frontmatter for metadata:

```markdown
---
title: Payments API Runbook
services:
  - payments-api
  - payment-service
keywords:
  - stripe
  - payment failed
  - transaction error
  - timeout
---

# Payments API Runbook

## Overview

This runbook covers common issues with the payments-api service.

## Common Issues

### High Error Rate

1. Check Stripe status page
2. Review recent deployments
3. Check database connection pool

### Stripe API Timeouts

1. Verify Stripe API status
2. Check network connectivity
3. Review timeout configuration
...
```

**Frontmatter Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Human-readable title |
| `services` | list | Service names this runbook applies to |
| `keywords` | list | Search keywords for matching |
| `aliases` | list | Alternative names/terms |
| `severity` | string | Applicable severity levels |
| `updated` | date | Last update date |

### Confluence Pages

Runbooks stored in Confluence are indexed via the Confluence API:

```
┌─────────────────────────────────────────┐
│  Confluence Page                        │
├─────────────────────────────────────────┤
│  Title: Payments API Runbook            │
│  Space: Engineering/Runbooks            │
│  Labels: runbook, payments-api, stripe  │
│                                         │
│  [Page content...]                      │
└─────────────────────────────────────────┘
```

**Mapping:**
- `title` → Page title
- `services` → Labels starting with `service:` or service names in labels
- `keywords` → All labels + extracted terms

### Notion Pages

Runbooks in Notion databases:

```
┌─────────────────────────────────────────┐
│  Notion Database: Runbooks              │
├─────────────────────────────────────────┤
│  Properties:                            │
│  - Name: Payments API Runbook           │
│  - Services: payments-api               │
│  - Keywords: stripe, payment, timeout   │
│  - Status: Published                    │
└─────────────────────────────────────────┘
```

### GitHub Wiki

Runbooks in a GitHub repository wiki:

```
your-org/runbooks.wiki/
├── Home.md
├── payments-api.md      # Auto-matched to payments-api service
├── auth-service.md      # Auto-matched to auth-service
└── troubleshooting/
    └── stripe-issues.md
```

**Naming conventions:**
- `{service-name}.md` → Automatically linked to that service
- Files in `troubleshooting/` indexed by keywords

---

## Configuring Runbook Paths

### Local File System

For runbooks stored in a local directory:

```bash
# .env
RUNBOOK_PATH=/path/to/runbooks
RUNBOOK_FORMAT=markdown
```

**Directory structure:**
```
/path/to/runbooks/
├── services/
│   ├── payments-api.md
│   ├── auth-service.md
│   └── user-service.md
├── topics/
│   ├── database-issues.md
│   └── networking.md
└── index.yaml          # Optional: explicit mappings
```

### GitHub Repository

For runbooks in a GitHub repository:

```bash
# .env
RUNBOOK_SOURCE=github
RUNBOOK_GITHUB_REPO=your-org/runbooks
RUNBOOK_GITHUB_PATH=docs/runbooks  # Path within repo
RUNBOOK_GITHUB_BRANCH=main
```

### Confluence

For runbooks in Confluence:

```bash
# .env
RUNBOOK_SOURCE=confluence
CONFLUENCE_URL=https://your-company.atlassian.net/wiki
CONFLUENCE_TOKEN=your-api-token
CONFLUENCE_SPACE=ENG          # Space key
CONFLUENCE_LABEL=runbook      # Label to filter pages
```

### Notion

For runbooks in Notion:

```bash
# .env
RUNBOOK_SOURCE=notion
NOTION_TOKEN=secret_xxxxxxxxxxxxx
NOTION_DATABASE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

### Multiple Sources

Combine multiple runbook sources:

```bash
# .env
RUNBOOK_SOURCES=github,confluence

# GitHub config
RUNBOOK_GITHUB_REPO=your-org/runbooks
RUNBOOK_GITHUB_PATH=docs

# Confluence config
CONFLUENCE_URL=https://your-company.atlassian.net/wiki
CONFLUENCE_TOKEN=your-api-token
CONFLUENCE_SPACE=ENG
```

---

## Index Configuration

### index.yaml Format

Create an `index.yaml` file for explicit service-to-runbook mappings:

```yaml
# index.yaml
version: 1

# Default runbook URL pattern
default_url_pattern: "https://wiki.company.com/runbooks/{service}"

# Explicit mappings
services:
  payments-api:
    runbook: payments-api.md
    dashboard: https://grafana.company.com/d/payments
    keywords:
      - stripe
      - payment processing
      - transaction
    
  auth-service:
    runbook: https://wiki.company.com/auth-runbook
    dashboard: https://grafana.company.com/d/auth
    keywords:
      - authentication
      - login
      - oauth
      - jwt

  # Use a different runbook for specific alert types
  user-service:
    runbook: user-service.md
    alerts:
      "High Memory Usage":
        runbook: memory-troubleshooting.md
      "Database Connection Pool":
        runbook: database-runbook.md

# Keyword-based fallbacks
keywords:
  timeout:
    runbook: network-troubleshooting.md
  "out of memory":
    runbook: memory-troubleshooting.md
  "disk full":
    runbook: disk-space-runbook.md
```

### Environment Variable Configuration

```bash
# Enable/disable runbook linking
RUNBOOK_ENABLED=true

# Minimum score threshold (0.0-1.0)
RUNBOOK_MIN_SCORE=0.6

# Cache TTL for runbook index (seconds)
RUNBOOK_CACHE_TTL=3600

# Index refresh interval (seconds)
RUNBOOK_REFRESH_INTERVAL=300
```

---

## Custom Runbook Integration

### Webhook-Based Integration

For custom runbook systems, implement a webhook endpoint:

```bash
# .env
RUNBOOK_SOURCE=webhook
RUNBOOK_WEBHOOK_URL=https://your-runbook-service.com/api/search
RUNBOOK_WEBHOOK_TOKEN=your-api-token
```

**Expected Request:**

```json
POST /api/search
{
  "service": "payments-api",
  "title": "High Error Rate",
  "keywords": ["timeout", "stripe"],
  "severity": "high"
}
```

**Expected Response:**

```json
{
  "runbook": {
    "title": "Payments API Runbook",
    "url": "https://wiki.company.com/runbooks/payments-api",
    "score": 0.95,
    "sections": [
      {
        "title": "High Error Rate",
        "anchor": "#high-error-rate"
      }
    ]
  }
}
```

### Custom Adapter

Create a custom adapter by implementing the `RunbookProvider` interface:

```python
# src/integrations/runbooks/custom.py

from typing import Protocol
from ..models import Incident, Runbook

class RunbookProvider(Protocol):
    """Protocol for runbook providers."""
    
    async def search(
        self, 
        service: str,
        title: str,
        keywords: list[str],
    ) -> Runbook | None:
        """Search for a matching runbook."""
        ...
    
    async def refresh_index(self) -> None:
        """Refresh the runbook index."""
        ...


class CustomRunbookProvider:
    """Custom runbook provider implementation."""
    
    def __init__(self, settings):
        self.api_url = settings.custom_runbook_api_url
        self.api_key = settings.custom_runbook_api_key
    
    async def search(
        self,
        service: str,
        title: str,
        keywords: list[str],
    ) -> Runbook | None:
        # Your implementation here
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/search",
                json={
                    "service": service,
                    "title": title,
                    "keywords": keywords,
                },
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            
            if response.status_code == 200:
                data = response.json()
                return Runbook(
                    title=data["title"],
                    url=data["url"],
                    score=data.get("score", 1.0),
                )
            
            return None
    
    async def refresh_index(self) -> None:
        # Optional: implement index refresh
        pass
```

Register your provider:

```python
# src/config.py

RUNBOOK_PROVIDERS = {
    "github": GitHubRunbookProvider,
    "confluence": ConfluenceRunbookProvider,
    "notion": NotionRunbookProvider,
    "webhook": WebhookRunbookProvider,
    "custom": CustomRunbookProvider,  # Add your provider
}
```

---

## Best Practices

### Runbook Structure

A well-structured runbook improves matching and usefulness:

```markdown
---
title: Service Name Runbook
services: [service-name]
keywords: [key, error, terms]
---

# Service Name Runbook

## Overview
Brief description of the service and its dependencies.

## Quick Reference
- Dashboard: [link]
- Logs: [link]
- Metrics: [link]
- On-call: @team-name

## Common Alerts

### Alert Name 1
**Triggered when:** Description of trigger condition

**Quick fix:**
1. Step one
2. Step two

**Investigation:**
- Check A
- Check B

**Escalation:**
Contact @person if unresolved after 15 minutes.

### Alert Name 2
...

## Troubleshooting

### Issue Category 1
...

## Dependencies
- Upstream: service-a, service-b
- Downstream: service-c

## Rollback Procedures
...
```

### Naming Conventions

| Pattern | Example | Benefit |
|---------|---------|---------|
| `{service}.md` | `payments-api.md` | Auto-matched to service |
| `{service}-runbook.md` | `payments-api-runbook.md` | Clear purpose |
| `{category}/{service}.md` | `services/payments-api.md` | Organized structure |

### Keyword Strategy

Include these types of keywords in frontmatter:

1. **Service variations**: `payments-api`, `payments`, `payment-service`
2. **Error types**: `timeout`, `connection refused`, `500 error`
3. **Dependencies**: `stripe`, `postgres`, `redis`
4. **Symptoms**: `high latency`, `memory spike`, `disk full`

### Keeping Runbooks Updated

1. **Review after incidents**: Update runbooks with new findings
2. **Link to post-mortems**: Reference related incident reviews
3. **Version history**: Track changes via Git
4. **Scheduled reviews**: Quarterly runbook audits

---

## Troubleshooting

### Runbooks Not Linking

**Symptoms**: Context cards don't include runbook URLs

**Checks**:
1. Verify runbook source is configured:
   ```bash
   echo $RUNBOOK_SOURCE
   echo $RUNBOOK_PATH
   ```

2. Check index was built:
   ```bash
   curl http://localhost:8000/debug/runbook-index
   ```

3. Test matching manually:
   ```bash
   curl -X POST http://localhost:8000/debug/runbook-search \
     -d '{"service": "payments-api", "title": "High Error Rate"}'
   ```

**Solutions**:
- Ensure runbook files have correct frontmatter
- Check service name matches exactly
- Lower `RUNBOOK_MIN_SCORE` threshold

### Wrong Runbook Linking

**Symptoms**: Incorrect runbook matched to incidents

**Solutions**:
1. Add more specific keywords to runbooks
2. Use explicit service mappings in `index.yaml`
3. Increase `RUNBOOK_MIN_SCORE` threshold
4. Add negative keywords to exclude false matches

### Index Not Refreshing

**Symptoms**: New runbooks not appearing

**Checks**:
```bash
# Force index refresh
curl -X POST http://localhost:8000/admin/runbook-refresh
```

**Solutions**:
- Check `RUNBOOK_REFRESH_INTERVAL` setting
- Verify API credentials for external sources
- Check for errors in application logs

---

*Runbook Guide version: 1.0*
*Last updated: January 2026*
