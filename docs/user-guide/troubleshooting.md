# 🔧 Troubleshooting Guide

This guide covers common issues and their solutions when using Incident Copilot.

---

## 🚨 Quick Diagnostics

### Health Check Endpoints

Check system health before investigating specific issues:

```bash
# Basic health check
curl http://localhost:8000/health

# Full health check (checks all integrations)
curl 'http://localhost:8000/health?full=true'

# Webhook health
curl http://localhost:8000/webhooks/health

# Kubernetes probes
curl http://localhost:8000/health/live    # Liveness
curl http://localhost:8000/health/ready   # Readiness
```

### Expected Health Response

```json
{
  "status": "healthy",
  "timestamp": "2025-01-15T10:00:00Z",
  "version": "0.1.0",
  "uptime_seconds": 3600.5,
  "components": [
    {"name": "redis", "status": "healthy", "latency_ms": 1.2},
    {"name": "database", "status": "healthy", "latency_ms": 5.4},
    {"name": "pagerduty", "status": "healthy", "latency_ms": 150.3},
    {"name": "github", "status": "healthy", "latency_ms": 89.2},
    {"name": "datadog", "status": "healthy", "latency_ms": 120.5},
    {"name": "slack", "status": "healthy", "latency_ms": 95.1},
    {"name": "anthropic", "status": "healthy", "latency_ms": 200.8}
  ]
}
```

---

## 🔔 Webhook Issues

### Webhooks Not Arriving

**Symptoms:**
- No context cards generated
- No webhook logs in application

**Checklist:**

| Check | Command/Action |
|-------|----------------|
| Server accessible | `curl -I https://your-domain.com/webhooks/health` |
| SSL certificate valid | `openssl s_client -connect your-domain.com:443` |
| Webhook URL correct | Verify in PagerDuty/Opsgenie |
| Firewall allows traffic | Check cloud provider security groups |
| Webhook enabled | Check integration status in alert source |

**Solutions:**

1. **For local testing:** Use ngrok to expose local server
   ```bash
   ngrok http 8000
   # Use the HTTPS URL: https://abc123.ngrok.io
   ```

2. **Check webhook delivery logs:**
   - PagerDuty: Integrations → Webhook → Recent Deliveries
   - Opsgenie: Settings → Integration → Logs

3. **Verify endpoint returns 200:**
   ```bash
   curl -X POST https://your-domain.com/webhooks/pagerduty \
     -H "Content-Type: application/json" \
     -d '{"test": true}'
   ```

### Invalid Signature Errors

**Symptoms:**
- HTTP 401 responses
- "Invalid signature" in logs

**Checks:**
```bash
# Verify secret is set (don't expose the actual value)
echo ${PAGERDUTY_WEBHOOK_SECRET:+Set}

# Check for whitespace
cat -A .env | grep WEBHOOK_SECRET
# Should show no trailing spaces or ^M characters
```

**Solutions:**
1. Re-copy the signing secret from PagerDuty/Opsgenie
2. Ensure no extra whitespace or quotes
3. Restart the application after changes

---

## 💬 Notification Issues

### Slack Messages Not Posting

**Symptoms:**
- Webhooks received but no Slack messages
- "channel_not_found" or "not_in_channel" errors

**Checks:**
```bash
# Verify bot token
curl -X POST https://slack.com/api/auth.test \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN"

# Test posting
curl -X POST https://slack.com/api/chat.postMessage \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel": "#incidents", "text": "Test"}'
```

**Solutions:**

| Error | Solution |
|-------|----------|
| `invalid_auth` | Regenerate bot token |
| `channel_not_found` | Check channel name/ID |
| `not_in_channel` | Invite bot: `/invite @Incident Copilot` |
| `missing_scope` | Add required scopes in Slack app settings |

### Teams Messages Not Posting

**Symptoms:**
- No messages in Teams channel
- HTTP errors when posting

**Checks:**
```bash
# Test webhook URL
curl -X POST "$TEAMS_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"@type":"MessageCard","text":"Test"}'
```

**Solutions:**
1. Verify webhook URL is complete (very long)
2. Check webhook hasn't been deleted in Teams
3. Recreate the webhook connector if needed

---

## 🐙 GitHub/GitLab Issues

### No Deployments Shown

**Symptoms:**
- Context cards missing deployment information
- "No recent deployments" message

**Checks:**
```bash
# Test GitHub API
curl -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/repos/$GITHUB_ORG/service-name/commits?per_page=5"

# Test GitLab API
curl -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://gitlab.com/api/v4/projects/group%2Fproject/repository/commits?per_page=5"
```

**Solutions:**

1. **Check service name mapping:**
   ```bash
   SERVICE_REPO_MAP='{"alert-service-name": "org/actual-repo"}'
   ```

2. **Verify token permissions:**
   - GitHub: `repo` scope for private repos
   - GitLab: `read_api`, `read_repository` scopes

3. **Check project path (GitLab):**
   - Must be URL-encoded: `group/subgroup/project` → `group%2Fsubgroup%2Fproject`

### Rate Limit Exceeded

**Symptoms:**
- HTTP 403 with rate limit message
- Incomplete data in context cards

**Solutions:**
1. Use GitHub App instead of PAT (15,000 vs 5,000 req/hour)
2. Enable caching (built-in)
3. Check rate limit status:
   ```bash
   curl -H "Authorization: Bearer $GITHUB_TOKEN" \
     https://api.github.com/rate_limit
   ```

---

## 📊 Log Provider Issues

### No Logs Found

**Symptoms:**
- Context cards show no error logs
- AI summary unavailable

**Checks by Provider:**

