# Error Codes and Troubleshooting

This document provides a comprehensive reference for error codes, common issues, and troubleshooting guidance.

---

## HTTP Status Codes

### Success Codes

| Code | Name | Description |
|------|------|-------------|
| 200 | OK | Request succeeded |
| 201 | Created | Resource created successfully |
| 204 | No Content | Request succeeded, no response body |

### Client Error Codes

| Code | Name | Description |
|------|------|-------------|
| 400 | Bad Request | Invalid request syntax or parameters |
| 401 | Unauthorized | Authentication required or failed |
| 403 | Forbidden | Authenticated but not authorized |
| 404 | Not Found | Resource doesn't exist |
| 409 | Conflict | Resource already exists |
| 422 | Unprocessable Entity | Valid syntax but invalid data |
| 429 | Too Many Requests | Rate limit exceeded |

### Server Error Codes

| Code | Name | Description |
|------|------|-------------|
| 500 | Internal Server Error | Unexpected server error |
| 502 | Bad Gateway | Upstream service error |
| 503 | Service Unavailable | Service temporarily down |
| 504 | Gateway Timeout | Upstream service timeout |

---

## Error Response Format

### Standard Error Response

```json
{
  "detail": "Human-readable error message"
}
```

### Error with Code

```json
{
  "detail": "Human-readable error message",
  "code": "error_code"
}
```

### Validation Error Response (422)

```json
{
  "detail": [
    {
      "loc": ["body", "field_name"],
      "msg": "field required",
      "type": "value_error.missing"
    },
    {
      "loc": ["body", "email"],
      "msg": "value is not a valid email address",
      "type": "value_error.email"
    }
  ]
}
```

### Rate Limit Error Response (429)

```json
{
  "detail": "Rate limit exceeded",
  "retry_after": 30
}
```

