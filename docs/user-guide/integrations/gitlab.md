# 🦊 GitLab Integration

GitLab integration enables Incident Copilot to fetch recent deployments, merge requests, pipeline status, and code ownership when incidents occur.

---

## 📋 Prerequisites

- [ ] GitLab account (gitlab.com or self-hosted)
- [ ] Access to projects you want to monitor
- [ ] Permission to create personal access tokens
- [ ] Project paths mapped to service names

---

## 🔧 Step-by-Step Setup

### Step 1: Create a Personal Access Token

1. Log in to your GitLab instance
2. Go to **User Settings** → **Access Tokens**

   ```
   ┌─────────────────────────────────────────┐
   │  GitLab                                 │
   │  ├── Profile                            │
   │  ├── Preferences                        │
   │  └── Access Tokens  ◄──                 │
   │                                         │
   └─────────────────────────────────────────┘
   ```

3. Click **Add new token**
4. Configure:

   | Setting | Value |
   |---------|-------|
   | **Token name** | Incident Copilot |
   | **Expiration date** | Set appropriate date (max 1 year) |

5. Select scopes:

   | Scope | Required | Purpose |
   |-------|----------|---------|
   | `read_api` | ✅ Yes | Access project data, MRs, pipelines |
   | `read_repository` | ✅ Yes | Read commits and files |

   ```
   ┌─────────────────────────────────────────┐
   │  Personal Access Tokens                 │
   ├─────────────────────────────────────────┤
   │  Token name: Incident Copilot           │
   │  Expires at: 2026-01-01                 │
   │                                         │
   │  Select scopes:                         │
   │  ☑ read_api                             │
   │  ☑ read_repository                      │
   │  ☐ write_repository                     │
   │  ☐ read_registry                        │
   │                                         │
   │  [Create personal access token]         │
   └─────────────────────────────────────────┘
   ```

6. Click **Create personal access token**
7. ⚠️ **Copy the token immediately** (starts with `glpat-`)

### Step 2: Configure Project Mapping

GitLab projects use paths that include groups and subgroups. You **must** map services to project paths:

```bash
GITLAB_PROJECT_MAP='{
  "payments-api": "mygroup/payments",
  "auth-service": "mygroup/backend/auth-service",
  "frontend": "web/frontend-app"
}'
```

### Step 3: Configure Environment Variables

```bash
# GitLab Configuration
GITLAB_TOKEN=glpat-your-token-here
GITLAB_URL=https://gitlab.com  # Or your self-hosted URL
GITLAB_PROJECT_MAP='{"service-name": "group/project"}'
```

### Step 4: Restart Incident Copilot

```bash
# Docker
docker-compose restart

# Or local
# Stop and restart uvicorn
```

---

## ✅ Testing the Integration

### Test API Access

```bash
curl -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://gitlab.com/api/v4/user"
```

**Expected:** Your GitLab user information.

### Test Project Access

```bash
# URL-encode the project path (replace / with %2F)
curl -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://gitlab.com/api/v4/projects/mygroup%2Fpayments"
```

**Expected:** Project details.

### Test Commits Access

```bash
curl -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://gitlab.com/api/v4/projects/mygroup%2Fpayments/repository/commits?per_page=5"
```

**Expected:** List of recent commits.

---

## 🔐 Required Permissions/Scopes

### Token Scopes

| Scope | Required | Purpose |
|-------|----------|---------|
| `read_api` | ✅ Yes | Access project data, MRs, pipelines |
| `read_repository` | ✅ Yes | Read commits and files (CODEOWNERS) |
| `api` | ⚡ Alternative | Full API access (more than needed) |

### Project Access Levels

The token owner needs at least **Reporter** role on projects to:
- View commits
- View merge requests
- View pipelines
- Read CODEOWNERS file

---

## 🔑 Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `GITLAB_TOKEN` | ✅ | Personal access token | `glpat-xxxx` |
| `GITLAB_URL` | ⚡ Optional | GitLab instance URL | `https://gitlab.com` |
| `GITLAB_PROJECT_MAP` | ✅ | Service to project mapping | `{"svc": "group/proj"}` |

---

## 📂 Project Path Format

GitLab project paths include groups and subgroups:

