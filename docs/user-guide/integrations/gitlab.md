# 🦊 GitLab Integration

Fetch recent deployments and commits from GitLab.

---

## 🔧 Setup

### Create Access Token

1. Go to **Settings** → **Access Tokens**
2. Create token with `read_api`, `read_repository` scopes
3. Add to `.env`:
   ```bash
   GITLAB_TOKEN=glpat-your-token
   GITLAB_URL=https://gitlab.com  # Or self-hosted URL
   GITLAB_GROUP=your-group
   ```

---

## 🗺️ Service Mapping

```bash
SERVICE_REPO_MAP='{
  "payments-api": "group/payments-service",
  "auth-service": "group/subgroup/auth"
}'
```

Note: Use URL-encoded paths for subgroups.

---

## ✅ Testing

```bash
incident-copilot test-integration gitlab
```

---

## 📚 Related Documentation

- [GitHub Integration](./github.md)
- [Context Cards](../features/context-cards.md)

---

*Need help? Check the [Troubleshooting Guide](../troubleshooting.md).*
