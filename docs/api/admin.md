# Admin API Reference

The Admin API provides endpoints for user management, tenant configuration, billing, SSO, rate limiting, and audit logging.

---

## Authentication

### List OAuth Providers

```http
GET /api/auth/providers
```

**Response:**

```json
{
  "providers": ["google", "github", "okta"]
}
```

### Sign Up

Create a new account with email/password.

```http
POST /api/auth/signup
```

**Request Body:**

```json
{
  "email": "user@example.com",
  "password": "securepassword123",
  "name": "Jane Doe",
  "company": "Acme Corp"
}
```

**Response:**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "id": "user_abc123",
    "email": "user@example.com",
    "name": "Jane Doe",
    "role": "owner"
  },
  "tenant": {
    "id": "tenant_xyz789",
    "name": "Acme Corp",
    "slug": "acme-corp",
    "plan": "free"
  }
}
```

### Login

Authenticate with email/password.

```http
POST /api/auth/login
```

**Request Body:**

```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Response:** Same as signup response.

### Refresh Token

```http
POST /api/auth/refresh
```

**Request Body:**

```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

### Logout

```http
POST /api/auth/logout
```

**Response:**

```json
{
  "status": "ok"
}
```

### Get Current User

```http
GET /api/auth/me
```

**Response:**

```json
{
  "user": {
    "id": "user_abc123",
    "email": "user@example.com",
    "name": "Jane Doe",
    "role": "owner",
    "avatar_url": "https://..."
  },
  "tenant": {
    "id": "tenant_xyz789",
    "name": "Acme Corp",
    "slug": "acme-corp",
    "plan": "pro"
  }
}
```

### OAuth Login

Initiate OAuth flow.

```http
GET /api/auth/oauth/{provider}
```

**Supported Providers:**
- `google`
- `github`
- `okta`
- `azure`

Redirects to provider's authorization page.

### OAuth Callback

```http
GET /api/auth/oauth/{provider}/callback
```

Handles OAuth provider callback. Redirects to dashboard with tokens.

---

## SSO Configuration

### Get SSO Configuration

```http
GET /auth/sso/config/{tenant_id}
```

**Response:**

```json
{
  "tenant_id": "tenant_xyz789",
  "sso_enabled": true,
  "sso_required": false,
  "jit_provisioning_enabled": true,
  "identity_providers": [
    {
      "id": "idp_abc123",
      "name": "Corporate Okta",
      "slug": "corporate-okta",
      "provider_type": "oidc",
      "is_active": true,
      "is_default": true,
      "email_domains": ["company.com"]
    }
  ]
}
```

### Enable SSO

```http
POST /auth/sso/config/{tenant_id}/enable
```

### Disable SSO

```http
POST /auth/sso/config/{tenant_id}/disable
```

### Add Identity Provider

```http
POST /auth/sso/config/{tenant_id}/idp
```

**Request Body (OIDC):**

```json
{
  "name": "Corporate Okta",
  "slug": "corporate-okta",
  "provider_type": "oidc",
  "email_domains": ["company.com"],
  "is_default": true,
  "oidc_settings": {
    "client_id": "0oa...",
    "client_secret": "...",
    "issuer": "https://company.okta.com",
    "authorization_endpoint": "https://company.okta.com/oauth2/v1/authorize",
    "token_endpoint": "https://company.okta.com/oauth2/v1/token",
    "userinfo_endpoint": "https://company.okta.com/oauth2/v1/userinfo",
    "scopes": ["openid", "email", "profile", "groups"],
    "use_pkce": true
  },
  "role_mapping": {
    "admin": "admin",
    "users": "member"
  }
}
```

**Request Body (SAML):**

```json
{
  "name": "Corporate ADFS",
  "slug": "corporate-adfs",
  "provider_type": "saml",
  "email_domains": ["company.com"],
  "saml_settings": {
    "idp_entity_id": "http://adfs.company.com/...",
    "idp_sso_url": "https://adfs.company.com/adfs/ls/",
    "idp_certificate": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
    "sp_entity_id": "https://your-app.com/auth/sso/saml/metadata/{tenant_id}",
    "assertion_consumer_url": "https://your-app.com/auth/sso/saml/acs/{tenant_id}",
    "name_id_format": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
  }
}
```

### Remove Identity Provider

```http
DELETE /auth/sso/config/{tenant_id}/idp/{idp_id}
```

### Discover Identity Provider

Find IdP for an email address.

```http
GET /auth/sso/discover?email=user@company.com
```

**Response:**

```json
{
  "tenant_id": "tenant_xyz789",
  "idp_id": "idp_abc123",
  "idp_name": "Corporate Okta",
  "provider_type": "oidc",
  "login_url": "/auth/sso/oidc/login/tenant_xyz789?idp=corporate-okta"
}
```

### SAML Login

```http
GET /auth/sso/saml/login/{tenant_id}
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `idp` | string | IdP slug |
| `return_to` | string | Return URL after login |

