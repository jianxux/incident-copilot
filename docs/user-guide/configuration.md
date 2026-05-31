# Configuration Reference

Complete reference for all Incident Copilot configuration options. All configuration is done via environment variables, typically in a `.env` file.

## Table of Contents

1. [Application Settings](#application-settings)
2. [Alert Sources](#alert-sources)
3. [Source Control](#source-control)
4. [Log Providers](#log-providers)
5. [Notification Channels](#notification-channels)
6. [AI Configuration](#ai-configuration)
7. [Issue Tracking](#issue-tracking)
8. [Database & Cache](#database--cache)
9. [On-Call Roster](#on-call-roster)
10. [Rate Limiting](#rate-limiting)
11. [SLA Tracking](#sla-tracking)
12. [Alert Correlation](#alert-correlation)
13. [Audit Logging](#audit-logging)
14. [Authentication & SSO](#authentication--sso)
15. [Billing (Stripe)](#billing-stripe)

---

## Application Settings

Basic application configuration.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `APP_NAME` | string | `incident-copilot` | Application name used in logs |
| `DEBUG` | bool | `false` | Enable debug mode with verbose logging |
| `APP_URL` | string | `http://localhost:8000` | Public URL of the application |
| `SECRET_KEY` | string | `change-me-in-production` | Secret key for signing tokens (change in production!) |

### Example

```bash
APP_NAME=incident-copilot
DEBUG=false
APP_URL=https://incident-copilot.example.com
SECRET_KEY=your-random-secure-string-here
```

---

## Alert Sources

### PagerDuty

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `PAGERDUTY_API_KEY` | string | | PagerDuty REST API key |
| `PAGERDUTY_WEBHOOK_SECRET` | string | | Webhook signing secret for verification |

### Opsgenie

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OPSGENIE_API_KEY` | string | | Opsgenie API key (GenieKey) |
| `OPSGENIE_WEBHOOK_SECRET` | string | | Webhook signing secret |
| `OPSGENIE_REGION` | string | `us` | API region: `us` or `eu` |

### Example

```bash
# PagerDuty
PAGERDUTY_API_KEY=your-pagerduty-api-key
PAGERDUTY_WEBHOOK_SECRET=your-webhook-signing-secret

# OR Opsgenie
OPSGENIE_API_KEY=your-opsgenie-geniekey
OPSGENIE_WEBHOOK_SECRET=your-webhook-secret
OPSGENIE_REGION=us
```

---

## Source Control

### GitHub

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `GITHUB_TOKEN` | string | | Personal access token |
| `GITHUB_ORG` | string | | GitHub organization name |
| `GITHUB_APP_ID` | string | | GitHub App ID (alternative to PAT) |
| `GITHUB_APP_PRIVATE_KEY_PATH` | string | | Path to GitHub App private key |
| `GITHUB_APP_INSTALLATION_ID` | string | | GitHub App installation ID |

### GitLab

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `GITLAB_TOKEN` | string | | GitLab personal access token |
| `GITLAB_URL` | string | `https://gitlab.com` | GitLab instance URL |
| `GITLAB_PROJECT_MAP` | JSON | `{}` | Service to project path mapping |

### Service Mapping

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SERVICE_REPO_MAP` | JSON | `{}` | Service name to repository mapping |

### Example

```bash
# GitHub with PAT
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
GITHUB_ORG=my-company

# Custom service mapping
SERVICE_REPO_MAP='{"payments-api": "my-company/payment-service", "auth": "my-company/auth-platform"}'

# OR GitLab
GITLAB_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx
GITLAB_URL=https://gitlab.my-company.com
GITLAB_PROJECT_MAP='{"payments-api": "backend/payments", "auth": "platform/auth"}'
```

---

## Log Providers

### Provider Selection

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `LOG_PROVIDER` | string | `datadog` | Log provider: `datadog`, `cloudwatch`, `loki`, `splunk`, `newrelic`, `elastic` |

### Datadog

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DATADOG_API_KEY` | string | | Datadog API key |
| `DATADOG_APP_KEY` | string | | Datadog application key |
| `DATADOG_SITE` | string | `datadoghq.com` | Datadog site URL |

### AWS CloudWatch

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AWS_REGION` | string | | AWS region |
| `AWS_ACCESS_KEY_ID` | string | | AWS access key (optional, uses boto3 defaults) |
| `AWS_SECRET_ACCESS_KEY` | string | | AWS secret key |
| `CLOUDWATCH_LOG_GROUP_MAP` | JSON | `{}` | Service to log group mapping |

### Grafana Loki

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `LOKI_URL` | string | | Loki base URL |
| `LOKI_AUTH_TYPE` | string | `none` | Auth type: `none`, `basic`, `bearer` |
| `LOKI_USERNAME` | string | | Username for basic auth |
| `LOKI_PASSWORD` | string | | Password for basic auth |
| `LOKI_TOKEN` | string | | Bearer token |
| `LOKI_ORG_ID` | string | | Tenant ID for multi-tenant |
| `LOKI_SERVICE_LABELS` | JSON | `{}` | Service to label selector mapping |

### Splunk

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SPLUNK_URL` | string | | Splunk REST API URL |
| `SPLUNK_TOKEN` | string | | Splunk auth token |
| `SPLUNK_USERNAME` | string | | Splunk username (alternative) |
| `SPLUNK_PASSWORD` | string | | Splunk password |
| `SPLUNK_INDEX_MAP` | JSON | `{}` | Service to index mapping |

### New Relic

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `NEWRELIC_API_KEY` | string | | User API key (NRAK-...) |
| `NEWRELIC_ACCOUNT_ID` | string | | Account ID |
| `NEWRELIC_REGION` | string | `us` | Region: `us` or `eu` |
| `NEWRELIC_APP_MAP` | JSON | `{}` | Service to app ID mapping |

### Elasticsearch

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ELASTIC_URL` | string | | Elasticsearch URL |
| `ELASTIC_API_KEY` | string | | API key |
| `ELASTIC_USERNAME` | string | | Username (alternative) |
| `ELASTIC_PASSWORD` | string | | Password |
| `ELASTIC_INDEX_PATTERN` | string | `logs-*` | Default index pattern |
| `ELASTIC_SERVICE_FIELD` | string | `service.name` | Field containing service name |
| `ELASTIC_TIMESTAMP_FIELD` | string | `@timestamp` | Timestamp field |
| `ELASTIC_MESSAGE_FIELD` | string | `message` | Message field |
| `ELASTIC_LEVEL_FIELD` | string | `log.level` | Log level field |
| `ELASTIC_VERIFY_SSL` | bool | `true` | Verify SSL certificates |
| `ELASTIC_SERVICE_INDEX_MAP` | JSON | `{}` | Service to index mapping |

### Example

```bash
# Datadog
LOG_PROVIDER=datadog
DATADOG_API_KEY=your-api-key
DATADOG_APP_KEY=your-app-key
DATADOG_SITE=datadoghq.com

# OR CloudWatch
LOG_PROVIDER=cloudwatch
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=<your-aws-access-key-id>
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/xxxxx
CLOUDWATCH_LOG_GROUP_MAP='{"payments": "/aws/lambda/payments"}'

# OR Loki (Grafana Cloud)
LOG_PROVIDER=loki
LOKI_URL=https://logs-prod-us-central1.grafana.net
LOKI_AUTH_TYPE=basic
LOKI_USERNAME=12345
LOKI_PASSWORD=glc_xxxxxxxx
```

---

## Notification Channels

### Provider Selection

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `NOTIFICATION_PROVIDER` | string | `slack` | Provider: `slack`, `teams`, or `both` |

### Slack

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SLACK_BOT_TOKEN` | string | | Bot OAuth token (xoxb-...) |
| `SLACK_SIGNING_SECRET` | string | | App signing secret |
| `SLACK_DEFAULT_CHANNEL` | string | `#incidents` | Default channel for notifications |

### Microsoft Teams

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TEAMS_WEBHOOK_URL` | string | | Incoming Webhook URL |

### Example

```bash
# Slack only
NOTIFICATION_PROVIDER=slack
SLACK_BOT_TOKEN=xoxb-<your-slack-bot-token>
SLACK_DEFAULT_CHANNEL=#incidents

# Teams only
NOTIFICATION_PROVIDER=teams
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/xxx

# Both
NOTIFICATION_PROVIDER=both
SLACK_BOT_TOKEN=xoxb-xxx
SLACK_DEFAULT_CHANNEL=#incidents
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/xxx
```

---

## AI Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ANTHROPIC_API_KEY` | string | | Anthropic (Claude) API key |
| `AI_MODEL` | string | `claude-3-haiku-20240307` | Claude model for summarization |
| `OPENAI_API_KEY` | string | | OpenAI API key (for embeddings) |

### Model Options

| Model | Speed | Cost | Use Case |
|-------|-------|------|----------|
| `claude-3-haiku-20240307` | Fastest | $ | Default, production |
| `claude-3-sonnet-20240229` | Medium | $$ | More detailed analysis |
| `claude-3-opus-20240229` | Slower | $$$ | Complex incidents |

### Example

```bash
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxx
AI_MODEL=claude-3-haiku-20240307
```

---

## Issue Tracking

### Jira

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `JIRA_BASE_URL` | string | | Jira Cloud URL |
| `JIRA_EMAIL` | string | | User email |
| `JIRA_API_TOKEN` | string | | API token |
| `JIRA_DEFAULT_PROJECT` | string | `INCIDENT` | Default project key |

### Linear

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `LINEAR_API_KEY` | string | | Linear API key |
| `LINEAR_TEAM_ID` | string | | Default team ID |
| `LINEAR_LABEL_IDS` | JSON array | `[]` | Label IDs to apply |

### ServiceNow

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SERVICENOW_INSTANCE` | string | | Instance URL |
| `SERVICENOW_USERNAME` | string | | Username |
| `SERVICENOW_PASSWORD` | string | | Password |
| `SERVICENOW_API_KEY` | string | | OAuth token (alternative) |
| `SERVICENOW_ASSIGNMENT_GROUP` | string | | Default assignment group |
| `SERVICENOW_CALLER_ID` | string | | Default caller ID |

### Example

```bash
# Jira
JIRA_BASE_URL=https://mycompany.atlassian.net
JIRA_EMAIL=oncall@mycompany.com
JIRA_API_TOKEN=ATATT3xFfGF0xxxx
JIRA_DEFAULT_PROJECT=INC

# OR Linear
LINEAR_API_KEY=lin_api_xxxxxxxxxxxxxxxxxxxx
LINEAR_TEAM_ID=abc123-def456-...
LINEAR_LABEL_IDS=["incident-label-id"]
```

---

## Database & Cache

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DATABASE_URL` | string | `postgresql+asyncpg://postgres:postgres@localhost:5432/incident_copilot` | PostgreSQL connection URL |
| `REDIS_URL` | string | `redis://localhost:6379/0` | Redis connection URL |

### Example

```bash
DATABASE_URL=postgresql+asyncpg://user:pass@db.example.com:5432/incident_copilot
REDIS_URL=redis://:password@redis.example.com:6379/0
```

---

## On-Call Roster

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ONCALL_PROVIDER` | string | `auto` | Provider: `pagerduty`, `opsgenie`, or `auto` |
| `ONCALL_ENABLED` | bool | `true` | Enable on-call roster fetching |
| `ONCALL_SCHEDULE_ID` | string | | Default schedule ID |
| `ONCALL_SCHEDULE_MAP` | JSON | `{}` | Service to schedule ID mapping |

### Example

```bash
ONCALL_PROVIDER=pagerduty
ONCALL_ENABLED=true
ONCALL_SCHEDULE_MAP='{"payments-api": "PABC123", "auth-service": "PDEF456"}'
```

---

## Rate Limiting

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `RATELIMIT_ENABLED` | bool | `true` | Enable API rate limiting |
| `RATELIMIT_EXCLUDE_PATHS` | JSON array | `["/health", ...]` | Paths to exclude |
| `RATELIMIT_IP_CAPACITY` | int | `100` | Max requests per IP (burst) |
| `RATELIMIT_IP_REFILL_RATE` | float | `10.0` | Tokens/second per IP |
| `RATELIMIT_API_KEY_CAPACITY` | int | `1000` | Max requests per API key |
| `RATELIMIT_API_KEY_REFILL_RATE` | float | `50.0` | Tokens/second per API key |
| `RATELIMIT_TENANT_CAPACITY` | int | `5000` | Max requests per tenant |
| `RATELIMIT_TENANT_REFILL_RATE` | float | `100.0` | Tokens/second per tenant |
| `RATELIMIT_USER_CAPACITY` | int | `200` | Max requests per user |
| `RATELIMIT_USER_REFILL_RATE` | float | `20.0` | Tokens/second per user |
| `RATELIMIT_GLOBAL_CAPACITY` | int | `10000` | Global API rate limit |
| `RATELIMIT_GLOBAL_REFILL_RATE` | float | `500.0` | Global tokens/second |

### Example

```bash
RATELIMIT_ENABLED=true
RATELIMIT_IP_CAPACITY=200
RATELIMIT_IP_REFILL_RATE=20.0
```

---

## SLA Tracking

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SLA_ENABLED` | bool | `true` | Enable SLA tracking |
| `SLA_RESPONSE_CRITICAL_MINUTES` | int | `15` | Response SLA for critical |
| `SLA_RESPONSE_HIGH_MINUTES` | int | `30` | Response SLA for high |
| `SLA_RESPONSE_MEDIUM_MINUTES` | int | `60` | Response SLA for medium |
| `SLA_RESPONSE_LOW_MINUTES` | int | `240` | Response SLA for low |
| `SLA_RESPONSE_INFO_MINUTES` | int | `480` | Response SLA for info |
| `SLA_RESOLUTION_CRITICAL_MINUTES` | int | `60` | Resolution SLA for critical |
| `SLA_RESOLUTION_HIGH_MINUTES` | int | `240` | Resolution SLA for high |
| `SLA_RESOLUTION_MEDIUM_MINUTES` | int | `480` | Resolution SLA for medium |
| `SLA_RESOLUTION_LOW_MINUTES` | int | `1440` | Resolution SLA for low |
| `SLA_RESOLUTION_INFO_MINUTES` | int | `2880` | Resolution SLA for info |
| `SLA_AT_RISK_THRESHOLD` | float | `0.75` | At-risk threshold (% elapsed) |

### Example

```bash
SLA_ENABLED=true
SLA_RESPONSE_CRITICAL_MINUTES=10
SLA_RESOLUTION_CRITICAL_MINUTES=30
```

---

## Alert Correlation

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `CORRELATION_ENABLED` | bool | `true` | Enable alert correlation |
| `CORRELATION_DEFAULT_RULES` | bool | `true` | Set up default rules on startup |
| `CORRELATION_TIME_WINDOW_SECONDS` | int | `300` | Time window for grouping (5 min) |
| `CORRELATION_SIMILARITY_THRESHOLD` | float | `0.7` | Fuzzy match threshold |
| `CORRELATION_GROUP_TTL` | int | `86400` | Group TTL in seconds (24h) |
| `CORRELATION_STALE_AFTER_SECONDS` | int | `3600` | Mark stale after inactivity (1h) |
| `CORRELATION_MAX_ALERTS_PER_GROUP` | int | `1000` | Max alerts per group |
| `CORRELATION_SUPPRESS_DUPLICATES` | bool | `true` | Suppress duplicate notifications |
| `CORRELATION_RE_NOTIFY_AFTER_SECONDS` | int | `1800` | Re-notify after (30 min) |

### Example

```bash
CORRELATION_ENABLED=true
CORRELATION_TIME_WINDOW_SECONDS=600
CORRELATION_SUPPRESS_DUPLICATES=true
```

---

## Audit Logging

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AUDIT_ENABLED` | bool | `true` | Enable audit logging |
| `AUDIT_RETENTION_DAYS` | int | `90` | Days to retain audit logs |
| `AUDIT_LOG_ALL_REQUESTS` | bool | `false` | Log all API requests (verbose) |
| `AUDIT_EXCLUDE_PATHS` | JSON array | `["/health", ...]` | Paths to exclude |

### Example

```bash
AUDIT_ENABLED=true
AUDIT_RETENTION_DAYS=180
AUDIT_LOG_ALL_REQUESTS=false
```

---

## Authentication & SSO

### OAuth Providers

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `GITHUB_OAUTH_CLIENT_ID` | string | | GitHub OAuth App client ID |
| `GITHUB_OAUTH_CLIENT_SECRET` | string | | GitHub OAuth App client secret |
| `GOOGLE_OAUTH_CLIENT_ID` | string | | Google OAuth client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | string | | Google OAuth client secret |

### SSO General

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SSO_SESSION_LIFETIME_MINUTES` | int | `10` | SSO session state lifetime |
| `SSO_JIT_PROVISIONING_DEFAULT` | bool | `true` | Enable JIT user provisioning |

### SAML

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SAML_SP_PRIVATE_KEY` | string | | SP private key (PEM) |
| `SAML_SP_CERTIFICATE` | string | | SP certificate (PEM) |
| `SAML_WANT_ASSERTIONS_SIGNED` | bool | `true` | Require signed assertions |
| `SAML_WANT_MESSAGES_SIGNED` | bool | `true` | Require signed messages |

### OIDC

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OIDC_DEFAULT_SCOPES` | string | `openid email profile` | Default OIDC scopes |
| `OIDC_USE_PKCE_DEFAULT` | bool | `true` | Use PKCE by default |

---

## Billing (Stripe)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `STRIPE_API_KEY` | string | | Stripe API secret key |
| `STRIPE_PUBLISHABLE_KEY` | string | | Stripe publishable key |
| `STRIPE_WEBHOOK_SECRET` | string | | Stripe webhook signing secret |
| `STRIPE_PRICE_STARTER` | string | | Price ID for Starter plan |
| `STRIPE_PRICE_PRO` | string | | Price ID for Pro plan |
| `STRIPE_PRICE_ENTERPRISE` | string | | Price ID for Enterprise plan |

---

## Example Complete Configuration

```bash
# =============================================================================
# INCIDENT COPILOT - PRODUCTION CONFIGURATION
# =============================================================================

# Application
APP_NAME=incident-copilot
DEBUG=false
APP_URL=https://incident-copilot.example.com
SECRET_KEY=your-256-bit-random-secret-key

# Alert Source - PagerDuty
PAGERDUTY_API_KEY=your-pagerduty-api-key
PAGERDUTY_WEBHOOK_SECRET=your-webhook-secret

# Source Control - GitHub
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
GITHUB_ORG=your-organization
SERVICE_REPO_MAP='{"payments": "your-org/payment-service"}'

# Log Provider - Datadog
LOG_PROVIDER=datadog
DATADOG_API_KEY=your-datadog-api-key
DATADOG_APP_KEY=your-datadog-app-key
DATADOG_SITE=datadoghq.com

# Notifications - Slack
NOTIFICATION_PROVIDER=slack
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_DEFAULT_CHANNEL=#incidents

# AI - Claude
ANTHROPIC_API_KEY=sk-ant-api03-your-key
AI_MODEL=claude-3-haiku-20240307

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/incident_copilot
REDIS_URL=redis://redis:6379/0

# On-Call
ONCALL_PROVIDER=pagerduty
ONCALL_ENABLED=true

# Security
RATELIMIT_ENABLED=true
AUDIT_ENABLED=true
```

---

*← [Integrations](./integrations.md) | [Troubleshooting](./troubleshooting.md) →*
