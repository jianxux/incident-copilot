# Configuration

Incident Copilot is configured via environment variables. Settings are loaded using **Pydantic Settings** from `.env` by default.

!!! warning
    Do not commit secrets. Use `.env` locally and a secret manager in production.

## Core

| Variable | Default | Description |
|---|---:|---|
| `APP_NAME` | `incident-copilot` | Application name |
| `DEBUG` | `false` | Enable debug mode |
| `APP_URL` | `http://localhost:8000` | Public URL of the application |
| `SECRET_KEY` | `change-me-in-production` | Secret key for signing tokens |

## PagerDuty

| Variable | Default | Description |
|---|---:|---|
| `PAGERDUTY_API_KEY` | `""` | PagerDuty API key |
| `PAGERDUTY_WEBHOOK_SECRET` | `""` | PagerDuty webhook signing secret |
| `PAGERDUTY_OAUTH_CLIENT_ID` | `""` | PagerDuty OAuth Client ID |
| `PAGERDUTY_OAUTH_CLIENT_SECRET` | `""` | PagerDuty OAuth Client Secret |

## Opsgenie

| Variable | Default | Description |
|---|---:|---|
| `OPSGENIE_API_KEY` | `""` | Opsgenie API key |
| `OPSGENIE_WEBHOOK_SECRET` | `""` | Opsgenie webhook signing secret |
| `OPSGENIE_REGION` | `us` | Opsgenie region (`us` or `eu`) |

## On-call roster

| Variable | Default | Description |
|---|---:|---|
| `ONCALL_PROVIDER` | `auto` | On-call provider: `pagerduty`, `opsgenie`, or `auto` |
| `ONCALL_SCHEDULE_ID` | `""` | Default on-call schedule ID to fetch |
| `ONCALL_SCHEDULE_MAP` | `{}` | Service → schedule ID mapping (JSON) |
| `ONCALL_ENABLED` | `true` | Enable on-call roster fetching |

## Source control

### GitHub

| Variable | Default | Description |
|---|---:|---|
| `GITHUB_TOKEN` | `""` | GitHub personal access token |
| `GITHUB_ORG` | `""` | GitHub organization name |
| `GITHUB_OAUTH_CLIENT_ID` | `""` | GitHub OAuth App Client ID |
| `GITHUB_OAUTH_CLIENT_SECRET` | `""` | GitHub OAuth App Client Secret |

### GitLab

| Variable | Default | Description |
|---|---:|---|
| `GITLAB_TOKEN` | `""` | GitLab personal access token |
| `GITLAB_URL` | `https://gitlab.com` | GitLab instance URL |
| `GITLAB_PROJECT_MAP` | `{}` | Service → GitLab project path mapping (JSON) |

### Service → repo mapping

| Variable | Default | Description |
|---|---:|---|
| `SERVICE_REPO_MAP` | `{}` | Service → repo mapping (JSON) |

## Logs / Observability

### Provider selection

| Variable | Default | Description |
|---|---:|---|
| `LOG_PROVIDER` | `datadog` | `datadog`, `cloudwatch`, `loki`, or `splunk` |

### Datadog

| Variable | Default | Description |
|---|---:|---|
| `DATADOG_API_KEY` | `""` | Datadog API key |
| `DATADOG_APP_KEY` | `""` | Datadog application key |
| `DATADOG_SITE` | `datadoghq.com` | Datadog site |

### AWS / CloudWatch

| Variable | Default | Description |
|---|---:|---|
| `AWS_REGION` | `""` | AWS region for CloudWatch |
| `AWS_ACCESS_KEY_ID` | `""` | AWS access key ID (optional; boto defaults) |
| `AWS_SECRET_ACCESS_KEY` | `""` | AWS secret access key (optional) |
| `CLOUDWATCH_LOG_GROUP_MAP` | `{}` | Service → CloudWatch Log Group mapping (JSON) |

### Grafana Loki

| Variable | Default | Description |
|---|---:|---|
| `LOKI_URL` | `""` | Loki base URL |
| `LOKI_AUTH_TYPE` | `none` | `none`, `basic`, or `bearer` |
| `LOKI_USERNAME` | `""` | Loki username (basic auth) |
| `LOKI_PASSWORD` | `""` | Loki password (basic auth) |
| `LOKI_TOKEN` | `""` | Loki bearer token |
| `LOKI_ORG_ID` | `""` | Loki tenant ID (`X-Scope-OrgID`) |
| `LOKI_SERVICE_LABELS` | `{}` | Service → Loki label selector mapping (JSON) |

### Splunk

