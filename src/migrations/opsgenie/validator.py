"""Pre-migration validation for Opsgenie imports."""

import logging
from typing import Any

from src.migrations.models import MigrationEntityType, MigrationPreview

from .client import OpsgenieClient

logger = logging.getLogger(__name__)


class OpsgenieValidator:
    """Validate Opsgenie API access and inventory available data."""

    def __init__(self, client: OpsgenieClient) -> None:
        self.client = client

    async def validate_connection(self) -> tuple[bool, str]:
        """Check if the API key is valid."""
        valid = await self.client.validate_api_key()
        if valid:
            return True, "Successfully connected to Opsgenie API"
        return False, "Invalid API key or unable to connect to Opsgenie"

    async def check_permissions(self) -> list[MigrationEntityType]:
        """Probe which entity types are accessible."""
        available: list[MigrationEntityType] = []
        checks = [
            (MigrationEntityType.SERVICES, "/services"),
            (MigrationEntityType.TEAMS, "/teams"),
            (MigrationEntityType.USERS, "/users"),
            (MigrationEntityType.SCHEDULES, "/schedules"),
            (MigrationEntityType.ESCALATIONS, "/escalations"),
            (MigrationEntityType.ALERTS, "/alerts"),
            (MigrationEntityType.INTEGRATIONS, "/integrations"),
        ]
        for entity_type, path in checks:
            try:
                await self.client._request("GET", path, params={"limit": 1})
                available.append(entity_type)
            except Exception:
                logger.debug("No access to %s", entity_type)
        return available

    async def inventory(self) -> list[MigrationPreview]:
        """Count entities available for migration with sample names."""
        previews: list[MigrationPreview] = []
        fetchers: list[tuple[MigrationEntityType, str]] = [
            (MigrationEntityType.SERVICES, "get_services"),
            (MigrationEntityType.TEAMS, "get_teams"),
            (MigrationEntityType.USERS, "get_users"),
            (MigrationEntityType.SCHEDULES, "get_schedules"),
            (MigrationEntityType.ESCALATIONS, "get_escalations"),
            (MigrationEntityType.ALERTS, "get_alerts"),
            (MigrationEntityType.INTEGRATIONS, "get_integrations"),
        ]
        name_keys = {
            MigrationEntityType.SERVICES: "name",
            MigrationEntityType.TEAMS: "name",
            MigrationEntityType.USERS: "fullName",
            MigrationEntityType.SCHEDULES: "name",
            MigrationEntityType.ESCALATIONS: "name",
            MigrationEntityType.ALERTS: "message",
            MigrationEntityType.INTEGRATIONS: "name",
        }
        for entity_type, method_name in fetchers:
            try:
                data = await getattr(self.client, method_name)()
                name_key = name_keys[entity_type]
                samples = [item.get(name_key, "?") for item in data[:5]]
                previews.append(
                    MigrationPreview(
                        entity_type=entity_type,
                        count=len(data),
                        sample_names=samples,
                    )
                )
            except Exception as e:
                logger.warning("Failed to inventory %s: %s", entity_type, e)
        return previews

    async def full_validate(
        self,
    ) -> dict[str, Any]:
        """Run full validation: connection, permissions, and inventory."""
        valid, message = await self.validate_connection()
        if not valid:
            return {
                "valid": False,
                "message": message,
                "permissions": [],
                "previews": [],
            }
        permissions = await self.check_permissions()
        previews = await self.inventory()
        return {
            "valid": True,
            "message": message,
            "permissions": [p.value for p in permissions],
            "previews": [p.model_dump() for p in previews],
        }
