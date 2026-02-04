# 🔑 API Keys

API keys enable programmatic access to Incident Copilot for automation, integrations, and custom tooling.

---

## 🎯 When to Use API Keys

Use API keys for:
- **Automation scripts** - Trigger context cards programmatically
- **CI/CD integration** - Link deployments to incidents
- **Custom integrations** - Build your own tools
- **Monitoring dashboards** - Fetch analytics data
- **Backup/export** - Extract incident data

---

## 🔧 Creating API Keys

### Via Web UI

1. Go to **Settings** → **API Keys**
2. Click **Create API Key**
3. Configure:
   - **Name:** Descriptive name (e.g., "CI/CD Pipeline")
   - **Scopes:** Select permissions
   - **Expiration:** Optional expiry date
4. Click **Create**
5. ⚠️ **Copy the key immediately** - it won't be shown again!

### Via API

```bash
POST /api/api-keys
Authorization: Bearer <user-token>
Content-Type: application/json

{
  "name": "CI/CD Pipeline",
  "scopes": ["incidents:read", "incidents:write"],
  "expires_at": "2025-12-31T23:59:59Z"
}
```

**Response:**
```json
{
  "id": "key_abc123",
  "name": "CI/CD Pipeline",
  "key": "ic_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "scopes": ["incidents:read", "incidents:write"],
  "created_at": "2025-01-15T10:00:00Z",
  "expires_at": "2025-12-31T23:59:59Z",
  "last_used": null
}
```

⚠️ **Important:** The `key` field is only returned once at creation.

---

## 🔐 API Key Format

```
ic_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
│  │    └────────────────────────────────── 32 character random string
│  └──────────────────────────────────────── Environment (live/test)
└─────────────────────────────────────────── Prefix (ic = Incident Copilot)
```

Example: `ic_live_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6`

---

## 🔒 Scopes & Permissions

### Available Scopes

| Scope | Description |
|-------|-------------|
| `incidents:read` | View incidents and context cards |
| `incidents:write` | Create/update incidents |
| `postmortems:read` | View postmortems |
| `postmortems:write` | Create/edit postmortems |
| `analytics:read` | Access analytics data |
| `users:read` | View user information |
| `users:write` | Manage users (admin only) |
| `integrations:read` | View integration configs |
| `integrations:write` | Manage integrations (admin only) |

### Scope Examples

**Read-only dashboard:**
```json
{
  "scopes": ["incidents:read", "analytics:read"]
}
```

**CI/CD integration:**
```json
{
  "scopes": ["incidents:read", "incidents:write"]
}
```

**Full automation:**
```json
{
  "scopes": ["incidents:read", "incidents:write", "postmortems:write"]
}
```

---

## 📡 Using API Keys

### Authentication Header

Include the API key in the `Authorization` header:

```bash
curl -X GET "https://api.example.com/v1/incidents" \
  -H "Authorization: Bearer ic_live_your-api-key"
```

### Alternative: X-API-Key Header

```bash
curl -X GET "https://api.example.com/v1/incidents" \
  -H "X-API-Key: ic_live_your-api-key"
```

---

## 📊 API Examples

### List Incidents

```bash
curl -X GET "https://api.example.com/v1/incidents?limit=10" \
  -H "Authorization: Bearer ic_live_your-api-key"
```

### Create Incident (Manual Trigger)

```bash
curl -X POST "https://api.example.com/v1/incidents" \
  -H "Authorization: Bearer ic_live_your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "payments-api",
    "title": "High error rate detected",
    "severity": "high"
  }'
```

### Get Analytics

```bash
curl -X GET "https://api.example.com/v1/analytics/mttr?days=30" \
  -H "Authorization: Bearer ic_live_your-api-key"
```

---

## 🔄 Managing API Keys

### List API Keys

```bash
GET /api/api-keys

Response:
{
  "api_keys": [
    {
      "id": "key_abc123",
      "name": "CI/CD Pipeline",
      "scopes": ["incidents:read", "incidents:write"],
      "created_at": "2025-01-15T10:00:00Z",
      "last_used": "2025-01-16T14:30:00Z",
      "expires_at": "2025-12-31T23:59:59Z"
    }
  ]
}
```

Note: The actual key value is never shown after creation.

### Revoke API Key

```bash
DELETE /api/api-keys/{key_id}
```

Revocation is immediate - the key stops working instantly.

### Rotate API Key

