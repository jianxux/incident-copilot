# ❓ Frequently Asked Questions (FAQ)

Common questions and answers about Incident Copilot.

---

## 🚀 Getting Started

### What is Incident Copilot?

Incident Copilot is a context-aware assistant for on-call engineers. When an alert fires, it automatically:
- Fetches recent deployments from GitHub/GitLab
- Pulls error logs from Datadog, CloudWatch, or Splunk
- Summarizes issues using AI (Claude)
- Delivers a "context card" to Slack/Teams within 10 seconds

**Result:** Engineers get actionable context immediately, reducing MTTR by 30-50%.

### What's the minimum setup required?

You need:
1. **Alerting tool:** PagerDuty or Opsgenie
2. **Code repository:** GitHub or GitLab
3. **Log provider:** Datadog, CloudWatch, Loki, or Splunk
4. **Notification channel:** Slack or Microsoft Teams
5. **AI API key:** Anthropic (Claude)

See the [Getting Started Guide](./getting-started.md) for step-by-step setup.

### How long does setup take?

Basic setup takes **5-15 minutes**. Full setup with all integrations typically takes **30-60 minutes**.

### Can I try it without production data?

Yes! Use the demo endpoint:
```bash
curl -X POST http://localhost:8000/demo/trigger \
  -H "Content-Type: application/json" \
  -d '{"service_name": "test-service", "title": "Test Alert", "severity": "high"}'
```

Or use the CLI:
```bash
incident-copilot send-test
```

---

## 💰 Pricing & Plans

### Is Incident Copilot free?

Incident Copilot is **open source** and free to self-host. You only pay for:
- Your own infrastructure (hosting, database)
- Third-party API costs (Anthropic, OpenAI for embeddings)

### What are the API costs?

Approximate costs per incident:
- **Claude API (AI summary):** ~$0.01-0.05 per incident
- **OpenAI Embeddings (similarity):** ~$0.001 per incident (optional)

For 100 incidents/month, expect ~$1-5 in API costs.

### Is there a managed/hosted version?

Not currently. Incident Copilot is designed for self-hosting. Enterprise support options may be available in the future.

---

## 🔧 Configuration

### How do I add multiple alerting sources?

Configure both PagerDuty and Opsgenie:

```bash
# PagerDuty
PAGERDUTY_API_KEY=your-key
PAGERDUTY_WEBHOOK_SECRET=your-secret

# Opsgenie
OPSGENIE_API_KEY=your-key
OPSGENIE_WEBHOOK_SECRET=your-secret
```

Both webhook endpoints will be active:
- `/webhooks/pagerduty`
- `/webhooks/opsgenie`

### How do I map service names to repositories?

If your PagerDuty service names don't match your repo names:

```bash
SERVICE_REPO_MAP='{
  "payments-service": "org/payments-api",
  "auth-svc": "org/authentication"
}'
```

### How do I change the AI model?

```bash
AI_MODEL=claude-3-opus-20240229  # More capable, slower
AI_MODEL=claude-3-haiku-20240307  # Faster, cheaper (default)
```

### Can I use OpenAI instead of Anthropic?

Currently, Incident Copilot is optimized for Claude (Anthropic). OpenAI support is on the roadmap.

### How do I configure for multiple environments?

Use different `.env` files:

```bash
# Development
cp .env.example .env.development

# Production
cp .env.example .env.production

# Run with specific env
ENV_FILE=.env.production docker-compose up
```

---

## 🔔 Alerts & Notifications

### Why am I not receiving context cards?

Check these common issues:

1. **Webhook not configured:** Verify webhook URL in PagerDuty/Opsgenie
2. **Signature mismatch:** Re-copy the webhook secret
3. **Slack bot not in channel:** Invite the bot to the channel
4. **Server not accessible:** Use ngrok for local testing

See [Troubleshooting](./troubleshooting.md) for detailed diagnostics.

### Can I send to multiple Slack channels?

Yes, configure per-service routing:

```bash
SLACK_CHANNEL_ROUTING='{
  "payments-api": "#payments-alerts",
  "auth-service": "#auth-alerts",
  "default": "#incidents"
}'
```

### Can I use both Slack and Teams?

Yes! Set up both:

```bash
NOTIFICATION_PROVIDER=both
SLACK_BOT_TOKEN=xoxb-xxx
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/...
```

### How do I customize the context card format?

Context cards use templates. Create custom templates in `templates/cards/`:

```bash
# Use custom template
CONTEXT_CARD_TEMPLATE=custom_minimal
```

### Can I filter which incidents generate cards?

Yes, configure filters:

```bash
# Only high and critical severity
MIN_SEVERITY_FOR_CARD=high

# Exclude specific services
EXCLUDED_SERVICES=["test-service", "staging"]
```

---

## 📊 Features

### How does similar incident search work?

Incident Copilot uses embeddings to find semantically similar past incidents:

1. Incident description is converted to a vector embedding
2. Compared against embeddings of past incidents
3. Returns matches above similarity threshold

Requires OpenAI API key for embeddings:
```bash
OPENAI_API_KEY=sk-xxx
```

### Can I disable AI features?

Yes, run in "minimal" mode:

```bash
AI_ENABLED=false
```

You'll still get deployments and logs, just no AI summary.

### How are postmortems generated?

AI postmortems are generated from:
- Incident timeline and events
- Log analysis
- Similar past incidents
- Resolution notes