### SAML Metadata

Get SP metadata for SAML configuration.

```http
GET /auth/sso/saml/metadata/{tenant_id}
```

Returns XML metadata document.

### OIDC Login

```http
GET /auth/sso/oidc/login/{tenant_id}
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `idp` | string | IdP slug |
| `return_to` | string | Return URL after login |

### List OIDC Presets

```http
GET /auth/sso/presets
```

**Response:**

```json
{
  "presets": {
    "google": {
      "name": "Google",
      "issuer": "https://accounts.google.com",
      "scopes": ["openid", "email", "profile"]
    },
    "okta": {
      "name": "Okta",
      "issuer_format": "https://{your-okta-domain}",
      "scopes": ["openid", "email", "profile", "groups"]
    },
    "azure_ad": {
      "name": "Azure AD",
      "issuer_format": "https://login.microsoftonline.com/{tenant-id}/v2.0"
    }
  }
}
```

---

## Billing

### List Plans

```http
GET /api/billing/plans
```

**Response:**

```json
[
  {
    "id": "free",
    "name": "Free",
    "price_monthly": 0,
    "max_incidents": 50,
    "max_users": 3,
    "max_integrations": 3,
    "features": [
      "Basic context assembly",
      "Slack notifications",
      "GitHub deployments",
      "Community support"
    ]
  },
  {
    "id": "starter",
    "name": "Starter",
    "price_monthly": 49,
    "max_incidents": 500,
    "max_users": 10,
    "max_integrations": 5,
    "features": [
      "Everything in Free",
      "AI log summaries",
      "Past incident search",
      "Email support"
    ]
  },
  {
    "id": "pro",
    "name": "Pro",
    "price_monthly": 149,
    "max_incidents": 2000,
    "max_users": 50,
    "max_integrations": 10,
    "features": [
      "Everything in Starter",
      "Runbook automation",
      "Advanced analytics",
      "SSO/SAML",
      "Priority support"
    ]
  },
  {
    "id": "enterprise",
    "name": "Enterprise",
    "price_monthly": -1,
    "max_incidents": -1,
    "max_users": -1,
    "max_integrations": -1,
    "features": [
      "Everything in Pro",
      "Unlimited everything",
      "Custom integrations",
      "Dedicated support",
      "SLA guarantees"
    ]
  }
]
```

### Get Current Subscription

```http
GET /api/billing/current
```

**Response:**

```json
{
  "plan": "pro",
  "plan_info": {...},
  "usage": {
    "incidents_this_month": 150,
    "max_incidents": 2000,
    "billing_cycle_start": "2024-01-01T00:00:00Z"
  },
  "has_stripe_customer": true,
  "has_subscription": true
}
```

### Create Checkout Session

Upgrade to a paid plan.

```http
POST /api/billing/checkout
```

**Request Body:**

```json
{
  "plan": "pro"
}
```

**Response:**

```json
{
  "checkout_url": "https://checkout.stripe.com/..."
}
```

### Create Portal Session

Access Stripe Customer Portal.

```http
POST /api/billing/portal
```

**Response:**

```json
{
  "portal_url": "https://billing.stripe.com/..."
}
```

### Stripe Webhook

Handle Stripe webhook events.

```http
POST /api/billing/webhook
```

**Headers:**

| Header | Required | Description |
|--------|----------|-------------|
| `Stripe-Signature` | Yes | Stripe webhook signature |

---

## Rate Limiting

### Get Rate Limit Status

```http
GET /admin/ratelimit/status
```

**Response:**

```json
{
  "enabled": true,
  "configs": {
    "tenant": {
      "name": "Per-Tenant Limit",
      "capacity": 1000,
      "refill_rate": 16.67,
      "tokens_per_minute": 1000,
      "tokens_per_hour": 60000,
      "enabled": true,
      "description": "Rate limit per tenant"
    },
    "user": {
      "name": "Per-User Limit",
      "capacity": 100,
      "refill_rate": 1.67,
      "tokens_per_minute": 100,
      "enabled": true
    },
    "ip": {
      "name": "Per-IP Limit",
      "capacity": 60,
      "refill_rate": 1.0,
      "tokens_per_minute": 60,
      "enabled": true
    }
  },
  "overrides": [
    {
      "key": "tenant_enterprise_abc",
      "scope": "tenant",
      "capacity": 5000,
      "refill_rate": 83.33,
      "enabled": true,
      "expires_at": null,
      "reason": "Enterprise customer",
      "created_at": "2024-01-01T00:00:00Z",
      "created_by": "admin@company.com"
    }
  ]
}
```

### Get Key Status

Check rate limit status for a specific key.

```http
POST /admin/ratelimit/status/key
```

**Request Body:**

```json
{
  "scope": "tenant",
  "identifier": "tenant_xyz789"
}
```

**Response:**

```json
{
  "key": "tenant:tenant_xyz789",
  "scope": "tenant",
  "current_tokens": 850.5,
  "capacity": 1000,
  "refill_rate": 16.67,
  "last_refill": "2024-01-15T10:30:00Z",
  "requests_in_window": 150,
  "utilization": 0.15
}
```

### Reset Rate Limit

Reset rate limit for a specific key.

```http
POST /admin/ratelimit/reset/{key}
```

**Request Body:**

```json
{
  "scope": "tenant",
  "identifier": "tenant_xyz789"
}
```

### Update Rate Limit Configuration

```http
PUT /admin/ratelimit/config/{scope}
```

**Scopes:** `tenant`, `user`, `ip`, `api_key`, `webhook`

**Request Body:**

```json
{
  "capacity": 1500,
  "refill_rate": 25.0,
  "enabled": true
}
```

### Set Rate Limit Override

```http
POST /admin/ratelimit/override
```

**Request Body:**

```json
{
  "key": "tenant_enterprise_abc",
  "scope": "tenant",
  "capacity": 5000,
  "refill_rate": 83.33,
  "enabled": true,
  "expires_at": "2024-12-31T23:59:59Z",
  "reason": "Enterprise customer upgrade"
}
```

### Remove Rate Limit Override

```http
DELETE /admin/ratelimit/override/{scope}/{key}
```

### Test Rate Limit

Test rate limiting without consuming tokens.

```http
POST /admin/ratelimit/test
```

**Request Body:**

```json
{
  "scope": "tenant",
  "identifier": "tenant_xyz789",
  "cost": 1
}
```

**Response:**

```json
{
  "scope": "tenant",
  "identifier": "tenant_xyz789",
  "cost": 1,
  "would_allow": true,
  "current_tokens": 850.5,
  "tokens_after_request": 849.5,
  "capacity": 1000,
  "refill_rate": 16.67,
  "utilization": 0.15
}
```

### Get Rate Limit Metrics

```http
GET /admin/ratelimit/metrics
```

**Response:**

```json
{
  "scopes": {
    "tenant": {
      "enabled": true,
      "capacity": 1000,
      "refill_rate": 16.67,
      "tokens_per_minute": 1000
    }
  },
  "overrides_count": 5,
  "using_redis": true
}
```

---

## Audit Logging

### List Audit Events

```http
GET /api/audit/events
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tenant_id` | string | Yes | Tenant ID |
| `user_id` | string | No | Filter by user |
| `event_type` | string | No | Filter by event type |
| `category` | string | No | Filter by category |
| `resource_type` | string | No | Filter by resource type |
| `resource_id` | string | No | Filter by resource ID |
| `outcome` | string | No | Filter by outcome |
| `start_date` | datetime | No | Start of time range |
| `end_date` | datetime | No | End of time range |
| `limit` | integer | No | Max results (1-1000) |
| `offset` | integer | No | Pagination offset |

**Event Types:**

| Type | Description |
|------|-------------|
| `user.login` | User logged in |
| `user.logout` | User logged out |
| `user.created` | User account created |
| `user.updated` | User account updated |
| `user.deleted` | User account deleted |
| `api_key.created` | API key created |
| `api_key.revoked` | API key revoked |
| `settings.updated` | Settings changed |
| `integration.connected` | Integration connected |
| `integration.disconnected` | Integration disconnected |
| `incident.accessed` | Incident accessed |
| `postmortem.exported` | Postmortem exported |

**Categories:**

| Category | Description |
|----------|-------------|
| `authentication` | Login/logout events |
| `authorization` | Permission changes |
| `data_access` | Data read operations |
| `data_modification` | Data write operations |
| `configuration` | Settings changes |
| `integration` | External integration events |

**Outcomes:**

| Outcome | Description |
|---------|-------------|
| `success` | Operation succeeded |
| `failure` | Operation failed |
| `error` | Unexpected error |

**Response:**

```json
{
  "events": [
    {
      "id": "evt_abc123",
      "event_type": "user.login",
      "category": "authentication",
      "outcome": "success",
      "user_id": "user_xyz789",
      "user_email": "jane@example.com",
      "resource_type": "session",
      "resource_id": "sess_123",
      "ip_address": "192.168.1.1",
      "user_agent": "Mozilla/5.0...",
      "timestamp": "2024-01-15T10:30:00Z",
      "details": {
        "method": "password",
        "mfa_used": false
      }
    }
  ],
  "count": 50,
  "limit": 100,
  "offset": 0
}
```

### Get Audit Event

```http
GET /api/audit/events/{event_id}
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tenant_id` | string | Yes | Tenant ID |

### Get Audit Statistics

```http
GET /api/audit/stats
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tenant_id` | string | Required | Tenant ID |
| `days` | integer | 7 | Number of days (1-90) |

**Response:**

```json
{
  "tenant_id": "tenant_xyz789",
  "period_days": 7,
  "total_events": 1500,
  "events_by_type": {
    "user.login": 500,
    "incident.accessed": 800,
    "settings.updated": 50
  },
  "events_by_category": {
    "authentication": 550,
    "data_access": 850,
    "configuration": 100
  },
  "events_by_outcome": {
    "success": 1450,
    "failure": 45,
    "error": 5
  }
}
```

---

## Health Checks

### Comprehensive Health Check

```http
GET /health
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `full` | boolean | false | Check all external dependencies |

