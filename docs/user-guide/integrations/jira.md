# 🎫 Jira Integration

Jira integration enables Incident Copilot to automatically create and manage incident tickets in Jira Cloud or Jira Server.

---

## 📋 Prerequisites

- [ ] Jira Cloud or Jira Server account
- [ ] API token (Cloud) or Personal Access Token (Server)
- [ ] Project with appropriate issue types configured
- [ ] Permission to create issues in the target project

---

## 🔧 Step-by-Step Setup

### Step 1: Create an API Token (Jira Cloud)

1. Go to [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click **Create API token**
3. Configure:
   - **Label:** Incident Copilot
4. Click **Create**
5. ⚠️ **Copy the API token**

### Step 1b: Create Personal Access Token (Jira Server)

1. Go to your Jira Server → **Profile** → **Personal Access Tokens**
2. Click **Create token**
3. Configure:
   - **Token name:** Incident Copilot
   - **Expiry:** Set appropriate expiry
4. Click **Create**
5. ⚠️ **Copy the token**

### Step 2: Identify Your Project

1. Go to your Jira project
2. Note the **Project Key** (e.g., `INCIDENT`, `OPS`, `SRE`)
3. Verify the project has an appropriate issue type (e.g., "Incident", "Bug", "Task")

### Step 3: Configure Environment Variables

```bash
# Jira Configuration
JIRA_BASE_URL=https://yourcompany.atlassian.net  # Or your Server URL
JIRA_EMAIL=your-email@company.com  # Your Atlassian account email
JIRA_API_TOKEN=your-api-token-here
JIRA_DEFAULT_PROJECT=INCIDENT  # Your project key
```

### Step 4: Restart Incident Copilot

```bash
docker-compose restart
```

---

## ✅ Testing the Integration

### Test API Access

```bash
curl -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "$JIRA_BASE_URL/rest/api/3/myself"
```

**Expected:** Your Jira user profile information.

### Test Project Access

```bash
curl -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "$JIRA_BASE_URL/rest/api/3/project/INCIDENT"
```

**Expected:** Project details (replace `INCIDENT` with your project key).

### Create a Test Issue

```bash
curl -X POST \
  -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  -H "Content-Type: application/json" \
  "$JIRA_BASE_URL/rest/api/3/issue" \
  -d '{
    "fields": {
      "project": {"key": "INCIDENT"},
      "summary": "Test Incident from Incident Copilot",
      "issuetype": {"name": "Task"}
    }
  }'
```

---

## 🔐 Required Permissions

### Jira Cloud Permissions

| Permission | Required | Purpose |
|------------|----------|---------|
| Browse Projects | ✅ Yes | View project and issues |
| Create Issues | ✅ Yes | Create incident tickets |
| Edit Issues | ⚡ Optional | Update ticket status |
| Add Comments | ⚡ Optional | Add context to tickets |

### Project Role

The API user should have at least **Developer** or **Administrator** role in the target project.

---

## 🔑 Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `JIRA_BASE_URL` | ✅ | Jira instance URL | `https://company.atlassian.net` |
| `JIRA_EMAIL` | ✅ | Atlassian account email | `user@company.com` |
| `JIRA_API_TOKEN` | ✅ | API token | `abc123...` |
| `JIRA_DEFAULT_PROJECT` | ✅ | Default project key | `INCIDENT` |

---

## 📊 Issue Creation

### Default Issue Fields

When an incident fires, Incident Copilot creates an issue with:

| Field | Source |
|-------|--------|
| **Summary** | `[SEV-X] {service}: {incident title}` |
| **Description** | Context card content (deployments, logs, AI summary) |
| **Priority** | Mapped from incident severity |
| **Labels** | `incident`, service name |

### Priority Mapping

| Incident Severity | Jira Priority |
|-------------------|---------------|
| Critical | Highest |
| High | High |
| Medium | Medium |
| Low | Low |

### Example Issue

```
┌─────────────────────────────────────────────────────┐
│ INCIDENT-123                                        │
│ [SEV-2] payments-api: High Error Rate               │
├─────────────────────────────────────────────────────┤
│ Priority: High                                      │
│ Status: To Do                                       │
│ Labels: incident, payments-api                      │
├─────────────────────────────────────────────────────┤
│ Description:                                        │
│                                                     │
│ ## Incident Details                                 │
│ - Service: payments-api                             │
│ - Severity: HIGH                                    │
│ - Triggered: 2025-01-15 10:30 UTC                   │
│ - PagerDuty: https://...                            │
│                                                     │
│ ## Recent Deployments                               │
│ - abc1234 by @sarah - Fix retry logic               │
│                                                     │
│ ## AI Analysis                                      │
│ The service is experiencing connection timeouts...  │
└─────────────────────────────────────────────────────┘
```

---

## 🔄 Workflow Integration

### Automatic Status Updates (Future)

Planned features:
- Acknowledge → Move to "In Progress"
- Resolve → Move to "Done"
- Link postmortem when generated

### Custom Workflows

If your project uses custom workflows, configure the status mapping:

```bash
# Future configuration
# JIRA_STATUS_MAP='{"acknowledged": "In Progress", "resolved": "Done"}'
```

---

## 🏷️ Custom Fields

### Adding Custom Fields

To include custom fields in created issues:

```bash
# Future configuration
# JIRA_CUSTOM_FIELDS='{
#   "customfield_10001": "Incident",
#   "customfield_10002": "{severity}"
# }'
```

### Common Custom Fields

| Field Type | Example |
|------------|---------|
| Team | `customfield_10001` |
| Environment | `customfield_10002` |
| Affected Users | `customfield_10003` |

---

## 🐛 Troubleshooting

### "Unauthorized" Error

**Symptoms:** HTTP 401 responses

**Checks:**
```bash
# Test authentication
curl -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "$JIRA_BASE_URL/rest/api/3/myself"
```

**Solutions:**
- Verify email is your Atlassian account email
- Regenerate API token
- Check token hasn't expired

### "Project Not Found"

**Symptoms:** HTTP 404 when creating issues

**Checks:**
```bash
# List accessible projects
curl -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "$JIRA_BASE_URL/rest/api/3/project"
```

**Solutions:**
- Verify project key is correct (case-sensitive)
- Check user has access to the project
- Ensure project exists and isn't archived

### "Issue Type Not Found"

**Symptoms:** Error about missing issue type

**Checks:**
```bash
# List issue types for project
curl -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "$JIRA_BASE_URL/rest/api/3/project/INCIDENT/statuses"
```

**Solutions:**
- Check project has the expected issue type
- Configure custom issue type name if needed

### "Field Not Editable"

**Symptoms:** Error about required fields

**Cause:** Project requires fields Incident Copilot doesn't set

**Solutions:**
- Modify project settings to make fields optional
- Use custom field configuration (future feature)

---

## 📚 Additional Resources

- [Jira Cloud REST API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/)
- [Jira API Tokens](https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/)
- [Jira Permissions](https://confluence.atlassian.com/adminjiraserver/managing-project-permissions-938847145.html)
- [Linear Integration](./linear.md) (alternative)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or open an issue on GitHub.*
