"""Notification service for processing and sending notifications."""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from .channels import ChannelError, create_channel
from .models import (
    ROLE_DEFAULTS,
    ChannelType,
    DigestFrequency,
    NotificationChannel,
    NotificationPayload,
    NotificationPreference,
    NotificationRule,
    NotificationType,
    Severity,
    UserRole,
)
from .templates import TemplateRenderer

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for managing and sending notifications."""

    def __init__(
        self,
        preference_store: "PreferenceStore | None" = None,
        renderer: TemplateRenderer | None = None,
    ):
        self.preference_store = preference_store or InMemoryPreferenceStore()
        self.renderer = renderer or TemplateRenderer()
        self._digest_queue: dict[str, list[NotificationPayload]] = defaultdict(list)
        self._last_digest: dict[str, datetime] = {}

    async def should_notify(
        self,
        user_id: str,
        notification_type: NotificationType,
        severity: Severity,
        service: str | None = None,
        team: str | None = None,
        tags: list[str] | None = None,
    ) -> tuple[bool, list[ChannelType], DigestFrequency]:
        """
        Determine if a user should be notified.

        Returns:
            Tuple of (should_notify, channels_to_use, digest_frequency)
        """
        prefs = await self.preference_store.get(user_id)

        if not prefs or not prefs.enabled:
            return False, [], DigestFrequency.REALTIME

        # Check quiet hours
        if prefs.quiet_hours.is_active():
            if not prefs.quiet_hours.should_override(severity):
                logger.debug(f"User {user_id} in quiet hours, notification suppressed")
                return False, [], DigestFrequency.REALTIME

        # Find matching rules
        matching_rule: NotificationRule | None = None
        for rule in prefs.rules:
            if rule.matches(notification_type, severity, service, team, tags):
                matching_rule = rule
                break

        if not matching_rule:
            # No rule matches - use default behavior based on role
            return self._apply_role_defaults(prefs.role, notification_type, severity)

        # Get channels from rule or preference defaults
        channel_types = matching_rule.channels or [
            c.type for c in prefs.get_enabled_channels()
        ]

        return True, channel_types, matching_rule.digest_frequency

    def _apply_role_defaults(
        self,
        role: UserRole,
        notification_type: NotificationType,
        severity: Severity,
    ) -> tuple[bool, list[ChannelType], DigestFrequency]:
        """Apply role-based default notification behavior."""
        ROLE_DEFAULTS.get(role, {})

        # Check severity thresholds based on role
        severity_order = {
            Severity.P1: 1,
            Severity.P2: 2,
            Severity.P3: 3,
            Severity.P4: 4,
            Severity.P5: 5,
        }

        if role == UserRole.ON_CALL:
            # On-call gets P1-P3 in realtime
            if severity_order[severity] <= 3:
                return (
                    True,
                    [ChannelType.SLACK, ChannelType.SMS],
                    DigestFrequency.REALTIME,
                )
        elif role == UserRole.MANAGER:
            # Managers get P1-P2 in realtime, rest as digest
            if severity_order[severity] <= 2:
                return (
                    True,
                    [ChannelType.SLACK, ChannelType.EMAIL],
                    DigestFrequency.REALTIME,
                )
            elif notification_type == NotificationType.DIGEST:
                return True, [ChannelType.EMAIL], DigestFrequency.DAILY
        elif role == UserRole.EXECUTIVE:
            # Executives only get P1
            if severity == Severity.P1:
                return True, [ChannelType.EMAIL], DigestFrequency.REALTIME
        elif role == UserRole.ENGINEER:
            # Engineers get assignments and P1-P2
            if notification_type == NotificationType.ASSIGNMENT:
                return True, [ChannelType.SLACK], DigestFrequency.REALTIME
            if severity_order[severity] <= 2:
                return True, [ChannelType.SLACK], DigestFrequency.REALTIME

        return False, [], DigestFrequency.REALTIME

    async def get_channels(
        self,
        user_id: str,
        channel_types: list[ChannelType] | None = None,
    ) -> list[NotificationChannel]:
        """Get user's notification channels, optionally filtered by type."""
        prefs = await self.preference_store.get(user_id)
        if not prefs:
            return []

        return prefs.get_enabled_channels(channel_types)

    async def send_notification(
        self,
        user_id: str,
        payload: NotificationPayload,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Send a notification to a user.

        Args:
            user_id: Target user ID
            payload: Notification payload
            force: Skip preference checks and send immediately

        Returns:
            Delivery results for each channel
        """
        prefs = await self.preference_store.get(user_id)

        if not force:
            should_send, channel_types, frequency = await self.should_notify(
                user_id,
                payload.type,
                payload.severity,
                payload.service,
                payload.team,
                payload.tags,
            )

            if not should_send:
                return {"status": "suppressed", "reason": "preferences"}

            # Handle digest batching
            if frequency != DigestFrequency.REALTIME:
                return await self._queue_for_digest(user_id, payload, frequency)
        else:
            channel_types = None  # Use all enabled channels

        # Get channels and send
        channels = await self.get_channels(user_id, channel_types)

        if not channels:
            return {"status": "no_channels", "reason": "no enabled channels"}

        results = {}
        for channel_config in channels:
            try:
                channel = create_channel(
                    channel_config, self._get_renderer(user_id, prefs)
                )
                result = await channel.send(payload)
                results[channel_config.type.value] = {"success": True, "result": result}
                payload.channels_succeeded.append(channel_config.type)
            except ChannelError as e:
                logger.error(f"Failed to send via {channel_config.type}: {e}")
                results[channel_config.type.value] = {"success": False, "error": str(e)}
            finally:
                payload.channels_attempted.append(channel_config.type)
                await channel.close()

        return {"status": "sent", "results": results}

    async def send_to_multiple(
        self,
        user_ids: list[str],
        payload: NotificationPayload,
    ) -> dict[str, Any]:
        """Send notification to multiple users concurrently."""

        async def send_one(uid: str) -> tuple[str, dict]:
            result = await self.send_notification(uid, payload)
            return uid, result

        tasks = [send_one(uid) for uid in user_ids]
        results = {}

        for coro in asyncio.as_completed(tasks):
            uid, result = await coro
            results[uid] = result

        return results

    async def _queue_for_digest(
        self,
        user_id: str,
        payload: NotificationPayload,
        frequency: DigestFrequency,
    ) -> dict[str, Any]:
        """Queue a notification for digest delivery."""
        key = f"{user_id}:{frequency.value}"
        self._digest_queue[key].append(payload)

        return {
            "status": "queued",
            "digest_frequency": frequency.value,
            "queue_size": len(self._digest_queue[key]),
        }

    async def process_digests(self) -> dict[str, Any]:
        """Process and send queued digest notifications."""
        now = datetime.utcnow()
        results = {}

        for key, payloads in list(self._digest_queue.items()):
            if not payloads:
                continue

            user_id, freq_str = key.rsplit(":", 1)
            frequency = DigestFrequency(freq_str)

            # Check if it's time to send
            last_sent = self._last_digest.get(key, datetime.min)

            if frequency == DigestFrequency.HOURLY:
                interval = timedelta(hours=1)
            elif frequency == DigestFrequency.DAILY:
                interval = timedelta(days=1)
            elif frequency == DigestFrequency.WEEKLY:
                interval = timedelta(weeks=1)
            else:
                continue

            if now - last_sent < interval:
                continue

            # Build digest payload
            digest_payload = self._build_digest(payloads, frequency)

            # Send digest
            result = await self.send_notification(user_id, digest_payload, force=True)
            results[key] = result

            # Clear queue and update timestamp
            self._digest_queue[key] = []
            self._last_digest[key] = now

        return results

    def _build_digest(
        self,
        payloads: list[NotificationPayload],
        frequency: DigestFrequency,
    ) -> NotificationPayload:
        """Build a digest notification from queued payloads."""
        # Count incidents by severity
        by_severity = defaultdict(list)
        for p in payloads:
            by_severity[p.severity].append(p)

        # Build summary
        total = len(payloads)
        critical = len(by_severity[Severity.P1]) + len(by_severity[Severity.P2])

        # Format incident list
        incident_list = "\n".join(
            f"- [{p.severity.value}] {p.title}" for p in payloads[:10]
        )
        if len(payloads) > 10:
            incident_list += f"\n... and {len(payloads) - 10} more"

        period = {
            DigestFrequency.HOURLY: "Last Hour",
            DigestFrequency.DAILY: "Today",
            DigestFrequency.WEEKLY: "This Week",
        }.get(frequency, "Recent")

        return NotificationPayload(
            id=str(uuid4()),
            type=NotificationType.DIGEST,
            severity=Severity.P3,  # Digests are medium priority
            title=f"Incident Digest - {period}",
            message=f"{total} incidents, {critical} critical",
            data={
                "period": period,
                "total_incidents": total,
                "critical_incidents": critical,
                "incident_list": incident_list,
                "payloads": [p.model_dump() for p in payloads],
            },
        )

    def _get_renderer(
        self,
        user_id: str,
        prefs: NotificationPreference | None,
    ) -> TemplateRenderer:
        """Get template renderer with user customizations."""
        if prefs and prefs.use_custom_templates:
            return TemplateRenderer(prefs.template_overrides)
        return self.renderer

    async def apply_preferences(
        self,
        user_id: str,
        updates: dict[str, Any],
    ) -> NotificationPreference:
        """Update user's notification preferences."""
        prefs = await self.preference_store.get(user_id)

        if not prefs:
            # Create new preferences with role defaults
            role = UserRole(updates.get("role", "engineer"))
            prefs = self._create_default_preferences(user_id, role)

        # Apply updates
        for key, value in updates.items():
            if hasattr(prefs, key):
                setattr(prefs, key, value)

        prefs.updated_at = datetime.utcnow()

        await self.preference_store.save(prefs)
        return prefs

    def _create_default_preferences(
        self,
        user_id: str,
        role: UserRole,
    ) -> NotificationPreference:
        """Create default preferences based on role."""
        defaults = ROLE_DEFAULTS.get(role, {})

        rules = []
        for rule_data in defaults.get("rules", []):
            rules.append(
                NotificationRule(
                    id=str(uuid4()),
                    **rule_data,
                )
            )

        return NotificationPreference(
            user_id=user_id,
            role=role,
            default_digest_frequency=defaults.get(
                "default_digest_frequency",
                DigestFrequency.REALTIME,
            ),
            rules=rules,
        )


class PreferenceStore:
    """Abstract interface for preference storage."""

    async def get(self, user_id: str) -> NotificationPreference | None:
        raise NotImplementedError

    async def save(self, prefs: NotificationPreference) -> None:
        raise NotImplementedError

    async def delete(self, user_id: str) -> bool:
        raise NotImplementedError

    async def list_all(self) -> list[NotificationPreference]:
        raise NotImplementedError


class InMemoryPreferenceStore(PreferenceStore):
    """In-memory preference storage for testing/development."""

    def __init__(self):
        self._store: dict[str, NotificationPreference] = {}

    async def get(self, user_id: str) -> NotificationPreference | None:
        return self._store.get(user_id)

    async def save(self, prefs: NotificationPreference) -> None:
        self._store[prefs.user_id] = prefs

    async def delete(self, user_id: str) -> bool:
        if user_id in self._store:
            del self._store[user_id]
            return True
        return False

    async def list_all(self) -> list[NotificationPreference]:
        return list(self._store.values())


# Singleton service instance
_service: NotificationService | None = None


def get_notification_service() -> NotificationService:
    """Get or create the notification service singleton."""
    global _service
    if _service is None:
        _service = NotificationService()
    return _service
