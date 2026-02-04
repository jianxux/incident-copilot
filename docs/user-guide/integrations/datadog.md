# 📊 Datadog Integration

Datadog is the default log provider for Incident Copilot. When incidents fire, error logs are fetched from Datadog and summarized by AI.

---

## 📋 Prerequisites

- [ ] Datadog account with access to logs
- [ ] Permission to create API and Application keys
- [ ] Services tagged with the `service` tag in Datadog

---

## 🔧 Step-by-Step Setup

### Step 1: Create an API Key

1. Log in to Datadog
2. Go to **Organization Settings** → **API Keys**

   ```
   ┌─────────────────────────────────────────┐
   │  Datadog                                │
   │  ├── Dashboards                         │
   │  ├── Logs                               │
   │  └── Organization Settings              │
   │      ├── API Keys  ◄──                  │
   │      └── Application Keys               │
   └─────────────────────────────────────────┘
   ```

3. Click **+ New Key**
4. Name: `Incident Copilot`
5. ⚠️ **Copy the API Key**

### Step 2: Create an Application Key

1. Go to **Organization Settings** → **Application Keys**
2. Click **+ New Key**
3. Name: `Incident Copilot`
4. ⚠️ **Copy the Application Key**

### Step 3: Configure Environment Variables

```bash
# Datadog Configuration
LOG_PROVIDER=datadog
DATADOG_API_KEY=your-api-key
DATADOG_APP_KEY=your-application-key
DATADOG_SITE=datadoghq.com  # See site options below
```

### Step 4: Restart Incident Copilot

```bash
docker-compose restart
```

---

## ✅ Testing the Integration

### Verify API Keys

```bash
curl -X GET "https://api.datadoghq.com/api/v1/validate" \
  -H "DD-API-KEY: $DATADOG_API_KEY" \
  -H "DD-APPLICATION-KEY: $DATADOG_APP_KEY"
```

**Expected:** `{"valid": true}`

### Test Log Query

```bash
curl -X POST "https://api.datadoghq.com/api/v2/logs/events/search" \
  -H "DD-API-KEY: $DATADOG_API_KEY" \
  -H "DD-APPLICATION-KEY: $DATADOG_APP_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "filter": {
      "query": "service:your-service status:error",
      "from": "now-15m",
      "to": "now"
    },
    "page": {"limit": 10}
  }'
```

**Expected:** List of log entries (or empty if no errors).

---

## 🔐 Required Permissions

### API Key

- Automatically has access to ingest data
- Can validate API connection

### Application Key

The Application Key needs these scopes:

| Scope | Required | Purpose |
|-------|----------|---------|
| `logs_read_data` | ✅ Yes | Query log entries |
| `metrics_read` | ⚡ Optional | Fetch metrics (error rate, latency) |
| `apm_service_read` | ⚡ Optional | APM trace data |

---

## 🔑 Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `LOG_PROVIDER` | ✅ | Set to `datadog` | `datadog` |
| `DATADOG_API_KEY` | ✅ | Datadog API key | `abc123...` |
| `DATADOG_APP_KEY` | ✅ | Datadog Application key | `def456...` |
| `DATADOG_SITE` | ⚡ Recommended | Datadog site/region | `datadoghq.com` |

---

## 🌍 Datadog Sites

Choose the site based on your Datadog account region:

| Site | Variable Value | Region |
|------|----------------|--------|
| US1 (default) | `datadoghq.com` | US |
| US3 | `us3.datadoghq.com` | US |
| US5 | `us5.datadoghq.com` | US |
| EU1 | `datadoghq.eu` | EU |
| AP1 | `ap1.datadoghq.com` | Asia-Pacific |
| US1-FED | `ddog-gov.com` | US Government |

**How to find your site:**
- Check your Datadog URL: `app.datadoghq.com` = US1, `app.datadoghq.eu` = EU1

---

## 📊 Log Query Configuration

### Default Query

Incident Copilot queries logs using:

```
service:{service-name} status:(error OR warn)
```

### Time Range

- **Default:** Last 15 minutes
- Adjusts based on incident duration

### Log Limit

- Fetches up to **100 log entries**
- Most recent entries prioritized

---

## 🏷️ Service Tagging

For Incident Copilot to find your logs, services must be tagged:

### Using Unified Service Tagging

```yaml
# In your application or container config
DD_SERVICE: payments-api
DD_ENV: production
DD_VERSION: 1.2.3
```

### Log Example

```json
{
  "service": "payments-api",
  "status": "error",
  "message": "Connection timeout to Stripe API",
  "@timestamp": "2025-01-15T10:30:00Z"
}
```

### Verifying Tags

In Datadog Logs, run:
```
service:your-service-name
```

If no results, check your logging configuration.

---

## 📈 Metrics Integration (Optional)

Incident Copilot can also fetch metrics:

### Error Rate

```
avg:trace.http.request.errors{service:payments-api}.as_rate()
```

### Latency (P99)

```
percentile:trace.http.request.duration{service:payments-api}.p99
```

### Configuration

Metrics are fetched automatically if the Application Key has `metrics_read` scope.

---

## 🐛 Troubleshooting

### "Forbidden" Error

**Symptoms:** HTTP 403 when querying logs

**Cause:** Missing permissions on Application Key

**Solutions:**
1. Check Application Key scopes in Datadog
2. Regenerate key with `logs_read_data` scope
3. Verify you're using the Application Key (not API Key)

### "No logs found"

**Symptoms:** Context cards show no log data

**Checks:**
1. Verify service name matches:
   ```bash
   # In Datadog Logs explorer
   service:your-service-name status:error
   ```

2. Check time range has data

3. Ensure logs are being ingested

**Solutions:**
- Fix service tagging in your application
- Add mapping if names differ (see below)
- Verify log ingestion pipeline

### "Invalid API key"

**Symptoms:** HTTP 401/403 errors

**Checks:**
```bash
# Verify key format (typically 32 characters)
echo $DATADOG_API_KEY | wc -c
echo $DATADOG_APP_KEY | wc -c
```

**Solutions:**
- Regenerate API and Application keys
- Ensure keys are from the same Datadog organization
- Check for whitespace in `.env` file

### "Site mismatch"

**Symptoms:** Connection errors or invalid responses

**Cause:** Using wrong `DATADOG_SITE` for your account

**Solution:**
Check your Datadog URL and match the site:
```bash
# If your Datadog is at app.datadoghq.eu
DATADOG_SITE=datadoghq.eu
```

### Rate Limiting

**Symptoms:** HTTP 429 errors

**Info:** Datadog rate limits vary by plan and endpoint

**Solutions:**
- Implement caching (built-in)
- Reduce query frequency
- Contact Datadog support for limit increases

---

## 🔄 Service Name Mapping

If your PagerDuty/Opsgenie service names don't match Datadog:

```bash
# Service name mapping (same as GitHub mapping)
SERVICE_REPO_MAP='{
  "pagerduty-payments": "payments-api",
  "auth-alerts": "auth-service"
}'
```

This maps:
- Alert service name → Datadog service tag
- Alert service name → GitHub repository name

---

## 📚 Additional Resources

- [Datadog API Documentation](https://docs.datadoghq.com/api/)
- [Unified Service Tagging](https://docs.datadoghq.com/getting_started/tagging/unified_service_tagging/)
- [Log Management](https://docs.datadoghq.com/logs/)
- [CloudWatch Integration](./cloudwatch.md) (alternative)
- [Splunk Integration](./splunk.md) (alternative)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or open an issue on GitHub.*