**Response:**

```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "version": "0.1.0",
  "uptime_seconds": 86400,
  "components": [
    {
      "name": "redis",
      "status": "healthy",
      "latency_ms": 1.5,
      "message": "Connected"
    },
    {
      "name": "database",
      "status": "healthy",
      "latency_ms": 3.2,
      "message": "Connected"
    },
    {
      "name": "pagerduty",
      "status": "healthy",
      "latency_ms": 150.0,
      "message": "API accessible"
    },
    {
      "name": "github",
      "status": "healthy",
      "latency_ms": 200.0,
      "message": "API accessible",
      "details": {
        "rate_limit_remaining": 4500,
        "rate_limit_limit": 5000
      }
    }
  ]
}
```

**Health Statuses:**

| Status | HTTP Code | Description |
|--------|-----------|-------------|
| `healthy` | 200 | All systems operational |
| `degraded` | 200 | Some non-critical issues |
| `unhealthy` | 503 | Critical systems down |

### Liveness Probe

Kubernetes liveness check.

```http
GET /health/live
```

**Response:**

```json
{
  "status": "alive"
}
```

### Readiness Probe

Kubernetes readiness check.

```http
GET /health/ready
```

**Response (Ready):**

```json
{
  "status": "ready"
}
```

**Response (Not Ready):**

```json
{
  "status": "not_ready",
  "redis": "unhealthy",
  "database": "healthy"
}
```

---

## User Roles

| Role | Description | Capabilities |
|------|-------------|--------------|
| `owner` | Tenant owner | Full access, manage billing |
| `admin` | Administrator | Manage users, settings |
| `member` | Regular user | Access incidents, create postmortems |
| `viewer` | Read-only | View incidents only |

---

*See also: [API Overview](README.md) | [Error Codes](errors.md)*
