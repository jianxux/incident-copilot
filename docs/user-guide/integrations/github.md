# 🐙 GitHub Integration

Fetch recent deployments and commits for context cards.

---

## 🔧 Setup

### Create Personal Access Token

1. Go to **Settings** → **Developer settings** → **Personal access tokens**
2. Generate new token with `repo` scope
3. Add to `.env`:
   ```bash
   GITHUB_TOKEN=ghp_your-token
   GITHUB_ORG=your-org
   ```

### Or Use GitHub App (Recommended)

For higher rate limits (15,000 vs 5,000 req/hour):

1. Create a GitHub App
2. Install on your organization
3. Configure:
   ```bash
   GITHUB_APP_ID=123456
   GITHUB_APP_PRIVATE_KEY_PATH=/path/to/key.pem
   GITHUB_APP_INSTALLATION_ID=12345678
   ```

---

## 🗺️ Service Mapping

Map alert service names to repositories:

```bash
SERVICE_REPO_MAP='{
  "payments-api": "myorg/payments-service",
  "auth-service": "myorg/authentication"
}'
```

---

## ✅ Testing

```bash
incident-copilot test-integration github
```

---

## 📚 Related Documentation

- [GitLab Integration](./gitlab.md)
- [Context Cards](../features/context-cards.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