**Headers:**

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1640995200
Retry-After: 30
```

---

## Error Codes Reference

### Authentication Errors

| Code | HTTP Status | Description | Solution |
|------|-------------|-------------|----------|
| `auth_required` | 401 | No authentication provided | Include `Authorization` header |
| `invalid_token` | 401 | Token is invalid or malformed | Verify token format |
| `token_expired` | 401 | Access token has expired | Refresh the token |
| `refresh_token_expired` | 401 | Refresh token has expired | Re-authenticate |
| `invalid_credentials` | 401 | Wrong email or password | Check credentials |
| `account_disabled` | 403 | Account has been disabled | Contact support |
| `insufficient_permissions` | 403 | User lacks required permissions | Request appropriate role |

### Authorization Errors

| Code | HTTP Status | Description | Solution |
|------|-------------|-------------|----------|
| `forbidden` | 403 | Action not allowed for user | Check user permissions |
| `owner_required` | 403 | Only tenant owner can perform action | Contact tenant owner |
| `admin_required` | 403 | Admin role required | Request admin access |
| `wrong_tenant` | 403 | Resource belongs to different tenant | Verify tenant context |

### Resource Errors

| Code | HTTP Status | Description | Solution |
|------|-------------|-------------|----------|
| `not_found` | 404 | Resource doesn't exist | Verify resource ID |
| `incident_not_found` | 404 | Incident doesn't exist | Check incident ID |
| `postmortem_not_found` | 404 | Postmortem doesn't exist | Generate postmortem first |
| `user_not_found` | 404 | User doesn't exist | Check user ID |
| `tenant_not_found` | 404 | Tenant doesn't exist | Check tenant ID |
| `already_exists` | 409 | Resource already exists | Use existing resource or update |
| `conflict` | 409 | Operation conflicts with current state | Resolve conflict |

### Validation Errors

| Code | HTTP Status | Description | Solution |
|------|-------------|-------------|----------|
| `validation_error` | 422 | Request data validation failed | Check request body |
| `invalid_email` | 422 | Email format invalid | Provide valid email |
| `invalid_date` | 422 | Date format invalid | Use ISO 8601 format |
| `invalid_severity` | 422 | Unknown severity level | Use: critical, high, medium, low, info |
| `field_required` | 422 | Required field missing | Include required field |
| `field_too_long` | 422 | Field exceeds max length | Shorten field value |
| `invalid_status_transition` | 400 | Invalid status change | Follow allowed transitions |

### Rate Limit Errors

| Code | HTTP Status | Description | Solution |
|------|-------------|-------------|----------|
| `rate_limited` | 429 | Too many requests | Wait and retry with backoff |
| `tenant_rate_limited` | 429 | Tenant limit exceeded | Contact support for increase |
| `ip_rate_limited` | 429 | IP address limit exceeded | Wait or use different IP |

### Integration Errors

| Code | HTTP Status | Description | Solution |
|------|-------------|-------------|----------|
| `webhook_signature_invalid` | 401 | Webhook signature verification failed | Check webhook secret |
| `integration_not_configured` | 503 | Required integration not set up | Configure integration |
| `external_service_error` | 502 | External API returned error | Check external service status |
| `external_service_timeout` | 504 | External API timed out | Retry request |

### Billing Errors

| Code | HTTP Status | Description | Solution |
|------|-------------|-------------|----------|
| `billing_not_configured` | 501 | Stripe not configured | Contact administrator |
| `no_billing_account` | 400 | No Stripe customer exists | Complete billing setup |
| `invalid_plan` | 400 | Unknown plan tier | Check available plans |
| `plan_limit_exceeded` | 403 | Usage exceeds plan limit | Upgrade plan |
| `payment_required` | 402 | Payment method required | Add payment method |

### SSO Errors

| Code | HTTP Status | Description | Solution |
|------|-------------|-------------|----------|
| `sso_not_enabled` | 400 | SSO not enabled for tenant | Enable SSO first |
| `idp_not_found` | 404 | Identity provider not found | Check IdP configuration |
| `sso_session_expired` | 400 | SSO session expired | Restart SSO flow |
| `sso_validation_error` | 400 | SSO response validation failed | Check IdP configuration |
| `sso_denied` | 400 | User denied SSO consent | Retry and approve |

### Internal Errors

| Code | HTTP Status | Description | Solution |
|------|-------------|-------------|----------|
| `internal_error` | 500 | Unexpected server error | Report to support |
| `database_error` | 500 | Database operation failed | Retry request |
| `service_unavailable` | 503 | Service temporarily unavailable | Retry later |

---

## Common Issues and Solutions

### Authentication Issues

#### "Invalid token" error

**Cause:** The access token is malformed, corrupted, or from a different environment.

**Solution:**
1. Verify the token is complete (no truncation)
2. Check you're using the correct environment (prod vs staging)
3. Ensure the token is from the correct `Authorization: Bearer <token>` format
4. Try refreshing or re-authenticating

#### Token expires too quickly

**Cause:** Access tokens expire after 24 hours by default.

**Solution:**
```python
# Implement token refresh logic
def get_valid_token():
    if is_token_expired(access_token):
        new_tokens = refresh_token(refresh_token)
        save_tokens(new_tokens)
        return new_tokens["access_token"]
    return access_token
```

#### OAuth callback fails

**Cause:** OAuth state mismatch or callback URL misconfiguration.

**Solution:**
1. Verify redirect URI matches exactly (including trailing slash)
2. Ensure OAuth state is preserved across redirect
3. Check browser cookies are enabled
4. Verify OAuth provider configuration

### Rate Limiting Issues

#### Getting rate limited frequently

**Solution:**
1. Implement exponential backoff
2. Cache responses where possible
3. Use webhooks instead of polling
4. Request a rate limit increase for production

```python
import time
import random

def exponential_backoff(attempt, base_delay=1, max_delay=60):
    delay = min(base_delay * (2 ** attempt), max_delay)
    jitter = random.uniform(0, delay * 0.1)
    return delay + jitter

def request_with_backoff(func, max_attempts=5):
    for attempt in range(max_attempts):
        try:
            return func()
        except RateLimitError as e:
            if attempt == max_attempts - 1:
                raise
            delay = exponential_backoff(attempt)
            time.sleep(delay)
```

### Webhook Issues

#### Webhook signature verification fails

**Cause:** Incorrect webhook secret or signature calculation.

**Solution:**
1. Verify the webhook secret matches (no extra whitespace)
2. Use the raw request body for signature verification
3. Ensure proper HMAC-SHA256 implementation

```python
import hmac
import hashlib

def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    # Calculate expected signature
    expected = hmac.new(
        secret.encode('utf-8'),
        body,  # Must be raw bytes, not parsed JSON
        hashlib.sha256
    ).hexdigest()
    
    # Compare securely
    return hmac.compare_digest(expected, signature)
