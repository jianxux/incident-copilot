"""
LaunchDarkly Collector - Collect feature flag changes.
"""

from datetime import datetime
from typing import Optional

import httpx

from ..models import ChangeSource, ChangeStatus, FeatureFlag, RiskLevel


class LaunchDarklyCollector:
    """Collect feature flag changes from LaunchDarkly."""

    source = ChangeSource.LAUNCHDARKLY

    def __init__(
        self,
        api_key: str,
        project_key: str,
        environments: Optional[list[str]] = None,
        base_url: str = "https://app.launchdarkly.com/api/v2",
    ):
        self.api_key = api_key
        self.project_key = project_key
        self.environments = environments or ["production"]
        self.base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": self.api_key, "Content-Type": "application/json"},
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def collect_changes(
        self, since: datetime, until: Optional[datetime] = None
    ) -> list[FeatureFlag]:
        """Collect feature flag changes from audit log."""
        changes: list[FeatureFlag] = []

        # Get audit log entries
        audit_entries = await self._get_audit_log(since, until)

        for entry in audit_entries:
            flag_change = self._parse_audit_entry(entry)
            if flag_change:
                changes.append(flag_change)

        return changes

    async def _get_audit_log(self, since: datetime, until: Optional[datetime]) -> list[dict]:
        """Get audit log entries for flag changes."""
        client = await self._get_client()
        entries = []

        params = {
            "after": int(since.timestamp() * 1000),
            "limit": 100,
            "spec": f"proj/{self.project_key}:*",
        }

        if until:
            params["before"] = int(until.timestamp() * 1000)

        resp = await client.get("/auditlog", params=params)

        if resp.status_code != 200:
            return entries

        data = resp.json()

        # Filter for flag-related actions
        flag_actions = {
            "updateOn",
            "updateOff",
            "updateFlagVariations",
            "updateRules",
            "updateFallthrough",
            "updateTargets",
            "createFlag",
            "deleteFlag",
            "updateFlagDefaultVariations",
        }

        for item in data.get("items", []):
            if item.get("kind") == "flag":
                if any(action in item.get("name", "") for action in flag_actions):
                    entries.append(item)
                elif item.get("accesses"):
                    for access in item["accesses"]:
                        if access.get("action") in flag_actions:
                            entries.append(item)
                            break

        return entries

    async def get_flag_state(
        self, flag_key: str, environment: str = "production"
    ) -> Optional[dict]:
        """Get current state of a feature flag."""
        client = await self._get_client()

        resp = await client.get(
            f"/flags/{self.project_key}/{flag_key}", params={"env": environment}
        )

        if resp.status_code != 200:
            return None

        flag = resp.json()
        env_config = flag.get("environments", {}).get(environment, {})

        return {
            "key": flag_key,
            "name": flag.get("name"),
            "on": env_config.get("on", False),
            "targeting_enabled": bool(env_config.get("rules")),
            "fallthrough_variation": env_config.get("fallthrough", {}).get("variation"),
            "off_variation": env_config.get("offVariation"),
        }

    async def get_deployment(self, deployment_id: str) -> Optional[FeatureFlag]:
        """Get a specific flag change by ID (from audit log)."""
        # LaunchDarkly doesn't have a direct way to get a single audit entry
        # This would require storing/caching audit entries
        return None

    def _parse_audit_entry(self, entry: dict) -> Optional[FeatureFlag]:
        """Parse an audit log entry into a FeatureFlag change."""
        try:
            # Extract flag key from target
            target = entry.get("target", {})
            flag_key = None

            if target.get("resources"):
                for resource in target["resources"]:
                    if resource.get("type") == "flag":
                        flag_key = resource.get("key")
                        break

            if not flag_key:
                # Try to extract from name
                name = entry.get("name", "")
                if ":" in name:
                    parts = name.split(":")
                    flag_key = parts[-1] if parts else None

            if not flag_key:
                return None

            # Determine the change
            title = entry.get("title", entry.get("name", "Flag change"))
            description = entry.get("description", "")

            # Parse timestamp
            timestamp = entry.get("date")
            if isinstance(timestamp, int):
                started_at = datetime.fromtimestamp(timestamp / 1000)
            else:
                started_at = datetime.utcnow()

            # Determine new state
            new_state = True
            previous_state = None

            if "turned on" in title.lower() or "updateon" in entry.get("name", "").lower():
                new_state = True
                previous_state = False
            elif "turned off" in title.lower() or "updateoff" in entry.get("name", "").lower():
                new_state = False
                previous_state = True

            # Extract environment
            environment = "production"
            if entry.get("accesses"):
                for access in entry["accesses"]:
                    resource = access.get("resource", "")
                    if "env/" in resource:
                        env_part = resource.split("env/")[1].split(":")[0]
                        environment = env_part
                        break

            # Assess risk
            risk = self._assess_flag_risk(entry, new_state, previous_state)

            return FeatureFlag(
                id=f"ld-{entry.get('_id', '')}",
                source=ChangeSource.LAUNCHDARKLY,
                status=ChangeStatus.COMPLETED,
                title=title,
                description=description,
                started_at=started_at,
                completed_at=started_at,
                author=entry.get("member", {}).get("email", "unknown"),
                environment=environment,
                service=self.project_key,
                risk_level=risk,
                flag_key=flag_key,
                flag_name=flag_key,  # Would need separate API call for name
                previous_state=previous_state,
                new_state=new_state,
                external_url=f"https://app.launchdarkly.com/{self.project_key}/{environment}/features/{flag_key}",
                metadata={
                    "audit_id": entry.get("_id"),
                    "kind": entry.get("kind"),
                    "action": entry.get("name"),
                },
            )
        except Exception:
            return None

    def _assess_flag_risk(
        self, entry: dict, new_state: bool, previous_state: Optional[bool]
    ) -> RiskLevel:
        """Assess risk level of a flag change."""
        # Turning off a flag in production is high risk
        if previous_state is True and new_state is False:
            return RiskLevel.HIGH

        # Enabling a flag is medium risk
        if previous_state is False and new_state is True:
            return RiskLevel.MEDIUM

        # Rule changes are medium risk
        name = entry.get("name", "")
        if "rules" in name.lower() or "targets" in name.lower():
            return RiskLevel.MEDIUM

        return RiskLevel.LOW

    async def list_flags(self, environment: str = "production") -> list[dict]:
        """List all feature flags in the project."""
        client = await self._get_client()

        resp = await client.get(f"/flags/{self.project_key}", params={"env": environment})

        if resp.status_code != 200:
            return []

        flags = []
        for item in resp.json().get("items", []):
            env_config = item.get("environments", {}).get(environment, {})
            flags.append({
                "key": item.get("key"),
                "name": item.get("name"),
                "on": env_config.get("on", False),
                "archived": item.get("archived", False),
                "temporary": item.get("temporary", False),
            })

        return flags
