# Plugin Framework

The Incident Copilot Plugin Framework enables custom integrations without code changes.

## Plugin Types

| Type | Purpose |
|------|---------|
| **Webhook** | Send context cards to external systems |
| **Enrichment** | Fetch additional context from APIs |
| **Filter** | Filter/modify alerts before processing |

## API Endpoints

- `POST /plugins` - Register plugin
- `GET /plugins` - List plugins
- `GET /plugins/{id}` - Get plugin
- `PUT /plugins/{id}` - Update plugin
- `DELETE /plugins/{id}` - Remove plugin
- `POST /plugins/{id}/test` - Test plugin
- `POST /plugins/{id}/enable` - Enable plugin
- `POST /plugins/{id}/disable` - Disable plugin

## Webhook Config

```json
{
  "id": "my-webhook",
  "name": "My Webhook",
  "type": "webhook",
  "events": ["context.assembled"],
  "webhook_config": {
    "url": "https://example.com/webhook",
    "method": "POST",
    "headers": {"Authorization": "Bearer token"},
    "timeout_ms": 10000,
    "retry": {"max_retries": 3, "initial_delay_ms": 1000},
    "hmac": {"secret": "your-secret", "algorithm": "sha256"}
  }
}
```

## Filter Config

```json
{
  "id": "critical-filter",
  "name": "Critical Only",
  "type": "filter",
  "events": ["incident.triggered"],
  "filter_config": {
    "conditions": [{"field": "severity", "operator": "eq", "value": "critical"}],
    "match_mode": "all",
    "action": "include"
  }
}
```

## Events

- `incident.triggered` - New incident received
- `incident.resolved` - Incident resolved
- `incident.updated` - Incident updated
- `context.assembled` - Context card ready
- `postmortem.created` - Postmortem created

## Filter Operators

`eq`, `ne`, `in`, `not_in`, `contains`, `matches`, `gt`, `lt`, `gte`, `lte`

## HMAC Signatures

Webhooks support HMAC-SHA256/SHA512 signatures for security:
```
X-Webhook-Signature: sha256=hex_digest
```

## Retry Logic

Exponential backoff with jitter:
- Retries on 5xx errors and network failures
- No retry on 4xx client errors
- Configurable max_retries, initial_delay_ms, max_delay_ms

## Auto-Disable

Plugins auto-disable after 5 consecutive failures. Re-enable with:
```http
POST /plugins/{id}/enable
```
