# 📈 Analytics & Metrics

Track MTTR and incident metrics to improve your incident response.

---

## 🎯 Key Metrics

### MTTR (Mean Time to Resolve)
```
MTTR = Σ(resolved_at - triggered_at) / incident_count
```

### TTA (Time to Acknowledge)
```
TTA = acknowledged_at - triggered_at
```

### TTC (Time to Context)
```
TTC = context_delivered_at - triggered_at
```
Target: <10 seconds

---

## 📊 API Endpoints

### Get MTTR Stats

```bash
GET /api/analytics/mttr?days=30

Response:
{
  "mean_mttr_seconds": 1380,
  "median_mttr_seconds": 1200,
  "p90_mttr_seconds": 2400,
  "incidents_count": 47
}
```

### Compare Periods

```bash
GET /api/analytics/mttr/compare?days=30

Response:
{
  "mttr_change_percent": -14.8,
  "trend": "improving"
}
```

---

## 🎯 Benchmarks

| Metric | Good | Better | Best |
|--------|------|--------|------|
| MTTR (Critical) | <1 hr | <30 min | <15 min |
| TTA (Critical) | <10 min | <5 min | <2 min |
| TTC | <30 sec | <15 sec | <10 sec |

---

## 📚 Related Documentation

- [Scheduled Reports](./scheduled-reports.md)
- [API Reference](../api-reference.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
