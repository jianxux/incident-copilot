# 🔐 SSO Configuration

Incident Copilot supports enterprise Single Sign-On (SSO) via SAML 2.0 and OpenID Connect (OIDC).

---

## 🎯 SSO Overview

SSO enables:
- **Centralized authentication** via your identity provider
- **Automatic user provisioning** (JIT provisioning)
- **Enhanced security** with existing policies
- **Simplified access** for users

### Supported Protocols

| Protocol | Use Case |
|----------|----------|
| **SAML 2.0** | Enterprise IdPs (Okta, Azure AD, OneLogin) |
| **OIDC** | Modern IdPs, custom OAuth |

---

## 🔧 SAML Configuration

### Prerequisites

- [ ] SAML 2.0 compatible Identity Provider
- [ ] Admin access to your IdP
- [ ] Pro or Enterprise plan

### Step 1: Get Service Provider Details

Incident Copilot's SP metadata:

```
Entity ID (Issuer):
https://your-domain.com/auth/saml/metadata

ACS URL (Reply URL):
https://your-domain.com/auth/saml/callback

Single Logout URL:
https://your-domain.com/auth/saml/logout
```

### Step 2: Configure Your IdP

#### Okta

1. Go to **Applications** → **Create App Integration**
2. Select **SAML 2.0**
3. Configure:
   - **App name:** Incident Copilot
   - **Single sign-on URL:** `https://your-domain.com/auth/saml/callback`
   - **Audience URI:** `https://your-domain.com/auth/saml/metadata`
4. Attribute Statements:
   | Name | Value |
   |------|-------|
   | email | user.email |
   | firstName | user.firstName |
   | lastName | user.lastName |
5. Download the **Identity Provider metadata** or note:
   - IdP SSO URL
   - IdP Certificate

#### Azure AD

1. Go to **Enterprise Applications** → **New application**
2. Select **Create your own application**
3. Choose **Integrate any other application (Non-gallery)**
4. Go to **Single sign-on** → **SAML**
5. Configure Basic SAML Configuration:
   - **Identifier:** `https://your-domain.com/auth/saml/metadata`
   - **Reply URL:** `https://your-domain.com/auth/saml/callback`
6. User Attributes:
   | Claim | Source attribute |
   |-------|------------------|
   | email | user.mail |
   | name | user.displayname |
7. Download **Federation Metadata XML**

### Step 3: Configure Incident Copilot

#### Via API

```bash
POST /api/tenants/{tenant_id}/sso
{
  "type": "saml",
  "config": {
    "idp_entity_id": "https://idp.example.com/...",
    "idp_sso_url": "https://idp.example.com/sso",
    "idp_certificate": "-----BEGIN CERTIFICATE-----\n...",
    "sp_entity_id": "https://your-domain.com/auth/saml/metadata",
    "attribute_mapping": {
      "email": "email",
      "name": "displayName"
    }
  },
  "jit_provisioning": true,
  "default_role": "member"
}
```

#### Via Environment Variables

```bash
# SAML SP Configuration
SAML_SP_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----...
SAML_SP_CERTIFICATE=-----BEGIN CERTIFICATE-----...
SAML_WANT_ASSERTIONS_SIGNED=true
SAML_WANT_MESSAGES_SIGNED=true
```

### Step 4: Test SSO

```
GET /auth/saml/login?tenant=your-tenant

→ Redirect to IdP
→ Authenticate
→ Return to Incident Copilot
→ User session created
```

---

## 🔧 OIDC Configuration

### Prerequisites

- [ ] OIDC-compatible Identity Provider
- [ ] Client credentials (client_id, client_secret)
- [ ] Pro or Enterprise plan

### Step 1: Register OAuth Client

In your IdP, create an OAuth/OIDC client:

| Setting | Value |
|---------|-------|
| **Client Type** | Confidential |
| **Redirect URI** | `https://your-domain.com/auth/oidc/callback` |
| **Scopes** | openid, email, profile |

### Step 2: Configure Incident Copilot

```bash
POST /api/tenants/{tenant_id}/sso
{
  "type": "oidc",
  "config": {
    "issuer_url": "https://idp.example.com",
    "client_id": "your-client-id",
    "client_secret": "your-client-secret",
    "scopes": "openid email profile",
    "use_pkce": true
  },
  "jit_provisioning": true,
  "default_role": "member"
}
```

