"""Opsgenie integration adapter."""

import hashlib
import hmac
from datetime import datetime, UTC
from typing import Any

import httpx
import structlog

from ..config import Settings
from ..models import OpsgenieAlert, Severity

logger = structlog.get_logger()

# Opsgenie API base URLs by region
OPSGENIE_API_URLS = {
    "us": "https://api.opsgenie.com/v2",
    "eu": "https://api.eu.opsgenie.com/v2",
}


class OpsgenieAdapter:
    """Adapter for Opsgenie webhooks and API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_key = settings.opsgenie_api_key
        self.webhook_secret = settings.opsgenie_webhook_secret
        self.api_base = OPSGENIE_API_URLS.get(
            settings.opsgenie_region, OPSGENIE_API_URLS["us"]
        )

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify Opsgenie webhook signature.

        Opsgenie signs webhooks using HMAC-SHA256.
        The signature is sent in the X-OpsGenie-Signature header.
        """
        if not self.webhook_secret:
            # Production safety: never accept unsigned webhooks.
            logger.error("opsgenie_webhook_secret_not_configured")
            return False

        expected = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected.lower(), signature.lower())

    def parse_webhook(self, payload: dict) -> OpsgenieAlert | None:
        """
        Parse Opsgenie v2 webhook payload into our model.

        Opsgenie webhook payload structure:
        {
            "action": "Create|Acknowledge|...",
            "alert": {
                "alertId": "...",
                "message": "...",
                "priority": "P1-P5",
                "tags": [...],
                ...
            },
            "source": {...},
            "integrationId": "...",
            "integrationName": "..."
        }
        """
        try:
            action = payload.get("action", "")

            # Only process alert creation
            if action.lower() != "create":
                logger.info("ignoring_opsgenie_event", action=action)
                return None

            alert_data = payload.get("alert", {})

            if not alert_data:
                logger.warning("opsgenie_webhook_missing_alert_data")
                return None

            # Map Opsgenie priority (P1-P5) to our severity
            priority = alert_data.get("priority", "P3")
            severity_map = {
                "P1": Severity.CRITICAL,
                "P2": Severity.HIGH,
                "P3": Severity.MEDIUM,
                "P4": Severity.LOW,
                "P5": Severity.INFO,
            }
            severity = severity_map.get(priority, Severity.MEDIUM)

            # Extract tags
            tags = alert_data.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]

            # Extract service from tags or alias
            service_name = self._extract_service(alert_data, tags)

            # Parse timestamp
            created_at = alert_data.get("createdAt")
            try:
                if created_at:
                    # Opsgenie sends timestamp in milliseconds
                    if isinstance(created_at, (int, float)):
                        triggered_at = datetime.utcfromtimestamp(created_at / 1000)
                    else:
                        triggered_at = datetime.fromisoformat(
                            str(created_at).replace("Z", "+00:00")
                        )
                else:
                    triggered_at = datetime.now(UTC)
            except (ValueError, TypeError):
                triggered_at = datetime.now(UTC)

            # Extract responders (teams/users assigned)
            responders = []
            for responder in alert_data.get("responders", []):
                if isinstance(responder, dict):
                    name = responder.get("name") or responder.get("username", "")
                    if name:
                        responders.append(name)
                elif isinstance(responder, str):
                    responders.append(responder)

            return OpsgenieAlert(
                alert_id=alert_data.get("alertId", ""),
                tiny_id=alert_data.get("tinyId"),
                message=alert_data.get("message", "Unknown Alert"),
                description=alert_data.get("description"),
                priority=priority,
                severity=severity,
                tags=tags,
                service_name=service_name,
                alias=alert_data.get("alias"),
                triggered_at=triggered_at,
                source=alert_data.get("source"),
                entity=alert_data.get("entity"),
                responders=responders,
                extra_properties=alert_data.get("details", {}),
            )

        except Exception as e:
            logger.error("failed_to_parse_opsgenie_webhook", error=str(e))
            return None

    def _extract_service(self, alert_data: dict, tags: list[str]) -> str:
        """
        Extract service name from alert data.

        Tries multiple sources in order:
        1. 'service' tag (e.g., "service:payments-api")
        2. 'entity' field
        3. 'alias' field (often contains service name)
        4. First tag that looks like a service name
        5. Default to 'unknown-service'
        """
        # Check for service: tag
        for tag in tags:
            if tag.lower().startswith("service:"):
                return tag.split(":", 1)[1].strip()

        # Check entity field
        entity = alert_data.get("entity")
        if entity:
            return str(entity)

        # Check alias (often formatted like "service-name/alert-type")
        alias = alert_data.get("alias", "")
        if alias and "/" in alias:
            return alias.split("/")[0]

        # Use first non-generic tag
        generic_tags = {"critical", "high", "low", "p1", "p2", "p3", "p4", "p5"}
        for tag in tags:
            if tag.lower() not in generic_tags:
                return tag

        return "unknown-service"

    async def get_alert_details(self, alert_id: str) -> dict[str, Any] | None:
        """
        Fetch additional alert details from Opsgenie API.

        Useful for getting full description, notes, and other metadata
        not included in the webhook payload.
        """
        if not self.api_key:
            logger.warning("opsgenie_api_key not configured")
            return None

        url = f"{self.api_base}/alerts/{alert_id}"
        headers = {
            "Authorization": f"GenieKey {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                return data.get("data", {})
        except httpx.HTTPStatusError as e:
            logger.error(
                "opsgenie_api_error",
                alert_id=alert_id,
                status_code=e.response.status_code,
                error=str(e),
            )
            return None
        except Exception as e:
            logger.error("opsgenie_api_request_failed", alert_id=alert_id, error=str(e))
            return None

    async def get_alert_notes(self, alert_id: str) -> list[dict] | None:
        """Fetch notes/comments for an alert."""
        if not self.api_key:
            return None

        url = f"{self.api_base}/alerts/{alert_id}/notes"
        headers = {
            "Authorization": f"GenieKey {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                return data.get("data", [])
        except Exception as e:
            logger.error("opsgenie_notes_fetch_failed", alert_id=alert_id, error=str(e))
            return None

    async def enrich_alert(self, alert: "OpsgenieAlert") -> "OpsgenieAlert":
        """
        Enrich alert with additional details from API.

        Fetches full alert details and notes, adding them to the alert model.
        """
        if not self.api_key:
            return alert

        # Fetch additional details
        details = await self.get_alert_details(alert.alert_id)
        if details:
            # Update with full description if available
            if details.get("description") and not alert.description:
                alert.description = details["description"]

            # Add teams
            teams = details.get("teams", [])
            if teams and not alert.responders:
                alert.responders = [t.get("name", "") for t in teams if t.get("name")]

            # Add extra properties
            if details.get("details"):
                alert.extra_properties.update(details["details"])

        return alert
