# 🐙 GitHub Integration

GitHub integration enables Incident Copilot to fetch recent deployments, commits, and code ownership information when incidents occur.

---

## 📋 Prerequisites

- [ ] GitHub account with access to your organization's repositories
- [ ] Permission to create personal access tokens or GitHub Apps
- [ ] Repository names that map to your service names

---

## 🔧 Setup Options

You have two options for authenticating with GitHub:

| Option | Best For | Token Limit | Complexity |
|--------|----------|-------------|------------|
| **Personal Access Token** | Quick setup, small teams | 5,000 req/hour | ⭐ Easy |
| **GitHub App** | Production, organizations | 15,000 req/hour | ⭐⭐ Medium |

---

## 🔧 Option A: Personal Access Token (PAT)

### Step 1: Create a Personal Access Token

1. Go to GitHub → **Settings** → **Developer settings** → **Personal access tokens**
2. Click **Tokens (classic)** → **Generate new token (classic)**

   ```
   ┌─────────────────────────────────────────┐
   │  GitHub Settings                        │
   │  ├── Account                            │
   │  ├── Appearance                         │
   │  └── Developer settings                 │
   │      └── Personal access tokens         │
   │          ├── Fine-grained tokens        │
   │          └── Tokens (classic)  ◄──      │
   └─────────────────────────────────────────┘
   ```

3. Configure the token:

   | Setting | Value |
   |---------|-------|
   | **Note** | Incident Copilot |
   | **Expiration** | 90 days (or custom) |

4. Select scopes:

   | Scope | Required | Purpose |
   |-------|----------|---------|
   | `repo` | ✅ Yes | Access private repositories |
   | `public_repo` | ⚡ Alternative | Only if using public repos |

5. Click **Generate token**
6. ⚠️ **Copy the token immediately** (starts with `ghp_`)

### Step 2: Configure Environment Variables

```bash
# GitHub Configuration (PAT method)
GITHUB_TOKEN=ghp_your-personal-access-token
GITHUB_ORG=your-organization-name
```

---

## 🔧 Option B: GitHub App (Recommended for Production)

### Step 1: Create a GitHub App

1. Go to your organization → **Settings** → **Developer settings** → **GitHub Apps**
2. Click **New GitHub App**
3. Configure:

   | Setting | Value |
   |---------|-------|
   | **App name** | Incident Copilot |
   | **Homepage URL** | `https://your-domain.com` |
   | **Webhook** | Uncheck "Active" (not needed) |

4. Set **Repository Permissions**:

   | Permission | Access | Purpose |
   |------------|--------|---------|
   | Contents | Read-only | Fetch commits, files |
   | Metadata | Read-only | Repository info |

5. Set **Organization Permissions** (optional):

   | Permission | Access | Purpose |
   |------------|--------|---------|
   | Members | Read-only | CODEOWNERS lookup |

6. Click **Create GitHub App**

### Step 2: Generate Private Key

1. On the app settings page, scroll to **Private keys**
2. Click **Generate a private key**
3. Save the downloaded `.pem` file securely

### Step 3: Install the App

1. Go to your app → **Install App**
2. Select your organization
3. Choose repository access:
   - **All repositories**, OR
   - **Only select repositories** (choose your service repos)
4. Click **Install**
5. Note the **Installation ID** from the URL

### Step 4: Configure Environment Variables

```bash
# GitHub Configuration (App method)
GITHUB_APP_ID=123456
GITHUB_APP_INSTALLATION_ID=12345678
GITHUB_APP_PRIVATE_KEY_PATH=/path/to/private-key.pem
# Or inline (base64 encoded):
# GITHUB_APP_PRIVATE_KEY=LS0tLS1CRUdJTi...
GITHUB_ORG=your-organization-name
```

---

## ✅ Testing the Integration

### Test API Access (PAT)

```bash
curl -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/user"
```

**Expected:** Your GitHub user information.

### Test Repository Access

```bash
curl -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/repos/$GITHUB_ORG/your-service/commits?per_page=5"
```

**Expected:** List of recent commits.

### Check Rate Limit

```bash
curl -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/rate_limit"
```

**Expected:** Shows remaining API calls.

---

## 🔐 Required Permissions/Scopes

### Personal Access Token Scopes

