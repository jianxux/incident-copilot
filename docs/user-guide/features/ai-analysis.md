# 🤖 AI Analysis

Incident Copilot uses Claude AI to analyze error logs and provide actionable insights during incidents. This page explains how the AI summarization works.

---

## 🎯 What AI Analysis Does

When an incident fires, AI analysis:

1. **Parses error logs** from your log provider
2. **Identifies patterns** and recurring errors
3. **Counts occurrences** to prioritize issues
4. **Generates explanations** in plain English
5. **Suggests probable causes** and next steps

---

## 📊 AI Summary Components

### Top Issues

The most frequent error patterns:

```
📋 Top Issues (AI Analysis)
• ConnectionTimeout to stripe-api (847 occurrences)
• Retry limit exceeded (612 occurrences)
• HTTP 503 from payment-gateway (234 occurrences)
```

**How it works:** The AI clusters similar log messages and counts unique occurrences.

### Explanation

Plain-English description of what's happening:

```
The service is experiencing connection timeouts when calling Stripe's 
payment API. These timeouts started around 02:30 UTC, approximately 
15 minutes after the latest deployment that modified retry logic.
```

### Likely Cause

AI's assessment of the root cause:

```
Likely cause: The recent deployment (abc1234) changed the connection 
timeout from 30s to 5s. Combined with Stripe's current elevated 
response times, requests are timing out before completing.
```

### Suggested Actions

Recommended investigation steps:

```
Suggested actions:
• Check Stripe status page for ongoing incidents
• Review commit abc1234's timeout configuration
• Consider rolling back the retry logic changes
• Monitor connection pool metrics
```

---

## 🧠 How It Works

### 1. Log Collection

Incident Copilot fetches recent logs:
- **Time range:** Last 15 minutes
- **Filters:** ERROR, WARN, CRITICAL, FATAL levels
- **Limit:** Up to 100 log entries

### 2. Prompt Construction

The AI receives a structured prompt:

```
Analyze these error logs from {service-name}. Identify:

1. Top 3-5 error patterns with occurrence counts
2. Brief explanation of what's happening
3. Most likely cause based on the patterns
4. Suggested next steps (2-3 bullets)

Keep response concise for Slack/Teams delivery.

Logs:
[ERROR] 02:31:15 ConnectionTimeout: stripe-api after 5000ms
[ERROR] 02:31:16 ConnectionTimeout: stripe-api after 5000ms
[WARN] 02:31:17 Retry attempt 3/5 for payment-123
...
```

### 3. AI Processing

Claude analyzes the logs and returns structured insights:

```json
{
  "top_issues": [
    "ConnectionTimeout to stripe-api (847 occurrences)",
    "Retry limit exceeded (612 occurrences)"
  ],
  "explanation": "The service is experiencing...",
  "likely_cause": "The recent deployment changed...",
  "suggested_actions": [
    "Check Stripe status page",
    "Review recent deployment"
  ]
}
```

### 4. Integration with Context

The AI summary is combined with:
- Recent deployments (correlation)
- Similar past incidents (pattern matching)
- Runbook suggestions

---

## ⚙️ Configuration

### Model Selection

Choose the Claude model:

```bash
# Default: Fast and cost-effective
AI_MODEL=claude-3-haiku-20240307

# Alternative: More capable but slower
AI_MODEL=claude-3-5-sonnet-20241022

# Premium: Best quality (higher cost)
AI_MODEL=claude-3-opus-20240229
```

### API Key

```bash
ANTHROPIC_API_KEY=sk-ant-your-api-key
```

---

## 📈 Model Comparison

| Model | Speed | Quality | Cost | Best For |
|-------|-------|---------|------|----------|
| Haiku | ⚡⚡⚡ Fast | ⭐⭐⭐ Good | $ Low | Real-time alerts |
| Sonnet | ⚡⚡ Medium | ⭐⭐⭐⭐ Better | $$ Medium | Balanced |
| Opus | ⚡ Slower | ⭐⭐⭐⭐⭐ Best | $$$ High | Complex analysis |

**Recommendation:** Start with Haiku for real-time context cards. Use Sonnet or Opus for postmortem generation.

---

## 🎯 Accuracy Tips

### Better Logs = Better Analysis

The AI works best with structured logs:

✅ **Good:**
```json
{
  "level": "error",
  "service": "payments",
  "message": "Connection timeout",
  "target": "stripe-api",
  "duration_ms": 5000,
  "trace_id": "abc123"
}
```

❌ **Less Useful:**
```
Error occurred during processing
```

### Service Context

Include deployment info for better correlation:

```bash
# The AI sees recent commits
abc1234 by @sarah - Reduce timeout to 5s
def5678 by @mike - Update stripe SDK

# And can correlate with errors
"ConnectionTimeout" started after abc1234
```

---

## 🔒 Privacy & Security

### What Data is Sent

- Log messages (up to 100 entries)
- Service name
- Incident title and severity
- Recent commit messages (not code)

### What is NOT Sent

- Full source code
- API keys or secrets (should be masked in logs)
- User PII (if properly handled in logging)
- Database contents

### Anthropic's Data Policy

- Data is not used for training
- Processed transiently
- Enterprise-grade security

See [Anthropic's Security Documentation](https://www.anthropic.com/security) for details.

---

## 🐛 Troubleshooting

### "AI summary unavailable"

**Causes:**
1. No `ANTHROPIC_API_KEY` configured
2. No logs to analyze
3. API rate limit or error

**Solutions:**
- Verify API key is set
- Check logs are being fetched
- Review server logs for API errors

### Slow AI Responses

**Cause:** Large log volume or complex patterns

**Solutions:**
- Reduce log limit
- Use Haiku model for speed
- Pre-filter logs before sending

### Unhelpful Summaries

**Cause:** Logs lack context

**Solutions:**
- Add structured logging
- Include error codes and messages
- Ensure service names are consistent

### Rate Limiting

**Symptoms:** HTTP 429 errors

**Solutions:**
- Implement request queuing
- Use caching for repeated errors
- Contact Anthropic for higher limits

---

## 📊 Cost Estimation

### Per-Incident Cost (Haiku)

| Component | Tokens | Cost |
|-----------|--------|------|
| Input (logs + prompt) | ~2,000 | ~$0.0005 |
| Output (summary) | ~500 | ~$0.0003 |
| **Total per incident** | | **~$0.001** |

### Monthly Estimates

| Incidents/Month | Monthly Cost |
|-----------------|--------------|
| 100 | ~$0.10 |
| 1,000 | ~$1.00 |
| 10,000 | ~$10.00 |

*Costs are approximate and may vary based on log complexity.*

---

## 🔮 Advanced Features

### Custom Prompts (Future)

Configure organization-specific analysis:

```bash
# Future configuration
# AI_CUSTOM_PROMPT="Additionally, check for payment compliance issues..."
```

### Confidence Scores (Future)

AI will provide confidence levels:

```
Likely cause (85% confidence): Connection timeout
```

### Feedback Loop (Future)

Rate AI summaries to improve over time:

```
Was this summary helpful? 👍 👎
```

---

## 📚 Related Documentation

- [Context Cards](./context-cards.md) - Where AI summaries appear
- [Postmortems](./postmortems.md) - AI-generated post-incident reports
- [Similar Incidents](./similar-incidents.md) - AI-powered matching

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or open an issue on GitHub.*
