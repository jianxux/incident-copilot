# 📐 Linear Integration

Linear is a modern issue tracker that integrates with Incident Copilot for automatic incident ticket creation and management.

---

## 📋 Prerequisites

- [ ] Linear workspace
- [ ] Access to create API keys
- [ ] Team configured for incident tracking
- [ ] Permission to create issues in the target team

---

## 🔧 Step-by-Step Setup

### Step 1: Create a Linear API Key

1. Log in to Linear at [linear.app](https://linear.app)
2. Go to **Settings** → **API** (or visit [linear.app/settings/api](https://linear.app/settings/api))
3. Click **Create new API key**
4. Configure:
   - **Label:** Incident Copilot
5. Click **Create**
6. ⚠️ **Copy the API key** (starts with `lin_api_`)

### Step 2: Find Your Team ID

#### Option A: Via Linear URL

1. Go to your team's issues page in Linear
2. Note the team key from the URL (e.g., `ENG`, `OPS`)
3. Use the GraphQL API to get the UUID:

```bash
curl -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ teams { nodes { id name key } } }"}'
```

#### Option B: Via API Explorer

1. Go to the [Linear API Explorer](https://studio.apollographql.com/public/Linear-API/variant/current/explorer)
2. Run the teams query
3. Copy your team's `id` field

### Step 3: (Optional) Find Label IDs

To auto-apply labels to incidents:

```bash
curl -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ team(id: \"YOUR_TEAM_ID\") { labels { nodes { id name color } } } }"}'
```

### Step 4: Configure Environment Variables

```bash
# Linear Configuration
LINEAR_API_KEY=lin_api_xxxxxxxxxxxxxxxxxxxx
LINEAR_TEAM_ID=your-team-uuid-here

# Optional: Auto-apply labels
LINEAR_LABEL_IDS=["label-uuid-1","label-uuid-2"]
```

### Step 5: Restart Incident Copilot

```bash
docker-compose restart
```

---

## ✅ Testing the Integration

### Test API Access

```bash
curl -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ viewer { id name email } }"}'
```

**Expected:** Your Linear user information.

### Test Team Access

```bash
curl -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ team(id: \"YOUR_TEAM_ID\") { id name key } }"}'
```

**Expected:** Team details.

### Create a Test Issue

```bash
curl -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "mutation { issueCreate(input: { teamId: \"YOUR_TEAM_ID\", title: \"Test Issue\" }) { success issue { id identifier url } } }"
  }'
```

---

## 🔐 Required Permissions

### API Key Permissions

Linear API keys have full access to workspace data by default. Required capabilities:

| Capability | Purpose |
|------------|---------|
| Create Issues | Create incident tickets |
| Read Teams | Access team information |
| Read Labels | Apply labels to issues |
| Read Workflow States | Transition issue states |
| Create Comments | Add context to issues |

---

## 🔑 Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `LINEAR_API_KEY` | ✅ | Linear API key | `lin_api_xxxx` |
| `LINEAR_TEAM_ID` | ✅ | Team UUID | `a1b2c3d4-...` |
| `LINEAR_LABEL_IDS` | ⚡ Optional | Label UUIDs to apply | `["uuid1","uuid2"]` |

---

## 📊 Issue Creation

### Default Issue Fields

When an incident fires, Incident Copilot creates an issue with:

| Field | Value |
|-------|-------|
| **Title** | `[SEV-X] {service}: {incident title}` |
| **Description** | Context card content (Markdown) |
| **Priority** | Mapped from incident severity |
| **Labels** | Configured labels (if set) |
| **State** | Triage (initial workflow state) |

### Priority Mapping

| Incident Severity | Linear Priority |
|-------------------|-----------------|
| Critical (SEV1) | 1 - Urgent |
| High (SEV2) | 2 - High |
| Medium (SEV3) | 3 - Normal |
| Low (SEV4) | 4 - Low |

### Example Issue

```
┌─────────────────────────────────────────────────────┐
│ ENG-123  [SEV-2] payments-api: High Error Rate      │
├─────────────────────────────────────────────────────┤
│ Priority: ⚡ High                                    │
│ Status: 🔵 Triage                                   │
│ Labels: 🔴 Incident, 💳 Payments                    │
├─────────────────────────────────────────────────────┤
│ ## Incident Details                                 │
│ - **Service:** payments-api                         │
│ - **Severity:** HIGH                                │
│ - **Triggered:** 2025-01-15 10:30 UTC               │
│ - **Alert:** [View in PagerDuty](https://...)       │
│                                                     │
│ ## Recent Deployments                               │
│ - `abc1234` by @sarah - Fix retry logic             │
│                                                     │
│ ## AI Analysis                                      │
│ The service is experiencing connection timeouts     │
│ when calling Stripe's API...                        │
└─────────────────────────────────────────────────────┘
```

---

## 🔄 Workflow Integration

### Workflow States

Incident Copilot maps incident states to Linear workflow states:

| Incident State | Linear State Type |
|----------------|-------------------|
| New | `triage` |
| In Progress | `started` |
| Resolved | `completed` |

### Automatic Transitions

When an incident is resolved, Incident Copilot:
1. Adds a resolution comment
2. Transitions to the first `completed` state (usually "Done")

---

## 🏷️ Label Configuration

### Creating Incident Labels

In Linear:
1. Go to **Settings** → **Labels**
2. Create labels like:
   - `Incident` (red)
   - `SEV1` (red)
   - `SEV2` (orange)
   - `SEV3` (yellow)
   - `Postmortem Needed` (purple)

### Configuring Auto-Apply

```bash
LINEAR_LABEL_IDS='["incident-label-uuid", "service-label-uuid"]'
```

Find label UUIDs via the API query shown earlier.

---

## 🐛 Troubleshooting

### "Authentication required"

**Symptoms:** API calls fail with auth errors

**Checks:**
```bash
# Verify token format
echo $LINEAR_API_KEY | head -c 12
# Should start with "lin_api_"
```

**Solutions:**
- Regenerate API key
- Check for whitespace in `.env`
- Ensure token hasn't been revoked

### "Team not found"

**Symptoms:** Cannot create issues

**Checks:**
```bash
# List all teams
curl -X POST https://api.linear.app/graphql \
  -H "Authorization: $LINEAR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ teams { nodes { id name key } } }"}'
```

**Solutions:**
- Verify `LINEAR_TEAM_ID` is a UUID (not the team key)
- Check you have access to the team
- Ensure team exists and isn't archived

### "No done state found"

**Symptoms:** Issues created but not transitioned

**Cause:** Team has no `completed` workflow state

**Solutions:**
1. Go to **Settings** → **Teams** → Your Team → **Workflow**
2. Ensure at least one state has type `completed`
3. Usually "Done" or "Closed"

### Rate Limiting

**Symptoms:** HTTP 429 errors

**Info:** Linear allows ~400 requests/minute

**Solutions:**
- Implement request batching
- Add caching for repeated queries
- Contact Linear support for increases

---

## 🆚 Linear vs Jira Comparison

| Feature | Linear | Jira |
|---------|--------|------|
| API Type | GraphQL | REST |
| Authentication | API Key (Bearer) | Email + Token (Basic) |
| Issue ID Format | `ENG-123` | `PROJ-123` |
| Setup Complexity | ⭐ Easy | ⭐⭐ Medium |
| Workflow | Team-based | Project-based |
| Best For | Startups, modern teams | Enterprise, complex workflows |

---

## 📚 Additional Resources

- [Linear API Documentation](https://developers.linear.app/docs)
- [Linear GraphQL API Explorer](https://studio.apollographql.com/public/Linear-API/variant/current/explorer)
- [Linear Webhooks](https://developers.linear.app/docs/graphql/webhooks)
- [Jira Integration](./jira.md) (alternative)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or open an issue on GitHub.*
