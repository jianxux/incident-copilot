# 🔍 Similar Incidents

Incident Copilot can find similar past incidents to help engineers quickly identify patterns and apply learnings from previous resolutions.

---

## 🎯 What is Similarity Matching?

When an incident fires, the system searches for similar past incidents:

```
🔍 Similar Past Incidents
• Stripe API outage (Jan 10, 2025) - 92% match
  └─ Root cause: Third-party outage
  └─ Resolution: Waited for Stripe to resolve
  
• Payment gateway timeout (Dec 15, 2024) - 78% match
  └─ Root cause: Connection pool exhaustion
  └─ Resolution: Increased pool size to 50
```

This helps engineers:
- **Recognize patterns** from past issues
- **Apply known solutions** faster
- **Avoid reinvestigating** the same problems
- **Reduce MTTR** through historical context

---

## 🧠 How It Works

### Vector Embeddings

Incidents are converted to numerical vectors that capture semantic meaning:

```
┌─────────────────┐        ┌─────────────────┐
│ "High error     │        │                 │
│  rate in        │───────▶│  [0.23, -0.15,  │
│  payments-api"  │ OpenAI │   0.87, ...]    │
└─────────────────┘ embed  └─────────────────┘
        Text              1536-dim vector
```

### Cosine Similarity

Past incidents are ranked by similarity:

```
Similarity = cos(current_incident, past_incident)

Where:
- 1.0 = Identical
- 0.7+ = Very similar
- 0.5+ = Somewhat similar
- <0.5 = Different
```

### Matching Process

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
│   Current    │     │    Generate      │     │    Search    │
│   Incident   │────▶│    Embedding     │────▶│   Vector DB  │
└──────────────┘     └──────────────────┘     └──────┬───────┘
                                                     │
                                                     ▼
┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
│   Display    │◀────│   Rank by        │◀────│   Compare    │
│   Top 3      │     │   Similarity     │     │   Vectors    │
└──────────────┘     └──────────────────┘     └──────────────┘
```

---

## 📊 What Gets Matched

The similarity calculation considers:

| Factor | Weight | Description |
|--------|--------|-------------|
| **Title** | High | Incident title/summary |
| **Service** | Medium | Affected service name |
| **Error Patterns** | High | Top error types from logs |
| **Description** | Medium | Additional context |

### Example Matching

Current incident:
```
Title: "High error rate in payments-api"
Service: payments-api
Errors: ConnectionTimeout to stripe-api
```

Matches with:
```
Past Incident 1: "Payment service timeout errors" - 92%
Past Incident 2: "Stripe API connectivity issues" - 87%
Past Incident 3: "Checkout failing with timeouts" - 74%
```

---

## ⚙️ Configuration

### Enable Similarity Search

Requires an OpenAI API key for embeddings:

```bash
OPENAI_API_KEY=sk-your-openai-api-key
```

### Database Path

```bash
# SQLite database for storing incidents
SIMILARITY_DB_PATH=data/incidents.db
```

### Threshold Configuration

```bash
# Minimum similarity score to show (0.0 - 1.0)
# Default: 0.5 (50%)
# SIMILARITY_THRESHOLD=0.5

# Maximum results to show
# Default: 3
# SIMILARITY_MAX_RESULTS=3
```

---

## 📂 Incident Storage

### What Gets Stored

For each incident:

| Field | Description |
|-------|-------------|
| `incident_id` | Unique identifier |
| `title` | Incident title |
| `service` | Service name |
| `description` | Full description |
| `embedding` | 1536-dimension vector |
| `occurred_at` | Timestamp |
| `root_cause` | Root cause (if resolved) |
| `resolution` | How it was fixed |

### Storage Location

Default: `data/incidents.db` (SQLite)

For production, consider:
- PostgreSQL with pgvector extension
- Pinecone or Weaviate for larger scale

---

## 🔄 Building History

### Automatic Storage

Each incident is automatically stored when:
1. An alert webhook is received
2. Context card is generated
3. Embedding is created from available context

### Manual Import

Import historical incidents:

```bash
# Future feature
python -m incident_copilot.cli import-incidents \
  --source pagerduty \
  --days 90
```

### Enriching Past Incidents

Add root causes and resolutions to improve matching:

```bash
POST /api/incidents/{id}
{
  "root_cause": "Third-party API outage",
  "resolution": "Waited for upstream to resolve"
}
```

---

## 📱 Display Formats

### In Context Cards

```
🔍 Similar Past Incidents
• Stripe outage (Jan 10) - 92% match
• Gateway timeout (Dec 15) - 78% match
```

### In Postmortems

```markdown
## Similar Past Incidents

| Date | Title | Similarity | Root Cause |
|------|-------|------------|------------|
| Jan 10 | Stripe outage | 92% | Third-party |
| Dec 15 | Gateway timeout | 78% | Pool exhaustion |
```

### Via API

```bash
GET /api/incidents/{id}/similar

Response:
{
  "similar_incidents": [
    {
      "incident_id": "inc-456",
      "title": "Stripe API outage",
      "similarity_score": 92.3,
      "occurred_at": "2025-01-10T...",
      "root_cause": "Third-party outage"
    }
  ]
}
```

---

## 🎯 Best Practices

### Improve Match Quality

1. **Use consistent naming** for services
2. **Add detailed descriptions** to incidents
3. **Document root causes** after resolution
4. **Include error patterns** in descriptions

### Review and Refine

Periodically review matched incidents:
- Are the matches helpful?
- Update incorrect root causes
- Remove noise/false positives

### Build History

The more historical data, the better:
- Import past incidents from PagerDuty/Opsgenie
- Document major incidents thoroughly
- Track resolutions for future reference

---

## 🐛 Troubleshooting

### "Similar incidents unavailable"

**Causes:**
1. No `OPENAI_API_KEY` configured
2. No historical incidents stored
3. Embedding generation failed

**Solutions:**
- Configure OpenAI API key
- Import historical incidents
- Check server logs for errors

### Poor Match Quality

**Causes:**
- Limited historical data
- Inconsistent service naming
- Missing context

**Solutions:**
- Import more historical incidents
- Standardize service names
- Add detailed descriptions

### "No similar incidents found"

**Causes:**
- Genuinely novel incident
- Threshold too high
- No matching service

**Solutions:**
- This might be expected for new issues
- Lower similarity threshold
- Check service name matches history

---

## 📊 Cost Estimation

### OpenAI Embedding Costs

| Component | Tokens | Cost |
|-----------|--------|------|
| Per incident embedding | ~500 | ~$0.00001 |
| Search query | ~500 | ~$0.00001 |

**Monthly estimate** (1,000 incidents): ~$0.02

---

## 📚 Related Documentation

- [Context Cards](./context-cards.md) - Where matches appear
- [Postmortems](./postmortems.md) - Historical analysis
- [Analytics](./analytics.md) - Pattern tracking

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or open an issue on GitHub.*
