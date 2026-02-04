# 🃏 Context Cards

Context cards are the core deliverable of Incident Copilot. When an incident fires, a rich, actionable card is delivered to your notification channel within seconds.

---

## 🎯 What is a Context Card?

A context card is an automatically assembled summary that provides on-call engineers with everything they need to start investigating an incident:

```
┌─────────────────────────────────────────────────────┐
│ 🟠 payments-api: High Error Rate                    │
├─────────────────────────────────────────────────────┤
│ Severity: HIGH  |  Triggered: 02:47 UTC             │
│ 🔗 View in PagerDuty | 📊 Dashboard                 │
├─────────────────────────────────────────────────────┤
│ 🚀 Recent Deployments                               │
│ • abc1234 by @sarah - Fix retry logic (2h ago)      │
│ • def5678 by @mike - Update dependencies (5h ago)   │
├─────────────────────────────────────────────────────┤
│ 📋 Top Issues (AI Analysis)                         │
│ • ConnectionTimeout to stripe-api (847 occurrences) │
│ • Retry limit exceeded (612 occurrences)            │
│                                                     │
│ The service is experiencing timeouts when           │
│ connecting to Stripe's API. This started around     │
│ 02:30 UTC, approximately 15 minutes after the       │
│ latest deployment...                                │
├─────────────────────────────────────────────────────┤
│ 🔍 Similar Past Incidents                           │
│ • Stripe API outage (Jan 10) - 92% match            │
│ • Payment gateway timeout (Dec 15) - 78% match      │
├─────────────────────────────────────────────────────┤
│ 👥 On-Call: @sarah, @mike                           │
│ 📖 Runbook: payments-api-errors                     │
│                                                     │
│ ⏱️ Context assembled in 3420ms                      │
└─────────────────────────────────────────────────────┘
```

---

## 📊 Card Sections

### 1. Header

The header provides at-a-glance incident information:

| Element | Description |
|---------|-------------|
| **Severity Indicator** | 🔴 Critical, 🟠 High, 🟡 Medium, 🟢 Low |
| **Service Name** | The affected service |
| **Title** | Incident title from alerting system |
| **Timestamp** | When the incident was triggered |

### 2. Quick Links

Direct links to:
- **Alert Source** - PagerDuty or Opsgenie incident page
- **Dashboard** - Monitoring dashboard (if configured)
- **Runbook** - Relevant documentation

### 3. Recent Deployments

Shows code changes that might have caused the issue:

```
🚀 Recent Deployments
• abc1234 by @sarah - Fix retry logic (2h ago)
  └─ Files: payments/stripe.py, payments/retry.py
• def5678 by @mike - Update dependencies (5h ago)
```

**Source:** GitHub or GitLab (last 10 commits to default branch)

### 4. AI Analysis

The AI summarization section includes:

| Component | Description |
|-----------|-------------|
| **Top Issues** | Most frequent error patterns with counts |
| **Explanation** | Plain-English description of what's happening |
| **Likely Cause** | AI's assessment of the root cause |
| **Suggested Actions** | Recommended next steps |

### 5. Similar Incidents

Shows related past incidents:

```
🔍 Similar Past Incidents
• Stripe API outage (Jan 10, 2025) - 92% match
  └─ Root cause: Third-party outage
• Payment gateway timeout (Dec 15, 2024) - 78% match
  └─ Root cause: Connection pool exhaustion
```

**Matching:** Based on vector similarity of incident titles and error patterns.

### 6. On-Call & Ownership

Shows who to contact:

```
👥 On-Call: @sarah (primary), @mike (secondary)
📂 Code Owners: @payments-team
📖 Runbook: payments-api-high-error-rate
```

**Sources:**
- On-call: PagerDuty or Opsgenie schedules
- Code owners: CODEOWNERS file in repository
- Runbooks: Configured runbook sources

### 7. Footer

Metadata about the card itself:

```
⏱️ Context assembled in 3420ms
```

---

## ⚡ Assembly Process

When an incident fires, Incident Copilot:

