# 📝 AI-Powered Postmortems

Generate comprehensive incident postmortems automatically.

---

## 📋 What's Included

AI-generated postmortems include:

1. **Executive Summary** — Brief overview
2. **Timeline** — Detailed event sequence
3. **Impact Analysis** — What was affected
4. **Root Cause Analysis** — Why it happened
5. **What Went Well** — Positive observations
6. **What Went Wrong** — Issues identified
7. **Action Items** — Recommended improvements

---

## 📊 Example

```markdown
# Postmortem: payments-api High Error Rate
**Date:** January 15, 2025
**Duration:** 18 minutes
**Severity:** High

## Executive Summary
The payments-api service experienced connection timeouts
to Stripe's API, causing payment failures for approximately
15% of checkout attempts over an 18-minute period.

## Timeline
- 02:45 - Deployment abc1234 pushed to production
- 02:47 - Alerts triggered (error rate >5%)
- 02:49 - On-call engineer acknowledged
- 02:52 - Identified Stripe API as source
- 03:05 - Stripe recovered, incident resolved

## Root Cause
Stripe's API experienced degraded performance during
a maintenance window, causing our retry logic to
exhaust retries before Stripe recovered.

## Action Items
- [ ] Implement circuit breaker for Stripe calls
- [ ] Add Stripe status page to monitoring
- [ ] Review retry configuration
```

---

## 🔧 Generate Postmortem

### Via API

```bash
POST /api/postmortems/generate
{
  "incident_id": "inc_12345",
  "format": "markdown"
}
```

### Via Web UI

1. Navigate to incident
2. Click **Generate Postmortem**
3. Review and edit
4. Share or export

---

## ⚙️ Configuration

```bash
POSTMORTEM_AUTO_GENERATE=false  # Auto-generate on resolution
POSTMORTEM_TEMPLATE=default  # Template to use
POSTMORTEM_INCLUDE_METRICS=true  # Include MTTR etc.
```

---

## 📚 Related Documentation

- [AI Analysis](./ai-analysis.md)
- [Incident Timeline](./incident-timeline.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
