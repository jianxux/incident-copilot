"""GitHub integration adapter."""

import asyncio
from datetime import datetime, timedelta, UTC

import httpx
import structlog

from ..config import Settings, get_settings
from ..db.supabase_db import get_db
from ..models import Deployment, GitHubContext, GitHubDeployment, GitHubPullRequest
from ..security.crypto import decrypt_json
from ..supabase_client import is_supabase_db_enabled

logger = structlog.get_logger()


async def resolve_github_creds(tenant_id: str | None) -> tuple[str, str]:
    """Resolve GitHub token/org from env first, then tenant integration config."""
    settings = get_settings()
    token = settings.github_token or ""
    org = settings.github_org or ""
    if token:
        logger.debug("github_creds_resolved_from_env", org=org)
        return token, org

    if not tenant_id:
        logger.debug("github_creds_skipped", reason="no_tenant_id")
        return "", ""

    if not is_supabase_db_enabled():
        logger.debug("github_creds_skipped", reason="supabase_db_disabled")
        return "", ""

    logger.debug("github_creds_resolving_from_db", tenant_id=tenant_id)

    try:
        db = get_db(use_admin=True)

        def _fetch():
            return (
                db.client.table("integration_configs")
                .select("config")
                .eq("type", "github")
                .eq("tenant_id", tenant_id)
                .limit(1)
                .execute()
            )

        result = await db._to_thread(_fetch)
        if not result.data:
            logger.warning(
                "github_creds_not_found_in_db",
                tenant_id=tenant_id,
                reason="no_integration_config_rows",
            )
            return "", ""

        config = result.data[0].get("config")
        if not isinstance(config, dict):
            logger.warning(
                "github_creds_invalid_config",
                tenant_id=tenant_id,
                reason="config_not_dict",
                config_type=type(config).__name__,
            )
            return "", ""

        encrypted = config.get("encrypted")
        if not encrypted:
            logger.warning(
                "github_creds_missing_encrypted_field",
                tenant_id=tenant_id,
                reason="no_encrypted_key_in_config",
                config_keys=list(config.keys()),
            )
            return "", ""

        decrypted = decrypt_json(encrypted)
        if not isinstance(decrypted, dict):
            logger.warning(
                "github_creds_decrypt_unexpected_type",
                tenant_id=tenant_id,
                decrypted_type=type(decrypted).__name__,
            )
            return "", ""

        token = decrypted.get("token", "")
        org = decrypted.get("org", "")
        if not token:
            logger.warning(
                "github_creds_empty_token_after_decrypt", tenant_id=tenant_id
            )
        else:
            logger.info("github_creds_resolved_from_db", tenant_id=tenant_id, org=org)
        return token, org
    except Exception as exc:
        logger.warning(
            "github_credentials_resolution_failed",
            tenant_id=tenant_id,
            error=str(exc),
            exc_type=type(exc).__name__,
        )
        return "", ""


async def resolve_github_credentials(
    settings: Settings,
    tenant_id: str | None = None,
) -> tuple[str, str]:
    """Backward-compatible wrapper for older call sites."""
    if settings.github_token:
        logger.debug(
            "github_credentials_resolved_from_settings", org=settings.github_org
        )
        return settings.github_token, settings.github_org
    return await resolve_github_creds(tenant_id)


