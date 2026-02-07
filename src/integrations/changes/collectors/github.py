"""
GitHub Collector - Collect deployments and PRs from GitHub.
"""

import hashlib
from datetime import datetime
from typing import Optional

import httpx

from ..models import (
    ChangeEvent, ChangeSource, ChangeStatus, ChangeType,
    Deployment, RiskLevel
)


class GitHubCollector:
    """Collect change events from GitHub."""
    
    source = ChangeSource.GITHUB
    
    def __init__(
        self,
        token: str,
        org: str,
        repos: Optional[list[str]] = None,
        base_url: str = "https://api.github.com"
    ):
        self.token = token
        self.org = org
        self.repos = repos or []
        self.base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28"
                },
                timeout=30.0
            )
        return self._client
    
    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def collect_changes(
        self,
        since: datetime,
        until: Optional[datetime] = None
    ) -> list[ChangeEvent]:
        """Collect deployments and merged PRs from GitHub."""
        changes: list[ChangeEvent] = []
        
        repos = self.repos or await self._list_repos()
        
        for repo in repos:
            # Get deployments
            deployments = await self._get_deployments(repo, since, until)
            changes.extend(deployments)
            
            # Get merged PRs
            prs = await self._get_merged_prs(repo, since, until)
            changes.extend(prs)
        
        return changes
    
    async def _list_repos(self) -> list[str]:
        """List all repos in the org."""
        client = await self._get_client()
        repos = []
        page = 1
        
        while True:
            resp = await client.get(
                f"/orgs/{self.org}/repos",
                params={"per_page": 100, "page": page}
            )
            if resp.status_code != 200:
                break
            
            data = resp.json()
            if not data:
                break
            
            repos.extend(r["name"] for r in data)
            page += 1
        
        return repos
    
    async def _get_deployments(
        self,
        repo: str,
        since: datetime,
        until: Optional[datetime]
    ) -> list[Deployment]:
        """Get deployments for a repo."""
        client = await self._get_client()
        deployments = []
        
        resp = await client.get(
            f"/repos/{self.org}/{repo}/deployments",
            params={"per_page": 100}
        )
        
        if resp.status_code != 200:
            return deployments
        
        for dep in resp.json():
            created_at = datetime.fromisoformat(dep["created_at"].replace("Z", "+00:00"))
            
            if created_at < since:
                continue
            if until and created_at > until:
                continue
            
            # Get deployment status
            status_resp = await client.get(
                f"/repos/{self.org}/{repo}/deployments/{dep['id']}/statuses"
            )
            
            status = ChangeStatus.IN_PROGRESS
            completed_at = None
            
            if status_resp.status_code == 200:
                statuses = status_resp.json()
                if statuses:
                    latest = statuses[0]
                    status = self._map_status(latest["state"])
                    completed_at = datetime.fromisoformat(
                        latest["created_at"].replace("Z", "+00:00")
                    )
            
            deployment = Deployment(
                id=f"gh-deploy-{dep['id']}",
                source=ChangeSource.GITHUB,
                status=status,
                title=f"Deploy {dep['ref']} to {dep['environment']}",
                description=dep.get("description"),
                started_at=created_at,
                completed_at=completed_at,
                author=dep["creator"]["login"] if dep.get("creator") else "unknown",
                environment=dep["environment"],
                service=repo,
                version=dep["ref"],
                commit_sha=dep["sha"],
                external_url=f"https://github.com/{self.org}/{repo}/deployments/{dep['id']}",
                metadata={
                    "github_deployment_id": dep["id"],
                    "task": dep.get("task"),
                    "transient_environment": dep.get("transient_environment", False),
                    "production_environment": dep.get("production_environment", False),
                }
            )
            
            deployments.append(deployment)
        
        return deployments
    
    async def _get_merged_prs(
        self,
        repo: str,
        since: datetime,
        until: Optional[datetime]
    ) -> list[ChangeEvent]:
        """Get merged PRs as change events."""
        client = await self._get_client()
        changes = []
        
        resp = await client.get(
            f"/repos/{self.org}/{repo}/pulls",
            params={
                "state": "closed",
                "sort": "updated",
                "direction": "desc",
                "per_page": 50
            }
        )
        
        if resp.status_code != 200:
            return changes
        
        for pr in resp.json():
            if not pr.get("merged_at"):
                continue
            
            merged_at = datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00"))
            
            if merged_at < since:
                continue
            if until and merged_at > until:
                continue
            
            # Determine risk level from labels
            risk = self._assess_pr_risk(pr)
            
            change = ChangeEvent(
                id=f"gh-pr-{pr['id']}",
                type=ChangeType.DEPLOYMENT,
                source=ChangeSource.GITHUB,
                status=ChangeStatus.COMPLETED,
                title=pr["title"],
                description=pr.get("body", "")[:500] if pr.get("body") else None,
                started_at=datetime.fromisoformat(pr["created_at"].replace("Z", "+00:00")),
                completed_at=merged_at,
                author=pr["user"]["login"],
                service=repo,
                environment="production",  # Assume merged PRs go to prod
                risk_level=risk,
                pr_number=pr["number"],
                commit_sha=pr.get("merge_commit_sha"),
                external_url=pr["html_url"],
                tags=[label["name"] for label in pr.get("labels", [])],
                metadata={
                    "additions": pr.get("additions", 0),
                    "deletions": pr.get("deletions", 0),
                    "changed_files": pr.get("changed_files", 0),
                }
            )
            
            changes.append(change)
        
        return changes
    
    async def get_deployment(self, deployment_id: str) -> Optional[Deployment]:
        """Get a specific deployment by ID."""
        if not deployment_id.startswith("gh-deploy-"):
            return None
        
        gh_id = deployment_id.replace("gh-deploy-", "")
        client = await self._get_client()
        
        # Search through repos
        repos = self.repos or await self._list_repos()
        
        for repo in repos:
            resp = await client.get(f"/repos/{self.org}/{repo}/deployments/{gh_id}")
            if resp.status_code == 200:
                dep = resp.json()
                return Deployment(
                    id=deployment_id,
                    source=ChangeSource.GITHUB,
                    status=ChangeStatus.COMPLETED,
                    title=f"Deploy {dep['ref']} to {dep['environment']}",
                    started_at=datetime.fromisoformat(dep["created_at"].replace("Z", "+00:00")),
                    author=dep["creator"]["login"] if dep.get("creator") else "unknown",
                    environment=dep["environment"],
                    service=repo,
                    version=dep["ref"],
                    commit_sha=dep["sha"],
                )
        
        return None
    
    def _map_status(self, gh_status: str) -> ChangeStatus:
        """Map GitHub deployment status to ChangeStatus."""
        mapping = {
            "success": ChangeStatus.COMPLETED,
            "failure": ChangeStatus.FAILED,
            "error": ChangeStatus.FAILED,
            "pending": ChangeStatus.PENDING,
            "in_progress": ChangeStatus.IN_PROGRESS,
            "queued": ChangeStatus.PENDING,
            "inactive": ChangeStatus.COMPLETED,
        }
        return mapping.get(gh_status, ChangeStatus.IN_PROGRESS)
    
    def _assess_pr_risk(self, pr: dict) -> RiskLevel:
        """Assess risk level of a PR based on labels and size."""
        labels = [l["name"].lower() for l in pr.get("labels", [])]
        
        # Check for explicit risk labels
        if any(l in labels for l in ["critical", "breaking", "high-risk"]):
            return RiskLevel.CRITICAL
        if any(l in labels for l in ["major", "risky", "needs-review"]):
            return RiskLevel.HIGH
        
        # Check size
        additions = pr.get("additions", 0)
        deletions = pr.get("deletions", 0)
        total_changes = additions + deletions
        
        if total_changes > 1000:
            return RiskLevel.HIGH
        if total_changes > 300:
            return RiskLevel.MEDIUM
        
        return RiskLevel.LOW
