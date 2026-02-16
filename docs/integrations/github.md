# GitHub

Incident Copilot uses GitHub to enrich incidents with recent deploys/commits/PR context.

## Personal Access Token (PAT)

1. GitHub → Settings → Developer settings → **Personal access tokens**
2. Create a token with least-privilege access for your repos.

Common permissions:

- `repo` (classic PAT) or fine-grained read access to contents/metadata
- optional: read deployments / environments if you use GitHub Deployments

## Configure env vars

```bash
GITHUB_TOKEN=ghp_...
GITHUB_ORG=my-org

# Optional OAuth (if you support user connect)
GITHUB_OAUTH_CLIENT_ID=...
GITHUB_OAUTH_CLIENT_SECRET=...
APP_URL=https://<your-app>

# Map service name → repo
SERVICE_REPO_MAP='{"payments-api":"my-org/payments"}'
```

!!! tip
    `SERVICE_REPO_MAP` is useful when your alert payload includes a service name that doesn’t exactly match the repo path.

## Repo mapping

In many setups, the alert payload contains a service identifier (e.g. `payments-api`). Configure mapping so Incident Copilot knows where to look for deploys.

Example:

```bash
SERVICE_REPO_MAP='{"payments-api":"my-org/payments","checkout":"my-org/checkout"}'
```

## Troubleshooting

- **403 / rate limit**: use a token with sufficient permissions; consider GitHub App auth for higher limits.
- **Repo not found**: verify `GITHUB_ORG` and `SERVICE_REPO_MAP`.