class GitHubAdapter:
    """Adapter for GitHub API."""

    BASE_URL = "https://api.github.com"

    def __init__(
        self, settings: Settings, *, token: str | None = None, org: str | None = None
    ):
        self.settings = settings
        self.token = token if token is not None else settings.github_token
        self.org = org if org is not None else settings.github_org
        self.service_repo_map = settings.service_repo_map

    @classmethod
    def from_credentials(
        cls, token: str, org: str, settings: Settings
    ) -> "GitHubAdapter":
        return cls(settings, token=token, org=org)

    def _get_headers(self) -> dict:
        """Get auth headers for GitHub API."""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _get_repo_for_service(self, service_name: str) -> str | None:
        """Map service name to GitHub repo."""
        # Check explicit mapping first
        if service_name in self.service_repo_map:
            return self.service_repo_map[service_name]

        # Fall back to org/service-name convention
        if self.org:
            return f"{self.org}/{service_name}"

        return None

    async def get_context(
        self, service_name: str, since_hours: int = 24
    ) -> GitHubContext | None:
        """Get GitHub context for a service."""
        repo = self._get_repo_for_service(service_name)
        if not repo:
            logger.warning("no_repo_mapping", service=service_name)
            return None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                deploys, codeowners, prs, deployments = await asyncio.gather(
                    self._fetch_recent_commits(client, repo, since_hours),
                    self._fetch_codeowners(client, repo),
                    self._fetch_merged_prs(client, repo, since_hours),
                    self._fetch_deployments(client, repo),
                )

                return GitHubContext(
                    repo=repo,
                    recent_deploys=deploys,
                    codeowners=codeowners,
                    recent_prs=prs,
                    recent_deployments=deployments,
                )

        except Exception as e:
            logger.error("github_fetch_failed", repo=repo, error=str(e))
            return None

    async def _fetch_recent_commits(
        self, client: httpx.AsyncClient, repo: str, since_hours: int
    ) -> list[Deployment]:
        """Fetch recent commits from main/master branch."""
        since = (datetime.now(UTC) - timedelta(hours=since_hours)).isoformat() + "Z"

        url = f"{self.BASE_URL}/repos/{repo}/commits"
        params = {"since": since, "per_page": 10}

        resp = await client.get(url, headers=self._get_headers(), params=params)

        if resp.status_code != 200:
            logger.warning("github_commits_failed", repo=repo, status=resp.status_code)
            return []

        commits = resp.json()
        deploys = []

        for commit in commits[:5]:  # Limit to 5 most recent
            sha = commit.get("sha", "")
            commit_data = commit.get("commit", {})
            author = commit_data.get("author", {})

            # Parse timestamp
            timestamp_str = author.get("date", "")
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                timestamp = datetime.now(UTC)

            deploys.append(
                Deployment(
                    sha=sha,
                    short_sha=sha[:7],
                    author=author.get("name", "unknown"),
                    message=commit_data.get("message", "").split("\n")[0][:100],
                    timestamp=timestamp,
                    url=commit.get("html_url"),
                )
            )

        return deploys

    async def _fetch_codeowners(
        self, client: httpx.AsyncClient, repo: str
    ) -> list[str]:
        """Fetch CODEOWNERS file and extract owners."""
        # Try common CODEOWNERS locations
        paths = [".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"]

        for path in paths:
            url = f"{self.BASE_URL}/repos/{repo}/contents/{path}"
            resp = await client.get(url, headers=self._get_headers())

            if resp.status_code == 200:
                import base64

                content = resp.json().get("content", "")
                try:
                    decoded = base64.b64decode(content).decode("utf-8")
                    return self._parse_codeowners(decoded)
                except Exception:
                    pass

        return []

    def _parse_codeowners(self, content: str) -> list[str]:
        """Parse CODEOWNERS file and extract unique owners."""
        owners = set()

        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Format: path @owner1 @owner2
            parts = line.split()
            for part in parts[1:]:  # Skip the path
                if part.startswith("@"):
                    owners.add(part)

        return list(owners)[:10]  # Limit to 10 owners

    async def _fetch_merged_prs(
        self, client: httpx.AsyncClient, repo: str, since_hours: int
    ) -> list[GitHubPullRequest]:
        """Fetch recently merged pull requests."""
        since = (datetime.now(UTC) - timedelta(hours=since_hours)).isoformat() + "Z"

        url = f"{self.BASE_URL}/repos/{repo}/pulls"
        params = {
            "state": "closed",
            "sort": "updated",
            "direction": "desc",
            "per_page": 10,
        }

        try:
            resp = await client.get(url, headers=self._get_headers(), params=params)
            if resp.status_code != 200:
                logger.warning("github_prs_failed", repo=repo, status=resp.status_code)
                return []

            prs = []
            for pr in resp.json():
                merged_at_str = pr.get("merged_at")
                if not merged_at_str:
                    continue
                try:
                    merged_at = datetime.fromisoformat(
                        merged_at_str.replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    continue

                user = pr.get("user") or {}
                prs.append(
                    GitHubPullRequest(
                        number=pr.get("number", 0),
                        title=pr.get("title", "")[:200],
                        author=user.get("login", "unknown"),
                        merged_at=merged_at,
                        url=pr.get("html_url"),
                        additions=pr.get("additions", 0),
                        deletions=pr.get("deletions", 0),
                    )
                )
                if len(prs) >= 5:
                    break
            return prs
        except Exception as e:
            logger.warning("github_prs_error", repo=repo, error=str(e))
            return []

    async def _fetch_deployments(
        self, client: httpx.AsyncClient, repo: str
    ) -> list[GitHubDeployment]:
        """Fetch recent deployments from GitHub Deployments API."""
        url = f"{self.BASE_URL}/repos/{repo}/deployments"
        params = {"per_page": 10}

        try:
            resp = await client.get(url, headers=self._get_headers(), params=params)
            if resp.status_code != 200:
                logger.warning(
                    "github_deployments_failed", repo=repo, status=resp.status_code
                )
                return []

            deployments = []
            for dep in resp.json()[:5]:
                created_str = dep.get("created_at", "")
                try:
                    created_at = datetime.fromisoformat(
                        created_str.replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    created_at = datetime.now(UTC)

                creator = dep.get("creator") or {}
                # Fetch latest status
                statuses_url = dep.get("statuses_url", "")
                dep_status = "unknown"
                if statuses_url:
                    try:
                        status_resp = await client.get(
                            statuses_url, headers=self._get_headers()
                        )
                        if status_resp.status_code == 200:
                            statuses = status_resp.json()
                            if statuses:
                                dep_status = statuses[0].get("state", "unknown")
                    except Exception:
                        pass

                deployments.append(
                    GitHubDeployment(
                        id=str(dep.get("id", "")),
                        environment=dep.get("environment", "unknown"),
                        status=dep_status,
                        created_at=created_at,
                        url=dep.get("url"),
                        creator=creator.get("login", "unknown"),
                    )
                )
            return deployments
        except Exception as e:
            logger.warning("github_deployments_error", repo=repo, error=str(e))
            return []
