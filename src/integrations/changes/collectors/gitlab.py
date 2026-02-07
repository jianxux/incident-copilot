"""
GitLab Collector - Collect deployments and MRs from GitLab.
"""

from datetime import datetime
from typing import Optional

import httpx

from ..models import (
    ChangeEvent, ChangeSource, ChangeStatus, ChangeType,
    Deployment, RiskLevel
)


class GitLabCollector:
    """Collect change events from GitLab."""
    
    source = ChangeSource.GITLAB
    
    def __init__(
        self,
        token: str,
        group: Optional[str] = None,
        projects: Optional[list[str]] = None,
        base_url: str = "https://gitlab.com/api/v4"
    ):
        self.token = token
        self.group = group
        self.projects = projects or []
        self.base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"PRIVATE-TOKEN": self.token},
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
        """Collect deployments and merged MRs from GitLab."""
        changes: list[ChangeEvent] = []
        
        projects = self.projects or await self._list_projects()
        
        for project_id in projects:
            # Get deployments
            deployments = await self._get_deployments(project_id, since, until)
            changes.extend(deployments)
            
            # Get merged MRs
            mrs = await self._get_merged_mrs(project_id, since, until)
            changes.extend(mrs)
        
        return changes
    
    async def _list_projects(self) -> list[str]:
        """List all projects in the group."""
        if not self.group:
            return []
        
        client = await self._get_client()
        projects = []
        page = 1
        
        while True:
            resp = await client.get(
                f"/groups/{self.group}/projects",
                params={"per_page": 100, "page": page, "include_subgroups": True}
            )
            if resp.status_code != 200:
                break
            
            data = resp.json()
            if not data:
                break
            
            projects.extend(str(p["id"]) for p in data)
            page += 1
        
        return projects
    
    async def _get_deployments(
        self,
        project_id: str,
        since: datetime,
        until: Optional[datetime]
    ) -> list[Deployment]:
        """Get deployments for a project."""
        client = await self._get_client()
        deployments = []
        
        resp = await client.get(
            f"/projects/{project_id}/deployments",
            params={
                "per_page": 100,
                "order_by": "created_at",
                "sort": "desc"
            }
        )
        
        if resp.status_code != 200:
            return deployments
        
        # Get project info for service name
        project_resp = await client.get(f"/projects/{project_id}")
        project_name = project_id
        if project_resp.status_code == 200:
            project_name = project_resp.json().get("name", project_id)
        
        for dep in resp.json():
            created_at = datetime.fromisoformat(dep["created_at"].replace("Z", "+00:00"))
            
            if created_at < since:
                continue
            if until and created_at > until:
                continue
            
            finished_at = None
            if dep.get("finished_at"):
                finished_at = datetime.fromisoformat(dep["finished_at"].replace("Z", "+00:00"))
            
            deployment = Deployment(
                id=f"gl-deploy-{dep['id']}",
                source=ChangeSource.GITLAB,
                status=self._map_status(dep["status"]),
                title=f"Deploy {dep['ref']} to {dep['environment']}",
                started_at=created_at,
                completed_at=finished_at,
                author=dep["user"]["username"] if dep.get("user") else "unknown",
                environment=dep["environment"],
                service=project_name,
                version=dep["ref"],
                commit_sha=dep.get("sha"),
                external_url=dep.get("web_url"),
                metadata={
                    "gitlab_deployment_id": dep["id"],
                    "iid": dep.get("iid"),
                    "project_id": project_id,
                }
            )
            
            deployments.append(deployment)
        
        return deployments
    
    async def _get_merged_mrs(
        self,
        project_id: str,
        since: datetime,
        until: Optional[datetime]
    ) -> list[ChangeEvent]:
        """Get merged MRs as change events."""
        client = await self._get_client()
        changes = []
        
        # Get project info
        project_resp = await client.get(f"/projects/{project_id}")
        project_name = project_id
        if project_resp.status_code == 200:
            project_name = project_resp.json().get("name", project_id)
        
        resp = await client.get(
            f"/projects/{project_id}/merge_requests",
            params={
                "state": "merged",
                "order_by": "updated_at",
                "sort": "desc",
                "per_page": 50
            }
        )
        
        if resp.status_code != 200:
            return changes
        
        for mr in resp.json():
            if not mr.get("merged_at"):
                continue
            
            merged_at = datetime.fromisoformat(mr["merged_at"].replace("Z", "+00:00"))
            
            if merged_at < since:
                continue
            if until and merged_at > until:
                continue
            
            risk = self._assess_mr_risk(mr)
            
            change = ChangeEvent(
                id=f"gl-mr-{mr['id']}",
                type=ChangeType.DEPLOYMENT,
                source=ChangeSource.GITLAB,
                status=ChangeStatus.COMPLETED,
                title=mr["title"],
                description=mr.get("description", "")[:500] if mr.get("description") else None,
                started_at=datetime.fromisoformat(mr["created_at"].replace("Z", "+00:00")),
                completed_at=merged_at,
                author=mr["author"]["username"] if mr.get("author") else "unknown",
                service=project_name,
                environment="production",
                risk_level=risk,
                pr_number=mr["iid"],
                commit_sha=mr.get("merge_commit_sha"),
                external_url=mr["web_url"],
                tags=mr.get("labels", []),
                metadata={
                    "gitlab_mr_id": mr["id"],
                    "iid": mr["iid"],
                    "project_id": project_id,
                    "source_branch": mr.get("source_branch"),
                    "target_branch": mr.get("target_branch"),
                }
            )
            
            changes.append(change)
        
        return changes
    
    async def get_deployment(self, deployment_id: str) -> Optional[Deployment]:
        """Get a specific deployment by ID."""
        if not deployment_id.startswith("gl-deploy-"):
            return None
        
        gl_id = deployment_id.replace("gl-deploy-", "")
        client = await self._get_client()
        
        projects = self.projects or await self._list_projects()
        
        for project_id in projects:
            resp = await client.get(f"/projects/{project_id}/deployments/{gl_id}")
            if resp.status_code == 200:
                dep = resp.json()
                return Deployment(
                    id=deployment_id,
                    source=ChangeSource.GITLAB,
                    status=self._map_status(dep["status"]),
                    title=f"Deploy {dep['ref']} to {dep['environment']}",
                    started_at=datetime.fromisoformat(dep["created_at"].replace("Z", "+00:00")),
                    author=dep["user"]["username"] if dep.get("user") else "unknown",
                    environment=dep["environment"],
                    service=project_id,
                    version=dep["ref"],
                    commit_sha=dep.get("sha"),
                )
        
        return None
    
    def _map_status(self, gl_status: str) -> ChangeStatus:
        """Map GitLab deployment status to ChangeStatus."""
        mapping = {
            "success": ChangeStatus.COMPLETED,
            "failed": ChangeStatus.FAILED,
            "canceled": ChangeStatus.FAILED,
            "running": ChangeStatus.IN_PROGRESS,
            "pending": ChangeStatus.PENDING,
            "created": ChangeStatus.PENDING,
            "blocked": ChangeStatus.PENDING,
        }
        return mapping.get(gl_status, ChangeStatus.IN_PROGRESS)
    
    def _assess_mr_risk(self, mr: dict) -> RiskLevel:
        """Assess risk level of an MR based on labels."""
        labels = [l.lower() for l in mr.get("labels", [])]
        
        if any(l in labels for l in ["critical", "breaking-change", "high-risk"]):
            return RiskLevel.CRITICAL
        if any(l in labels for l in ["major", "risky"]):
            return RiskLevel.HIGH
        if any(l in labels for l in ["minor", "safe"]):
            return RiskLevel.LOW
        
        return RiskLevel.MEDIUM
