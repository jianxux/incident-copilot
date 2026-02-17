"""GitLab integration adapter."""

from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import Settings
from ..models import Deployment, GitLabContext, MergeRequest, Pipeline
from .oauth_tokens import oauth_token_store

logger = structlog.get_logger()


class GitLabAdapter:
    """Adapter for GitLab API.

    Supports both gitlab.com and self-hosted instances.
    Handles project paths in group/subgroup/project format.
    """

    DEFAULT_URL = "https://gitlab.com"

    def __init__(self, settings: Settings, tenant_id: str | None = None):
        self.settings = settings
        self.token = settings.gitlab_token
        self.tenant_id = tenant_id
        self.base_url = (
            settings.gitlab_url.rstrip("/") if settings.gitlab_url else self.DEFAULT_URL
        )
        self.project_map = settings.gitlab_project_map

    @property
    def api_url(self) -> str:
        """Get the GitLab API base URL."""
        return f"{self.base_url}/api/v4"

    def _get_headers(self, token: str | None = None) -> dict:
        """Get auth headers for GitLab API."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        auth_token = token or self.token
        if auth_token:
            headers["PRIVATE-TOKEN"] = auth_token
        return headers

    def _get_project_for_service(self, service_name: str) -> str | None:
        """Map service name to GitLab project path.

        GitLab project paths can include groups and subgroups:
        - group/project
        - group/subgroup/project
        - group/subgroup/subsubgroup/project
        """
        # Check explicit mapping first
        if service_name in self.project_map:
            return self.project_map[service_name]

        # No fallback convention for GitLab since we need the full path
        logger.warning("no_gitlab_project_mapping", service=service_name)
        return None

    def _encode_project_path(self, project_path: str) -> str:
        """URL-encode project path for GitLab API.

        GitLab requires project paths to be URL-encoded (/ becomes %2F).
        """
        return quote(project_path, safe="")

    async def get_context(
        self, service_name: str, since_hours: int = 24
    ) -> GitLabContext | None:
        """Get GitLab context for a service.

        Fetches:
        - Recent commits/deployments
        - Recent merge requests
        - Pipeline status
        - CODEOWNERS
        """
        token = self.token
        if self.tenant_id:
            token = await oauth_token_store.get_access_token(
                tenant_id=self.tenant_id,
                provider="gitlab",
            ) or self.token
        if not token:
            logger.debug("gitlab_token_not_configured")
            return None

        project_path = self._get_project_for_service(service_name)
        if not project_path:
            return None

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Fetch data in parallel
                deploys = await self._fetch_recent_commits(
                    client, project_path, since_hours, token=token
                )
                merge_requests = await self._fetch_recent_merge_requests(
                    client, project_path, since_hours, token=token
                )
                pipelines = await self._fetch_recent_pipelines(
                    client, project_path, since_hours, token=token
                )
                codeowners = await self._fetch_codeowners(
                    client, project_path, token=token
                )

                return GitLabContext(
                    project=project_path,
                    recent_deploys=deploys,
                    merge_requests=merge_requests,
                    pipelines=pipelines,
                    codeowners=codeowners,
                )

        except Exception as e:
            logger.error("gitlab_fetch_failed", project=project_path, error=str(e))
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _fetch_recent_commits(
        self,
        client: httpx.AsyncClient,
        project_path: str,
        since_hours: int,
        token: str | None = None,
    ) -> list[Deployment]:
        """Fetch recent commits from the default branch."""
        since = (datetime.now(UTC) - timedelta(hours=since_hours)).isoformat()
        encoded_path = self._encode_project_path(project_path)

        url = f"{self.api_url}/projects/{encoded_path}/repository/commits"
        params = {"since": since, "per_page": 10}

        resp = await client.get(url, headers=self._get_headers(token), params=params)

        if resp.status_code == 404:
            logger.warning("gitlab_project_not_found", project=project_path)
            return []

        if resp.status_code != 200:
            logger.warning(
                "gitlab_commits_failed",
                project=project_path,
                status=resp.status_code,
                body=resp.text[:200],
            )
            return []

        commits = resp.json()
        deploys = []

        for commit in commits[:5]:  # Limit to 5 most recent
            sha = commit.get("id", "")

            # Parse timestamp
            timestamp_str = commit.get("committed_date", "") or commit.get(
                "created_at", ""
            )
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                timestamp = datetime.now(UTC)

            deploys.append(
                Deployment(
                    sha=sha,
                    short_sha=sha[:7],
                    author=commit.get("author_name", "unknown"),
                    message=commit.get("title", "").split("\n")[0][:100],
                    timestamp=timestamp,
                    url=commit.get("web_url"),
                )
            )

        return deploys

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _fetch_recent_merge_requests(
        self,
        client: httpx.AsyncClient,
        project_path: str,
        since_hours: int,
        token: str | None = None,
    ) -> list[MergeRequest]:
        """Fetch recently merged MRs."""
        since = (datetime.now(UTC) - timedelta(hours=since_hours)).isoformat()
        encoded_path = self._encode_project_path(project_path)

        url = f"{self.api_url}/projects/{encoded_path}/merge_requests"
        params = {
            "state": "merged",
            "updated_after": since,
            "per_page": 10,
            "order_by": "updated_at",
            "sort": "desc",
        }

        resp = await client.get(url, headers=self._get_headers(token), params=params)

        if resp.status_code != 200:
            logger.warning(
                "gitlab_mrs_failed",
                project=project_path,
                status=resp.status_code,
            )
            return []

        mrs = resp.json()
        merge_requests = []

        for mr in mrs[:5]:  # Limit to 5 most recent
            # Parse timestamp
            merged_at_str = mr.get("merged_at", "") or mr.get("updated_at", "")
            try:
                merged_at = datetime.fromisoformat(merged_at_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                merged_at = datetime.now(UTC)

            merge_requests.append(
                MergeRequest(
                    iid=mr.get("iid", 0),
                    title=mr.get("title", "")[:100],
                    author=mr.get("author", {}).get("username", "unknown"),
                    merged_at=merged_at,
                    url=mr.get("web_url"),
                    labels=mr.get("labels", []),
                )
            )

        return merge_requests

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _fetch_recent_pipelines(
        self,
        client: httpx.AsyncClient,
        project_path: str,
        since_hours: int,
        token: str | None = None,
    ) -> list[Pipeline]:
        """Fetch recent CI/CD pipelines."""
        encoded_path = self._encode_project_path(project_path)

        url = f"{self.api_url}/projects/{encoded_path}/pipelines"
        params = {
            "per_page": 10,
            "order_by": "updated_at",
            "sort": "desc",
        }

        resp = await client.get(url, headers=self._get_headers(token), params=params)

        if resp.status_code != 200:
            logger.warning(
                "gitlab_pipelines_failed",
                project=project_path,
                status=resp.status_code,
            )
            return []

        pipelines_data = resp.json()
        pipelines = []

        since = datetime.now(UTC) - timedelta(hours=since_hours)

        for pipeline in pipelines_data:
            # Parse timestamp
            created_at_str = pipeline.get("created_at", "")
            try:
                created_at = datetime.fromisoformat(
                    created_at_str.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                created_at = datetime.now(UTC)

            # Filter by time
            if created_at.replace(tzinfo=None) < since.replace(tzinfo=None):
                continue

            pipelines.append(
                Pipeline(
                    id=pipeline.get("id", 0),
                    status=pipeline.get("status", "unknown"),
                    ref=pipeline.get("ref", ""),
                    sha=pipeline.get("sha", "")[:7],
                    created_at=created_at,
                    url=pipeline.get("web_url"),
                )
            )

        return pipelines[:5]  # Limit to 5 most recent

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _fetch_deployments(
        self,
        client: httpx.AsyncClient,
        project_path: str,
        environment: str = "production",
        token: str | None = None,
    ) -> list[dict]:
        """Fetch recent deployments from an environment."""
        encoded_path = self._encode_project_path(project_path)

        # First, get environment ID
        env_url = f"{self.api_url}/projects/{encoded_path}/environments"
        params = {"name": environment}

        resp = await client.get(env_url, headers=self._get_headers(token), params=params)

        if resp.status_code != 200:
            logger.debug("gitlab_environments_not_found", project=project_path)
            return []

        envs = resp.json()
        if not envs:
            return []

        # Now fetch deployments for this environment
        deploy_url = f"{self.api_url}/projects/{encoded_path}/deployments"
        params = {
            "environment": environment,
            "per_page": 5,
            "order_by": "created_at",
            "sort": "desc",
        }

        resp = await client.get(
            deploy_url,
            headers=self._get_headers(token),
            params=params,
        )

        if resp.status_code != 200:
            logger.warning(
                "gitlab_deployments_failed",
                project=project_path,
                status=resp.status_code,
            )
            return []

        return resp.json()

    async def _fetch_codeowners(
        self,
        client: httpx.AsyncClient,
        project_path: str,
        token: str | None = None,
    ) -> list[str]:
        """Fetch CODEOWNERS file and extract owners."""
        encoded_path = self._encode_project_path(project_path)

        # Try common CODEOWNERS locations
        paths = ["CODEOWNERS", ".gitlab/CODEOWNERS", "docs/CODEOWNERS"]

        for path in paths:
            encoded_file_path = quote(path, safe="")
            url = f"{self.api_url}/projects/{encoded_path}/repository/files/{encoded_file_path}"
            params = {"ref": "main"}  # Try main first

            resp = await client.get(url, headers=self._get_headers(token), params=params)

            if resp.status_code == 404:
                # Try master branch
                params["ref"] = "master"
                resp = await client.get(
                    url, headers=self._get_headers(token), params=params
                )

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

    async def get_project_info(self, project_path: str) -> dict | None:
        """Get project information (useful for validation)."""
        token = self.token
        if self.tenant_id:
            token = await oauth_token_store.get_access_token(
                tenant_id=self.tenant_id,
                provider="gitlab",
            ) or self.token
        if not token:
            return None

        encoded_path = self._encode_project_path(project_path)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"{self.api_url}/projects/{encoded_path}"
                resp = await client.get(url, headers=self._get_headers(token))

                if resp.status_code == 200:
                    return resp.json()

                logger.warning(
                    "gitlab_project_info_failed",
                    project=project_path,
                    status=resp.status_code,
                )
                return None

        except Exception as e:
            logger.error(
                "gitlab_project_info_error", project=project_path, error=str(e)
            )
            return None
