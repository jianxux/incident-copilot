# Enterprise Setup Guide

This guide covers enterprise deployment of Incident Copilot, including Single Sign-On (SSO), Role-Based Access Control (RBAC), and multi-tenant configuration.

## Overview

Enterprise deployments require additional security, compliance, and organizational controls. This guide walks you through:

- SSO integration with major identity providers
- RBAC configuration for fine-grained permissions
- Multi-tenant setup for organizations with multiple teams
- Compliance and audit logging

---

## Prerequisites

Before beginning enterprise setup:

- [ ] Admin access to your identity provider (Okta, Azure AD, etc.)
- [ ] Incident Copilot Enterprise license key
- [ ] Database configured for multi-tenant isolation
- [ ] SSL certificates for secure communication

---

## 1. Single Sign-On (SSO) Configuration

### Supported Identity Providers

| Provider | Protocol | Status |
|----------|----------|--------|
| Okta | SAML 2.0, OIDC | ✅ Fully Supported |
| Azure AD | SAML 2.0, OIDC | ✅ Fully Supported |
| Google Workspace | OIDC | ✅ Fully Supported |
| OneLogin | SAML 2.0 | ✅ Fully Supported |
| Ping Identity | SAML 2.0 | ✅ Fully Supported |
| Custom SAML | SAML 2.0 | ✅ Supported |

### Step 1: Enable SSO in Configuration

```yaml
# config/enterprise.yaml
auth:
  sso:
    enabled: true
    provider: okta  # okta, azure, google, onelogin, saml
    enforce_sso: true  # Disable password login
    
  session:
    timeout_minutes: 480
    refresh_enabled: true
```

### Step 2: Configure Okta (Example)

**In Okta Admin Console:**

1. Navigate to **Applications** → **Create App Integration**
2. Select **SAML 2.0** and click **Next**
3. Configure the following:

```
App name: Incident Copilot
Single sign-on URL: https://your-domain.com/auth/saml/callback
Audience URI: https://your-domain.com/auth/saml/metadata
Name ID format: EmailAddress
```

<!-- Diagram: Okta SAML Configuration Screen -->
<!-- Shows the Okta admin panel with SAML settings highlighted -->

4. Download the **Identity Provider metadata** XML file

**In Incident Copilot:**

```yaml
# config/sso/okta.yaml
saml:
  idp_metadata_url: "https://your-org.okta.com/app/xxx/sso/saml/metadata"
  sp_entity_id: "https://your-domain.com/auth/saml/metadata"
  assertion_consumer_service_url: "https://your-domain.com/auth/saml/callback"
  
  attribute_mapping:
    email: "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"
    first_name: "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname"
    last_name: "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname"
    groups: "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups"
```

### Step 3: Configure Azure AD (Example)

```yaml
# config/sso/azure.yaml
oidc:
  client_id: "${AZURE_CLIENT_ID}"
  client_secret: "${AZURE_CLIENT_SECRET}"
  tenant_id: "${AZURE_TENANT_ID}"
  
  scopes:
    - openid
    - profile
    - email
    - offline_access
    
  redirect_uri: "https://your-domain.com/auth/oidc/callback"
```

### Step 4: Test SSO Integration

```bash
# Verify SSO configuration
incident-copilot sso verify --provider okta

# Test authentication flow (dry run)
incident-copilot sso test --email test@company.com --dry-run

# View SSO logs
incident-copilot logs --filter auth.sso --tail
```

---

## 2. Role-Based Access Control (RBAC)

### Default Roles

| Role | Description | Permissions |
|------|-------------|-------------|
| `viewer` | Read-only access | View incidents, dashboards |
| `responder` | Incident response | + Create, update, acknowledge |
| `manager` | Team management | + Assign, close, reporting |
| `admin` | Full access | + Settings, users, integrations |
| `super_admin` | Multi-tenant admin | + Tenant management |

### Step 1: Define Custom Roles

```yaml
# config/rbac/roles.yaml
roles:
  - name: sre_lead
    description: "SRE Team Lead with elevated permissions"
    inherits: responder
    permissions:
      - incidents:assign
      - incidents:escalate
      - runbooks:execute
      - reports:generate
      - oncall:manage
      
  - name: security_analyst
    description: "Security team member"
    inherits: viewer
    permissions:
      - incidents:view:security
      - incidents:comment
      - audit_logs:view
      - compliance:view
```

### Step 2: Configure Permission Scopes

```yaml
# config/rbac/scopes.yaml
scopes:
  # Incident permissions
  incidents:
    view: "View incident details"
    create: "Create new incidents"
    update: "Update incident properties"
    assign: "Assign incidents to users"
    escalate: "Escalate to higher severity"
    close: "Close/resolve incidents"
    delete: "Delete incidents (audit retained)"
    
  # Team-scoped permissions
  incidents:view:security:
    description: "View security-tagged incidents only"
    filter:
      tags: ["security", "breach", "vulnerability"]
      
  incidents:view:team:
    description: "View incidents assigned to user's team"
    filter:
      team: "${user.team_id}"
```

### Step 3: Assign Roles to Users

**Via CLI:**

```bash
# Assign role to user
incident-copilot rbac assign --user alice@company.com --role sre_lead

# Assign role to group (from SSO)
incident-copilot rbac assign --group "SRE Team" --role sre_lead

# List user permissions
incident-copilot rbac permissions --user alice@company.com
```

**Via API:**

