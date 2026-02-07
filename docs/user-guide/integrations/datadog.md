# 📊 Datadog Integration

Datadog integration enables Incident Copilot to fetch error logs and metrics when incidents occur, providing valuable context for troubleshooting.

---

## Overview

| Feature | Status |
|---------|--------|
| Log fetching | ✅ Supported |
| Error filtering | ✅ Supported |
| Time-range queries | ✅ Supported |
| Service filtering | ✅ Supported |
| Multi-region | ✅ Supported |

---

## What It Provides

When an incident fires, Incident Copilot fetches from Datadog:

- **Recent error logs** - Errors from the last 15 minutes
- **Warning logs** - Warnings if configured
- **Log counts** - Frequency of each error type
- **AI summary** - Intelligent analysis of error patterns

Example context card section:
```
📋 Log Analysis:
• ConnectionTimeout to stripe-api (847x)
• Retry limit exceeded (612x)
• Payment validation failed (89x)

💡 AI Summary:
The service is experiencing timeouts when connecting to Stripe's
payment API. This correlates with the recent deployment that 
modified retry logic. Consider rolling back commit abc1234.
```

---

## Prerequisites

- Datadog account
- API Key and Application Key
- Logs indexed for your services (with `service` tag)

---

## 🔧 Setup

### Step 1: Create API Key

1. Log in to Datadog
2. Go to **Organization Settings** → **API Keys**
3. Click **+ New Key**
4. Name it `Incident Copilot`
5. Copy the key

### Step 2: Create Application Key

1. Go to **Organization Settings** → **Application Keys**
2. Click **+ New Key**
3. Name it `Incident Copilot`
4. Copy the key

### Step 3: Configure

Add to your `.env`:
```bash
LOG_PROVIDER=datadog
DATADOG_API_KEY=your-api-key
DATADOG_APP_KEY=your-application-key
DATADOG_SITE=datadoghq.com
```

### Regional Sites

| Region | Site Value |
|--------|------------|
| US1 (default) | `datadoghq.com` |
| US3 | `us3.datadoghq.com` |
| US5 | `us5.datadoghq.com` |
| EU | `datadoghq.eu` |
| AP1 | `ap1.datadoghq.com` |
| US1-FED | `ddog-gov.com` |

---

## ⚙️ Configuration Options

### Basic Configuration

```bash
LOG_PROVIDER=datadog
DATADOG_API_KEY=xxxx
DATADOG_APP_KEY=xxxx
DATADOG_SITE=datadoghq.com
```

### Advanced Configuration

```bash
# Time range for log queries (default: 15 minutes)
DATADOG_LOG_TIME_RANGE_MINUTES=15

# Maximum logs to fetch (default: 100)
DATADOG_MAX_LOGS=100

# Log levels to include (default: error,warn)
DATADOG_LOG_LEVELS=error,warn,critical

# Additional query filters
DATADOG_EXTRA_QUERY_FILTER="env:production"
```

---

## 🏷️ Service Tagging

Incident Copilot matches logs using the `service` tag in Datadog.

### Ensure Proper Tagging

Your logs should have a `service` tag that matches your PagerDuty service name:

```
service:payments-api
```

### Custom Mapping

If your Datadog service tags differ from PagerDuty names:

```bash
DATADOG_SERVICE_MAP='{
  "payments-api": "payments",
  "auth-service": "authentication",
  "checkout": "checkout-svc"
}'
```

---

## 📝 Query Customization

### Default Query

By default, Incident Copilot queries:
```
service:{service_name} status:(error OR warn)
```

### Custom Queries per Service

Define custom queries for specific services:

```bash
DATADOG_CUSTOM_QUERIES='{
  "payments-api": "service:payments @payment.status:failed",
  "auth-service": "service:auth @auth.result:failure"
}'
```

### Adding Environment Filters

Include only production logs:
```bash
DATADOG_EXTRA_QUERY_FILTER="env:production"
```

---

## 🔐 Required Permissions

The API key needs these permissions:
- **Logs**: `logs_read_data`
- **Metrics** (optional): `metrics_read`

### Create a Restricted Key

For better security, create a restricted API key:

1. Go to **Organization Settings** → **API Keys**
2. Click **+ New Key**
3. Enable **Key Restrictions**
4. Allow only:
   - `logs_read_data` 
   - `logs_read_index_data`

---

## ✅ Testing

### Validate Configuration

```bash
incident-copilot validate
```

### Test Datadog Connection

```bash
incident-copilot test-integration datadog
```

### Test Log Query

```bash
# Using curl
curl -X POST "https://api.datadoghq.com/api/v2/logs/events/search" \
  -H "DD-API-KEY: $DATADOG_API_KEY" \
  -H "DD-APPLICATION-KEY: $DATADOG_APP_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "filter": {
      "query": "service:YOUR_SERVICE status:error",
      "from": "now-15m",
      "to": "now"
    },
    "page": {
      "limit": 10
    }
  }'
```

### Verify API Key

```bash
curl -X GET "https://api.datadoghq.com/api/v1/validate" \
  -H "DD-API-KEY: $DATADOG_API_KEY" \
  -H "DD-APPLICATION-KEY: $DATADOG_APP_KEY"
```

---

## 🐛 Troubleshooting

### "403 Forbidden" Error

**Causes**:
- Invalid API key
- Key doesn't have required permissions

**Solutions**:
1. Regenerate API and App keys
2. Verify keys have `logs_read_data` permission
3. Check you're using the correct regional site

### No Logs Returned

**Causes**:
- No logs in time range
- Service tag doesn't match
- Logs not indexed

**Solutions**:
1. Verify logs exist in Datadog UI with the same query
2. Check `service` tag matches PagerDuty service name
3. Verify logs are indexed (not just archived)
4. Extend time range: `DATADOG_LOG_TIME_RANGE_MINUTES=30`

### Wrong Datadog Site

**Symptoms**:
- Connection timeouts
- 404 errors

**Solution**: Check your Datadog account's region and set `DATADOG_SITE` accordingly.

### Rate Limiting

**Symptoms**:
- 429 errors
- Slow log fetching

**Solutions**:
1. Reduce `DATADOG_MAX_LOGS`
2. Enable caching with Redis
3. Contact Datadog for higher limits

---

## 📈 Best Practices

### 1. Ensure Consistent Tagging

Use the same service names across:
- PagerDuty services
- Datadog `service` tag
- GitHub repository names (or use mapping)

### 2. Index Important Logs

Ensure error and warning logs are indexed, not just archived.

### 3. Use Environment Tags

Filter to production only:
```bash
DATADOG_EXTRA_QUERY_FILTER="env:production"
```

### 4. Set Reasonable Limits

Balance detail vs. performance:
```bash
DATADOG_MAX_LOGS=100
DATADOG_LOG_TIME_RANGE_MINUTES=15
```

---

## 📚 Related Documentation

- [CloudWatch Integration](./cloudwatch.md) - Alternative log provider
- [Splunk Integration](./splunk.md) - Enterprise log provider
- [AI Analysis](../features/ai-analysis.md) - How logs are summarized
- [Configuration Reference](../configuration.md) - All config options
- [Troubleshooting](../troubleshooting.md) - General troubleshooting

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or [FAQ](../faq.md).*
