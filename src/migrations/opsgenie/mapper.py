"""Map Opsgenie data models to incident-copilot models."""

from typing import Any

from src.models import Severity
from src.services.models import ServiceCreate, ServiceCriticality


class OpsgenieMapper:
    """Static methods to map Opsgenie entities to our domain models."""

    SEVERITY_MAP: dict[str, Severity] = {
        "P1": Severity.CRITICAL,
        "P2": Severity.HIGH,
        "P3": Severity.MEDIUM,
        "P4": Severity.LOW,
        "P5": Severity.INFO,
    }

    ALERT_STATUS_MAP: dict[str, str] = {
        "open": "triggered",
        "closed": "resolved",
        "acked": "acknowledged",
    }

    @staticmethod
    def map_severity(priority: str) -> Severity:
        """Map Opsgenie priority (P1-P5) to our Severity enum."""
        return OpsgenieMapper.SEVERITY_MAP.get(priority, Severity.MEDIUM)

    @staticmethod
    def map_alert_status(status: str) -> str:
        """Map Opsgenie alert status to our incident status."""
        return OpsgenieMapper.ALERT_STATUS_MAP.get(status.lower(), "triggered")

    @staticmethod
    def map_service(og_service: dict[str, Any]) -> ServiceCreate:
        """Map an Opsgenie service to a ServiceCreate model."""
        return ServiceCreate(
            id=og_service.get("id"),
            name=og_service.get("name", "Unknown Service"),
            description=og_service.get("description"),
            team=og_service.get("teamId"),
            tags=og_service.get("tags", []),
            criticality=ServiceCriticality.MEDIUM,
            metadata={"opsgenie_id": og_service.get("id"), "source": "opsgenie"},
        )

    @staticmethod
    def map_team(og_team: dict[str, Any]) -> dict[str, Any]:
        """Map an Opsgenie team to our team model."""
        return {
            "name": og_team.get("name", ""),
            "description": og_team.get("description", ""),
            "members": [
                {"id": m.get("user", {}).get("id"), "role": m.get("role")}
                for m in og_team.get("members", [])
            ],
            "metadata": {"opsgenie_id": og_team.get("id"), "source": "opsgenie"},
        }

    @staticmethod
    def map_user(og_user: dict[str, Any]) -> dict[str, Any]:
        """Map an Opsgenie user to our user model."""
        return {
            "id": og_user.get("id"),
            "name": og_user.get("fullName", ""),
            "email": og_user.get("username", ""),
            "role": og_user.get("role", {}).get("name", "user"),
            "timezone": og_user.get("timeZone", "UTC"),
            "metadata": {"opsgenie_id": og_user.get("id"), "source": "opsgenie"},
        }

    @staticmethod
    def map_schedule(og_schedule: dict[str, Any]) -> dict[str, Any]:
        """Map an Opsgenie schedule to our on-call schedule model."""
        return {
            "name": og_schedule.get("name", ""),
            "description": og_schedule.get("description", ""),
            "timezone": og_schedule.get("timezone", "UTC"),
            "team": og_schedule.get("ownerTeam", {}).get("name"),
            "rotations": og_schedule.get("rotations", []),
            "enabled": og_schedule.get("enabled", True),
            "metadata": {"opsgenie_id": og_schedule.get("id"), "source": "opsgenie"},
        }

    @staticmethod
    def map_escalation(og_escalation: dict[str, Any]) -> dict[str, Any]:
        """Map an Opsgenie escalation policy to our escalation model."""
        rules = []
        for rule in og_escalation.get("rules", []):
            rules.append({
                "delay_minutes": rule.get("delay", {}).get("timeAmount", 0),
                "notify": rule.get("recipient", {}),
                "condition": rule.get("condition", "if-not-acked"),
            })
        return {
            "name": og_escalation.get("name", ""),
            "description": og_escalation.get("description", ""),
            "team": og_escalation.get("ownerTeam", {}).get("name"),
            "rules": rules,
            "repeat": og_escalation.get("repeat", {}),
            "metadata": {"opsgenie_id": og_escalation.get("id"), "source": "opsgenie"},
        }

    @staticmethod
    def map_alert_to_incident(og_alert: dict[str, Any]) -> dict[str, Any]:
        """Map an Opsgenie alert to our incident record."""
        return {
            "title": og_alert.get("message", ""),
            "description": og_alert.get("description", ""),
            "severity": OpsgenieMapper.map_severity(
                og_alert.get("priority", "P3")
            ).value,
            "status": OpsgenieMapper.map_alert_status(
                og_alert.get("status", "open")
            ),
            "source": "opsgenie",
            "service": og_alert.get("impactedServices", [""])[0]
            if og_alert.get("impactedServices")
            else None,
            "created_at": og_alert.get("createdAt"),
            "updated_at": og_alert.get("updatedAt"),
            "acknowledged_at": og_alert.get("report", {}).get("ackTime"),
            "resolved_at": og_alert.get("report", {}).get("closeTime"),
            "tags": og_alert.get("tags", []),
            "metadata": {"opsgenie_id": og_alert.get("id"), "source": "opsgenie"},
        }
