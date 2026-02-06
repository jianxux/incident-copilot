# 🤖 AI Analysis

Incident Copilot uses Claude (Anthropic) to analyze logs and generate actionable summaries.

---

## 📋 What AI Does

1. **Pattern Detection** — Identifies recurring error patterns
2. **Root Cause Hypothesis** — Suggests likely causes
3. **Correlation** — Links errors to recent changes
4. **Summarization** — Creates human-readable summary

---

## 📊 Example Output

```
📋 AI Analysis:

Top Error Patterns:
• ConnectionTimeout to stripe-api (847 occurrences)
• Retry limit exceeded after 3 attempts (612 occurrences)
• HTTP 503 from payment gateway (234 occurrences)

Summary:
The payments-api service is experiencing connection timeouts
when calling Stripe's API. The issue began at 02:45 AM,
approximately 10 minutes after deployment abc1234 which
modified retry logic. The previous similar incident on
2024-01-10 was resolved by Stripe fixing their API.

Likely Cause: External dependency (Stripe API) degradation
Confidence: High (based on error patterns and past incidents)
```

---

## ⚙️ Configuration

### Model Selection

```bash
# Faster, cheaper (default)
AI_MODEL=claude-3-haiku-20240307

# More capable
AI_MODEL=claude-3-opus-20240229
```

### Token Limits

```bash
AI_MAX_INPUT_TOKENS=10000  # Log excerpt limit
AI_MAX_OUTPUT_TOKENS=1000  # Summary length
```

### Disable AI

```bash
AI_ENABLED=false
```

---

## 💰 Cost Estimation

| Model | Cost per 1K tokens | ~Cost per incident |
|-------|-------------------|-------------------|
| Haiku | $0.00025 | ~$0.01 |
| Sonnet | $0.003 | ~$0.05 |
| Opus | $0.015 | ~$0.15 |

---

## 📚 Related Documentation

- [Context Cards](./context-cards.md)
- [Postmortems](./postmortems.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
