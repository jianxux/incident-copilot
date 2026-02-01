# Integration Guide

This guide walks you through setting up Incident Copilot with all supported integrations.

## Table of Contents

1. [PagerDuty Setup](#pagerduty-setup)
2. [Opsgenie Setup](#opsgenie-setup)
3. [GitHub Setup](#github-setup)
4. [Datadog Setup](#datadog-setup)
5. [CloudWatch Setup](#cloudwatch-setup)
6. [Slack Setup](#slack-setup)
7. [Troubleshooting](#troubleshooting)

---

## PagerDuty Setup

### Step 1: Create a PagerDuty API Key

1. Log in to your PagerDuty account
2. Navigate to **Integrations** → **API Access Keys**

   <!-- Screenshot: pagerduty-api-keys-menu.png -->
   ```
   ┌─────────────────────────────────────────┐
   │  PagerDuty                              │
   │  ├── Incidents                          │
   │  ├── Services                           │
   │  ├── Integrations  ◄──                  │
   │  │   └── API Access Keys  ◄──           │
   │  └── ...                                │
   └─────────────────────────────────────────┘
   ```

3. Click **Create New API Key**
4. Enter a description: "Incident Copilot"
5. Select **Read-only** access (we don't need write access)
6. Click **Create Key**
7. **Copy the API key** (you won't be able to see it again!)

   <!-- Screenshot: pagerduty-api-key-created.png -->

8. Add to your `.env`:
   ```bash
   PAGERDUTY_API_KEY=your-api-key-here
   ```

### Step 2: Configure Webhook Integration

1. Go to **Services** → Select the service you want to monitor
2. Click **Integrations** tab
3. Click **Add Integration**

   <!-- Screenshot: pagerduty-add-integration.png -->

4. Search for and select **Generic Webhook (v3)**
5. Configure the webhook:
   - **Name**: Incident Copilot
   - **Endpoint URL**: `https://your-domain.com/webhooks/pagerduty`

   <!-- Screenshot: pagerduty-webhook-config.png -->
   ```
   ┌─────────────────────────────────────────┐
   │  Add Webhook Integration                │
   ├─────────────────────────────────────────┤
   │  Name: Incident Copilot                 │
   │  URL:  https://copilot.example.com      │
   │        /webhooks/pagerduty              │
   │                                         │
   │  Events:                                │
   │  ☑ incident.triggered                   │
   │  ☐ incident.acknowledged                │
   │  ☐ incident.resolved                    │
   │                                         │
   │  [Save Integration]                     │
   └─────────────────────────────────────────┘
   ```

6. After saving, **copy the Signing Secret**

   <!-- Screenshot: pagerduty-webhook-secret.png -->

7. Add to your `.env`:
   ```bash
   PAGERDUTY_WEBHOOK_SECRET=your-signing-secret
   ```

### Step 3: Test the Integration

1. In PagerDuty, go to your service
2. Click **New Incident** (or trigger from monitoring)
3. Check your Slack channel for the context card

### Recommended Event Subscriptions

| Event | Required | Notes |
|-------|----------|-------|
| `incident.triggered` | ✅ Yes | Core functionality |
| `incident.acknowledged` | ❌ Optional | Future: update card |
| `incident.resolved` | ❌ Optional | Future: resolution tracking |

---

## Opsgenie Setup

### Step 1: Create an API Integration

1. Log in to Opsgenie
2. Go to **Settings** → **Integrations**
3. Click **Add Integration**
4. Search for **API** and select it

   <!-- Screenshot: opsgenie-add-api-integration.png -->

5. Configure:
   - **Name**: Incident Copilot API
   - **Team** (optional): Assign to a team

6. Enable required permissions:
   - ✅ Read
   - ❌ Create/Update/Delete (not needed)

7. Click **Save Integration**
8. **Copy the API Key (GenieKey)**

   <!-- Screenshot: opsgenie-api-key.png -->

9. Add to your `.env`:
   ```bash
   OPSGENIE_API_KEY=your-geniekey-here
   OPSGENIE_REGION=us  # or 'eu' for EU region
   ```

### Step 2: Create Webhook Integration

1. Go to **Settings** → **Integrations**
2. Click **Add Integration**
3. Search for **Webhook** and select it

   <!-- Screenshot: opsgenie-add-webhook.png -->

4. Configure the webhook:
   - **Name**: Incident Copilot Webhook
   - **Webhook URL**: `https://your-domain.com/webhooks/opsgenie`
   - **Post to URL on these alert actions**:
     - ✅ Create
     - ❌ Others (optional)

   <!-- Screenshot: opsgenie-webhook-config.png -->
   ```
   ┌─────────────────────────────────────────┐
   │  Webhook Integration                    │
   ├─────────────────────────────────────────┤
   │  Name: Incident Copilot Webhook         │
   │                                         │
   │  Webhook URL:                           │
   │  https://copilot.example.com/webhooks/  │
   │  opsgenie                               │
   │                                         │
   │  Alert Actions:                         │
   │  ☑ Create                               │
   │  ☐ Acknowledge                          │
   │  ☐ Close                                │
   │  ☐ Add Note                             │
   └─────────────────────────────────────────┘
   ```

5. Under **Advanced Settings**, enable **Add Headers**:
   - Add custom header for signature (if available)

6. Click **Save Integration**
7. Note the integration ID for the webhook secret

8. Add to your `.env`:
   ```bash
   OPSGENIE_WEBHOOK_SECRET=your-webhook-secret
   ```

### Step 3: Test the Integration

1. In Opsgenie, go to **Alerts** → **Create Alert**
2. Create a test alert with a service tag
3. Check your Slack channel for the context card

### Priority Mapping

| Opsgenie | Incident Copilot |
|----------|------------------|
| P1 | Critical |
| P2 | High |
| P3 | Medium |
| P4 | Low |
| P5 | Info |

---

## GitHub Setup

You have two options: **GitHub App** (recommended) or **Personal Access Token**.

### Option A: Personal Access Token (Simpler)

Best for: Quick setup, personal projects, small teams

1. Go to GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)**

   <!-- Screenshot: github-pat-menu.png -->

2. Click **Generate new token (classic)**

3. Configure:
   - **Note**: Incident Copilot
   - **Expiration**: 90 days (or custom)
   - **Scopes**:
     - ✅ `repo` (Full control of private repositories)
     - Or just `public_repo` if only using public repos

   <!-- Screenshot: github-pat-scopes.png -->
   ```
   ┌─────────────────────────────────────────┐
   │  New personal access token (classic)    │
   ├─────────────────────────────────────────┤
   │  Note: Incident Copilot                 │
   │  Expiration: 90 days                    │
   │                                         │
   │  Select scopes:                         │
   │  ☑ repo                                 │
   │    ☑ repo:status                        │
   │    ☑ repo_deployment                    │
   │    ☑ public_repo                        │
   │    ☑ repo:invite                        │
   │    ☑ security_events                    │
   └─────────────────────────────────────────┘
   ```

4. Click **Generate token**
5. **Copy the token** (starts with `ghp_`)

6. Add to your `.env`:
   ```bash
   GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
   GITHUB_ORG=your-organization-name
   ```

### Option B: GitHub App (Recommended for Production)

Best for: Organizations, production deployments, granular permissions

**Step 1: Create the GitHub App**

1. Go to your organization → **Settings** → **Developer settings** → **GitHub Apps**
2. Click **New GitHub App**

   <!-- Screenshot: github-new-app.png -->

3. Configure:
   - **Name**: Incident Copilot
   - **Homepage URL**: `https://your-domain.com`
   - **Webhook**: Uncheck "Active" (we don't need GitHub webhooks)

4. Set Permissions:
   - **Repository permissions**:
     - Contents: Read-only
     - Metadata: Read-only
   - **Organization permissions**:
     - Members: Read-only (optional, for CODEOWNERS)

5. Click **Create GitHub App**

**Step 2: Generate Private Key**

1. On the app settings page, scroll to **Private keys**
2. Click **Generate a private key**
3. Save the `.pem` file securely

**Step 3: Install the App**

1. Go to your app → **Install App**
2. Select your organization
3. Choose repositories:
   - **All repositories** or
   - **Only select repositories** (select services' repos)
4. Click **Install**
5. Note the **Installation ID** from the URL

**Step 4: Configure Environment**

```bash
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH=/path/to/private-key.pem
# Or inline (base64 encoded):
GITHUB_APP_PRIVATE_KEY=LS0tLS1CRUdJTi...
GITHUB_APP_INSTALLATION_ID=12345678
GITHUB_ORG=your-organization-name
```

### Service to Repository Mapping

By default, Incident Copilot assumes the repository name matches the service name:
- Service `payments-api` → Repo `your-org/payments-api`

For custom mappings, use the `SERVICE_REPO_MAP` environment variable:

```bash
# JSON format
SERVICE_REPO_MAP='{"payments-api": "myorg/payment-service", "auth": "myorg/identity-service"}'
```

---

## Datadog Setup

### Step 1: Create API Keys

1. Log in to Datadog
2. Go to **Organization Settings** → **API Keys**

   <!-- Screenshot: datadog-api-keys-menu.png -->

3. Click **+ New Key**
4. Name it: "Incident Copilot"
5. **Copy the API Key**

   <!-- Screenshot: datadog-api-key.png -->

### Step 2: Create Application Key

1. Go to **Organization Settings** → **Application Keys**
2. Click **+ New Key**
3. Name it: "Incident Copilot"
4. **Copy the Application Key**

   <!-- Screenshot: datadog-app-key.png -->

### Step 3: Configure Environment

```bash
DATADOG_API_KEY=your-api-key
DATADOG_APP_KEY=your-application-key
DATADOG_SITE=datadoghq.com  # or datadoghq.eu, us3.datadoghq.com, etc.
```

### Available Datadog Sites

| Site | URL | Region |
|------|-----|--------|
| US1 | datadoghq.com | US (default) |
| US3 | us3.datadoghq.com | US |
| US5 | us5.datadoghq.com | US |
| EU1 | datadoghq.eu | EU |
| AP1 | ap1.datadoghq.com | Asia-Pacific |
| GOV | ddog-gov.com | US Government |

### Required Permissions

The API key needs access to:
- **Logs**: Read logs data
- **Metrics**: Read metrics data
- **APM**: Read APM data (if using APM)

### Log Query Configuration

Incident Copilot queries logs using:
```
service:{service-name} status:(error OR warn)
```

Ensure your services are properly tagged with the `service` tag in Datadog.

---

## CloudWatch Setup

Use CloudWatch Logs instead of Datadog by setting `LOG_PROVIDER=cloudwatch`.

### Step 1: Create IAM User or Role

**Option A: IAM User (simpler)**

1. Go to AWS IAM → **Users** → **Add users**
2. **User name**: `incident-copilot`
3. **Access type**: ✅ Access key - Programmatic access
4. Click **Next: Permissions**
5. **Attach policies directly** → **Create policy**

**Option B: IAM Role (for EC2/ECS)**

1. Go to AWS IAM → **Roles** → **Create role**
2. **Trusted entity**: AWS service (EC2, ECS, Lambda)
3. Attach the policy below

### Step 2: Create IAM Policy

Create a custom policy with these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "IncidentCopilotCloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:FilterLogEvents",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams",
        "logs:GetLogEvents",
        "logs:StartQuery",
        "logs:GetQueryResults",
        "logs:StopQuery"
      ],
      "Resource": [
        "arn:aws:logs:*:YOUR_ACCOUNT_ID:log-group:*",
        "arn:aws:logs:*:YOUR_ACCOUNT_ID:log-group:*:log-stream:*"
      ]
    }
  ]
}
```

**Restricted version** (specific log groups only):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "IncidentCopilotCloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:FilterLogEvents",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams",
        "logs:GetLogEvents",
        "logs:StartQuery",
        "logs:GetQueryResults",
        "logs:StopQuery"
      ],
      "Resource": [
        "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/payments-*",
        "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/payments-*:log-stream:*",
        "arn:aws:logs:us-east-1:123456789012:log-group:/ecs/payments-*",
        "arn:aws:logs:us-east-1:123456789012:log-group:/ecs/payments-*:log-stream:*"
      ]
    }
  ]
}
```

### Step 3: Configure Environment

```bash
LOG_PROVIDER=cloudwatch
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

**Or use IAM roles** (recommended for EC2/ECS):
```bash
LOG_PROVIDER=cloudwatch
AWS_REGION=us-east-1
# No access keys needed - uses instance profile
```

### Step 4: Configure Log Group Mapping

By default, Incident Copilot tries these log group patterns:
- `/aws/lambda/{service-name}`
- `/ecs/{service-name}`
- `/aws/ecs/{service-name}`
- `/application/{service-name}`

For custom mappings:

```bash
CLOUDWATCH_LOG_GROUP_MAP='{
  "payments-api": "/aws/lambda/payments,/ecs/payments-production",
  "auth-service": "/aws/ecs/auth-prod"
}'
```

---

## Slack Setup

### Step 1: Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App**
3. Choose **From scratch**
4. Configure:
   - **App Name**: Incident Copilot
   - **Workspace**: Select your workspace
5. Click **Create App**

   <!-- Screenshot: slack-create-app.png -->
   ```
   ┌─────────────────────────────────────────┐
   │  Create a Slack App                     │
   ├─────────────────────────────────────────┤
   │  ○ From scratch                         │
   │  ○ From an app manifest                 │
   │                                         │
   │  App Name: Incident Copilot             │
   │  Workspace: My Company                  │
   │                                         │
   │  [Create App]                           │
   └─────────────────────────────────────────┘
   ```

### Step 2: Configure Bot Permissions

1. In the app settings, go to **OAuth & Permissions**
2. Scroll to **Scopes** → **Bot Token Scopes**
3. Add these scopes:

   | Scope | Purpose |
   |-------|---------|
   | `chat:write` | Send messages to channels bot is in |
   | `chat:write.public` | Send messages to any public channel |

   <!-- Screenshot: slack-bot-scopes.png -->
   ```
   ┌─────────────────────────────────────────┐
   │  Bot Token Scopes                       │
   ├─────────────────────────────────────────┤
   │  ✓ chat:write                           │
   │    Send messages as @incident-copilot   │
   │                                         │
   │  ✓ chat:write.public                    │
   │    Send messages to public channels     │
   │    without joining                      │
   │                                         │
   │  [Add an OAuth Scope]                   │
   └─────────────────────────────────────────┘
   ```

### Step 3: Install to Workspace

1. Scroll up to **OAuth Tokens for Your Workspace**
2. Click **Install to Workspace**
3. Review permissions and click **Allow**
4. **Copy the Bot User OAuth Token** (starts with `xoxb-`)

   <!-- Screenshot: slack-oauth-token.png -->

### Step 4: Configure Environment

```bash
SLACK_BOT_TOKEN=xoxb-1234567890-1234567890123-abcdefghijklmnop
SLACK_DEFAULT_CHANNEL=#incidents
```

### Step 5: Invite Bot to Channels (Optional)

If not using `chat:write.public`, invite the bot:

1. Go to your incidents channel
2. Type `/invite @Incident Copilot`

Or use channel settings → **Integrations** → **Add an App**

### Step 6: Customize App Appearance (Optional)

1. Go to **Basic Information** → **Display Information**
2. Set:
   - **App name**: Incident Copilot
   - **App icon**: Upload a 512x512 icon
   - **Background color**: `#FF5733` (orange-red)
   - **Short description**: Context-aware incident copilot

---

## Troubleshooting

### Common Issues

#### Webhooks Not Arriving

**Symptoms**: No context cards appearing, no logs of webhook receipt

**Checks**:
1. Verify URL is publicly accessible:
   ```bash
   curl -I https://your-domain.com/webhooks/health
   # Should return 200 OK
   ```

2. Check SSL certificate is valid:
   ```bash
   openssl s_client -connect your-domain.com:443 -servername your-domain.com
   ```

3. Verify firewall allows inbound HTTPS (port 443)

4. Check PagerDuty/Opsgenie webhook logs for delivery attempts:
   - PagerDuty: **Integrations** → Webhook → **Recent Deliveries**
   - Opsgenie: **Settings** → Integration → **Logs**

**Solutions**:
- Ensure HTTPS is properly configured
- Check for IP allowlisting requirements
- Verify webhook URL includes `/webhooks/pagerduty` or `/webhooks/opsgenie`

---

#### Invalid Signature Errors

**Symptoms**: 401 errors in webhook responses, "Invalid signature" in logs

**Checks**:
1. Verify webhook secret matches exactly:
   ```bash
   echo $PAGERDUTY_WEBHOOK_SECRET
   ```

2. Check for extra whitespace or newlines:
   ```bash
   # Should be one line, no trailing newline
   cat -A .env | grep WEBHOOK_SECRET
   ```

**Solutions**:
- Re-copy the webhook secret from PagerDuty/Opsgenie
- Ensure no extra spaces or quotes around the value
- Check if secret contains special characters that need escaping

---

#### Context Cards Not Posting to Slack

**Symptoms**: Webhooks received, but no Slack messages

**Checks**:
1. Verify Slack token:
   ```bash
   curl -X POST https://slack.com/api/auth.test \
     -H "Authorization: Bearer $SLACK_BOT_TOKEN"
   ```

2. Check bot permissions:
   ```bash
   curl https://slack.com/api/auth.test \
     -H "Authorization: Bearer $SLACK_BOT_TOKEN" | jq .
   ```

3. Look for errors in application logs:
   ```bash
   docker-compose logs -f | grep slack
   ```

**Solutions**:
- Regenerate Slack bot token if expired
- Ensure bot has `chat:write` and `chat:write.public` scopes
- Invite bot to private channels: `/invite @Incident Copilot`
- Check channel name matches `SLACK_DEFAULT_CHANNEL`

---

#### Slow Context Assembly

**Symptoms**: Cards take >10 seconds or timeout

**Checks**:
1. Test external API connectivity:
   ```bash
   # GitHub
   curl -I https://api.github.com
   
   # Datadog
   curl -I https://api.datadoghq.com
   
   # Slack
   curl -I https://slack.com/api/api.test
   ```

2. Check application logs for timeouts:
   ```bash
   docker-compose logs | grep -i timeout
   ```

**Solutions**:
- Check if any external APIs are experiencing issues
- Verify network connectivity from your server
- Consider increasing timeout values (not recommended long-term)
- Check for rate limiting (see below)

---

#### Rate Limiting

**Symptoms**: 429 errors, incomplete data

**API Rate Limits**:

| Service | Rate Limit | Notes |
|---------|------------|-------|
| GitHub | 5,000 req/hour | Per token |
| Datadog | Varies | Check your plan |
| Slack | Tier-based | ~1 msg/sec for chat.postMessage |
| PagerDuty | 900 req/min | Per account |

**Solutions**:
- Use caching for repeated queries
- Implement exponential backoff
- Upgrade API plan if needed
- Use GitHub App for higher limits

---

#### Missing GitHub Context

**Symptoms**: No deployments shown in context card

**Checks**:
1. Verify service-to-repo mapping:
   ```bash
   # Service name should match repo or be in SERVICE_REPO_MAP
   echo $SERVICE_REPO_MAP
   ```

2. Check GitHub token permissions:
   ```bash
   curl -H "Authorization: Bearer $GITHUB_TOKEN" \
     https://api.github.com/repos/your-org/your-repo
   ```

3. Verify recent commits exist:
   ```bash
   curl -H "Authorization: Bearer $GITHUB_TOKEN" \
     "https://api.github.com/repos/your-org/your-repo/commits?per_page=5"
   ```

**Solutions**:
- Add explicit mapping in `SERVICE_REPO_MAP`
- Ensure token has `repo` scope
- Check repository visibility (private repos need `repo` scope)

---

#### Missing Datadog Logs

**Symptoms**: No logs or AI summary in context card

**Checks**:
1. Verify Datadog credentials:
   ```bash
   curl -X GET "https://api.datadoghq.com/api/v1/validate" \
     -H "DD-API-KEY: $DATADOG_API_KEY" \
     -H "DD-APPLICATION-KEY: $DATADOG_APP_KEY"
   ```

2. Test log query:
   ```bash
   curl -X POST "https://api.datadoghq.com/api/v2/logs/events/search" \
     -H "DD-API-KEY: $DATADOG_API_KEY" \
     -H "DD-APPLICATION-KEY: $DATADOG_APP_KEY" \
     -H "Content-Type: application/json" \
     -d '{"filter": {"query": "service:your-service status:error", "from": "now-15m", "to": "now"}}'
   ```

**Solutions**:
- Verify service name matches Datadog `service` tag exactly
- Check Datadog site setting (`datadoghq.com` vs `datadoghq.eu`)
- Ensure API and App keys are for the same organization

---

### Debug Mode

Enable debug logging for more detailed output:

```bash
DEBUG=true
LOG_LEVEL=debug
```

View logs:
```bash
docker-compose logs -f
# Or
uvicorn src.main:app --reload --log-level debug
```

### Getting Help

If you're still stuck:

1. Check the [GitHub Issues](https://github.com/jianxux/incident-copilot/issues)
2. Enable debug logging and collect logs
3. Open a new issue with:
   - Environment (Docker/K8s/VM)
   - Integration type (PagerDuty/Opsgenie)
   - Error messages and logs
   - Steps to reproduce

---

*Integration Guide version: 1.0*
*Last updated: January 2026*