| Type | Format | Example |
|------|--------|---------|
| Simple | `group/project` | `myorg/payments` |
| Subgroup | `group/subgroup/project` | `myorg/backend/auth` |
| Nested | `group/sub1/sub2/project` | `myorg/team/frontend/web` |

### Finding Your Project Path

1. Go to your project in GitLab
2. The path is in the URL: `gitlab.com/mygroup/subgroup/project`
3. Or find it in **Settings** → **General** → **Path**

---

## 📊 What Data is Fetched

### Recent Commits

Last 10 commits to the default branch:

```json
{
  "short_sha": "abc1234",
  "author": "sarah",
  "message": "Fix retry logic for API calls",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

### Recent Merge Requests

Recently merged MRs (last 7 days):

```json
{
  "title": "Fix payment processing",
  "author": "mike",
  "merged_at": "2025-01-14T15:00:00Z",
  "web_url": "https://gitlab.com/org/project/-/merge_requests/123"
}
```

### Pipeline Status

Recent pipeline results:

```json
{
  "status": "success",
  "ref": "main",
  "created_at": "2025-01-15T09:00:00Z"
}
```

### CODEOWNERS

If `CODEOWNERS` exists in repo root, `.gitlab/`, or `docs/`:

```
# CODEOWNERS
*.py @backend-team
/payments/ @payments-team
```

---

## 🌐 Self-Hosted GitLab

For self-hosted GitLab instances:

```bash
# Set your GitLab instance URL
GITLAB_URL=https://gitlab.mycompany.com
GITLAB_TOKEN=glpat-xxxx
```

### Self-Signed Certificates

If using self-signed SSL certificates:

```bash
# In your deployment
SSL_CERT_FILE=/path/to/ca-bundle.crt
# Or disable verification (not recommended)
GITLAB_VERIFY_SSL=false
```

---

## 🐛 Troubleshooting

### "401 Unauthorized" Error

**Symptoms:** All GitLab API calls fail

**Checks:**
```bash
# Verify token format
echo $GITLAB_TOKEN | head -c 10
# Should start with "glpat-"
```

**Solutions:**
- Regenerate the token
- Ensure token hasn't expired
- Check for extra whitespace

### "404 Project Not Found"

**Symptoms:** Cannot fetch project data

**Checks:**
```bash
# Test with URL-encoded project path
curl -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://gitlab.com/api/v4/projects/$(echo 'mygroup/project' | jq -sRr @uri)"
```

**Solutions:**
- Verify project path is correct
- Check project visibility (public/internal/private)
- Ensure token owner has access to the project
- URL-encode the project path (replace `/` with `%2F`)

### "No Commits Found"

**Symptoms:** Context cards show no deployments

**Cause:** Project mapping is incorrect

**Solution:**
```bash
# Verify mapping
echo $GITLAB_PROJECT_MAP | jq .

# Test the specific project
curl -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://gitlab.com/api/v4/projects/mygroup%2Fproject/repository/commits"
```

### Rate Limiting

**Symptoms:** HTTP 429 errors

**Info:** GitLab rate limits by tier:

| Tier | Requests/minute |
|------|-----------------|
| Free | 300 |
| Premium | 400 |
| Ultimate | 600 |
| Self-hosted | Configurable |

**Solutions:**
- Implement request caching (built-in)
- Reduce concurrent requests
- Contact GitLab admin for self-hosted

---

## 🔄 GitHub vs GitLab

| Feature | GitHub | GitLab |
|---------|--------|--------|
| Auth Method | PAT or App | PAT only |
| Project Path | `org/repo` | `group/subgroup/project` |
| Default Branch | Usually `main` | Could be `main` or `master` |
| CODEOWNERS | Root or `.github/` | Root, `.gitlab/`, or `docs/` |
| API Rate Limit | 5,000/hour (PAT) | 300-600/minute |

---

## 📚 Additional Resources

- [GitLab Personal Access Tokens](https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html)
- [GitLab API Documentation](https://docs.gitlab.com/ee/api/)
- [CODEOWNERS in GitLab](https://docs.gitlab.com/ee/user/project/codeowners/)
- [GitHub Integration](./github.md) (alternative)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or open an issue on GitHub.*