**Datadog:**
```bash
curl -X POST "https://api.datadoghq.com/api/v2/logs/events/search" \
  -H "DD-API-KEY: $DATADOG_API_KEY" \
  -H "DD-APPLICATION-KEY: $DATADOG_APP_KEY" \
  -d '{"filter":{"query":"service:your-service status:error"}}'
```

**CloudWatch:**
```bash
aws logs filter-log-events \
  --log-group-name "/aws/lambda/your-service" \
  --filter-pattern "ERROR" \
  --limit 10
```

**Solutions:**
1. Verify service name matches log tags
2. Check log provider credentials
3. Ensure logs exist in the time range
4. Configure explicit service mapping

### Wrong Log Provider

**Symptoms:**
- Trying to fetch from Datadog when using CloudWatch

**Solution:**
```bash
# Set correct provider
LOG_PROVIDER=cloudwatch  # or datadog, loki, splunk
```

---

## 🤖 AI Issues

### AI Summary Unavailable

**Symptoms:**
- "AI summary unavailable" in context cards
- No analysis section

**Checks:**
```bash
# Verify API key format (don't expose full key)
echo ${ANTHROPIC_API_KEY:0:10}...

# Test API access
curl https://api.anthropic.com/v1/models \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01"
```

**Solutions:**
1. Configure `ANTHROPIC_API_KEY`
2. Verify key hasn't expired
3. Check account has API access
4. Ensure logs are being fetched (AI needs input)

### Slow AI Responses

**Symptoms:**
- Context cards taking >10 seconds
- AI section appears last

**Solutions:**
1. Use faster model: `AI_MODEL=claude-3-haiku-20240307`
2. Reduce log volume sent to AI
3. Check Anthropic status page

---

## 🗄️ Database Issues

### Connection Errors

**Symptoms:**
- Health check shows database unhealthy
- "Connection refused" errors

**Checks:**
```bash
# PostgreSQL
psql $DATABASE_URL -c "SELECT 1"

# Redis
redis-cli -u $REDIS_URL ping
```

**Solutions:**
1. Verify database is running
2. Check connection string format
3. Verify network connectivity
4. Check credentials

### Migration Errors

**Symptoms:**
- Application fails to start
- "Relation does not exist" errors

**Solutions:**
```bash
# Run migrations
alembic upgrade head

# Check current version
alembic current
```

---

## 🔐 Authentication Issues

### Invalid Token

**Symptoms:**
- HTTP 401 on API calls
- "Invalid token" errors

**Checks:**
- Token format correct (Bearer token)
- Token hasn't expired
- Token has required scopes

**Solutions:**
1. Refresh token or re-authenticate
2. Check token expiration
3. Verify scopes match required permissions

### SSO Not Working

**Symptoms:**
- Redirect loop
- "Invalid SAML response"

**Solutions:**
1. Verify IdP configuration matches SP metadata
2. Check certificate hasn't expired
3. Ensure clock sync between systems
4. Verify ACS URL is correct

---

## 📈 Performance Issues

### Slow Context Cards (>10 seconds)

**Symptoms:**
- Cards taking too long to deliver
- Timeout errors

**Diagnostic Steps:**
1. Check health endpoint for slow components
2. Review timing in card footer
3. Check external API response times

**Solutions:**

| Slow Component | Solution |
|----------------|----------|
| GitHub API | Enable caching, use App |
| Datadog/CloudWatch | Reduce query scope |
| AI | Use Haiku model |
| Network | Check connectivity |

### High Memory Usage

**Symptoms:**
- OOM errors
- Container restarts

**Solutions:**
1. Increase memory limits
2. Review log volume being processed
3. Check for memory leaks (report if found)

---

## 🐛 Debug Logging

### Enable Debug Mode

```bash
# In .env
DEBUG=true
LOG_LEVEL=debug
```

### View Logs

```bash
# Docker
docker-compose logs -f

# Kubernetes
kubectl logs -f deployment/incident-copilot

# Local
uvicorn src.main:app --reload --log-level debug
```

### Log Format

```
2025-01-15 10:30:00 INFO  [webhook] Received PagerDuty webhook
2025-01-15 10:30:00 DEBUG [webhook] Payload: {"event_type": "incident.triggered"...}
2025-01-15 10:30:01 INFO  [github] Fetching commits for payments-api
2025-01-15 10:30:02 INFO  [datadog] Fetching logs for payments-api
2025-01-15 10:30:03 INFO  [ai] Generating summary
2025-01-15 10:30:05 INFO  [slack] Sending context card
2025-01-15 10:30:05 INFO  [orchestrator] Context card delivered in 5000ms
```

---

## 🆘 Getting Support

### Before Contacting Support

1. ✅ Check this troubleshooting guide
2. ✅ Review integration-specific docs
3. ✅ Enable debug logging and collect logs
4. ✅ Note error messages exactly

### Information to Include

When reporting issues, provide:

```markdown
**Environment:**
- Deployment: Docker/Kubernetes/Local
- Version: 0.1.0
- Log provider: Datadog/CloudWatch/etc

**Issue:**
- What happened
- What you expected
- Steps to reproduce

**Logs:**
```
[paste relevant log excerpts]
```

**Configuration:**
- Integrations configured: PagerDuty, GitHub, Datadog, Slack
- (Don't include API keys!)
```

### Support Channels

| Channel | Best For |
|---------|----------|
| GitHub Issues | Bug reports, feature requests |
| Documentation | Guides and reference |
| Email Support | Pro/Enterprise customers |

---

## 📚 Related Documentation

- [Getting Started](./getting-started.md)
- [Integration Guides](./integrations/)
- [Feature Documentation](./features/)
- [Admin Guides](./admin/)

---

*Can't find your issue? Open a GitHub issue with debug logs and configuration details.*
