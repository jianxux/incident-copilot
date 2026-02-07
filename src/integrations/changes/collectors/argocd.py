"""
ArgoCD Collector - Collect deployment events from ArgoCD.
"""

from datetime import datetime
from typing import Optional

import httpx

from ..models import ChangeSource, ChangeStatus, Deployment, RiskLevel


class ArgoCDCollector:
    """Collect deployment events from ArgoCD."""

    source = ChangeSource.ARGOCD

    def __init__(
        self, base_url: str, token: str, applications: Optional[list[str]] = None
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.applications = applications
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
                verify=False,  # nosec B501 - ArgoCD often uses self-signed certs
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def collect_changes(
        self, since: datetime, until: Optional[datetime] = None
    ) -> list[Deployment]:
        """Collect deployment events from ArgoCD applications."""
        deployments: list[Deployment] = []

        apps = await self._list_applications()

        if self.applications:
            apps = [a for a in apps if a["metadata"]["name"] in self.applications]

        for app in apps:
            app_deployments = await self._get_app_deployments(app, since, until)
            deployments.extend(app_deployments)

        return deployments

    async def _list_applications(self) -> list[dict]:
        """List all ArgoCD applications."""
        client = await self._get_client()

        resp = await client.get("/api/v1/applications")
        if resp.status_code != 200:
            return []

        return resp.json().get("items", [])

    async def _get_app_deployments(
        self, app: dict, since: datetime, until: Optional[datetime]
    ) -> list[Deployment]:
        """Get deployment history for an application."""
        client = await self._get_client()
        deployments = []

        app_name = app["metadata"]["name"]
        namespace = app["metadata"].get("namespace", "argocd")

        # Get application history
        resp = await client.get(f"/api/v1/applications/{app_name}")
        if resp.status_code != 200:
            return deployments

        app_data = resp.json()
        history = app_data.get("status", {}).get("history", [])

        for idx, entry in enumerate(history):
            deployed_at = self._parse_timestamp(entry.get("deployedAt"))
            if not deployed_at:
                continue

            if deployed_at < since:
                continue
            if until and deployed_at > until:
                continue

            # Determine if this was a rollback
            is_rollback = False
            previous_version = None
            if idx > 0:
                prev = history[idx - 1]
                previous_version = prev.get("revision", "")[:12]
                # If revision is older than previous, it's likely a rollback
                if entry.get("id", 0) > prev.get("id", 0):
                    is_rollback = entry.get("revision") in [
                        h.get("revision") for h in history[: idx - 1]
                    ]

            # Get sync status
            sync_status = (
                app_data.get("status", {}).get("sync", {}).get("status", "Unknown")
            )
            health_status = (
                app_data.get("status", {}).get("health", {}).get("status", "Unknown")
            )

            status = self._determine_status(sync_status, health_status)

            # Extract deployment info
            source = entry.get("source", {})

            deployment = Deployment(
                id=f"argo-{app_name}-{entry.get('id', idx)}",
                source=ChangeSource.ARGOCD,
                status=status,
                title=f"Sync {app_name} to {entry.get('revision', 'unknown')[:12]}",
                description=f"ArgoCD sync for {app_name}",
                started_at=deployed_at,
                completed_at=deployed_at,  # ArgoCD doesn't track duration well
                author=entry.get("initiatedBy", {}).get("username", "argocd"),
                environment=self._determine_environment(app_name, namespace),
                service=app_name,
                version=entry.get("revision", "unknown")[:12],
                previous_version=previous_version,
                commit_sha=entry.get("revision"),
                is_rollback=is_rollback,
                risk_level=RiskLevel.HIGH if is_rollback else RiskLevel.MEDIUM,
                cluster=app_data.get("spec", {}).get("destination", {}).get("server"),
                namespace=app_data.get("spec", {})
                .get("destination", {})
                .get("namespace"),
                external_url=f"{self.base_url}/applications/{app_name}",
                metadata={
                    "argocd_app": app_name,
                    "sync_status": sync_status,
                    "health_status": health_status,
                    "source_repo": source.get("repoURL"),
                    "source_path": source.get("path"),
                    "source_chart": source.get("chart"),
                    "revision_id": entry.get("id"),
                },
            )

            deployments.append(deployment)

        return deployments

    async def get_deployment(self, deployment_id: str) -> Optional[Deployment]:
        """Get a specific deployment by ID."""
        if not deployment_id.startswith("argo-"):
            return None

        parts = deployment_id.replace("argo-", "").rsplit("-", 1)
        if len(parts) != 2:
            return None

        app_name, revision_id = parts
        client = await self._get_client()

        resp = await client.get(f"/api/v1/applications/{app_name}")
        if resp.status_code != 200:
            return None

        app_data = resp.json()
        history = app_data.get("status", {}).get("history", [])

        for entry in history:
            if str(entry.get("id")) == revision_id:
                deployed_at = self._parse_timestamp(entry.get("deployedAt"))
                return Deployment(
                    id=deployment_id,
                    source=ChangeSource.ARGOCD,
                    status=ChangeStatus.COMPLETED,
                    title=f"Sync {app_name}",
                    started_at=deployed_at or datetime.utcnow(),
                    author=entry.get("initiatedBy", {}).get("username", "argocd"),
                    environment="production",
                    service=app_name,
                    version=entry.get("revision", "unknown")[:12],
                    commit_sha=entry.get("revision"),
                )

        return None

    async def get_current_state(self, app_name: str) -> Optional[dict]:
        """Get current sync and health state of an application."""
        client = await self._get_client()

        resp = await client.get(f"/api/v1/applications/{app_name}")
        if resp.status_code != 200:
            return None

        app = resp.json()
        status = app.get("status", {})

        return {
            "app_name": app_name,
            "sync_status": status.get("sync", {}).get("status"),
            "health_status": status.get("health", {}).get("status"),
            "revision": status.get("sync", {}).get("revision"),
            "resources": len(status.get("resources", [])),
        }

    def _parse_timestamp(self, ts: Optional[str]) -> Optional[datetime]:
        """Parse ArgoCD timestamp."""
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    def _determine_status(self, sync_status: str, health_status: str) -> ChangeStatus:
        """Determine deployment status from ArgoCD statuses."""
        if sync_status == "Synced" and health_status == "Healthy":
            return ChangeStatus.COMPLETED
        if sync_status == "OutOfSync":
            return ChangeStatus.IN_PROGRESS
        if health_status in ("Degraded", "Missing"):
            return ChangeStatus.FAILED
        if sync_status == "Unknown" or health_status == "Unknown":
            return ChangeStatus.PENDING
        return ChangeStatus.IN_PROGRESS

    def _determine_environment(self, app_name: str, namespace: str) -> str:
        """Determine environment from app name or namespace."""
        name_lower = app_name.lower()
        ns_lower = namespace.lower()

        for env in ["production", "prod", "prd"]:
            if env in name_lower or env in ns_lower:
                return "production"

        for env in ["staging", "stage", "stg"]:
            if env in name_lower or env in ns_lower:
                return "staging"

        for env in ["development", "dev"]:
            if env in name_lower or env in ns_lower:
                return "development"

        return "production"  # Default to production
