# 🔑 API Keys Management

Manage API keys for programmatic access to Incident Copilot.

---

## 📋 Overview

API keys allow external applications to authenticate with the Incident Copilot API. Use them for:
- CI/CD integrations
- Custom dashboards
- Automation scripts
- Third-party tool integrations

---

## 🔧 Creating API Keys

### Via Web UI

1. Navigate to **Settings** → **API Keys**
2. Click **Create New Key**
3. Configure:
   - **Name:** Descriptive name (e.g., "CI/CD Pipeline")
   - **Expiration:** Never, 30 days, 90 days, or custom
   - **Scopes:** Select permissions (see below)
4. Click **Create**
5. ⚠️ **Copy the key immediately** — it won't be shown again

### Via API

```bash
curl -X POST http://localhost:8000/api/admin/api-keys \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CI/CD Pipeline",
    "scopes": ["read:incidents", "write:incidents"],
    "expires_in_days": 90
  }'
```

---

## 🔐 Scopes

| Scope | Description |
|-------|-------------|
| `read:incidents` | View incidents and context cards |
| `write:incidents` | Create/update incidents |
| `read:analytics` | View MTTR and metrics |
| `read:postmortems` | View postmortems |
| `write:postmortems` | Create/update postmortems |
| `admin:users` | Manage users |
| `admin:integrations` | Manage integrations |

---

## 🔒 Using API Keys

Include the key in the `Authorization` header:

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
  https://your-instance.com/api/analytics/mttr
```

---

## ♻️ Rotating Keys

1. Create a new key with the same scopes
2. Update your applications to use the new key
3. Revoke the old key

---

## 📚 Related Documentation

- [API Reference](../api-reference.md)
- [User Management](./user-management.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
