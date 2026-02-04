# 🔎 Splunk Integration

Splunk is an alternative log provider for Incident Copilot. It supports both Splunk Enterprise and Splunk Cloud deployments.

---

## 📋 Prerequisites

- [ ] Splunk Enterprise or Splunk Cloud account
- [ ] API access enabled on your Splunk instance
- [ ] Authentication token or username/password
- [ ] Services indexed with searchable fields

---

## 🔧 Step-by-Step Setup

### Step 1: Enable REST API Access

For **Splunk Enterprise:**
1. Ensure the REST API is accessible (default port: 8089)
2. Verify HTTPS is enabled for the management port

For **Splunk Cloud:**
1. Enable the REST API via your Splunk Cloud admin
2. Note your API endpoint URL

### Step 2: Create an Authentication Token (Recommended)

1. Log in to Splunk Web
2. Go to **Settings** → **Tokens** (or **User** → **Edit Tokens**)
3. Click **New Token**
4. Configure:

   | Setting | Value |
   |---------|-------|
   | **Token Name** | Incident Copilot |
   | **Audience** | API Access |
   | **Expiration** | Set appropriate expiry |

5. Click **Create**
6. ⚠️ **Copy the token value**

### Step 3: (Alternative) Use Username/Password

If tokens aren't available:
- Use a Splunk account with search capabilities
- Not recommended for production (use tokens instead)

### Step 4: Configure Environment Variables

```bash
# Splunk Configuration
LOG_PROVIDER=splunk
SPLUNK_URL=https://splunk.example.com:8089  # Include port!
SPLUNK_TOKEN=your-auth-token

# Or for username/password auth
# SPLUNK_USERNAME=your-username
# SPLUNK_PASSWORD=your-password

# Index mapping (optional)
SPLUNK_INDEX_MAP='{"payments-api": "payments_logs", "auth": "security_logs"}'
```

### Step 5: Restart Incident Copilot

```bash
docker-compose restart
```

---

## ✅ Testing the Integration

### Test API Access (Token Auth)

```bash
curl -k -H "Authorization: Bearer $SPLUNK_TOKEN" \
  "$SPLUNK_URL/services/server/info"
```

### Test API Access (Basic Auth)

```bash
curl -k -u "$SPLUNK_USERNAME:$SPLUNK_PASSWORD" \
  "$SPLUNK_URL/services/server/info"
```

**Expected:** XML response with server information.

### Test Search Query

```bash
curl -k -H "Authorization: Bearer $SPLUNK_TOKEN" \
  "$SPLUNK_URL/services/search/jobs" \
  -d "search=search index=main sourcetype=* | head 10" \
  -d "output_mode=json"
```

---

## 🔐 Required Permissions

### User/Token Capabilities

| Capability | Required | Purpose |
|------------|----------|---------|
| `search` | ✅ Yes | Execute searches |
| `list_indexes` | ⚡ Optional | Auto-discover indexes |
| `rest_properties_get` | ⚡ Optional | API metadata |

### Index Access

The user/token must have read access to relevant indexes.

---

## 🔑 Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `LOG_PROVIDER` | ✅ | Set to `splunk` | `splunk` |
| `SPLUNK_URL` | ✅ | Splunk REST API URL with port | `https://splunk:8089` |
| `SPLUNK_TOKEN` | ⚡ | Auth token (recommended) | `abc123...` |
| `SPLUNK_USERNAME` | ⚡ | Username (if no token) | `admin` |
| `SPLUNK_PASSWORD` | ⚡ | Password (if no token) | `secret` |
| `SPLUNK_INDEX_MAP` | ⚡ | Service to index mapping | `{"svc": "index"}` |

---

## 📂 Index Mapping

### Default Behavior

Without explicit mapping, Incident Copilot searches:
- Index: `main`
- Filter by `service` or `app` field

### Custom Mapping

Map services to specific indexes:

```bash
SPLUNK_INDEX_MAP='{
  "payments-api": "payments_logs",
  "auth-service": "security_logs",
  "frontend": "web_logs"
}'
```

---

## 📊 Search Query Configuration

### Default Search

Incident Copilot generates searches like:

```spl
index=payments_logs (ERROR OR WARN OR CRITICAL OR FATAL)
| where _time >= relative_time(now(), "-15m")
| head 100
```

### Field Requirements

For best results, ensure your logs include:
- `_time` - Timestamp
- `message` or `_raw` - Log message
- `level` or `severity` - Log level
- `service` or `app` - Service identifier

---

## 🔒 SSL/TLS Configuration

### Self-Signed Certificates

For self-signed certificates:

```bash
# Option 1: Provide CA bundle
SSL_CERT_FILE=/path/to/ca-bundle.crt

# Option 2: Disable verification (NOT recommended for production)
SPLUNK_VERIFY_SSL=false
```

### Splunk Cloud

Splunk Cloud uses valid certificates by default. No special configuration needed.

---

## 🐛 Troubleshooting

### "Connection Refused"

**Symptoms:** Cannot connect to Splunk URL

**Checks:**
1. Verify URL includes port (usually 8089)
2. Check Splunk management port is accessible
3. Verify firewall allows traffic

**Solutions:**
- Use correct URL format: `https://splunk.example.com:8089`
- Check network connectivity
- Verify Splunk is running

### "Unauthorized" Error

**Symptoms:** HTTP 401/403 responses

**Checks:**
```bash
# Test authentication
curl -k -u "$SPLUNK_USERNAME:$SPLUNK_PASSWORD" \
  "$SPLUNK_URL/services/authentication/current-context"
```

**Solutions:**
- Verify token or credentials
- Check token hasn't expired
- Ensure user has search capabilities

### "No Results Found"

**Symptoms:** Context cards show no logs

**Checks:**
1. Verify index name is correct
2. Test search manually in Splunk Web
3. Check time range has data

**Solutions:**
- Update `SPLUNK_INDEX_MAP` with correct indexes
- Verify service field naming in logs
- Check log ingestion pipeline

### SSL Certificate Errors

**Symptoms:** SSL verification failures

**Solutions:**
- Provide CA certificate file
- Update certificates on Splunk server
- As last resort: `SPLUNK_VERIFY_SSL=false`

---

## 📚 Additional Resources

- [Splunk REST API Reference](https://docs.splunk.com/Documentation/Splunk/latest/RESTREF/RESTprolog)
- [Splunk Authentication Tokens](https://docs.splunk.com/Documentation/Splunk/latest/Security/Setupauthenticationwithtokens)
- [Splunk Search Tutorial](https://docs.splunk.com/Documentation/Splunk/latest/SearchTutorial)
- [Datadog Integration](./datadog.md) (alternative)
- [CloudWatch Integration](./cloudwatch.md) (alternative)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or open an issue on GitHub.*
