# Integrations Guide

This guide provides step-by-step instructions for setting up all supported integrations with Incident Copilot.

## Table of Contents

1. [Alert Sources](#alert-sources)
   - [PagerDuty](#pagerduty)
   - [Opsgenie](#opsgenie)
2. [Source Control](#source-control)
   - [GitHub](#github)
   - [GitLab](#gitlab)
3. [Log Providers](#log-providers)
   - [Datadog](#datadog)
   - [AWS CloudWatch](#aws-cloudwatch)
   - [Grafana Loki](#grafana-loki)
   - [Other Providers](#other-log-providers)
4. [Notification Channels](#notification-channels)
   - [Slack](#slack)
   - [Microsoft Teams](#microsoft-teams)
5. [Issue Tracking](#issue-tracking)
   - [Jira](#jira)
   - [Linear](#linear)
   - [ServiceNow](#servicenow)
6. [AI Providers](#ai-providers)

---

## Alert Sources

You need to configure at least one alert source. Incident Copilot receives webhooks when alerts are triggered.

### PagerDuty

PagerDuty is the most common alerting platform. Follow these steps to connect it.

#### Step 1: Create an API Key

1. Log in to PagerDuty
2. Navigate to **Integrations** → **API Access Keys**
3. Click **Create New API Key**
4. Configure:
   - **Description**: Incident Copilot
   - **Access**: Read-only
5. Click **Create Key** and copy the key

![PagerDuty API Key](./images/pagerduty-api-key-placeholder.png)
*Screenshot: Creating a PagerDuty API key*

Add to your `.env`:
```bash
PAGERDUTY_API_KEY=your-api-key-here
```

#### Step 2: Configure Webhook

1. Go to **Services** → Select your service → **Integrations**
2. Click **Add Integration**
3. Search for and select **Generic Webhook (v3)**
4. Configure:
   - **Name**: Incident Copilot
   - **Endpoint URL**: `https://your-domain.com/webhooks/pagerduty`
   - **Events**: Select `incident.triggered`

![PagerDuty Webhook](./images/pagerduty-webhook-placeholder.png)
*Screenshot: Configuring PagerDuty webhook*

5. After saving, copy the **Signing Secret**

Add to your `.env`:
```bash
PAGERDUTY_WEBHOOK_SECRET=your-signing-secret
```

#### Step 3: Verify Connection

Trigger a test incident in PagerDuty. Check:
- PagerDuty: **Integrations** → Webhook → **Recent Deliveries** (should show 200)
- Incident Copilot logs: Should show webhook received
- Slack: Context card should appear

#### On-Call Roster Integration

To display on-call information, optionally map services to schedules:

```bash
ONCALL_PROVIDER=pagerduty
ONCALL_ENABLED=true
ONCALL_SCHEDULE_MAP='{"payments-api": "PABC123", "auth-service": "PDEF456"}'
```

---

### Opsgenie

Opsgenie is a popular alternative to PagerDuty, especially for Atlassian users.

#### Step 1: Create API Integration

1. Log in to Opsgenie
2. Go to **Settings** → **Integrations** → **Add Integration**
3. Select **API** integration type
4. Configure:
   - **Name**: Incident Copilot API
   - **Permissions**: Read only
5. Save and copy the **API Key (GenieKey)**

Add to your `.env`:
```bash
OPSGENIE_API_KEY=your-geniekey-here
OPSGENIE_REGION=us  # or 'eu' for EU region
```

#### Step 2: Create Webhook Integration

1. Go to **Settings** → **Integrations** → **Add Integration**
2. Select **Webhook**
3. Configure:
   - **Name**: Incident Copilot Webhook
   - **Webhook URL**: `https://your-domain.com/webhooks/opsgenie`
   - **Actions**: Enable `Create`
4. Save and note the integration secret

Add to your `.env`:
```bash
OPSGENIE_WEBHOOK_SECRET=your-webhook-secret
```

#### Priority Mapping

| Opsgenie Priority | Incident Copilot Severity |
|-------------------|---------------------------|
| P1 | CRITICAL |
| P2 | HIGH |
| P3 | MEDIUM |
| P4 | LOW |
| P5 | INFO |

---

## Source Control

Connect your source control to show recent deployments and code owners.

### GitHub

GitHub integration provides:
- Recent commits/deployments
- CODEOWNERS file parsing
- Repository file access

#### Option A: Personal Access Token (Simple)

Best for small teams and quick setup.

1. Go to **GitHub Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)**
2. Click **Generate new token (classic)**
3. Configure:
   - **Note**: Incident Copilot
   - **Expiration**: 90 days (or custom)
   - **Scopes**: Check `repo` (or just `public_repo` for public repos only)

![GitHub PAT](./images/github-pat-placeholder.png)
*Screenshot: Creating GitHub personal access token*

4. Copy the token and add to `.env`:
```bash
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
GITHUB_ORG=your-organization
```

#### Option B: GitHub App (Production)

Better for organizations with stricter security requirements.

1. Create a GitHub App in your organization settings
2. Configure permissions:
   - **Repository contents**: Read-only
   - **Metadata**: Read-only
3. Generate and download a private key
4. Install the app on required repositories

Add to your `.env`:
```bash
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH=/path/to/private-key.pem
GITHUB_APP_INSTALLATION_ID=12345678
GITHUB_ORG=your-organization
```

#### Service-to-Repository Mapping

By default, the service name is assumed to match the repository name:
- Service: `payments-api` → Repo: `your-org/payments-api`

For custom mappings:
```bash
SERVICE_REPO_MAP='{"payments-api": "myorg/payment-service", "auth": "myorg/identity-platform"}'
```

---

### GitLab

GitLab integration works similarly to GitHub and supports self-hosted instances.

#### Step 1: Create Access Token

1. Go to **User Settings** → **Access Tokens**
2. Create a new token with scopes:
   - `read_api`
   - `read_repository`
3. Copy the token

Add to your `.env`:
```bash
GITLAB_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx
GITLAB_URL=https://gitlab.com  # Or your self-hosted URL
```

#### Step 2: Configure Project Mapping

GitLab uses project paths instead of simple repo names:

```bash
GITLAB_PROJECT_MAP='{
  "payments-api": "mygroup/payments",
  "auth-service": "mygroup/subgroup/auth-service"
}'
```

---

## Log Providers

Connect a log provider to include error logs in context cards. Choose one:

### Datadog

Datadog is the default log provider.

#### Step 1: Create API Keys

1. Go to **Organization Settings** → **API Keys** → **+ New Key**
2. Name it "Incident Copilot" and copy the key
3. Go to **Application Keys** → **+ New Key**
4. Name it "Incident Copilot" and copy the key

Add to your `.env`:
```bash
LOG_PROVIDER=datadog
DATADOG_API_KEY=your-api-key
DATADOG_APP_KEY=your-application-key
DATADOG_SITE=datadoghq.com  # See available sites below
```

#### Datadog Sites

| Region | Site URL |
|--------|----------|
| US1 (default) | `datadoghq.com` |
| US3 | `us3.datadoghq.com` |
| US5 | `us5.datadoghq.com` |
| EU | `datadoghq.eu` |
| AP1 | `ap1.datadoghq.com` |
| US Gov | `ddog-gov.com` |

#### Log Query

Incident Copilot queries logs using:
```
service:{service-name} status:(error OR warn)
```

Ensure your services have the `service` tag set correctly in Datadog.

---

### AWS CloudWatch

Use CloudWatch Logs instead of Datadog.

#### Step 1: Create IAM Policy

Create an IAM policy with these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:FilterLogEvents",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams",
        "logs:GetLogEvents",
        "logs:StartQuery",
        "logs:GetQueryResults"
      ],
      "Resource": "arn:aws:logs:*:*:log-group:*"
    }
  ]
}
```

#### Step 2: Configure Credentials

**Option A**: IAM User

```bash
LOG_PROVIDER=cloudwatch
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=<your-aws-access-key-id>
AWS_SECRET_ACCESS_KEY=<your-aws-secret-access-key>
```

**Option B**: IAM Role (for EC2/ECS/Lambda)

```bash
LOG_PROVIDER=cloudwatch
AWS_REGION=us-east-1
# No credentials needed - uses instance profile
```

#### Step 3: Configure Log Group Mapping

Default patterns tried:
- `/aws/lambda/{service-name}`
- `/ecs/{service-name}`
- `/aws/ecs/{service-name}`
- `/application/{service-name}`

For custom mappings:
```bash
CLOUDWATCH_LOG_GROUP_MAP='{
  "payments-api": "/aws/lambda/payments,/ecs/payments-prod",
  "auth-service": "/aws/ecs/auth"
}'
```

---

### Grafana Loki

Use Grafana Loki for log aggregation.

#### For Self-Hosted Loki (No Auth)

```bash
LOG_PROVIDER=loki
LOKI_URL=http://loki:3100
LOKI_AUTH_TYPE=none
```

#### For Grafana Cloud

1. Get your User ID and API key from Grafana Cloud
2. Configure:

```bash
LOG_PROVIDER=loki
LOKI_URL=https://logs-prod-us-central1.grafana.net
LOKI_AUTH_TYPE=basic
LOKI_USERNAME=12345
LOKI_PASSWORD=glc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

#### Service Label Mapping

```bash
LOKI_SERVICE_LABELS='{
  "payments-api": "namespace=\"production\",app=\"payments\"",
  "auth-service": "service=\"auth\",env=\"prod\""
}'
```

---

### Other Log Providers

Incident Copilot also supports:

#### Splunk

```bash
LOG_PROVIDER=splunk
SPLUNK_URL=https://splunk.example.com:8089
SPLUNK_TOKEN=your-bearer-token
SPLUNK_INDEX_MAP='{"payments-api": "payments_logs"}'
```

#### New Relic

```bash
LOG_PROVIDER=newrelic
NEWRELIC_API_KEY=NRAK-xxxxxxxxxxxxxxxxxxxx
NEWRELIC_ACCOUNT_ID=1234567
NEWRELIC_REGION=us  # or 'eu'
NEWRELIC_APP_MAP='{"payments-api": "123456789"}'
```

#### Elasticsearch

```bash
LOG_PROVIDER=elastic
ELASTIC_URL=https://my-deployment.es.aws.elastic.co
ELASTIC_API_KEY=your-api-key
ELASTIC_INDEX_PATTERN=logs-*
ELASTIC_SERVICE_FIELD=service.name
ELASTIC_SERVICE_INDEX_MAP='{"payments-api": "logs-payments-*"}'
```

---

## Notification Channels

Configure where context cards are delivered. You can use one or both.

### Slack

Slack is the most common notification channel.

#### Step 1: Create Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App** → **From scratch**
3. Name it "Incident Copilot" and select your workspace

![Create Slack App](./images/slack-create-app-placeholder.png)
*Screenshot: Creating a new Slack app*

#### Step 2: Configure Bot Permissions

1. Go to **OAuth & Permissions**
2. Add Bot Token Scopes:
   - `chat:write` - Send messages
   - `chat:write.public` - Send to any public channel

![Slack Scopes](./images/slack-scopes-placeholder.png)
*Screenshot: Adding Slack bot scopes*

#### Step 3: Install to Workspace

1. Click **Install to Workspace**
2. Review and approve permissions
3. Copy the **Bot User OAuth Token** (starts with `xoxb-`)

Add to your `.env`:
```bash
SLACK_BOT_TOKEN=xoxb-<your-slack-bot-token>
SLACK_DEFAULT_CHANNEL=#incidents
NOTIFICATION_PROVIDER=slack
```

#### Step 4: Invite Bot (Optional)

For private channels, invite the bot:
```
/invite @Incident Copilot
```

---

### Microsoft Teams

Use Teams Incoming Webhooks for notifications.

#### Step 1: Create Incoming Webhook

1. Go to the channel where you want notifications
2. Click **⋯** → **Connectors** → **Incoming Webhook**
3. Configure:
   - **Name**: Incident Copilot
   - **Icon**: Upload an icon (optional)
4. Copy the webhook URL

![Teams Webhook](./images/teams-webhook-placeholder.png)
*Screenshot: Creating Teams incoming webhook*

Add to your `.env`:
```bash
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/xxx
NOTIFICATION_PROVIDER=teams
```

#### Using Both Slack and Teams

```bash
NOTIFICATION_PROVIDER=both
SLACK_BOT_TOKEN=xoxb-xxx
SLACK_DEFAULT_CHANNEL=#incidents
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/xxx
```

---

## Issue Tracking

Optionally create tickets automatically when incidents are triggered.

### Jira

#### Step 1: Create API Token

1. Go to [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click **Create API token**
3. Name it "Incident Copilot"
4. Copy the token

Add to your `.env`:
```bash
JIRA_BASE_URL=https://yourcompany.atlassian.net
JIRA_EMAIL=your-email@company.com
JIRA_API_TOKEN=your-api-token
JIRA_DEFAULT_PROJECT=INCIDENT
```

---

### Linear

#### Step 1: Create API Key

1. Go to **Linear Settings** → **API**
2. Click **Create new API key**
3. Name it "Incident Copilot"
4. Copy the key (starts with `lin_api_`)

Add to your `.env`:
```bash
LINEAR_API_KEY=lin_api_xxxxxxxxxxxxxxxxxxxx
LINEAR_TEAM_ID=your-team-uuid
LINEAR_LABEL_IDS=["incident-label-id"]  # Optional
```

---

### ServiceNow

```bash
SERVICENOW_INSTANCE=https://yourcompany.service-now.com
SERVICENOW_USERNAME=api-user
SERVICENOW_PASSWORD=your-password
SERVICENOW_ASSIGNMENT_GROUP=Incident Team
```

---

## AI Providers

Configure AI for log summarization.

### Anthropic (Claude)

1. Get an API key from [console.anthropic.com](https://console.anthropic.com)
2. Add to your `.env`:

```bash
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxx
AI_MODEL=claude-3-haiku-20240307  # Recommended for speed
```

#### Model Options

| Model | Speed | Use Case |
|-------|-------|----------|
| `claude-3-haiku-20240307` | Fastest | Default, production |
| `claude-3-sonnet-20240229` | Medium | More detailed analysis |
| `claude-3-opus-20240229` | Slower | Complex incidents |

---

## Verification Checklist

After setting up integrations, verify each one:

| Integration | How to Verify |
|-------------|---------------|
| PagerDuty | Trigger test incident, check webhook deliveries |
| Slack | Run `curl https://slack.com/api/auth.test -H "Authorization: Bearer $SLACK_BOT_TOKEN"` |
| GitHub | Run `curl -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/rate_limit` |
| Datadog | Run `curl -X GET "https://api.datadoghq.com/api/v1/validate" -H "DD-API-KEY: $DATADOG_API_KEY"` |
| Claude | Check first context card includes AI summary |

---

*← [Core Concepts](./core-concepts.md) | [Configuration Reference](./configuration.md) →*
