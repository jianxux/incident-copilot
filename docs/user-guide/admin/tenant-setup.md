# 🏢 Tenant Setup

Configure multi-tenant deployments of Incident Copilot.

---

## 📋 Overview

Multi-tenancy allows a single Incident Copilot deployment to serve multiple teams or organizations with complete data isolation.

---

## 🔧 Enabling Multi-Tenancy

```bash
# .env
MULTI_TENANT_ENABLED=true
DEFAULT_TENANT_ID=default
```

---

## 📊 Creating Tenants

### Via API

```bash
curl -X POST http://localhost:8000/api/admin/tenants \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "acme-corp",
    "name": "Acme Corporation",
    "settings": {
      "slack_channel": "#acme-incidents",
      "default_severity": "medium"
    }
  }'
```

---

## 🔐 Tenant Isolation

Each tenant has isolated:
- Incidents and context cards
- Analytics and metrics
- Postmortems
- API keys
- User access

---

## 🔗 Tenant Routing

Requests are routed to tenants via:

1. **Header:** `X-Tenant-ID: acme-corp`
2. **Subdomain:** `acme.incident-copilot.com`
3. **Path:** `/tenants/acme/api/...`

Configure the method:
```bash
TENANT_ROUTING=header  # header, subdomain, or path
```

---

## 📚 Related Documentation

- [User Management](./user-management.md)
- [SSO Configuration](./sso.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
