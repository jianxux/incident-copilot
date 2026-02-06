# Troubleshooting Guide

This guide helps you diagnose and fix common issues with Incident Copilot.

## Table of Contents

1. [Quick Diagnostics](#quick-diagnostics)
2. [Webhook Issues](#webhook-issues)
3. [Notification Issues](#notification-issues)
4. [Integration Issues](#integration-issues)
5. [Performance Issues](#performance-issues)
6. [Database Issues](#database-issues)
7. [Debug Mode](#debug-mode)
8. [Getting Help](#getting-help)

---

## Quick Diagnostics

Start here to quickly identify the issue.

### Health Check

```bash
# Check overall health
curl http://localhost:8000/health

# Expected response
{
  "status": "healthy",
  "checks": {
    "api": "ok",
    "database": "ok",
    "redis": "ok"
  }
}
```

### View Logs

```bash
# Docker
docker-compose logs -f incident-copilot

# Local development
uvicorn src.main:app --reload --log-level debug
```

### Common Quick Fixes

| Symptom | Quick Fix |
|---------|-----------|
| No context cards | Check webhook URL is correct and publicly accessible |
| 401 errors | Verify API keys are correct, no extra whitespace |
| Timeout errors | Check network connectivity to external APIs |
| Missing data in cards | Some integrations may be misconfigured |

---

## Webhook Issues

### Webhooks Not Arriving

**Symptoms:**
- No context cards appearing
- No webhook entries in logs
- PagerDuty/Opsgenie shows successful delivery, but nothing happens

**Diagnosis:**

1. **Check if URL is accessible:**
   ```bash
   curl -I https://your-domain.com/webhooks/pagerduty
   # Should return 200 OK or 405 Method Not Allowed (GET not allowed)
   ```

2. **Check SSL certificate:**
   ```bash
   openssl s_client -connect your-domain.com:443 -servername your-domain.com
   ```

3. **Check firewall/ingress rules:**
   - PagerDuty IPs: See [PagerDuty IP Safelist](https://support.pagerduty.com/docs/safelist-ips)
   - Opsgenie IPs: See [Opsgenie IP Addresses](https://support.atlassian.com/opsgenie/docs/opsgenie-ip-addresses/)

**Solutions:**

| Issue | Solution |
|-------|----------|
| URL not accessible | Ensure HTTPS is configured, check DNS |
| SSL errors | Fix certificate chain, ensure cert is valid |
| Firewall blocking | Add alerting provider IPs to allowlist |
| Wrong URL | Verify `/webhooks/pagerduty` or `/webhooks/opsgenie` |

---

### Invalid Signature Errors

**Symptoms:**
- 401 Unauthorized responses in webhook logs
- "Invalid signature" in application logs

**Diagnosis:**

1. **Check for whitespace in secret:**
   ```bash
   # Show hidden characters
   cat -A .env | grep WEBHOOK_SECRET
   # Should be a single line without trailing $ or ^M
   ```

2. **Verify secret matches:**
   - Go to PagerDuty/Opsgenie integration settings
   - Compare signing secret with your `.env` value exactly

**Solutions:**

```bash
# Remove any quotes or whitespace
PAGERDUTY_WEBHOOK_SECRET=abc123def456  # Correct
PAGERDUTY_WEBHOOK_SECRET="abc123def456"  # Wrong - has quotes
PAGERDUTY_WEBHOOK_SECRET= abc123def456   # Wrong - leading space
```

**Tip:** Copy the secret again from the source, paste directly without modification.

---

### Duplicate Webhooks

**Symptoms:**
- Multiple context cards for the same incident
- Duplicate entries in logs

**Causes:**
- Multiple webhook integrations configured
- Retry after temporary failure

**Solutions:**

1. Check for duplicate webhook integrations in PagerDuty/Opsgenie
2. Enable idempotency (built-in deduplication based on incident ID)
3. Configure alert correlation:
   ```bash
   CORRELATION_ENABLED=true
   CORRELATION_SUPPRESS_DUPLICATES=true
   ```

---

## Notification Issues

### Context Cards Not Posting to Slack

**Symptoms:**
- Webhooks received (in logs)
- No messages in Slack channel

**Diagnosis:**

1. **Test Slack token:**
   ```bash
   curl -X POST https://slack.com/api/auth.test \
     -H "Authorization: Bearer $SLACK_BOT_TOKEN"
   ```
   
   Expected response:
   ```json
   {"ok": true, "team": "Your Team", "user": "incident-copilot"}
   ```

2. **Check bot permissions:**
   ```bash
   curl https://slack.com/api/auth.test \
     -H "Authorization: Bearer $SLACK_BOT_TOKEN" | jq .
   ```

3. **Test posting a message:**
   ```bash
   curl -X POST https://slack.com/api/chat.postMessage \
     -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"channel": "#incidents", "text": "Test message"}'
   ```

**Solutions:**

| Error | Solution |
|-------|----------|
| `invalid_auth` | Token is wrong or expired - regenerate |
| `channel_not_found` | Channel name wrong or bot not invited |
| `not_in_channel` | Invite bot: `/invite @Incident Copilot` |
| `missing_scope` | Add `chat:write` and `chat:write.public` scopes |

---

### Teams Webhook Failures

**Symptoms:**
- No messages in Teams channel
- Errors in logs mentioning Teams

**Diagnosis:**

```bash
# Test webhook directly
curl -X POST "$TEAMS_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"text": "Test message from Incident Copilot"}'
```

**Solutions:**

| Error | Solution |
|-------|----------|
| 400 Bad Request | Check JSON payload format |
| 401 Unauthorized | Webhook URL may have expired - recreate |
| 404 Not Found | Webhook was deleted - recreate in Teams |

---

## Integration Issues

### Missing GitHub Context

**Symptoms:**
- No recent deployments shown in context card
- "GitHub: error" in card errors section

**Diagnosis:**

1. **Test GitHub token:**
   ```bash
   curl -H "Authorization: Bearer $GITHUB_TOKEN" \
     https://api.github.com/rate_limit
   ```

2. **Test repository access:**
   ```bash
   curl -H "Authorization: Bearer $GITHUB_TOKEN" \
     https://api.github.com/repos/YOUR_ORG/YOUR_REPO
   ```

3. **Test commits:**
   ```bash
   curl -H "Authorization: Bearer $GITHUB_TOKEN" \
     "https://api.github.com/repos/YOUR_ORG/YOUR_REPO/commits?per_page=5"
   ```

**Solutions:**

| Error | Solution |
|-------|----------|
| 401 Unauthorized | Token invalid or expired |
| 404 Not Found | Repository doesn't exist or no access |
| Wrong repo | Configure `SERVICE_REPO_MAP` |
| Rate limited | Use GitHub App instead of PAT |

**Service mapping:**
```bash
# If service name doesn't match repo name
SERVICE_REPO_MAP='{"payments-api": "my-org/payment-service"}'
```

---

### Missing Log Context

**Symptoms:**
- No log analysis in context card
- No AI summary
- "Datadog: error" or "CloudWatch: error" message

**Diagnosis:**

#### Datadog

```bash
# Validate credentials
curl -X GET "https://api.datadoghq.com/api/v1/validate" \
  -H "DD-API-KEY: $DATADOG_API_KEY" \
  -H "DD-APPLICATION-KEY: $DATADOG_APP_KEY"

# Test log search
curl -X POST "https://api.datadoghq.com/api/v2/logs/events/search" \
  -H "DD-API-KEY: $DATADOG_API_KEY" \
  -H "DD-APPLICATION-KEY: $DATADOG_APP_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "filter": {
      "query": "service:YOUR_SERVICE status:error",
      "from": "now-15m",
      "to": "now"
    }
  }'
```

#### CloudWatch

```bash
# Test AWS credentials
aws sts get-caller-identity

# List log groups
aws logs describe-log-groups

# Test log query
aws logs filter-log-events \
  --log-group-name "/aws/lambda/YOUR_SERVICE" \
  --filter-pattern "ERROR"
```

**Solutions:**

| Issue | Solution |
|-------|----------|
| Wrong Datadog site | Set `DATADOG_SITE=datadoghq.eu` for EU |
| No logs for service | Ensure `service` tag is set correctly in logs |
| CloudWatch no access | Check IAM policy has `logs:FilterLogEvents` |
| Wrong log group | Configure `CLOUDWATCH_LOG_GROUP_MAP` |

---

### AI Summary Not Appearing

**Symptoms:**
- Logs shown but no AI summary
- "AI: error" in card

**Diagnosis:**

```bash
# Check if API key is set
echo $ANTHROPIC_API_KEY | head -c 20

# Test API directly
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-haiku-20240307",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Say hello"}]
  }'
```

**Solutions:**

| Error | Solution |
|-------|----------|
| 401 Unauthorized | API key invalid |
| 429 Rate limited | Reduce request frequency or upgrade plan |
| No logs available | AI summary only runs when logs are fetched |
| Timeout | Increase timeout or use faster model (Haiku) |

---

## Performance Issues

### Slow Context Assembly

**Symptoms:**
- Context cards take >10 seconds to appear
- Timeout warnings in logs

**Diagnosis:**

Check which step is slow:
```bash
# Look for timing info in logs
docker-compose logs incident-copilot | grep -E "(elapsed|timeout|slow)"
```

**Common causes and solutions:**

| Slow Step | Cause | Solution |
|-----------|-------|----------|
| GitHub | Rate limited | Use GitHub App, enable caching |
| Datadog | Large log volume | Narrow time range, filter query |
| AI Summary | Large log payload | Truncate logs, use Haiku model |
| Slack | Network latency | Check connectivity |

**Optimization settings:**
```bash
# Use faster AI model
AI_MODEL=claude-3-haiku-20240307

# Enable caching (if using Redis)
REDIS_URL=redis://localhost:6379/0
```

---

### High Memory Usage

**Symptoms:**
- Container being OOM killed
- Slow response times

**Solutions:**

1. **Increase container memory:**
   ```yaml
   # docker-compose.yml
   services:
     incident-copilot:
       deploy:
         resources:
           limits:
             memory: 1G
   ```

2. **Limit log fetch size:**
   - Configure log providers to fetch fewer entries
   - Use more specific log queries

3. **Enable log rotation:**
   ```yaml
   logging:
     driver: "json-file"
     options:
       max-size: "10m"
       max-file: "3"
   ```

---

## Database Issues

### Connection Errors

**Symptoms:**
- Health check shows database unhealthy
- "Connection refused" errors

**Diagnosis:**

```bash
# Check if database is running
docker-compose ps postgres

# Test connection
psql $DATABASE_URL -c "SELECT 1"
```

**Solutions:**

| Error | Solution |
|-------|----------|
| Connection refused | Database not running or wrong host |
| Authentication failed | Check username/password |
| Database doesn't exist | Create database: `CREATE DATABASE incident_copilot;` |

---

### Redis Connection Issues

**Symptoms:**
- Caching not working
- Rate limiting not working

**Diagnosis:**

```bash
# Test Redis connection
redis-cli -u $REDIS_URL ping
```

**Solutions:**

```bash
# Common fixes
REDIS_URL=redis://localhost:6379/0  # Ensure correct format
REDIS_URL=redis://:password@host:6379/0  # With password
```

---

## Debug Mode

Enable detailed logging for troubleshooting:

### Enable Debug Logging

```bash
DEBUG=true
LOG_LEVEL=debug
```

### View Detailed Logs

```bash
# Docker
docker-compose logs -f incident-copilot 2>&1 | tee debug.log

# Local
LOG_LEVEL=debug uvicorn src.main:app --reload
```

### What to Look For

```
# Successful webhook
INFO: webhook_received source=pagerduty incident_id=P123

# Successful context assembly
INFO: context_assembled incident_id=P123 elapsed_ms=2450

# Errors to investigate
ERROR: github_context_failed error="401 Unauthorized"
ERROR: slack_send_failed error="channel_not_found"
```

---

## Getting Help

If you're still stuck:

### 1. Collect Information

Before asking for help, gather:

- Application logs (last 100 lines around the issue)
- Configuration (sanitized - remove secrets!)
- Steps to reproduce
- Expected vs actual behavior

### 2. Check GitHub Issues

Search existing issues: [GitHub Issues](https://github.com/your-org/incident-copilot/issues)

### 3. Open a New Issue

Include:
- **Environment**: Docker/K8s/Local, OS, versions
- **Configuration**: Sanitized `.env` (no secrets)
- **Logs**: Relevant error messages
- **Steps**: How to reproduce
- **Expected**: What should happen
- **Actual**: What actually happens

### Template

```markdown
## Environment
- Deployment: Docker Compose
- Version: 0.1.0
- OS: Ubuntu 22.04

## Configuration
```env
LOG_PROVIDER=datadog
NOTIFICATION_PROVIDER=slack
# (redacted secrets)
```

## Issue
Context cards are not appearing in Slack.

## Logs
```
ERROR: slack_send_failed channel=#incidents error="channel_not_found"
```

## Steps to Reproduce
1. Trigger incident in PagerDuty
2. Wait for context card
3. Nothing appears

## Expected
Context card should appear in #incidents channel.
```

---

## Quick Reference

### Common Error Messages

| Error Message | Likely Cause | Solution |
|---------------|--------------|----------|
| `Invalid signature` | Wrong webhook secret | Re-copy secret from source |
| `channel_not_found` | Wrong channel name or bot not invited | Check channel, invite bot |
| `invalid_auth` | Bad Slack token | Regenerate token |
| `401 Unauthorized` (GitHub) | Bad token or expired | Regenerate PAT |
| `Connection timeout` | Network issue | Check connectivity |
| `Rate limit exceeded` | Too many API calls | Implement caching, use App |

### Useful Commands

```bash
# Health check
curl http://localhost:8000/health

# View logs
docker-compose logs -f incident-copilot

# Restart after config change
docker-compose restart

# Test Slack
curl https://slack.com/api/auth.test -H "Authorization: Bearer $SLACK_BOT_TOKEN"

# Test GitHub
curl -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/rate_limit

# Test Datadog
curl "https://api.datadoghq.com/api/v1/validate" \
  -H "DD-API-KEY: $DATADOG_API_KEY" \
  -H "DD-APPLICATION-KEY: $DATADOG_APP_KEY"
```

---

*← [Configuration Reference](./configuration.md) | [Best Practices](./best-practices.md) →*