| Scope | Required | Purpose |
|-------|----------|---------|
| `repo` | ✅ Yes | Full access to private repos |
| `public_repo` | ⚡ Alternative | Public repos only |

### GitHub App Permissions

| Permission | Access | Purpose |
|------------|--------|---------|
| Contents | Read | Fetch commits, CODEOWNERS |
| Metadata | Read | Repository information |
| Members (org) | Read | Team and ownership info |

---

## 🔑 Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `GITHUB_TOKEN` | ✅ (PAT) | Personal access token | `ghp_xxxx` |
| `GITHUB_ORG` | ✅ | Organization name | `mycompany` |
| `GITHUB_APP_ID` | ✅ (App) | GitHub App ID | `123456` |
| `GITHUB_APP_INSTALLATION_ID` | ✅ (App) | Installation ID | `12345678` |
| `GITHUB_APP_PRIVATE_KEY_PATH` | ✅ (App) | Path to .pem file | `/secrets/key.pem` |
| `SERVICE_REPO_MAP` | ⚡ Optional | Service to repo mapping | `{"svc": "org/repo"}` |

---

## 📊 Service to Repository Mapping

### Default Behavior

By default, Incident Copilot assumes:
- Service name = Repository name
- Repository is in `GITHUB_ORG`

Example:
- Service: `payments-api`
- Repository: `myorg/payments-api`

### Custom Mapping

For different naming conventions, use `SERVICE_REPO_MAP`:

```bash
SERVICE_REPO_MAP='{
  "payments-api": "myorg/payment-service",
  "auth": "myorg/identity-platform",
  "frontend": "myorg/web-app"
}'
```

---

## 📂 What Data is Fetched

### Recent Commits

Incident Copilot fetches the last 10 commits to the default branch:

```json
{
  "sha": "abc1234",
  "author": "sarah",
  "message": "Fix retry logic for Stripe API",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

### CODEOWNERS

If a `CODEOWNERS` file exists, Incident Copilot extracts owners:

```
# CODEOWNERS
*.py @backend-team
/payments/ @payments-team @sarah
```

### Deployment Tags (Optional)

If using release tags, recent deployments are identified:

```bash
git tag -l "deploy-*" --sort=-creatordate
```

---

## 🐛 Troubleshooting

### "Bad credentials" Error

**Symptoms:** HTTP 401 errors

**Checks:**
```bash
# Verify token
echo $GITHUB_TOKEN | head -c 10
# Should start with "ghp_"
```

**Solutions:**
- Regenerate the token
- Ensure token hasn't expired
- Check for extra whitespace

### "Not Found" for Repository

**Symptoms:** HTTP 404 when fetching commits

**Checks:**
```bash
# Verify repo exists and is accessible
curl -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/repos/$GITHUB_ORG/service-name"
```

**Solutions:**
- Check repository name spelling
- Verify token has access to private repos
- Add explicit mapping in `SERVICE_REPO_MAP`

### "Rate limit exceeded"

**Symptoms:** HTTP 403 with rate limit message

**Info:**
- PAT: 5,000 requests/hour
- GitHub App: 15,000 requests/hour

**Solutions:**
- Switch to GitHub App for higher limits
- Implement caching (built-in)
- Reduce polling frequency

### Missing CODEOWNERS

**Symptoms:** No owners shown in context cards

**Checks:**
1. Verify `CODEOWNERS` file exists in repo root or `.github/`
2. Check file format is correct

**Solutions:**
- Create `CODEOWNERS` file
- Use GitHub's CODEOWNERS syntax

### No Recent Commits Shown

**Symptoms:** "No recent deployments" in context cards

**Cause:** Service name doesn't match repo name

**Solution:**
```bash
# Add explicit mapping
SERVICE_REPO_MAP='{"pagerduty-service-name": "org/actual-repo"}'
```

---

## 🔄 GitHub Enterprise

For GitHub Enterprise (self-hosted):

```bash
# Set custom GitHub API URL
GITHUB_API_URL=https://github.mycompany.com/api/v3
GITHUB_TOKEN=ghp_xxxx
GITHUB_ORG=myorg
```

---

## 📚 Additional Resources

- [GitHub Personal Access Tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token)
- [GitHub Apps Documentation](https://docs.github.com/en/developers/apps)
- [CODEOWNERS Syntax](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
- [GitLab Integration](./gitlab.md) (alternative)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or open an issue on GitHub.*
