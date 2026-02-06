# 🔐 SSO Configuration

Configure Single Sign-On with SAML or OIDC.

---

## 📋 Supported Providers

- Okta
- Azure AD
- Google Workspace
- OneLogin
- Auth0
- Any SAML 2.0 or OIDC provider

---

## 🔧 SAML Setup

### Step 1: Create Application in IdP

**Okta Example:**
1. Go to **Applications** → **Create App Integration**
2. Select **SAML 2.0**
3. Configure:
   - **Single Sign On URL:** `https://your-domain.com/auth/saml/callback`
   - **Audience URI:** `https://your-domain.com/auth/saml/metadata`
   - **Name ID format:** Email

### Step 2: Configure Incident Copilot

```bash
# .env
SSO_ENABLED=true
SSO_PROVIDER=saml
SAML_IDP_METADATA_URL=https://your-idp.com/metadata
SAML_SP_ENTITY_ID=https://your-domain.com/auth/saml/metadata
SAML_ACS_URL=https://your-domain.com/auth/saml/callback
```

---

## 🔧 OIDC Setup

### Step 1: Create Application

Create an OAuth 2.0/OIDC application in your IdP.

### Step 2: Configure Incident Copilot

```bash
# .env
SSO_ENABLED=true
SSO_PROVIDER=oidc
OIDC_CLIENT_ID=your-client-id
OIDC_CLIENT_SECRET=your-client-secret
OIDC_ISSUER_URL=https://your-idp.com
OIDC_REDIRECT_URI=https://your-domain.com/auth/oidc/callback
```

---

## 👥 Attribute Mapping

Map IdP attributes to Incident Copilot fields:

```bash
SSO_ATTRIBUTE_MAP='{
  "email": "email",
  "firstName": "given_name",
  "lastName": "family_name",
  "role": "groups"
}'
```

---

## 📚 Related Documentation

- [User Management](./user-management.md)
- [Tenant Setup](./tenant-setup.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