Generate via API or UI after an incident is resolved.

### Can I export analytics data?

Yes, via API:

```bash
# Get raw metrics
curl "http://localhost:8000/api/analytics/incidents?days=30&limit=1000"

# Or use the reports feature
curl -X POST "http://localhost:8000/api/reports/generate" \
  -d '{"report_type": "weekly", "format": "json"}'
```

---

## 🔐 Security

### Is my data secure?

Incident Copilot:
- **Does not store** full log contents (only summaries)
- **Does not send** data to external services (except configured APIs)
- **Supports** encryption at rest and in transit
- **Provides** audit logging for compliance

### What data is sent to AI providers?

Only:
- Log excerpts (configurable limit, default 10KB)
- Incident metadata (title, service, severity)

**Not sent:** API keys, PII (if properly configured), raw webhook payloads.

### How do I enable SSO?

See [SSO Configuration](./admin/sso.md) for SAML and OIDC setup.

### How do I rotate API keys?

1. Generate new key in admin panel
2. Update `.env` with new key
3. Restart application
4. Revoke old key

### Is there audit logging?

Yes, all actions are logged:

```bash
# View audit logs
curl "http://localhost:8000/api/audit/events?tenant_id=xxx"
```

---

## 🏗️ Deployment

### What are the system requirements?

**Minimum:**
- 1 CPU core
- 512MB RAM
- 1GB disk

**Recommended (production):**
- 2+ CPU cores
- 2GB+ RAM
- 10GB disk (for logs and cache)

### Can I run on Kubernetes?

Yes! Helm chart and manifests are provided:

```bash
helm install incident-copilot ./charts/incident-copilot
```

See [Kubernetes Deployment](../README.md#kubernetes-deployment).

### How do I scale horizontally?

Incident Copilot is stateless (with Redis for cache):

```yaml
# docker-compose.yml
services:
  app:
    deploy:
      replicas: 3
```

### What database is required?

- **PostgreSQL** (recommended for production)
- **SQLite** (fine for development/small deployments)

```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/incident_copilot
```

### How do I handle high availability?

1. Run multiple app replicas behind a load balancer
2. Use managed PostgreSQL with replicas
3. Use Redis cluster for caching
4. Configure health check endpoints for orchestrator

---

## 🐛 Troubleshooting

### Context cards are slow (>10 seconds)

Check which component is slow:
```bash
curl 'http://localhost:8000/health?full=true'
```

Common causes:
- **GitHub rate limits:** Use GitHub App instead of PAT
- **Slow log queries:** Reduce query scope
- **AI latency:** Use Haiku model instead of Opus

### "No logs found" in context cards

1. Verify service name matches log tags in Datadog/CloudWatch
2. Check log provider credentials
3. Ensure logs exist in the time range
4. Configure explicit service mapping

### Memory usage keeps growing

Potential memory leak. Please report with:
- Application logs
- Memory profile if available
- Reproduction steps

### Webhooks work locally but not in production

1. Verify HTTPS certificate is valid
2. Check firewall allows inbound traffic
3. Verify webhook URL includes correct path
4. Test with: `curl -X POST https://your-domain.com/webhooks/health`

---

## 🔌 Integrations

### Which log providers are supported?

- ✅ Datadog
- ✅ AWS CloudWatch
- ✅ Splunk
- ✅ Grafana Loki
- 🔜 Elasticsearch (coming soon)

### Which alerting tools are supported?

- ✅ PagerDuty
- ✅ Opsgenie
- 🔜 VictorOps (coming soon)
- 🔜 Prometheus AlertManager (coming soon)

### Can I add a custom integration?

Yes! Incident Copilot has a plugin system:

```python
# src/plugins/my_integration.py
from src.plugins import BasePlugin

class MyIntegration(BasePlugin):
    async def on_incident(self, incident):
        # Custom logic
        pass
```

See [Plugin Development](../CONTRIBUTING.md#plugins).

---

## 📈 Metrics & Analytics

### How is MTTR calculated?

```
MTTR = (resolved_at - triggered_at) / incident_count
```

Only resolved incidents are included in MTTR calculations.

### What's the difference between mean and median MTTR?

- **Mean:** Average of all values (affected by outliers)
- **Median:** Middle value (more robust)

Use median for better representation of "typical" resolution time.

### Can I track custom metrics?

Yes, via the API:

```bash
POST /api/incidents/{id}/events
{
  "event_type": "custom_metric",
  "data": {"key": "value"}
}
```

---

## 🆘 Getting Help

### Where do I report bugs?

Open an issue on GitHub with:
- Description of the issue
- Steps to reproduce
- Expected vs actual behavior
- Logs (with secrets redacted)

### How do I request features?

Open a GitHub issue with the `enhancement` label. Include:
- Use case description
- Proposed solution
- Alternative approaches considered

### Is there a community Discord/Slack?

Not yet, but planned! For now, use GitHub Discussions.

### How do I contribute?

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for guidelines.

---

## 📚 Related Documentation

- [Getting Started](./getting-started.md) - Initial setup
- [Troubleshooting](./troubleshooting.md) - Problem solving
- [CLI Reference](./cli.md) - Command line tools
- [API Reference](./api-reference.md) - REST API docs
- [Admin Guides](./admin/) - Configuration and management

---

*Still have questions? Open a GitHub issue or check the [Troubleshooting Guide](./troubleshooting.md).*
