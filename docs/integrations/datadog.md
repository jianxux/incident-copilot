# Datadog

Incident Copilot can pull logs and related telemetry from Datadog during an incident.

## Create keys

1. Datadog → **Organization Settings** → **API Keys** → create an API key
2. Datadog → **Organization Settings** → **Application Keys** → create an application key

## Configure env vars

```bash
LOG_PROVIDER=datadog
DATADOG_API_KEY=...
DATADOG_APP_KEY=...
DATADOG_SITE=datadoghq.com
```

Common `DATADOG_SITE` values:

- `datadoghq.com` (US1)
- `datadoghq.eu` (EU)
- `us3.datadoghq.com`, `us5.datadoghq.com`

## Validate

Trigger a test incident and confirm the context card includes:

- log query links
- example log lines (if enabled)

## Troubleshooting

- **401**: keys invalid or revoked.
- **No logs found**: ensure your service name / tags match your queries.