### Common IdP Configurations

#### Auth0

```json
{
  "issuer_url": "https://your-tenant.auth0.com",
  "client_id": "abc123...",
  "client_secret": "secret..."
}
```

#### Google Workspace

```json
{
  "issuer_url": "https://accounts.google.com",
  "client_id": "123456.apps.googleusercontent.com",
  "client_secret": "GOCSPX-..."
}
```

#### Keycloak

```json
{
  "issuer_url": "https://keycloak.example.com/realms/your-realm",
  "client_id": "incident-copilot",
  "client_secret": "secret..."
}
```

---

## 👥 Just-In-Time Provisioning

### What is JIT?

JIT (Just-In-Time) provisioning automatically creates user accounts when they first authenticate via SSO.

### Configuration

```json
{
  "jit_provisioning": true,
  "default_role": "member",
  "auto_sync_attributes": true
}
```

### Behavior

1. User authenticates via SSO
2. If user doesn't exist → Create with default role
3. Sync attributes from IdP (name, email)
4. Create session

### Disable JIT

For manual user provisioning only:

```json
{
  "jit_provisioning": false
}
```

Users must be pre-created before they can sign in.

---

## 🔑 Environment Variables

### SSO General

| Variable | Description | Default |
|----------|-------------|---------|
| `SSO_SESSION_LIFETIME_MINUTES` | Auth flow timeout | 10 |
| `SSO_JIT_PROVISIONING_DEFAULT` | Default JIT setting | true |

### SAML Specific

| Variable | Description |
|----------|-------------|
| `SAML_SP_PRIVATE_KEY` | SP signing key (PEM) |
| `SAML_SP_CERTIFICATE` | SP certificate (PEM) |
| `SAML_WANT_ASSERTIONS_SIGNED` | Require signed assertions |
| `SAML_WANT_MESSAGES_SIGNED` | Require signed messages |

### OIDC Specific

| Variable | Description | Default |
|----------|-------------|---------|
| `OIDC_DEFAULT_SCOPES` | Default scopes | `openid email profile` |
| `OIDC_USE_PKCE_DEFAULT` | Enable PKCE | true |

---

## 🔄 Attribute Mapping

Map IdP attributes to Incident Copilot user fields:

### SAML Attributes

```json
{
  "attribute_mapping": {
    "email": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
    "name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
    "first_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
    "last_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname"
  }
}
```

### OIDC Claims

```json
{
  "claim_mapping": {
    "email": "email",
    "name": "name",
    "picture": "picture"
  }
}
```

---

## 🔒 Security Considerations

### Certificate Management

- Rotate SP certificates annually
- Monitor IdP certificate expiration
- Store private keys securely

### Session Security

- Sessions expire after 12 hours by default
- Refresh tokens valid for 30 days
- Single logout supported (SAML)

### Domain Verification

Restrict SSO to verified email domains:

```json
{
  "allowed_domains": ["company.com", "subsidiary.com"]
}
```

---

## 🐛 Troubleshooting

### "SAML Response Invalid"

**Causes:**
- Clock skew between IdP and SP
- Certificate mismatch
- Incorrect ACS URL

**Solutions:**
- Sync server clocks (NTP)
- Verify certificate matches IdP config
- Check ACS URL in IdP configuration

### "User Not Provisioned"

**Cause:** JIT disabled and user doesn't exist

**Solution:**
- Enable JIT provisioning, OR
- Pre-create user accounts

### "Invalid Redirect URI"

**Cause:** Callback URL mismatch

**Solution:**
- Verify redirect URI matches exactly
- Check for trailing slashes
- Ensure HTTPS

### "Insufficient Scopes"

**Cause:** IdP not providing required claims

**Solution:**
- Add `email` and `profile` scopes
- Check attribute/claim mappings
- Verify IdP user has required attributes

---

## 📚 Related Documentation

- [User Management](./user-management.md) - User provisioning
- [Tenant Setup](./tenant-setup.md) - Multi-tenant SSO
- [API Keys](./api-keys.md) - Service account access

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or open an issue on GitHub.*