```bash
curl -X POST https://api.incident-copilot.com/v1/rbac/assignments \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_abc123",
    "role": "sre_lead",
    "scope": {
      "teams": ["team_infrastructure", "team_platform"]
    }
  }'
```

### Step 4: Group-Based Role Mapping

Map SSO groups to Incident Copilot roles automatically:

```yaml
# config/rbac/group-mapping.yaml
group_mappings:
  - sso_group: "Engineering"
    role: responder
    
  - sso_group: "SRE"
    role: sre_lead
    
  - sso_group: "Security"
    role: security_analyst
    
  - sso_group: "Platform Admins"
    role: admin
    
  # Regex matching
  - sso_group_pattern: "^Team-.*-Leads$"
    role: manager
```

---

## 3. Multi-Tenant Configuration

### Tenant Isolation Models

| Model | Description | Use Case |
|-------|-------------|----------|
| **Database per tenant** | Separate databases | Maximum isolation, compliance |
| **Schema per tenant** | Shared DB, separate schemas | Good isolation, easier backup |
| **Row-level security** | Shared tables with tenant_id | Cost-effective, simpler ops |

### Step 1: Enable Multi-Tenancy

```yaml
# config/multi-tenant.yaml
multi_tenant:
  enabled: true
  isolation_model: schema  # database, schema, row_level
  
  tenant_resolution:
    strategy: subdomain  # subdomain, header, path
    header_name: X-Tenant-ID  # if strategy is header
    
  defaults:
    max_users: 100
    max_incidents_per_month: 10000
    retention_days: 365
```

### Step 2: Create Tenants

```bash
# Create a new tenant
incident-copilot tenant create \
  --name "Acme Corp" \
  --slug acme \
  --admin-email admin@acme.com \
  --plan enterprise

# Output:
# Tenant created successfully
# Tenant ID: tenant_acme123
# Admin invite sent to: admin@acme.com
# URL: https://acme.incident-copilot.com
```

### Step 3: Configure Tenant-Specific Settings

```yaml
# config/tenants/acme.yaml
tenant:
  id: tenant_acme123
  name: "Acme Corp"
  slug: acme
  
  settings:
    timezone: "America/Los_Angeles"
    date_format: "MM/DD/YYYY"
    branding:
      logo_url: "https://cdn.acme.com/logo.png"
      primary_color: "#1a73e8"
      
  limits:
    max_users: 500
    max_incidents_per_month: 50000
    max_integrations: 25
    
  features:
    ai_copilot: true
    runbooks: true
    advanced_analytics: true
```

<!-- Diagram: Multi-Tenant Architecture -->
<!-- Shows load balancer routing to tenant-specific schemas/databases -->

### Step 4: Tenant Data Migration

```bash
# Export tenant data
incident-copilot tenant export \
  --tenant-id tenant_acme123 \
  --output /backups/acme_export.tar.gz

# Import to new tenant
incident-copilot tenant import \
  --tenant-id tenant_newacme456 \
  --input /backups/acme_export.tar.gz \
  --dry-run  # Preview first
```

---

## 4. Audit Logging & Compliance

### Enable Comprehensive Audit Logging

```yaml
# config/audit.yaml
audit:
  enabled: true
  retention_days: 2555  # 7 years for compliance
  
  events:
    - auth.*           # All authentication events
    - incidents.*      # All incident operations
    - settings.*       # Configuration changes
    - rbac.*           # Permission changes
    - integrations.*   # Integration modifications
    
  storage:
    primary: postgresql
    secondary: s3  # Long-term archival
    s3_bucket: "company-audit-logs"
    
  encryption:
    at_rest: true
    key_id: "arn:aws:kms:us-east-1:xxx:key/xxx"
```

### Query Audit Logs

```bash
# View recent authentication events
incident-copilot audit query \
  --event-type "auth.*" \
  --since "24h" \
  --limit 100

# Export for compliance review
incident-copilot audit export \
  --start-date 2024-01-01 \
  --end-date 2024-03-31 \
  --format csv \
  --output Q1-2024-audit.csv
```

---

## Best Practices

1. **Always enable MFA** - Require MFA for all admin accounts
2. **Use group-based roles** - Easier to manage than individual assignments
3. **Principle of least privilege** - Start with minimal permissions
4. **Regular access reviews** - Quarterly review of role assignments
5. **Audit log monitoring** - Set up alerts for suspicious activity
6. **Separate production tenant** - Use separate tenants for dev/staging/prod

---

## Common Pitfalls

| Issue | Cause | Solution |
|-------|-------|----------|
| SSO login loops | Mismatched callback URLs | Verify URLs match exactly in IdP and config |
| Users can't access incidents | Missing team scope | Check role scope includes user's team |
| Tenant data leakage | Row-level security misconfigured | Audit RLS policies, test with different users |
| Audit gaps | Events not configured | Review audit event list, add missing categories |

---

## Troubleshooting

```bash
# Debug SSO issues
incident-copilot sso debug --verbose

# Check RBAC evaluation
incident-copilot rbac check \
  --user alice@company.com \
  --action incidents:escalate \
  --resource incident_xyz

# Verify tenant isolation
incident-copilot tenant verify --tenant-id tenant_acme123
```

---

## Next Steps

- [SLA Configuration](./sla-configuration.md) - Set up SLA policies for your organization
- [Escalation Policies](./escalation-policies.md) - Configure escalation workflows
- [Webhook Integration](./webhook-integration.md) - Integrate with external systems