| Variable | Default | Description |
|---|---:|---|
| `SPLUNK_URL` | `""` | Splunk REST API URL |
| `SPLUNK_TOKEN` | `""` | Splunk auth token |
| `SPLUNK_USERNAME` | `""` | Splunk username (basic auth alternative) |
| `SPLUNK_PASSWORD` | `""` | Splunk password (basic auth) |
| `SPLUNK_INDEX_MAP` | `{}` | Service → Splunk index mapping (JSON) |

## Notifications

### Slack

| Variable | Default | Description |
|---|---:|---|
| `SLACK_BOT_TOKEN` | `""` | Slack bot OAuth token |
| `SLACK_SIGNING_SECRET` | `""` | Slack signing secret |
| `SLACK_DEFAULT_CHANNEL` | `#incidents` | Default Slack channel |
| `SLACK_OAUTH_CLIENT_ID` | `""` | Slack OAuth Client ID |
| `SLACK_OAUTH_CLIENT_SECRET` | `""` | Slack OAuth Client Secret |

### Microsoft Teams

| Variable | Default | Description |
|---|---:|---|
| `TEAMS_WEBHOOK_URL` | `""` | Teams Incoming Webhook URL |

### Notification provider

| Variable | Default | Description |
|---|---:|---|
| `NOTIFICATION_PROVIDER` | `slack` | `slack`, `teams`, or `both` |

## AI

| Variable | Default | Description |
|---|---:|---|
| `ANTHROPIC_API_KEY` | `""` | Anthropic API key |
| `AI_MODEL` | `claude-3-haiku-20240307` | AI model for summarization |
| `OPENAI_API_KEY` | `""` | OpenAI API key for embeddings |

## Data stores

| Variable | Default | Description |
|---|---:|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/incident_copilot` | PostgreSQL connection URL |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |

## OAuth (Google)

| Variable | Default | Description |
|---|---:|---|
| `GOOGLE_OAUTH_CLIENT_ID` | `""` | Google OAuth Client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | `""` | Google OAuth Client Secret |

## Supabase

| Variable | Default | Description |
|---|---:|---|
| `SUPABASE_URL` | `""` | Supabase project URL |
| `SUPABASE_ANON_KEY` | `""` | Supabase anon/public key |
| `SUPABASE_SERVICE_ROLE_KEY` | `""` | Supabase service role key |
| `SUPABASE_AUTH_ENABLED` | `false` | Use Supabase Auth |
| `SUPABASE_DB_ENABLED` | `false` | Use Supabase Postgres backend |

## Jira

| Variable | Default | Description |
|---|---:|---|
| `JIRA_BASE_URL` | `""` | Jira Cloud URL |
| `JIRA_EMAIL` | `""` | Jira user email |
| `JIRA_API_TOKEN` | `""` | Jira API token |
| `JIRA_DEFAULT_PROJECT` | `INCIDENT` | Default Jira project key |

## ServiceNow

| Variable | Default | Description |
|---|---:|---|
| `SERVICENOW_INSTANCE` | `""` | ServiceNow instance URL |
| `SERVICENOW_USERNAME` | `""` | ServiceNow username |
| `SERVICENOW_PASSWORD` | `""` | ServiceNow password |
| `SERVICENOW_API_KEY` | `""` | ServiceNow OAuth token / API key |
| `SERVICENOW_ASSIGNMENT_GROUP` | `""` | Default assignment group |
| `SERVICENOW_CALLER_ID` | `""` | Default caller ID |

## Linear

| Variable | Default | Description |
|---|---:|---|
| `LINEAR_API_KEY` | `""` | Linear API key |
| `LINEAR_TEAM_ID` | `""` | Default Linear team ID |
| `LINEAR_LABEL_IDS` | `[]` | Optional label IDs |

## Stripe

| Variable | Default | Description |
|---|---:|---|
| `STRIPE_API_KEY` | `""` | Stripe API secret key |
| `STRIPE_PUBLISHABLE_KEY` | `""` | Stripe publishable key |
| `STRIPE_WEBHOOK_SECRET` | `""` | Stripe webhook signing secret |
| `STRIPE_PRICE_STARTER` | `""` | Stripe Price ID (Starter) |
| `STRIPE_PRICE_PRO` | `""` | Stripe Price ID (Pro) |
| `STRIPE_PRICE_ENTERPRISE` | `""` | Stripe Price ID (Enterprise) |

## Email / SMTP

| Variable | Default | Description |
|---|---:|---|
| `EMAIL_PROVIDER` | `smtp` | `smtp` or `ses` |
| `SMTP_HOST` | `""` | SMTP host |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USERNAME` | `""` | SMTP username |
| `SMTP_PASSWORD` | `""` | SMTP password |
| `SMTP_USE_TLS` | `true` | Use TLS |
| `SMTP_FROM_EMAIL` | `""` | Sender email |
| `SMTP_FROM_NAME` | `Incident Copilot` | Sender name |
| `SES_REGION` | `""` | AWS SES region |
| `SES_FROM_EMAIL` | `""` | Sender email for SES |

