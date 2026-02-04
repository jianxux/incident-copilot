# 👥 User Management

Manage users and roles in Incident Copilot.

---

## 📋 Roles

| Role | Description | Permissions |
|------|-------------|-------------|
| **Viewer** | View incidents and analytics | Read-only access |
| **Responder** | Respond to incidents | View + acknowledge/resolve |
| **Admin** | Full access | All permissions |

---

## 🔧 Adding Users

### Via Web UI

1. Navigate to **Settings** → **Users**
2. Click **Add User**
3. Enter email and select role
4. Click **Send Invitation**

### Via API

```bash
curl -X POST http://localhost:8000/api/admin/users \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@company.com",
    "role": "responder",
    "send_invitation": true
  }'
```

---

## 🔐 With SSO

When SSO is enabled, users are automatically provisioned on first login. Configure default role:

```bash
SSO_DEFAULT_ROLE=responder
```

Map roles from IdP:
```bash
SSO_ROLE_MAPPING='{
  "admins": "admin",
  "oncall": "responder",
  "viewers": "viewer"
}'
```

---

## 📚 Related Documentation

- [SSO Configuration](./sso.md)
- [API Keys](./api-keys.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
