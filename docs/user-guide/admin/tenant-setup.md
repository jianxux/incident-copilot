# 🏢 Tenant Setup

Incident Copilot supports multi-tenant deployments where multiple organizations can share a single installation with isolated data and configurations.

---

## 🎯 What is Multi-Tenancy?

Multi-tenancy allows:
- **Multiple organizations** on one deployment
- **Isolated data** between tenants
- **Custom integrations** per tenant
- **Separate billing** and usage tracking

---

## 🏗️ Tenant Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  INCIDENT COPILOT                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌───────────────┐  ┌───────────────┐  ┌─────────────┐  │
│  │   Acme Corp   │  │  StartupXYZ   │  │  BigEnterprise │
│  │   (Tenant 1)  │  │   (Tenant 2)  │  │   (Tenant 3)  │
│  ├───────────────┤  ├───────────────┤  ├─────────────┤  │
│  │ • Users       │  │ • Users       │  │ • Users       │
│  │ • Integrations│  │ • Integrations│  │ • Integrations│
│  │ • Incidents   │  │ • Incidents   │  │ • Incidents   │
│  │ • Settings    │  │ • Settings    │  │ • Settings    │
│  └───────────────┘  └───────────────┘  └─────────────┘  │
│                                                         │
│  ┌─────────────────────────────────────────────────────┐│
│  │                 SHARED INFRASTRUCTURE               ││
│  │  • Database  • Redis  • AI APIs  • Webhook Router   ││
│  └─────────────────────────────────────────────────────┘│
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 🔧 Creating a Tenant

### Via API

```bash
POST /api/admin/tenants
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "name": "Acme Corporation",
  "slug": "acme",
  "plan": "pro"
}
```

**Response:**
```json
{
  "id": "tenant_abc123",
  "name": "Acme Corporation",
  "slug": "acme",
  "plan": "pro",
  "created_at": "2025-01-15T10:00:00Z",
  "max_incidents_per_month": 500,
  "max_users": 25,
  "max_integrations": 10
}
```

### Via CLI (Coming Soon)

```bash
python -m incident_copilot.cli tenant create \
  --name "Acme Corporation" \
  --slug "acme" \
  --plan pro
```

---

## 📊 Tenant Properties

| Property | Description |
|----------|-------------|
| `id` | Unique tenant identifier |
| `name` | Display name |
| `slug` | URL-friendly identifier (unique) |
| `plan` | Subscription plan (free, starter, pro, enterprise) |
| `created_at` | Creation timestamp |
| `max_incidents_per_month` | Usage limit |
| `max_users` | User seat limit |
| `max_integrations` | Integration limit |
| `stripe_customer_id` | Billing reference (if using Stripe) |

---

## 📦 Plan Tiers

### Available Plans

| Plan | Incidents/Month | Users | Integrations | Features |
|------|-----------------|-------|--------------|----------|
| Free | 50 | 3 | 2 | Basic |
| Starter | 200 | 10 | 5 | + Analytics |
| Pro | 500 | 25 | 10 | + SSO |
| Enterprise | Unlimited | Unlimited | Unlimited | + Custom |

### Plan Limits

```python
PLAN_LIMITS = {
    "free": {
        "max_incidents_per_month": 50,
        "max_users": 3,
        "max_integrations": 2
    },
    "starter": {
        "max_incidents_per_month": 200,
        "max_users": 10,
        "max_integrations": 5
    },
    "pro": {
        "max_incidents_per_month": 500,
        "max_users": 25,
        "max_integrations": 10
    },
    "enterprise": {
        "max_incidents_per_month": -1,  # Unlimited
        "max_users": -1,
        "max_integrations": -1
    }
}
```

---

## 🔧 Tenant Configuration

### Integration Settings

Each tenant configures their own integrations:

```bash
PUT /api/tenants/{tenant_id}/integrations
{
  "pagerduty": {
    "api_key": "encrypted_key",
    "webhook_secret": "encrypted_secret"
  },
  "github": {
    "token": "encrypted_token",
    "org": "acme-corp"
  },
  "slack": {
    "bot_token": "encrypted_token",
    "default_channel": "#incidents"
  }
}
```

### Notification Preferences

```bash
PUT /api/tenants/{tenant_id}/settings
{
  "notification_provider": "slack",
  "default_severity_threshold": "medium",
  "timezone": "America/New_York"
}
```

---

## 👥 User Assignment

Users belong to exactly one tenant:

```bash
POST /api/tenants/{tenant_id}/users
{
  "email": "john@acme.com",
  "name": "John Doe",
  "role": "admin"
}
```

### User Roles

| Role | Permissions |
|------|-------------|
| `owner` | Full control, billing, delete tenant |
| `admin` | Manage users, integrations, settings |
| `member` | View incidents, create postmortems |
| `viewer` | Read-only access |

---

## 🔒 Data Isolation

### Database Isolation

Each tenant's data is isolated:
- **Incidents** filtered by `tenant_id`
- **Users** scoped to tenant
- **Integrations** per-tenant encrypted storage

### API Isolation

All API requests are tenant-scoped:

```
Authorization: Bearer <user-token>
# Token contains tenant_id, all queries filtered automatically
```

### Webhook Isolation

Webhooks include tenant identification:

```
POST /webhooks/pagerduty?tenant=acme
X-Tenant-ID: acme
```

---

## 📊 Usage Tracking

### Monitor Tenant Usage

```bash
GET /api/admin/tenants/{tenant_id}/usage

Response:
{
  "tenant_id": "tenant_abc123",
  "period": "2025-01",
  "incidents_this_month": 127,
  "incidents_limit": 500,
  "users_count": 12,
  "users_limit": 25,
  "integrations_count": 6,
  "integrations_limit": 10
}
```

### Usage Alerts

Configure alerts when nearing limits:

```bash
# 80% of incident limit
# 90% of user limit
# Overage notification
```

---

## 🔄 Upgrading Plans

### Via API

```bash
PUT /api/tenants/{tenant_id}/plan
{
  "plan": "enterprise"
}
```

### Via Billing Portal

See [Billing](./billing.md) for self-service upgrades.

---

## 🗑️ Deleting a Tenant

⚠️ **Warning:** This permanently deletes all tenant data.

```bash
DELETE /api/admin/tenants/{tenant_id}
X-Confirm-Delete: true
```

### Data Retention

After deletion:
- User accounts removed
- Incidents archived for 30 days
- Integrations immediately removed
- API keys revoked

---

## 🔐 Admin Access

### Super Admin

For platform administrators:

```bash
# Create admin user
python -m incident_copilot.cli admin create \
  --email admin@platform.com \
  --name "Platform Admin"
```

Admin can:
- Create/delete tenants
- View all tenant usage
- Manage billing
- System configuration

---

## 🐛 Troubleshooting

### "Tenant limit reached"

**Cause:** Exceeded plan limits

**Solution:**
1. Upgrade plan
2. Wait for next billing period
3. Contact support for temporary increase

### "User already exists"

**Cause:** Email in use by another tenant

**Solution:**
- Users can only belong to one tenant
- Use different email or remove from other tenant

### "Integration limit exceeded"

**Solution:**
- Remove unused integrations
- Upgrade plan
- Consolidate integrations

---

## 📚 Related Documentation

- [User Management](./user-management.md) - Managing tenant users
- [Billing](./billing.md) - Plan management
- [SSO](./sso.md) - Enterprise authentication

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or open an issue on GitHub.*
