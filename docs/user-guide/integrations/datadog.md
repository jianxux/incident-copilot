# 📊 Datadog Integration

Fetch error logs and metrics from Datadog.

---

## 🔧 Setup

### Create API Keys

1. Go to **Organization Settings** → **API Keys**
2. Create API key
3. Go to **Application Keys** and create app key
4. Add to `.env`:
   ```bash
   LOG_PROVIDER=datadog
   DATADOG_API_KEY=your-api-key
   DATADOG_APP_KEY=your-app-key
   DATADOG_SITE=datadoghq.com  # or datadoghq.eu
   ```

---

## 🔍 Log Query Configuration

```bash
DATADOG_LOG_QUERY="service:{service} status:error"
DATADOG_LOG_LOOKBACK_MINUTES=15
DATADOG_LOG_LIMIT=100
```

---

## ✅ Testing

```bash
incident-copilot test-integration datadog
```

---

## 📚 Related Documentation

- [CloudWatch Integration](./cloudwatch.md)
- [Splunk Integration](./splunk.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
