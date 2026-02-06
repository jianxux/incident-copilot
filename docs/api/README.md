# Incident Copilot API Reference

Welcome to the Incident Copilot API documentation. This API enables you to integrate incident management, analytics, and automation into your workflows.

## Base URL

```
https://your-domain.com
```

For local development:
```
http://localhost:8000
```

## API Versioning

The API currently does not use versioning in the URL path. Breaking changes will be communicated via changelog and deprecation notices.

## OpenAPI Documentation

Interactive API documentation is available at:

| Format | URL | Description |
|--------|-----|-------------|
| Swagger UI | `/docs` | Interactive API explorer |
| ReDoc | `/redoc` | Clean API documentation |
| OpenAPI JSON | `/openapi.json` | Raw OpenAPI 3.0 specification |

---

## Authentication

Incident Copilot supports multiple authentication methods depending on the use case.

### 1. JWT Bearer Token (Recommended)

For user-facing applications and dashboard access.

```bash
curl -X GET https://api.example.com/api/auth/me \
  -H "Authorization: Bearer <access_token>"
```

**Obtaining Tokens:**

```bash
# Login with email/password
curl -X POST https://api.example.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "your-password"
  }'

# Response:
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {...},
  "tenant": {...}
}
```

**Token Refresh:**

```bash
curl -X POST https://api.example.com/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJhbGciOiJIUzI1NiIs..."}'
```

### 2. API Key Authentication

For server-to-server integrations and automated workflows.

```bash
curl -X GET https://api.example.com/api/analytics/mttr \
  -H "X-API-Key: <your-api-key>"
```

API keys are scoped to a tenant and can have limited permissions.

### 3. OAuth 2.0 / SSO

For enterprise single sign-on integrations.

**Supported Providers:**
- Google Workspace
- Okta
- Azure AD
- Auth0
- GitHub
- Custom SAML 2.0
- Custom OIDC

See [Admin API](admin.md#sso-configuration) for SSO configuration.

### 4. Webhook Signatures

For validating incoming webhooks from PagerDuty, Opsgenie, etc.

| Provider | Header | Algorithm |
|----------|--------|-----------|
| PagerDuty | `X-PagerDuty-Signature` | HMAC-SHA256 (`v1=<hex>`) |
| Opsgenie | `X-OpsGenie-Signature` | HMAC-SHA256 |
| Stripe | `Stripe-Signature` | HMAC-SHA256 |

---

## Rate Limiting

API requests are rate-limited to ensure fair usage and system stability.

### Default Limits

| Scope | Limit | Window |
|-------|-------|--------|
| Per Tenant | 1000 requests | per minute |
| Per User | 100 requests | per minute |
| Per IP | 60 requests | per minute |
| Webhooks | 60 requests | per minute |

### Rate Limit Headers

All responses include rate limit information:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 950
X-RateLimit-Reset: 1640995200
```

### Handling Rate Limits

When rate limited, you'll receive a `429 Too Many Requests` response:

```json
{
  "detail": "Rate limit exceeded",
  "retry_after": 30
}
```

**Best Practices:**
- Implement exponential backoff with jitter
- Cache responses where appropriate
- Use webhooks instead of polling
- Request rate limit increases for production workloads

---

## Pagination

List endpoints support cursor-based pagination.

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 50 | Maximum items to return (1-100) |
| `offset` | integer | 0 | Number of items to skip |

### Example

```bash
# First page
curl "https://api.example.com/api/incidents?limit=50&offset=0"

# Next page
curl "https://api.example.com/api/incidents?limit=50&offset=50"
```

### Response Format

```json
{
  "items": [...],
  "total": 150,
  "limit": 50,
  "offset": 50
}
```

---

## Request Format

### Content Type

All request bodies must be JSON:

```
Content-Type: application/json
```

### Date/Time Format

All timestamps use ISO 8601 format in UTC:

```
2024-01-15T10:30:00Z
```

### Request Example

```bash
curl -X POST https://api.example.com/api/analytics/record/triggered \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "incident_id": "INC-12345",
    "service_name": "payments-api",
    "severity": "high",
    "triggered_at": "2024-01-15T10:30:00Z"
  }'
