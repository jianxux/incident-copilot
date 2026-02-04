# 👥 User Management

Manage users, roles, and permissions within your Incident Copilot tenant.

---

## 🎯 User Roles

### Role Hierarchy

| Role | Level | Description |
|------|-------|-------------|
| `owner` | 4 | Full control including billing |
| `admin` | 3 | Manage users and settings |
| `member` | 2 | Full operational access |
| `viewer` | 1 | Read-only access |

### Permission Matrix

| Action | Owner | Admin | Member | Viewer |
|--------|-------|-------|--------|--------|
| View incidents | ✅ | ✅ | ✅ | ✅ |
| View context cards | ✅ | ✅ | ✅ | ✅ |
| Create postmortems | ✅ | ✅ | ✅ | ❌ |
| Edit postmortems | ✅ | ✅ | ✅ | ❌ |
| Manage integrations | ✅ | ✅ | ❌ | ❌ |
| Invite users | ✅ | ✅ | ❌ | ❌ |
| Change user roles | ✅ | ✅ | ❌ | ❌ |
| Remove users | ✅ | ✅ | ❌ | ❌ |
| Billing access | ✅ | ❌ | ❌ | ❌ |
| Delete tenant | ✅ | ❌ | ❌ | ❌ |

---

## 🔧 Adding Users

### Via API

```bash
POST /api/users
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "email": "jane@company.com",
  "name": "Jane Doe",
  "role": "member"
}
```

**Response:**
```json
{
  "id": "user_xyz789",
  "email": "jane@company.com",
  "name": "Jane Doe",
  "role": "member",
  "tenant_id": "tenant_abc123",
  "created_at": "2025-01-15T10:00:00Z",
  "email_verified": false
}
```

### Via Invitation

```bash
POST /api/users/invite
{
  "email": "jane@company.com",
  "role": "member",
  "message": "Welcome to the team!"
}
```

The user receives an email invitation to:
1. Create their account
2. Set their password (or use OAuth)
3. Join the tenant

---

## 🔐 Authentication Methods

### Email + Password

Traditional email/password authentication:

```bash
POST /api/auth/login
{
  "email": "jane@company.com",
  "password": "secure-password"
}
```

### OAuth (GitHub)

Sign in with GitHub:

```
GET /api/auth/oauth/github
→ Redirect to GitHub
→ Return with session
```

### OAuth (Google)

Sign in with Google:

```
GET /api/auth/oauth/google
→ Redirect to Google
→ Return with session
```

### SSO (SAML/OIDC)

Enterprise single sign-on:

See [SSO Configuration](./sso.md) for setup.

---

## 👤 User Properties

| Property | Description |
|----------|-------------|
| `id` | Unique user identifier |
| `email` | Email address (unique globally) |
| `name` | Display name |
| `role` | User role in tenant |
| `tenant_id` | Parent tenant |
| `avatar_url` | Profile picture URL |
| `email_verified` | Email verification status |
| `oauth_provider` | OAuth provider (if used) |
| `last_login` | Last login timestamp |
| `created_at` | Account creation time |

---

## 🔄 Managing Users

### List Users

```bash
GET /api/users

Response:
{
  "users": [
    {
      "id": "user_abc",
      "email": "owner@company.com",
      "name": "Owner",
      "role": "owner"
    },
    {
      "id": "user_xyz",
      "email": "jane@company.com",
      "name": "Jane Doe",
      "role": "member"
    }
  ],
  "total": 2
}
```

### Update User Role

```bash
PUT /api/users/{user_id}
{
  "role": "admin"
}
```

### Remove User

```bash
DELETE /api/users/{user_id}
```

⚠️ **Note:** Cannot remove the last owner.

---

## 🔑 Session Management

### Active Sessions

View user's active sessions:

```bash
GET /api/users/{user_id}/sessions

Response:
{
  "sessions": [
    {
      "id": "sess_abc",
      "user_agent": "Mozilla/5.0...",
      "ip_address": "192.168.1.1",
      "created_at": "2025-01-15T09:00:00Z",
      "expires_at": "2025-01-15T21:00:00Z"
    }
  ]
}
```

### Revoke Session

```bash
DELETE /api/sessions/{session_id}
```

### Revoke All Sessions

```bash
DELETE /api/users/{user_id}/sessions
```

---

## 📧 Email Verification

### Verification Flow

1. User signs up with email
2. Verification email sent
3. User clicks verification link
4. `email_verified` set to `true`

### Resend Verification

```bash
POST /api/users/{user_id}/verify/resend
```

---

## 🔒 Password Management

### Password Requirements

- Minimum 8 characters
- At least one uppercase letter
- At least one number
- At least one special character

### Reset Password

```bash
POST /api/auth/password/reset
{
  "email": "jane@company.com"
}
```

User receives reset link via email.

### Change Password (Authenticated)

```bash
PUT /api/auth/password
Authorization: Bearer <token>
{
  "current_password": "old-password",
  "new_password": "new-secure-password"
}
```

---

## 👥 Bulk Operations

### Import Users

```bash
POST /api/users/import
Content-Type: multipart/form-data

file: users.csv
```

CSV format:
```csv
email,name,role
jane@company.com,Jane Doe,member
john@company.com,John Smith,admin
```

### Export Users

```bash
GET /api/users/export?format=csv
```

---

## 📊 User Limits

### Plan Limits

| Plan | Max Users |
|------|-----------|
| Free | 3 |
| Starter | 10 |
| Pro | 25 |
| Enterprise | Unlimited |

### Check Limit

```bash
GET /api/tenant/limits

Response:
{
  "users": {
    "current": 8,
    "limit": 10
  }
}
```

---

## 🐛 Troubleshooting

### "User already exists"

**Cause:** Email is registered with another tenant

**Solution:**
- Each email can only belong to one tenant
- User must leave other tenant first
- Or use a different email

### "User limit exceeded"

**Cause:** Plan user limit reached

**Solution:**
1. Upgrade plan
2. Remove inactive users
3. Contact support

### "Cannot remove owner"

**Cause:** Trying to remove the only owner

**Solution:**
1. Transfer ownership to another user first
2. Then remove the original owner

### "Invitation expired"

**Cause:** Invitation link is no longer valid (24h default)

**Solution:**
1. Resend invitation
2. Create user directly (admin)

---

## 📚 Related Documentation

- [Tenant Setup](./tenant-setup.md) - Multi-tenant configuration
- [SSO](./sso.md) - Enterprise authentication
- [API Keys](./api-keys.md) - Programmatic access

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or open an issue on GitHub.*
