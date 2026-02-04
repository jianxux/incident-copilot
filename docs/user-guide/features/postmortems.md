# 📝 AI Postmortems

Incident Copilot can automatically generate comprehensive postmortem reports using AI analysis of incident data.

---

## 🎯 What is an AI Postmortem?

A postmortem is a structured document created after an incident to:
- **Document what happened** (timeline)
- **Identify root cause** (analysis)
- **Assess impact** (business effects)
- **Define action items** (prevent recurrence)
- **Capture learnings** (improve processes)

Incident Copilot generates these automatically from incident data.

---

## 📄 Postmortem Structure

### Executive Summary

AI-generated overview for leadership:

```markdown
## Executive Summary

On January 15, 2025, the payments-api service experienced a 15-minute 
outage affecting approximately 2,000 customers. The root cause was an 
overly aggressive connection timeout configuration deployed at 02:15 UTC.

The incident was detected automatically, acknowledged within 2 minutes, 
and resolved by rolling back the configuration change. Customer impact 
was limited to failed checkout attempts during the incident window.

Key action items include adding timeout validation to deployment pipelines 
and improving monitoring for third-party API latency.
```

### Timeline

Chronological event listing:

```markdown
## Timeline

| Time (UTC) | Event | Actor | Details |
|------------|-------|-------|---------|
| 02:15 | Deployment | @sarah | abc1234 - Reduce timeout to 5s |
| 02:30 | Alert | PagerDuty | High error rate detected |
| 02:32 | Acknowledged | @sarah | Started investigation |
| 02:35 | Root Cause | @sarah | Identified timeout issue |
| 02:38 | Mitigation | @sarah | Rolled back timeout config |
| 02:45 | Resolved | System | Error rate normalized |
```

### Root Cause Analysis

AI-identified primary and contributing causes:

```markdown
## Root Cause Analysis

### Primary Cause
The connection timeout for Stripe API calls was reduced from 30 seconds 
to 5 seconds in deployment abc1234. Stripe's API was experiencing elevated 
latency (p99: 8s) at the time, causing all requests to timeout.

### Contributing Factors
- No validation on timeout configuration values
- Stripe latency not monitored in pre-deployment checks
- Timeout change not flagged as high-risk

### Trigger
The incident was triggered when deployment abc1234 went live at 02:15 UTC.

### Detection
Automatic detection via PagerDuty alert on error rate threshold (>5%).
```

### Impact Assessment

Business and technical impact:

```markdown
## Impact

| Metric | Value |
|--------|-------|
| Duration | 15 minutes |
| Users Affected | ~2,000 |
| Failed Transactions | 847 |
| Revenue Impact | ~$12,000 (estimated) |
| SLA Breach | No (99.9% maintained) |

### Affected Services
- payments-api (primary)
- checkout-service (dependent)

### Customer Impact
Customers attempting checkout during the incident received timeout errors.
No data loss occurred; failed transactions can be retried.
```

### Action Items

Prioritized follow-up tasks:

```markdown
## Action Items

| Priority | Action | Owner | Due Date |
|----------|--------|-------|----------|
| 🔴 High | Add timeout validation to deploy pipeline | @mike | Jan 20 |
| 🔴 High | Create alert for Stripe API latency | @sarah | Jan 18 |
| 🟡 Medium | Add circuit breaker for Stripe calls | @team | Jan 31 |
| 🟡 Medium | Document timeout best practices | @docs | Jan 25 |
| 🟢 Low | Review all service timeouts | @team | Feb 15 |
```

### Lessons Learned

Organizational learnings:

```markdown
## Lessons Learned

### What Went Well
- Alert fired within 30 seconds of first errors
- On-call responded and acknowledged quickly
- Root cause identified within 5 minutes
- Clear rollback procedure existed

### What Went Poorly
- No pre-deployment check for third-party health
- Timeout change wasn't reviewed by senior engineer
- No warning in monitoring until threshold breached

### Lucky Factors
- Incident occurred during low-traffic hours
- Stripe's elevated latency was temporary
- No cascading failures to other services
```

---

## 🔧 Generating Postmortems

### Automatic Generation

Postmortems can be generated when an incident is resolved:

```bash
POST /api/incidents/{id}/postmortem/generate

Response:
{
  "postmortem_id": "pm-abc123",
  "status": "draft",
  "url": "/postmortems/pm-abc123"
}
```

### Manual Trigger

Generate via CLI or UI:

```bash
# Future CLI
python -m incident_copilot.cli generate-postmortem --incident-id inc-123
```

### Incremental Updates

Update postmortem as more information becomes available:

```bash
POST /api/postmortems/{id}/update
{
  "sections": ["timeline", "action_items"]
}
```

---

## 📊 Postmortem Workflow

### Status States

| Status | Description |
|--------|-------------|
| `draft` | AI-generated, needs review |
| `in_review` | Being reviewed by team |
| `approved` | Reviewed and approved |
| `published` | Shared with organization |

### Review Process

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Draft     │────▶│  In Review  │────▶│  Approved   │────▶│  Published  │
│  (AI Gen)   │     │  (Team)     │     │  (Manager)  │     │  (Shared)   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

---

## ⚙️ Configuration

### AI Model for Postmortems

Use a more capable model for thorough analysis:

```bash
# Default model (fast)
AI_MODEL=claude-3-haiku-20240307

# Better for postmortems (recommended)
AI_MODEL=claude-3-5-sonnet-20241022
```

### Template Customization (Future)

```bash
# Custom postmortem template
# POSTMORTEM_TEMPLATE_PATH=/path/to/template.md
```

---

## 📱 Accessing Postmortems

### Via API

```bash
# Get postmortem
GET /api/postmortems/{id}

# List postmortems
GET /api/postmortems?status=published

# Export as Markdown
GET /api/postmortems/{id}/export?format=markdown
```

### Export Formats

| Format | Use Case |
|--------|----------|
| Markdown | Documentation systems |
| PDF | Formal distribution |
| Confluence | Atlassian wiki |
| Notion | Notion databases |

---

## 🎯 Best Practices

### Before Generation

1. **Resolve the incident** first
2. **Ensure timeline is complete** with all events
3. **Add root cause** if known
4. **Document resolution** steps taken

### After Generation

1. **Review AI content** for accuracy
2. **Verify timeline** completeness
3. **Assign action item owners**
4. **Set realistic due dates**
5. **Share with stakeholders**

### Blameless Culture

- Focus on systems, not individuals
- "What" and "why", not "who"
- Encourage honest reporting
- Learn and improve

---

## 🐛 Troubleshooting

### "Generation failed"

**Causes:**
- Insufficient incident data
- API key issues
- Network timeout

**Solutions:**
- Ensure incident has context card
- Verify Anthropic API key
- Retry generation

### Poor Quality Output

**Causes:**
- Limited incident data
- Unclear error logs
- Missing timeline events

**Solutions:**
- Add more incident details
- Ensure logs were captured
- Manually add timeline events

### Missing Sections

**Causes:**
- Not enough data for that section

**Solutions:**
- Add data manually
- Re-generate after adding info

---

## 📊 Metrics

Track postmortem effectiveness:

| Metric | Description |
|--------|-------------|
| Generation Time | Time to create draft |
| Review Time | Time in review status |
| Action Completion | % of actions completed |
| Recurrence Rate | Similar incidents after |

---

## 📚 Related Documentation

- [AI Analysis](./ai-analysis.md) - How AI generates content
- [Incident Timeline](./incident-timeline.md) - Timeline details
- [Analytics](./analytics.md) - Post-incident metrics

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or open an issue on GitHub.*