To rotate a key:
1. Create a new key with the same scopes
2. Update your applications to use the new key
3. Verify the new key works
4. Revoke the old key

```bash
# 1. Create new key
POST /api/api-keys
{ "name": "CI/CD Pipeline (rotated)", "scopes": [...] }

# 2. Update applications with new key

# 3. Revoke old key
DELETE /api/api-keys/old_key_id
```

---

## ⏰ Expiration & Rotation

### Setting Expiration

```json
{
  "name": "Temporary access",
  "expires_at": "2025-03-01T00:00:00Z"
}
```

### Best Practices

| Key Type | Recommended Expiry |
|----------|-------------------|
| Production | 90-180 days |
| Development | 30 days |
| Temporary | As needed |
| CI/CD | 90 days |

### Expiration Alerts

Alerts are sent when keys are expiring:
- 30 days before: Email notification
- 7 days before: In-app warning
- Expired: Key stops working

---

## 📈 Rate Limits

API keys are subject to rate limiting:

### Default Limits

| Scope | Limit | Window |
|-------|-------|--------|
| Per API key | 1,000 requests | Per minute |
| Per tenant | 5,000 requests | Per minute |
| Per endpoint | Varies | See docs |

### Rate Limit Headers

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 950
X-RateLimit-Reset: 1642291200
```

### Handling Rate Limits

```bash
# When rate limited, you'll receive:
HTTP 429 Too Many Requests

{
  "error": "rate_limit_exceeded",
  "message": "Rate limit exceeded. Retry after 60 seconds.",
  "retry_after": 60
}
```

Implement exponential backoff:
```python
import time

def api_call_with_retry(url, max_retries=3):
    for attempt in range(max_retries):
        response = requests.get(url, headers=headers)
        if response.status_code == 429:
            wait = int(response.headers.get('Retry-After', 60))
            time.sleep(wait * (2 ** attempt))
        else:
            return response
```

---

## 🔒 Security Best Practices

### Do's ✅

- Store keys in environment variables or secrets managers
- Use minimum required scopes
- Set expiration dates
- Rotate keys regularly (every 90 days)
- Monitor key usage
- Use different keys for different purposes

### Don'ts ❌

- Never commit keys to source control
- Don't share keys between environments
- Don't use production keys in development
- Never log API keys
- Don't embed keys in client-side code

### Example: Secure Key Storage

```bash
# Environment variable
export INCIDENT_COPILOT_API_KEY=ic_live_xxx

# AWS Secrets Manager
aws secretsmanager get-secret-value --secret-id incident-copilot/api-key

# HashiCorp Vault
vault kv get secret/incident-copilot/api-key
```

---

## 📊 Monitoring Key Usage

### View Key Activity

```bash
GET /api/api-keys/{key_id}/activity?days=7

Response:
{
  "key_id": "key_abc123",
  "requests_last_7_days": 1234,
  "endpoints_used": [
    { "endpoint": "/v1/incidents", "count": 800 },
    { "endpoint": "/v1/analytics", "count": 434 }
  ],
  "last_used": "2025-01-16T14:30:00Z"
}
```

### Audit Logs

All API key usage is logged:

```bash
GET /api/audit?type=api_key&key_id=key_abc123

Response:
{
  "events": [
    {
      "timestamp": "2025-01-16T14:30:00Z",
      "key_id": "key_abc123",
      "endpoint": "/v1/incidents",
      "method": "GET",
      "ip_address": "192.168.1.1",
      "response_code": 200
    }
  ]
}
```

---

## 🐛 Troubleshooting

### "Invalid API key"

**Causes:**
- Key doesn't exist
- Key was revoked
- Typo in key

**Solutions:**
- Verify key is correct
- Check key hasn't been revoked
- Create a new key

### "Insufficient permissions"

**Cause:** Key doesn't have required scope

**Solution:**
- Check endpoint's required scope
- Create key with appropriate scopes

### "API key expired"

**Cause:** Key past expiration date

**Solution:**
- Create a new key
- Update applications with new key

### "Rate limit exceeded"

**Solution:**
- Implement exponential backoff
- Reduce request frequency
- Contact support for higher limits

---

## 📚 Related Documentation

- [User Management](./user-management.md) - User authentication
- [Tenant Setup](./tenant-setup.md) - Tenant-level keys
- [Billing](./billing.md) - API access by plan

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or open an issue on GitHub.*
