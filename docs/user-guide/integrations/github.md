# 🐙 GitHub Integration

GitHub integration enables Incident Copilot to fetch recent deployments, commits, and code owners for your services.

---

## Overview

| Feature | Status |
|---------|--------|
| Recent commits | ✅ Supported |
| Pull request links | ✅ Supported |
| Code owners (CODEOWNERS) | ✅ Supported |
| Deployment tracking | ✅ Supported |
| OAuth login | ✅ Supported |

---

## What It Provides

When an incident fires, Incident Copilot fetches from GitHub:

- **Recent commits** - Last 5 commits to the main branch
- **Merged PRs** - Recently merged pull requests
- **Deployments** - GitHub Deployments if used
- **Code owners** - From CODEOWNERS file for incident routing

Example context card section:
```
🚀 Recent Deployments:
• abc1234 by @sarah - Fix retry logic (2 hours ago)
• def5678 by @mike - Add circuit breaker (5 hours ago)
• ghi9012 by @alex - Update dependencies (1 day ago)
```

---

## Prerequisites

- GitHub organization or user account
- Access to the repositories you want to track
- Personal Access Token (PAT) or GitHub App

---

## 🔧 Setup

### Option A: Personal Access Token (Simpler)

Best for: Small teams, quick setup

#### Step 1: Create Token

1. Go to [GitHub Settings → Developer settings → Personal access tokens](https://github.com/settings/tokens)
2. Click **Generate new token (classic)**
3. Configure:
   - **Note**: `Incident Copilot`
   - **Expiration**: Set appropriate expiration
   - **Scopes**:
     - `repo` (Full control) - if private repos
     - `public_repo` - if only public repos
     - `read:org` - for org membership info

![GitHub PAT](../images/github-pat-placeholder.png)
*Screenshot: Creating a GitHub Personal Access Token*

4. Click **Generate token** and copy it immediately

Add to your `.env`:
```bash
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
GITHUB_ORG=your-organization
```

### Option B: GitHub App (Recommended for Production)

Best for: Production, multiple repos, better rate limits

#### Step 1: Create GitHub App

1. Go to [GitHub Settings → Developer settings → GitHub Apps](https://github.com/settings/apps)
2. Click **New GitHub App**
3. Configure:
   - **Name**: `Incident Copilot`
   - **Homepage URL**: Your Incident Copilot URL
   - **Webhook**: Disable (not needed)
4. Set permissions:

| Permission | Access |
|------------|--------|
| Contents | Read-only |
| Metadata | Read-only |
| Pull requests | Read-only |
| Deployments | Read-only |

5. Click **Create GitHub App**
6. Note the **App ID**
7. Scroll down and click **Generate a private key**
8. Save the `.pem` file securely

#### Step 2: Install App

1. In your GitHub App settings, click **Install App**
2. Select your organization
3. Choose repositories (all or specific)
4. Note the **Installation ID** from the URL

#### Step 3: Configure

Add to your `.env`:
```bash
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH=/path/to/private-key.pem
GITHUB_APP_INSTALLATION_ID=12345678
GITHUB_ORG=your-organization
```

Or inline the private key:
```bash
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----"
```

---

## 🗺️ Service Mapping

By default, Incident Copilot assumes:
- Service name in PagerDuty = Repository name in GitHub

### Custom Mapping

If your naming differs:

```bash
SERVICE_REPO_MAP='{
  "payments-api": "my-org/payment-service",
  "auth": "my-org/identity-platform",
  "checkout-v2": "my-org/checkout"
}'
```

### Multiple Repositories per Service

If a service spans multiple repos:

```bash
SERVICE_REPO_MAP='{
  "payments-api": "my-org/payments-api,my-org/payments-worker"
}'
```

---

## 👥 Code Owners

Incident Copilot reads the `CODEOWNERS` file to identify service owners.

### Setup CODEOWNERS

Create `.github/CODEOWNERS` in your repository:

```
# Default owners for everything
* @platform-team

# Specific directories
/src/payments/ @payments-team @sarah
/src/auth/ @security-team @mike
```

### Display in Context Cards

```
👥 Owners: @sarah, @mike (from CODEOWNERS)
```

---

## ⚙️ Configuration Options

### Basic Configuration

```bash
GITHUB_TOKEN=ghp_xxxx
GITHUB_ORG=my-organization
```

### Advanced Configuration

```bash
# Maximum commits to fetch
GITHUB_MAX_COMMITS=5

# Include PR details
GITHUB_INCLUDE_PRS=true

# Branch to track (default: main)
GITHUB_DEFAULT_BRANCH=main

# Timeout for API calls
GITHUB_TIMEOUT_SECONDS=10
```

---

## ✅ Testing

### Validate Configuration

```bash
incident-copilot validate
```

### Test GitHub Connection

```bash
incident-copilot test-integration github
```

### Test Specific Repository

```bash
# Using curl
curl -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/repos/YOUR_ORG/YOUR_REPO/commits?per_page=5"
```

### Check Rate Limits

```bash
curl -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://api.github.com/rate_limit
```

---

## 🐛 Troubleshooting

### "401 Unauthorized" Error

**Causes**:
- Token is invalid or expired
- Token doesn't have required scopes

**Solutions**:
1. Regenerate the token
2. Ensure `repo` scope is included
3. Check for extra whitespace in `.env`

### "404 Not Found" Error

**Causes**:
- Repository doesn't exist
- Token doesn't have access

**Solutions**:
1. Verify repo name and organization
2. Check token has access to private repos
3. Verify `SERVICE_REPO_MAP` if using custom mapping

### Rate Limiting

**Symptoms**:
- "403 Forbidden" with rate limit message
- Slow or missing deployment data

**Solutions**:
1. Use a GitHub App (10x higher rate limits)
2. Enable caching: `REDIS_URL=redis://localhost:6379`
3. Reduce `GITHUB_MAX_COMMITS`

### Missing Commits

**Causes**:
- Wrong branch configured
- Service mapping incorrect

**Solutions**:
1. Check `GITHUB_DEFAULT_BRANCH` matches your main branch
2. Verify `SERVICE_REPO_MAP`
3. Check commits exist in the time range

---

## 📚 Related Documentation

- [GitLab Integration](./gitlab.md) - Alternative source control
- [Configuration Reference](../configuration.md) - All config options
- [Troubleshooting](../troubleshooting.md) - General troubleshooting

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md) or [FAQ](../faq.md).*
