# 🔍 Similar Incidents

Find past incidents similar to the current one, helping you resolve issues faster.

---

## 📋 How It Works

1. **Embedding** — Incident description converted to vector
2. **Search** — Find similar vectors in past incidents
3. **Ranking** — Return top matches by similarity score

---

## 📊 Example Output

```
🔍 Similar Past Incidents:

1. Stripe API Timeout (2024-01-10) — 92% match
   Resolution: Stripe was experiencing an outage.
   Waited for recovery.

2. Payment Gateway Errors (2024-01-05) — 78% match
   Resolution: Rate limit exceeded. Implemented
   exponential backoff.
```

---

## ⚙️ Configuration

### Enable Similarity Search

```bash
# Requires OpenAI API key for embeddings
OPENAI_API_KEY=sk-xxx
SIMILAR_INCIDENTS_ENABLED=true
SIMILAR_INCIDENTS_THRESHOLD=0.7  # Minimum similarity
SIMILAR_INCIDENTS_LIMIT=3  # Max results
```

---

## 🔧 API Access

```bash
GET /api/correlation/similar?incident_id=inc_123

Response:
{
  "similar_incidents": [
    {
      "incident_id": "inc_100",
      "similarity_score": 0.92,
      "title": "Stripe API Timeout",
      "resolution_notes": "Stripe outage..."
    }
  ]
}
```

---

## 📚 Related Documentation

- [Context Cards](./context-cards.md)
- [AI Analysis](./ai-analysis.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