## Scheduled reports

| Variable | Default | Description |
|---|---:|---|
| `REPORTS_ENABLED` | `true` | Enable scheduled reports |
| `REPORTS_DEFAULT_TIMEZONE` | `UTC` | Default timezone |
| `REPORTS_AI_INSIGHTS_ENABLED` | `true` | Enable AI insights |

## SSO

### General

| Variable | Default | Description |
|---|---:|---|
| `SSO_SESSION_LIFETIME_MINUTES` | `10` | SSO session state lifetime |
| `SSO_JIT_PROVISIONING_DEFAULT` | `true` | Enable JIT provisioning |

### SAML

| Variable | Default | Description |
|---|---:|---|
| `SAML_SP_PRIVATE_KEY` | `""` | SP private key (PEM) |
| `SAML_SP_CERTIFICATE` | `""` | SP certificate (PEM) |
| `SAML_WANT_ASSERTIONS_SIGNED` | `true` | Require signed assertions |
| `SAML_WANT_MESSAGES_SIGNED` | `true` | Require signed messages |

### OIDC

| Variable | Default | Description |
|---|---:|---|
| `OIDC_DEFAULT_SCOPES` | `openid email profile` | Default OIDC scopes |
| `OIDC_USE_PKCE_DEFAULT` | `true` | Use PKCE by default |

## Rate limiting

| Variable | Default | Description |
|---|---:|---|
| `RATELIMIT_ENABLED` | `true` | Enable API rate limiting |
| `RATELIMIT_EXCLUDE_PATHS` | *(list)* | Paths to exclude from rate limiting |
| `RATELIMIT_IP_CAPACITY` | `100` | Per-IP burst capacity |
| `RATELIMIT_IP_REFILL_RATE` | `10.0` | Per-IP refill rate (tokens/sec) |
| `RATELIMIT_API_KEY_CAPACITY` | `1000` | Per-API-key burst capacity |
| `RATELIMIT_API_KEY_REFILL_RATE` | `50.0` | Per-API-key refill rate |
| `RATELIMIT_TENANT_CAPACITY` | `5000` | Per-tenant burst capacity |
| `RATELIMIT_TENANT_REFILL_RATE` | `100.0` | Per-tenant refill rate |
| `RATELIMIT_USER_CAPACITY` | `200` | Per-user burst capacity |
| `RATELIMIT_USER_REFILL_RATE` | `20.0` | Per-user refill rate |
| `RATELIMIT_GLOBAL_CAPACITY` | `10000` | Global burst capacity |
| `RATELIMIT_GLOBAL_REFILL_RATE` | `500.0` | Global refill rate |

## Alert correlation

| Variable | Default | Description |
|---|---:|---|
| `CORRELATION_ENABLED` | `true` | Enable correlation engine |
| `CORRELATION_DEFAULT_RULES` | `true` | Setup default rules on startup |
| `CORRELATION_TIME_WINDOW_SECONDS` | `300` | Grouping window |
| `CORRELATION_SIMILARITY_THRESHOLD` | `0.7` | Fuzzy match threshold |
| `CORRELATION_GROUP_TTL` | `86400` | Correlation group TTL |
| `CORRELATION_STALE_AFTER_SECONDS` | `3600` | Mark group stale |
| `CORRELATION_MAX_ALERTS_PER_GROUP` | `1000` | Max alerts per group |
| `CORRELATION_SUPPRESS_DUPLICATES` | `true` | Suppress duplicate notifications |
| `CORRELATION_RE_NOTIFY_AFTER_SECONDS` | `1800` | Re-notify interval |

## Audit logging

| Variable | Default | Description |
|---|---:|---|
| `AUDIT_ENABLED` | `true` | Enable audit logging |
| `AUDIT_RETENTION_DAYS` | `90` | Audit log retention |
| `AUDIT_LOG_ALL_REQUESTS` | `false` | Log all API requests |
| `AUDIT_EXCLUDE_PATHS` | *(list)* | Paths to exclude from audit logging |

---

## JSON-typed settings

Some settings are typed as `dict` / `list` in code. Provide them as JSON strings:

```bash
ONCALL_SCHEDULE_MAP='{"payments-api":"SCHED123"}'
GITLAB_PROJECT_MAP='{"payments-api":"mygroup/payments"}'
CLOUDWATCH_LOG_GROUP_MAP='{"payments-api":"/aws/lambda/payments"}'
LOKI_SERVICE_LABELS='{"payments-api":"service=\"payments\""}'
SPLUNK_INDEX_MAP='{"payments-api":"payments_logs"}'
LINEAR_LABEL_IDS='["label_1","label_2"]'
```
