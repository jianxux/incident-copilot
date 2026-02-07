"""GitHub integration adapter."""

from datetime import datetime, timedelta

import httpx
import structlog

from ..config import Settings
from ..models import Deployment, GitHubContext

logger = structlog.get_logger()


class GitHubAdapter:
    """Adapter for GitHub API."""

    BASE_URL = "https://api.github.com"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.token = settings.github_token
        self.org = settings.github_org
        self.service_repo_map = settings.service_repo_map

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

    async def get_context(self, service_name: str, since_hours: int = 24) -> GitHubContext | None:
        """Get GitHub context for a service."""
        repo = self._get_repo_for_service(service_name)
        if not repo:
            logger.warning("no_repo_mapping", service=service_name)
            return None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Fetch recent commits
                deploys = await self._fetch_recent_commits(client, repo, since_hours)

                # Fetch CODEOWNERS
                codeowners = await self._fetch_codeowners(client, repo)

                return GitHubContext(
                    repo=repo,
                    recent_deploys=deploys,
                    codeowners=codeowners,
                )

        except Exception as e:
            logger.error("github_fetch_failed", repo=repo, error=str(e))
            return None

    async def _fetch_recent_commits(
        self, client: httpx.AsyncClient, repo: str, since_hours: int
    ) -> list[Deployment]:
        """Fetch recent commits from main/master branch."""
        since = (datetime.utcnow() - timedelta(hours=since_hours)).isoformat() + "Z"

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
                timestamp = datetime.utcnow()

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

    async def _fetch_codeowners(self, client: httpx.AsyncClient, repo: str) -> list[str]:
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