```
┌─────────────┐     ┌─────────────────────────────────────────────────┐
│   Webhook   │────▶│              PARALLEL ASSEMBLY                   │
│   Received  │     │                                                  │
└─────────────┘     │  ┌──────────┐ ┌──────────┐ ┌──────────┐         │
                    │  │  GitHub  │ │  Datadog │ │ Runbooks │         │
                    │  │   API    │ │   Logs   │ │  Search  │         │
                    │  └────┬─────┘ └────┬─────┘ └────┬─────┘         │
                    │       │            │            │                │
                    │       └────────────┼────────────┘                │
                    │                    │                             │
                    │              ┌─────▼─────┐                       │
                    │              │    AI     │                       │
                    │              │ Summarize │                       │
                    │              └─────┬─────┘                       │
                    │                    │                             │
                    │              ┌─────▼─────┐                       │
                    │              │  Build    │                       │
                    │              │   Card    │                       │
                    │              └───────────┘                       │
                    └─────────────────────────────────────────────────┘
                                         │
                                         ▼
                              ┌─────────────────────┐
                              │  Deliver to Slack   │
                              │   or Teams (<10s)   │
                              └─────────────────────┘
```

### Performance Targets

| Step | Target Time |
|------|-------------|
| Webhook processing | <100ms |
| GitHub/GitLab fetch | <2s |
| Log fetch | <5s |
| AI summarization | <3s |
| Delivery | <1s |
| **Total** | **<10s** |

---

## 🎨 Customization

### Severity Colors

| Severity | Emoji | Color (Slack) |
|----------|-------|---------------|
| Critical | 🔴 | `#FF0000` |
| High | 🟠 | `#FFA500` |
| Medium | 🟡 | `#FFD700` |
| Low | 🟢 | `#00FF00` |

### Card Content

Control what appears in cards via configuration:

```bash
# Include/exclude sections (future feature)
# CONTEXT_CARD_SECTIONS=["header","deployments","logs","ai_summary","similar"]
```

---

## 📱 Platform Differences

### Slack

- Uses Block Kit for rich formatting
- Supports interactive buttons
- Can update existing messages
- Threading for updates

### Microsoft Teams

- Uses Adaptive Cards
- Limited interactivity
- Fixed message (no updates)
- Simpler formatting

---

## 🔄 Card Updates (Future)

Planned features for card lifecycle:

| Event | Card Update |
|-------|-------------|
| Acknowledged | Show who acknowledged, when |
| Escalated | Show escalation chain |
| Resolved | Mark resolved, show duration |
| Postmortem | Link to generated postmortem |

---

## 🐛 Troubleshooting

### "No deployments found"

**Cause:** Service name doesn't match repository name

**Solution:** Add mapping in `SERVICE_REPO_MAP`:
```bash
SERVICE_REPO_MAP='{"alert-service-name": "org/actual-repo"}'
```

### "No logs found"

**Cause:** Logs not tagged with service name

**Solution:** 
- Ensure logs have `service` tag in Datadog
- Add explicit mapping if needed

### "AI summary unavailable"

**Cause:** No Anthropic API key or no logs to summarize

**Solution:**
- Configure `ANTHROPIC_API_KEY`
- Verify logs are being fetched

### "Card delivered late (>10s)"

**Cause:** Slow external API responses

**Solutions:**
- Check network connectivity
- Review individual integration health
- Consider caching (built-in)

---

## 📊 Analytics

Track context card performance:

| Metric | Description |
|--------|-------------|
| Assembly Time | Time from webhook to delivery |
| Section Coverage | Which sections were populated |
| AI Summary Quality | User feedback on summaries |
| Similar Incident Accuracy | Was the match helpful? |

Access via the `/api/analytics` endpoints (coming soon).

---

## 📚 Related Documentation

- [AI Analysis](./ai-analysis.md) - How summarization works
- [Similar Incidents](./similar-incidents.md) - Matching algorithm
- [Incident Timeline](./incident-timeline.md) - Detailed event tracking

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or open an issue on GitHub.*
