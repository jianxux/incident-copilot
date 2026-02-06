# Best Practices for Incident Response Workflows

This guide covers best practices for getting the most out of Incident Copilot and improving your overall incident response process.

## Table of Contents

1. [Setting Up for Success](#setting-up-for-success)
2. [Optimizing Context Cards](#optimizing-context-cards)
3. [Team Workflows](#team-workflows)
4. [Runbook Management](#runbook-management)
5. [Alert Hygiene](#alert-hygiene)
6. [Post-Incident Practices](#post-incident-practices)
7. [Measuring Success](#measuring-success)
8. [Security Best Practices](#security-best-practices)

---

## Setting Up for Success

### Service Naming Convention

Use consistent, descriptive service names across all systems:

**Good:**
```
payments-api
user-auth-service
order-processor
notification-worker
```

**Avoid:**
```
svc1
prod-api-v2
my-service
test
```

**Why it matters:** Incident Copilot uses service names to:
- Match to GitHub repositories
- Query log providers
- Find relevant runbooks
- Identify on-call schedules

### Repository Structure

Organize repositories to match service names:

```
your-org/
├── payments-api/
│   ├── CODEOWNERS
│   ├── docs/
│   │   └── runbooks/
│   └── src/
├── user-auth-service/
└── order-processor/
```

### CODEOWNERS File

Always maintain a `CODEOWNERS` file in each repository:

```
# /CODEOWNERS
* @platform-team
/src/payments/ @payments-team
/src/auth/ @security-team
```

Incident Copilot uses this to identify owners and include them in context cards.

### Log Tagging

Ensure logs have proper metadata:

**Datadog:**
```python
import structlog
logger = structlog.get_logger()
logger.error("Payment failed", service="payments-api", environment="production")
```

**CloudWatch:**
```json
{
  "level": "ERROR",
  "service": "payments-api",
  "message": "Payment failed",
  "trace_id": "abc123"
}
```

---

## Optimizing Context Cards

### Configure Service Mapping

Always configure explicit mappings when service names don't match repository names:

```bash
SERVICE_REPO_MAP='{
  "payments-api": "your-org/payment-service",
  "auth": "your-org/identity-platform",
  "web": "your-org/frontend-app"
}'
```

### Configure On-Call Mapping

Map services to on-call schedules for relevant on-call information:

```bash
ONCALL_SCHEDULE_MAP='{
  "payments-api": "SCHEDULE_PAYMENTS",
  "auth": "SCHEDULE_PLATFORM",
  "web": "SCHEDULE_FRONTEND"
}'
```

### Optimize Log Queries

For faster, more relevant context:

1. **Use specific log groups** (CloudWatch):
   ```bash
   CLOUDWATCH_LOG_GROUP_MAP='{
     "payments-api": "/ecs/payments-production"
   }'
   ```

2. **Use specific labels** (Loki):
   ```bash
   LOKI_SERVICE_LABELS='{
     "payments-api": "namespace=\"prod\",app=\"payments\""
   }'
   ```

### AI Model Selection

Choose the right AI model for your needs:

| Scenario | Model | Why |
|----------|-------|-----|
| High-volume production | `claude-3-haiku-20240307` | Fastest, cost-effective |
| Complex debugging | `claude-3-sonnet-20240229` | More detailed analysis |
| Critical outages | `claude-3-opus-20240229` | Most thorough analysis |

---

## Team Workflows

### Incident Response Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        RECOMMENDED INCIDENT FLOW                            │
│                                                                             │
│  1. ALERT                                                                   │
│     └─► PagerDuty/Opsgenie notifies on-call engineer                       │
│                                                                             │
│  2. CONTEXT (Incident Copilot)                                             │
│     └─► Context card arrives in Slack within 10 seconds                    │
│     └─► Review: recent deploys, error patterns, AI summary                 │
│                                                                             │
│  3. ACKNOWLEDGE                                                             │
│     └─► Acknowledge in PagerDuty/Opsgenie                                  │
│     └─► Thread in Slack: "Investigating - reviewing recent deploy"        │
│                                                                             │
│  4. INVESTIGATE                                                             │
│     └─► Follow runbook links in context card                               │
│     └─► Check dashboards linked in card                                    │
│     └─► Collaborate in Slack thread                                        │
│                                                                             │
│  5. MITIGATE                                                                │
│     └─► Apply fix (rollback, config change, scale up)                      │
│     └─► Verify issue is resolved                                           │
│                                                                             │
│  6. RESOLVE                                                                 │
│     └─► Resolve in PagerDuty/Opsgenie                                      │
│     └─► Document resolution in Slack thread                                │
│                                                                             │
│  7. FOLLOW-UP                                                               │
│     └─► Create post-incident issue (Jira/Linear)                           │
│     └─► Schedule postmortem if needed                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Slack Channel Organization

Recommended channel structure:

| Channel | Purpose |
|---------|---------|
| `#incidents` | All context cards, incident notifications |
| `#incidents-critical` | Critical/P1 incidents only |
| `#incident-{id}` | Per-incident channel for major incidents |
| `#oncall` | On-call discussions and handoffs |
| `#postmortems` | Post-incident review scheduling |

### Thread Discipline

Always use threads for incident discussion:

**Good:**
```
🟠 payments-api: High Error Rate
└── @alice: Investigating - looks related to the Stripe deploy at 2pm
└── @alice: Confirmed - rolling back deployment abc123
└── @alice: Rollback complete, monitoring...
└── @alice: Resolved - error rate back to normal
```

**Avoid:**
Separate messages that clutter the channel and lose context.

---

## Runbook Management

### Runbook Structure

Create runbooks that work well with Incident Copilot's linking:

```markdown
# High Error Rate - Payments API

**Service:** payments-api
**Keywords:** error rate, 5xx, timeout, stripe

## Symptoms
- Error rate > 1%
- Increased latency
- Failed payments

## Quick Checks
1. Check Stripe status: https://status.stripe.com
2. Review recent deploys in context card
3. Check database connection pool

## Resolution Steps
...
```

### Runbook Location

Store runbooks where Incident Copilot can index them:

- **GitHub**: `docs/runbooks/` in service repositories
- **Confluence**: Tag pages with service names
- **Notion**: Use consistent page structure

### Keywords and Tags

Add relevant keywords to improve matching:

```markdown
---
tags: [payments, stripe, timeout, 5xx, error-rate]
services: [payments-api, payment-processor]
---
```

---

## Alert Hygiene

### Reduce Noise

Incident Copilot works best when alerts are meaningful:

1. **Set appropriate thresholds** - Avoid alerting on minor blips
2. **Add context to alerts** - Include service name, environment
3. **Group related alerts** - Use alert correlation

### Alert Correlation

Enable correlation to reduce duplicate notifications:

```bash
CORRELATION_ENABLED=true
CORRELATION_TIME_WINDOW_SECONDS=300
CORRELATION_SUPPRESS_DUPLICATES=true
```

### Severity Guidelines

| Severity | When to Use | Response Time |
|----------|-------------|---------------|
| **Critical** | User-facing outage, data loss risk | Immediate (< 15 min) |
| **High** | Major degradation, potential escalation | < 30 minutes |
| **Medium** | Minor impact, standard on-call response | < 1 hour |
| **Low** | No immediate impact, business hours | < 4 hours |
| **Info** | Awareness only, no action required | As available |

---

## Post-Incident Practices

### Document Resolution

After resolving an incident, document in the Slack thread:

```
✅ Resolved: Error rate back to normal

**Root Cause:** Connection pool exhaustion due to retry storm
**Resolution:** Rolled back deployment abc123
**Follow-up:** Create ticket for retry logic review

Time to Resolution: 23 minutes
```

### Create Follow-up Issues

Use the context card information to create detailed tickets:

```markdown
## Incident: High Error Rate - payments-api
**Date:** 2024-01-15 14:30 UTC
**Duration:** 23 minutes
**Severity:** High

### Summary
Payment processing experienced high error rates due to connection pool exhaustion.

### Root Cause
The deployment at 14:00 (commit abc1234) changed retry logic, causing a retry storm
under load that exhausted the Stripe connection pool.

### Action Items
- [ ] Review and fix retry logic configuration
- [ ] Add connection pool monitoring
- [ ] Add circuit breaker for Stripe calls
```

### Postmortem Triggers

Schedule a postmortem for:
- Any critical (P1) incident
- Incidents lasting > 30 minutes
- Incidents affecting > 10% of users
- Novel failure modes

---

## Measuring Success

### Key Metrics

Track these metrics to measure Incident Copilot effectiveness:

| Metric | Description | Target |
|--------|-------------|--------|
| **MTTR** | Mean Time To Resolution | Decrease by 30-50% |
| **MTTA** | Mean Time To Acknowledge | < 5 minutes |
| **Context Card Delivery** | Time from alert to card | < 10 seconds |
| **Context Completeness** | % of cards with all data | > 95% |

### Before/After Comparison

Track improvement over baseline:

```
Before Incident Copilot:
- Average MTTR: 45 minutes
- Time spent gathering context: 10-15 minutes
- Runbook lookup: 3-5 minutes

After Incident Copilot:
- Average MTTR: 25 minutes (44% reduction)
- Context delivered: 10 seconds
- Runbooks auto-linked
```

### Dashboard Suggestions

Create dashboards tracking:
- Incidents by service
- Resolution time trends
- Most common error patterns
- On-call workload distribution

---

## Security Best Practices

### Secret Management

**Never commit secrets to version control.**

Use a secrets manager in production:
- **AWS Secrets Manager**
- **HashiCorp Vault**
- **GCP Secret Manager**
- **Azure Key Vault**

### Rotate Credentials

Establish a rotation schedule:

| Credential | Rotation Frequency |
|------------|-------------------|
| GitHub PAT | 90 days |
| Slack Bot Token | On compromise only |
| API Keys (Datadog, etc.) | 180 days |
| Webhook Secrets | Annually |

### Least Privilege

Grant minimum required permissions:

| Integration | Required Scope |
|-------------|----------------|
| GitHub | `repo` read-only |
| Slack | `chat:write`, `chat:write.public` |
| Datadog | Read access to logs/metrics |
| PagerDuty | Read-only API access |

### Network Security

In production:
- Deploy in private subnet
- Use HTTPS for all webhook endpoints
- Consider IP allowlisting for alerting providers
- Use WAF for public endpoints

### Audit Trail

Enable audit logging:

```bash
AUDIT_ENABLED=true
AUDIT_RETENTION_DAYS=90
```

Review audit logs periodically for:
- Unauthorized access attempts
- Unusual API usage patterns
- Configuration changes

---

## Checklist for Production

### Before Go-Live

- [ ] All integrations tested and working
- [ ] Service-to-repo mapping configured
- [ ] On-call schedules mapped
- [ ] Slack channels set up
- [ ] Runbooks indexed
- [ ] Team trained on workflow
- [ ] Monitoring/alerting for Incident Copilot itself
- [ ] Secrets properly secured
- [ ] Backup alerting path if Copilot fails

### Weekly

- [ ] Review MTTR trends
- [ ] Check for new services to add
- [ ] Update runbooks based on recent incidents
- [ ] Verify integrations still working

### Monthly

- [ ] Review and update service mappings
- [ ] Rotate credentials as scheduled
- [ ] Review AI model performance
- [ ] Update documentation

---

## Summary

### Do

✅ Use consistent service naming
✅ Maintain CODEOWNERS files
✅ Create and link runbooks
✅ Use threads for incident discussion
✅ Document resolutions
✅ Track MTTR improvements
✅ Enable audit logging

### Don't

❌ Create noisy alerts
❌ Skip runbook updates after incidents
❌ Hardcode secrets in configuration
❌ Ignore context card errors
❌ Skip postmortems for major incidents

---

*← [Troubleshooting](./troubleshooting.md) | [Back to Index](./README.md)*
