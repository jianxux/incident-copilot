"""PagerDuty integration adapter."""

import hashlib
import hmac
from datetime import datetime

import structlog

from ..config import Settings
from ..models import PagerDutyIncident, Severity

logger = structlog.get_logger()


class PagerDutyAdapter:
    """Adapter for PagerDuty webhooks and API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.webhook_secret = settings.pagerduty_webhook_secret

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify PagerDuty webhook signature (v3 webhooks)."""
        if not self.webhook_secret:
            logger.warning("pagerduty_webhook_secret not configured, skipping verification")
            return True

        expected = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        # PagerDuty sends signature as "v1=<hex>"
        if signature.startswith("v1="):
            signature = signature[3:]

        return hmac.compare_digest(expected, signature)

    def parse_webhook(self, payload: dict) -> PagerDutyIncident | None:
        """Parse PagerDuty v3 webhook payload into our model."""
        try:
            event = payload.get("event", {})
            event_type = event.get("event_type", "")

            # Only process incident triggers
            if event_type != "incident.triggered":
                logger.info("ignoring_pagerduty_event", event_type=event_type)
                return None

            data = event.get("data", {})
            service = data.get("service", {})

            # Map PagerDuty urgency to our severity
            urgency = data.get("urgency", "low")
            severity_map = {
                "high": Severity.HIGH,
                "low": Severity.LOW,
            }
            severity = severity_map.get(urgency, Severity.MEDIUM)

            # Extract assignees
            assignments = data.get("assignments", [])
            assigned_to = [
                a.get("assignee", {}).get("summary", "")
                for a in assignments
                if a.get("assignee", {}).get("summary")
            ]

            # Parse timestamp
            created_at = data.get("created_at", "")
            try:
                triggered_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                triggered_at = datetime.utcnow()

            return PagerDutyIncident(
                incident_id=data.get("id", ""),
                incident_number=data.get("incident_number"),
                title=data.get("title", "Unknown Incident"),
                description=data.get("description"),
                severity=severity,
                service_name=service.get("summary", "unknown-service"),
                service_id=service.get("id"),
                triggered_at=triggered_at,
                html_url=data.get("html_url"),
                assigned_to=assigned_to,
            )

        except Exception as e:
            logger.error("failed_to_parse_pagerduty_webhook", error=str(e))
            return None