```

#### Webhooks not being received

**Troubleshooting:**
1. Verify your endpoint is publicly accessible
2. Check firewall rules allow incoming HTTPS
3. Confirm the webhook URL is correctly configured
4. Check webhook delivery logs in PagerDuty/Opsgenie
5. Verify SSL certificate is valid

### Integration Issues

#### External service timeout

**Cause:** GitHub, Datadog, or other services are slow/unavailable.

**Solution:**
1. Check the external service's status page
2. Implement retry logic with timeouts
3. Use async processing for non-critical operations
4. Configure appropriate timeout values

```python
import httpx

async def fetch_with_timeout(url, timeout=10):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=timeout)
            return response.json()
        except httpx.TimeoutException:
            # Handle timeout
            return None
```

#### "Integration not configured" error

**Cause:** Required API keys or credentials are missing.

**Solution:**
1. Check environment variables are set
2. Verify configuration in settings
3. Use the health endpoint to check integration status

```bash
# Check integration status
curl https://api.example.com/health?full=true \
  -H "Authorization: Bearer $TOKEN"
```

### Data Issues

#### Validation errors on request body

**Cause:** Request body doesn't match expected schema.

**Solution:**
1. Check the API documentation for required fields
2. Verify date formats (ISO 8601: `2024-01-15T10:30:00Z`)
3. Ensure enum values are valid (e.g., `severity` values)
4. Check field length limits

#### Empty or partial response

**Cause:** Query filters too restrictive or no matching data.

**Solution:**
1. Broaden filter criteria
2. Check the time range includes expected data
3. Verify pagination parameters
4. Check if data exists in the specified tenant

### WebSocket Issues

#### WebSocket connection drops frequently

**Cause:** Network instability or idle timeout.

**Solution:**
```javascript
// Implement reconnection logic
class ReconnectingWebSocket {
  constructor(url) {
    this.url = url;
    this.reconnectAttempts = 0;
    this.maxAttempts = 10;
  }
  
  connect() {
    this.ws = new WebSocket(this.url);
    
    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      // Start heartbeat
      this.heartbeatInterval = setInterval(() => {
        this.ws.send(JSON.stringify({ type: 'ping' }));
      }, 30000);
    };
    
    this.ws.onclose = () => {
      clearInterval(this.heartbeatInterval);
      this.scheduleReconnect();
    };
  }
  
  scheduleReconnect() {
    if (this.reconnectAttempts < this.maxAttempts) {
      const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
      setTimeout(() => {
        this.reconnectAttempts++;
        this.connect();
      }, delay);
    }
  }
}
```

#### Authentication fails on WebSocket

**Cause:** Token not provided or expired.

**Solution:**
1. Include token in URL: `wss://api.example.com/ws?token=<token>`
2. Or send auth message immediately after connect:
   ```json
   {"type": "auth", "token": "<token>"}
   ```

---

## Debugging Tips

### Enable Debug Logging

```python
import logging
import httpx

# Enable httpx debug logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("httpx").setLevel(logging.DEBUG)
```

### Inspect Request/Response

```python
import requests

response = requests.get(
    url,
    headers=headers
)

print(f"Status: {response.status_code}")
print(f"Headers: {dict(response.headers)}")
print(f"Body: {response.text}")
```

### Check Health Endpoints

```bash
# Basic health
curl https://api.example.com/health/live

# Full health with all integrations
curl https://api.example.com/health?full=true \
  -H "Authorization: Bearer $TOKEN"
```

### Use OpenAPI Documentation

Visit `/docs` for interactive API testing with Swagger UI.

---

## Getting Help

### Before Contacting Support

1. Check this troubleshooting guide
2. Review the API documentation
3. Check the status page for known issues
4. Gather error messages and request IDs

### What to Include in Support Requests

- Error message and code
- Request ID (from response headers)
- Timestamp of the error
- API endpoint being called
- Relevant request/response bodies (sanitized)
- Steps to reproduce

### Support Channels

- **Documentation**: [docs.incident-copilot.io](https://docs.incident-copilot.io)
- **Status Page**: [status.incident-copilot.io](https://status.incident-copilot.io)
- **GitHub Issues**: For bug reports and feature requests
- **Email**: api-support@incident-copilot.io
- **Slack**: #incident-copilot-support (for Enterprise customers)

---

*See also: [API Overview](README.md) | [Code Examples](examples.md)*
