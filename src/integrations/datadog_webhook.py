"""Datadog webhook adapter."""

import hashlib
import hmac
from datetime import datetime

import structlog

from ..config import Settings
from ..models import DatadogAlert, Severity

logger = structlog.get_logger()


class DatadogWebhookAdapter:
    """Adapter for Datadog webhook payloads."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.webhook_secret = settings.datadog_webhook_secret
        self.webhook_token = settings.datadog_webhook_token

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Datadog webhook signature if a secret is configured."""
        if not self.webhook_secret:
            logger.warning(
                "datadog_webhook_secret_not_configured_skipping_verification"
            )
            return True

        signature = signature.strip()
        if "=" in signature:
            signature = signature.split("=", 1)[1]

        expected = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected.lower(), signature.lower())

    def verify_webhook_token(self, token: str | None) -> bool:
        """Verify shared secret token header if configured."""
        if not self.webhook_token:
            return True
        if not token:
            return False
        return hmac.compare_digest(self.webhook_token, token)

    def parse_webhook(self, payload: dict) -> DatadogAlert | None:
        """Parse Datadog webhook payload into our model."""
        try:
            if not self._is_trigger_event(payload):
                logger.info(
                    "ignoring_datadog_event",
                    status=payload.get("status"),
                    alert_type=payload.get("alert_type"),
                )
                return None

            tags = self._parse_tags(payload.get("tags"))
            service_name = self._extract_service_name(tags, payload)
            severity = self._map_severity(payload)
            triggered_at = self._parse_timestamp(payload)

            alert_id = (
                payload.get("id")
                or payload.get("event_id")
                or payload.get("monitor_id")
                or payload.get("alert_id")
                or ""
            )

            title = (
                payload.get("title")
                or payload.get("monitor_name")
                or payload.get("alert_title")
                or "Datadog Alert"
            )
            description = (
                payload.get("text")
                or payload.get("msg")
                or payload.get("body")
                or payload.get("description")
            )

            return DatadogAlert(
                alert_id=str(alert_id),
                title=str(title),
                description=description,
                severity=severity,
                service_name=service_name,
                triggered_at=triggered_at,
                url=payload.get("link") or payload.get("url"),
                tags=tags,
                status=payload.get("status"),
                alert_type=payload.get("alert_type"),
            )
        except Exception as e:
            logger.error("failed_to_parse_datadog_webhook", error=str(e))
            return None

    def _is_trigger_event(self, payload: dict) -> bool:
        status = str(payload.get("status", "")).strip().lower()
        if status:
            trigger_statuses = {
                "alert",
                "warn",
                "warning",
                "no_data",
                "no data",
                "nodata",
            }
            ok_statuses = {"ok", "resolved", "recovered", "recovery"}
            if status in trigger_statuses:
                return True
            if status in ok_statuses:
                return False
            return False

        alert_type = str(payload.get("alert_type", "")).strip().lower()
        return alert_type in {"error", "warning", "warn"}

    def _parse_tags(self, raw_tags) -> list[str]:
        if not raw_tags:
            return []
        if isinstance(raw_tags, list):
            return [str(tag) for tag in raw_tags if str(tag).strip()]
        if isinstance(raw_tags, str):
            return [tag.strip() for tag in raw_tags.split(",") if tag.strip()]
        return []

    def _extract_service_name(self, tags: list[str], payload: dict) -> str:
        for tag in tags:
            if tag.lower().startswith("service:"):
                return tag.split(":", 1)[1].strip() or "unknown-service"

        payload_service = payload.get("service") or payload.get("service_name")
        if payload_service:
            return str(payload_service)

        scope = payload.get("scope")
        if isinstance(scope, str):
            for part in scope.split(","):
                part = part.strip()
                if part.lower().startswith("service:"):
                    return part.split(":", 1)[1].strip() or "unknown-service"

        return "unknown-service"

    def _map_severity(self, payload: dict) -> Severity:
        alert_type = str(payload.get("alert_type", "")).strip().lower()
        status = str(payload.get("status", "")).strip().lower()
        priority = str(payload.get("priority", "")).strip().lower()

        if alert_type in {"critical", "error"}:
            return Severity.CRITICAL
        if alert_type in {"warning", "warn"}:
            return Severity.HIGH
        if status in {"warn", "warning"}:
            return Severity.HIGH
        if priority in {"low"}:
            return Severity.LOW
        if alert_type in {"info"}:
            return Severity.MEDIUM
        if priority in {"normal"}:
            return Severity.MEDIUM
        return Severity.MEDIUM

    def _parse_timestamp(self, payload: dict) -> datetime:
        raw = (
            payload.get("date")
            or payload.get("last_updated")
            or payload.get("timestamp")
        )
        if isinstance(raw, (int, float)):
            value = float(raw)
            if value > 1_000_000_000_000:
                value /= 1000
            return datetime.utcfromtimestamp(value)
        if isinstance(raw, str) and raw:
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                pass
        return datetime.utcnow()