```

---

## Response Format

### Success Response

```json
{
  "status": "ok",
  "data": {...}
}
```

Or for list endpoints:

```json
{
  "items": [...],
  "total": 100,
  "limit": 50,
  "offset": 0
}
```

### Error Response

```json
{
  "detail": "Error message",
  "code": "error_code"
}
```

For validation errors:

```json
{
  "detail": [
    {
      "loc": ["body", "field_name"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## HTTP Status Codes

| Code | Meaning | When Used |
|------|---------|-----------|
| 200 | OK | Successful GET, PUT, PATCH, DELETE |
| 201 | Created | Successful POST creating a resource |
| 204 | No Content | Successful DELETE with no response body |
| 400 | Bad Request | Invalid request format or parameters |
| 401 | Unauthorized | Missing or invalid authentication |
| 403 | Forbidden | Authenticated but lacking permissions |
| 404 | Not Found | Resource doesn't exist |
| 409 | Conflict | Resource already exists |
| 422 | Unprocessable Entity | Valid JSON but invalid data |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Unexpected server error |
| 503 | Service Unavailable | Service temporarily unavailable |

---

## WebSocket API

Real-time updates are available via WebSocket:

```
wss://your-domain.com/api/realtime/ws?token=<access_token>
```

See [Real-time Events](integrations.md#websocket-api) for details.

---

## API Endpoints Overview

### Core APIs

| Endpoint | Description |
|----------|-------------|
| `/api/auth/*` | Authentication and user management |
| `/api/analytics/*` | MTTR metrics and incident analytics |
| `/api/insights/*` | AI-powered pattern detection |
| `/api/postmortems/*` | Postmortem generation and management |
| `/api/runbooks/*` | Runbook search and linking |
| `/api/costs/*` | Incident cost tracking and ROI |

### Integration APIs

| Endpoint | Description |
|----------|-------------|
| `/webhooks/*` | Incoming webhooks (PagerDuty, Opsgenie) |
| `/correlation/*` | Alert correlation rules |
| `/statuspage/*` | Status page management |
| `/plugins/*` | Custom plugin management |

### Admin APIs

| Endpoint | Description |
|----------|-------------|
| `/api/billing/*` | Subscription and billing |
| `/auth/sso/*` | SSO/SAML/OIDC configuration |
| `/admin/ratelimit/*` | Rate limit management |
| `/api/audit/*` | Audit log queries |

### System APIs

| Endpoint | Description |
|----------|-------------|
| `/health` | Comprehensive health check |
| `/health/live` | Kubernetes liveness probe |
| `/health/ready` | Kubernetes readiness probe |
| `/demo/*` | Demo mode and testing |

---

## SDKs and Client Libraries

### Official SDKs

- **Python**: `pip install incident-copilot` (coming soon)
- **JavaScript/TypeScript**: `npm install @incident-copilot/sdk` (coming soon)

### Community SDKs

- Go: [github.com/community/incident-copilot-go](https://github.com)
- Ruby: [github.com/community/incident-copilot-ruby](https://github.com)

### OpenAPI Code Generation

Generate clients for any language:

```bash
# Download OpenAPI spec
curl https://api.example.com/openapi.json -o openapi.json

# Generate Python client
openapi-generator generate -i openapi.json -g python -o ./client

# Generate TypeScript client
openapi-generator generate -i openapi.json -g typescript-axios -o ./client
```

---

## Support

- **Documentation**: [docs.incident-copilot.io](https://docs.incident-copilot.io)
- **API Status**: [status.incident-copilot.io](https://status.incident-copilot.io)
- **GitHub Issues**: [github.com/incident-copilot/issues](https://github.com)
- **Email**: api-support@incident-copilot.io

---

## Changelog

### v0.1.0 (Current)
- Initial API release
- Core incident management
- Analytics and insights
- Webhook integrations
- Real-time WebSocket updates

---

*Last updated: January 2024*
