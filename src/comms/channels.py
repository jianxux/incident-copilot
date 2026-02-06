"""Multi-channel communication delivery.

Provides delivery handlers for:
- Slack (internal team communication)
- Email (stakeholder notifications)
- SMS (urgent alerts)
- Status Page (public updates)
- Teams (internal communication)
- Webhooks (custom integrations)
"""

import asyncio
import secrets
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import structlog
from pydantic import BaseModel, Field

from .models import (
    AudienceType,
    CommunicationAuditEntry,
    CommunicationUpdate,
    DeliveryChannel,
    DeliveryStatus,
    Stakeholder,
)

logger = structlog.get_logger()


class DeliveryResult(BaseModel):
    """Result of a communication delivery attempt."""

    channel: DeliveryChannel
    success: bool
    status: DeliveryStatus
    recipient_count: int = 0
    message: str | None = None
    error: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    delivered_at: datetime = Field(default_factory=datetime.utcnow)
    message_id: str | None = None  # External message ID from provider


class ChannelHandler(ABC):
    """Abstract base class for channel delivery handlers."""

    @property
    @abstractmethod
    def channel(self) -> DeliveryChannel:
        """Get the channel type this handler supports."""
        pass

    @abstractmethod
    async def send(
        self,
        update: CommunicationUpdate,
        recipients: list[Stakeholder],
    ) -> DeliveryResult:
        """Send an update to recipients via this channel."""
        pass

    @abstractmethod
    async def validate_config(self) -> bool:
        """Validate that this channel is properly configured."""
        pass


class SlackChannel(ChannelHandler):
    """Slack delivery channel for internal communications."""

    def __init__(
        self,
        bot_token: str | None = None,
        default_channel: str | None = None,
    ) -> None:
        self._bot_token = bot_token
        self._default_channel = default_channel or "#incidents"

    @property
    def channel(self) -> DeliveryChannel:
        return DeliveryChannel.SLACK

    async def validate_config(self) -> bool:
        """Check if Slack is properly configured."""
        # In production, validate token by making API call
        return self._bot_token is not None

    async def send(
        self,
        update: CommunicationUpdate,
        recipients: list[Stakeholder],
    ) -> DeliveryResult:
        """Send update via Slack."""
        try:
            # Get Slack user IDs and channels to notify
            targets: list[str] = []

            for recipient in recipients:
                if recipient.slack_user_id:
                    targets.append(recipient.slack_user_id)

            # Add default channel for broadcasts
            if not targets:
                targets.append(self._default_channel)

            # Simulate sending (in production, use Slack API)
            logger.info(
                "slack_message_sent",
                incident_id=update.incident_id,
                targets=targets,
                subject=update.subject,
            )

            return DeliveryResult(
                channel=DeliveryChannel.SLACK,
                success=True,
                status=DeliveryStatus.DELIVERED,
                recipient_count=len(targets),
                message=f"Sent to {len(targets)} Slack targets",
                message_id=secrets.token_hex(8),
                details={
                    "targets": targets,
                    "channel": self._default_channel,
                    "simulated": True,
                },
            )

        except Exception as e:
            logger.error("slack_send_error", error=str(e))
            return DeliveryResult(
                channel=DeliveryChannel.SLACK,
                success=False,
                status=DeliveryStatus.FAILED,
                error=str(e),
            )

    async def send_to_channel(
        self,
        channel: str,
        subject: str,
        body: str,
        thread_ts: str | None = None,
    ) -> DeliveryResult:
        """Send a message to a specific Slack channel."""
        try:
            logger.info(
                "slack_channel_message",
                channel=channel,
                subject=subject,
                thread_ts=thread_ts,
            )

            return DeliveryResult(
                channel=DeliveryChannel.SLACK,
                success=True,
                status=DeliveryStatus.DELIVERED,
                recipient_count=1,
                message=f"Posted to {channel}",
                message_id=secrets.token_hex(8),
                details={
                    "channel": channel,
                    "thread_ts": thread_ts,
                    "simulated": True,
                },
            )

        except Exception as e:
            return DeliveryResult(
                channel=DeliveryChannel.SLACK,
                success=False,
                status=DeliveryStatus.FAILED,
                error=str(e),
            )


class EmailChannel(ChannelHandler):
    """Email delivery channel for stakeholder notifications."""

    def __init__(
        self,
        smtp_host: str | None = None,
        smtp_port: int = 587,
        smtp_user: str | None = None,
        smtp_password: str | None = None,
        from_address: str = "incidents@example.com",
        from_name: str = "Incident Response Team",
    ) -> None:
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._smtp_user = smtp_user
        self._smtp_password = smtp_password
        self._from_address = from_address
        self._from_name = from_name

    @property
    def channel(self) -> DeliveryChannel:
        return DeliveryChannel.EMAIL

    async def validate_config(self) -> bool:
        """Check if email is properly configured."""
        return self._smtp_host is not None

    async def send(
        self,
        update: CommunicationUpdate,
        recipients: list[Stakeholder],
    ) -> DeliveryResult:
        """Send update via email."""
        try:
            # Get email addresses
            emails = [r.email for r in recipients if r.email]

            if not emails:
                return DeliveryResult(
                    channel=DeliveryChannel.EMAIL,
                    success=False,
                    status=DeliveryStatus.SKIPPED,
                    error="No email recipients",
                )

            # Simulate sending (in production, use SMTP/SES/SendGrid)
            logger.info(
                "email_sent",
                incident_id=update.incident_id,
                recipient_count=len(emails),
                subject=update.subject,
            )

            return DeliveryResult(
                channel=DeliveryChannel.EMAIL,
                success=True,
                status=DeliveryStatus.DELIVERED,
                recipient_count=len(emails),
                message=f"Sent to {len(emails)} email addresses",
                message_id=secrets.token_hex(8),
                details={
                    "recipients": emails,
                    "from": self._from_address,
                    "simulated": True,
                },
            )

        except Exception as e:
            logger.error("email_send_error", error=str(e))
            return DeliveryResult(
                channel=DeliveryChannel.EMAIL,
                success=False,
                status=DeliveryStatus.FAILED,
                error=str(e),
            )

    async def send_individual(
        self,
        to_address: str,
        subject: str,
        body: str,
        body_html: str | None = None,
        reply_to: str | None = None,
    ) -> DeliveryResult:
        """Send an individual email."""
        try:
            logger.info(
                "individual_email_sent",
                to=to_address,
                subject=subject,
            )

            return DeliveryResult(
                channel=DeliveryChannel.EMAIL,
                success=True,
                status=DeliveryStatus.DELIVERED,
                recipient_count=1,
                message=f"Sent to {to_address}",
                message_id=secrets.token_hex(8),
                details={
                    "to": to_address,
                    "from": self._from_address,
                    "reply_to": reply_to,
                    "has_html": body_html is not None,
                    "simulated": True,
                },
            )

        except Exception as e:
            return DeliveryResult(
                channel=DeliveryChannel.EMAIL,
                success=False,
                status=DeliveryStatus.FAILED,
                error=str(e),
            )


class SMSChannel(ChannelHandler):
    """SMS delivery channel for urgent notifications."""

    def __init__(
        self,
        provider: str = "twilio",
        account_sid: str | None = None,
        auth_token: str | None = None,
        from_number: str | None = None,
    ) -> None:
        self._provider = provider
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number

    @property
    def channel(self) -> DeliveryChannel:
        return DeliveryChannel.SMS

    async def validate_config(self) -> bool:
        """Check if SMS is properly configured."""
        return all([self._account_sid, self._auth_token, self._from_number])

    async def send(
        self,
        update: CommunicationUpdate,
        recipients: list[Stakeholder],
    ) -> DeliveryResult:
        """Send update via SMS."""
        try:
            # Get phone numbers
            phones = [r.phone for r in recipients if r.phone]

            if not phones:
                return DeliveryResult(
                    channel=DeliveryChannel.SMS,
                    success=False,
                    status=DeliveryStatus.SKIPPED,
                    error="No SMS recipients",
                )

            # Truncate message for SMS (160 char limit per segment)
            sms_body = f"[{update.subject[:50]}] {update.body[:100]}..."

            # Simulate sending (in production, use Twilio/AWS SNS)
            logger.info(
                "sms_sent",
                incident_id=update.incident_id,
                recipient_count=len(phones),
            )

            return DeliveryResult(
                channel=DeliveryChannel.SMS,
                success=True,
                status=DeliveryStatus.DELIVERED,
                recipient_count=len(phones),
                message=f"Sent to {len(phones)} phone numbers",
                message_id=secrets.token_hex(8),
                details={
                    "recipient_count": len(phones),
                    "from": self._from_number,
                    "provider": self._provider,
                    "simulated": True,
                },
            )

        except Exception as e:
            logger.error("sms_send_error", error=str(e))
            return DeliveryResult(
                channel=DeliveryChannel.SMS,
                success=False,
                status=DeliveryStatus.FAILED,
                error=str(e),
            )


class StatusPageChannel(ChannelHandler):
    """Status page delivery channel for public updates."""

    def __init__(
        self,
        api_key: str | None = None,
        page_id: str | None = None,
        base_url: str = "https://api.statuspage.io/v1",
    ) -> None:
        self._api_key = api_key
        self._page_id = page_id
        self._base_url = base_url

    @property
    def channel(self) -> DeliveryChannel:
        return DeliveryChannel.STATUS_PAGE

    async def validate_config(self) -> bool:
        """Check if status page is properly configured."""
        return all([self._api_key, self._page_id])

    async def send(
        self,
        update: CommunicationUpdate,
        recipients: list[Stakeholder],
    ) -> DeliveryResult:
        """Post update to status page."""
        try:
            # Status page updates are public, recipients not used
            logger.info(
                "statuspage_update_posted",
                incident_id=update.incident_id,
                subject=update.subject,
            )

            return DeliveryResult(
                channel=DeliveryChannel.STATUS_PAGE,
                success=True,
                status=DeliveryStatus.DELIVERED,
                recipient_count=0,  # Public, no specific count
                message="Posted to status page",
                message_id=secrets.token_hex(8),
                details={
                    "page_id": self._page_id,
                    "status": "investigating",
                    "simulated": True,
                },
            )

        except Exception as e:
            logger.error("statuspage_error", error=str(e))
            return DeliveryResult(
                channel=DeliveryChannel.STATUS_PAGE,
                success=False,
                status=DeliveryStatus.FAILED,
                error=str(e),
            )

    async def create_incident(
        self,
        name: str,
        body: str,
        status: str = "investigating",
        component_ids: list[str] | None = None,
        impact: str = "minor",
    ) -> DeliveryResult:
        """Create a new incident on the status page."""
        try:
            logger.info(
                "statuspage_incident_created",
                name=name,
                status=status,
                impact=impact,
            )

            return DeliveryResult(
                channel=DeliveryChannel.STATUS_PAGE,
                success=True,
                status=DeliveryStatus.DELIVERED,
                message="Status page incident created",
                message_id=secrets.token_hex(12),  # Incident ID
                details={
                    "page_id": self._page_id,
                    "status": status,
                    "impact": impact,
                    "components": component_ids,
                    "simulated": True,
                },
            )

        except Exception as e:
            return DeliveryResult(
                channel=DeliveryChannel.STATUS_PAGE,
                success=False,
                status=DeliveryStatus.FAILED,
                error=str(e),
            )

    async def update_incident(
        self,
        incident_id: str,
        body: str,
        status: str,
    ) -> DeliveryResult:
        """Update an existing status page incident."""
        try:
            logger.info(
                "statuspage_incident_updated",
                incident_id=incident_id,
                status=status,
            )

            return DeliveryResult(
                channel=DeliveryChannel.STATUS_PAGE,
                success=True,
                status=DeliveryStatus.DELIVERED,
                message="Status page incident updated",
                message_id=incident_id,
                details={
                    "page_id": self._page_id,
                    "new_status": status,
                    "simulated": True,
                },
            )

        except Exception as e:
            return DeliveryResult(
                channel=DeliveryChannel.STATUS_PAGE,
                success=False,
                status=DeliveryStatus.FAILED,
                error=str(e),
            )


class TeamsChannel(ChannelHandler):
    """Microsoft Teams delivery channel."""

    def __init__(
        self,
        webhook_url: str | None = None,
    ) -> None:
        self._webhook_url = webhook_url

    @property
    def channel(self) -> DeliveryChannel:
        return DeliveryChannel.TEAMS

    async def validate_config(self) -> bool:
        """Check if Teams is properly configured."""
        return self._webhook_url is not None

    async def send(
        self,
        update: CommunicationUpdate,
        recipients: list[Stakeholder],
    ) -> DeliveryResult:
        """Send update via Teams."""
        try:
            # Get Teams user IDs for mentions
            teams_ids = [r.teams_user_id for r in recipients if r.teams_user_id]

            logger.info(
                "teams_message_sent",
                incident_id=update.incident_id,
                mention_count=len(teams_ids),
            )

            return DeliveryResult(
                channel=DeliveryChannel.TEAMS,
                success=True,
                status=DeliveryStatus.DELIVERED,
                recipient_count=len(teams_ids) or 1,  # At least channel
                message="Posted to Teams",
                message_id=secrets.token_hex(8),
                details={
                    "mentions": teams_ids,
                    "simulated": True,
                },
            )

        except Exception as e:
            logger.error("teams_send_error", error=str(e))
            return DeliveryResult(
                channel=DeliveryChannel.TEAMS,
                success=False,
                status=DeliveryStatus.FAILED,
                error=str(e),
            )


class WebhookChannel(ChannelHandler):
    """Generic webhook delivery channel for custom integrations."""

    def __init__(
        self,
        webhook_urls: list[str] | None = None,
    ) -> None:
        self._webhook_urls = webhook_urls or []

    @property
    def channel(self) -> DeliveryChannel:
        return DeliveryChannel.WEBHOOK

    async def validate_config(self) -> bool:
        """Check if webhooks are configured."""
        return len(self._webhook_urls) > 0

    async def send(
        self,
        update: CommunicationUpdate,
        recipients: list[Stakeholder],
    ) -> DeliveryResult:
        """Send update to webhooks."""
        try:
            if not self._webhook_urls:
                return DeliveryResult(
                    channel=DeliveryChannel.WEBHOOK,
                    success=False,
                    status=DeliveryStatus.SKIPPED,
                    error="No webhooks configured",
                )

            logger.info(
                "webhook_sent",
                incident_id=update.incident_id,
                webhook_count=len(self._webhook_urls),
            )

            return DeliveryResult(
                channel=DeliveryChannel.WEBHOOK,
                success=True,
                status=DeliveryStatus.DELIVERED,
                recipient_count=len(self._webhook_urls),
                message=f"Posted to {len(self._webhook_urls)} webhooks",
                message_id=secrets.token_hex(8),
                details={
                    "webhook_count": len(self._webhook_urls),
                    "simulated": True,
                },
            )

        except Exception as e:
            logger.error("webhook_send_error", error=str(e))
            return DeliveryResult(
                channel=DeliveryChannel.WEBHOOK,
                success=False,
                status=DeliveryStatus.FAILED,
                error=str(e),
            )


class ChannelDelivery:
    """Orchestrates multi-channel communication delivery."""

    def __init__(self) -> None:
        self._handlers: dict[DeliveryChannel, ChannelHandler] = {}
        self._audit_log: list[CommunicationAuditEntry] = []

    def register_handler(self, handler: ChannelHandler) -> None:
        """Register a channel handler."""
        self._handlers[handler.channel] = handler
        logger.info("channel_handler_registered", channel=handler.channel)

    def get_handler(self, channel: DeliveryChannel) -> ChannelHandler | None:
        """Get a registered channel handler."""
        return self._handlers.get(channel)

    async def initialize_default_handlers(self) -> None:
        """Initialize default channel handlers."""
        # Register default handlers (unconfigured but available)
        self.register_handler(SlackChannel())
        self.register_handler(EmailChannel())
        self.register_handler(SMSChannel())
        self.register_handler(StatusPageChannel())
        self.register_handler(TeamsChannel())
        self.register_handler(WebhookChannel())

        logger.info("default_channel_handlers_initialized")

    async def send_update(
        self,
        update: CommunicationUpdate,
        stakeholders: list[Stakeholder],
    ) -> dict[DeliveryChannel, DeliveryResult]:
        """Send an update through all specified channels.

        Returns a dict mapping channel to delivery result.
        """
        results: dict[DeliveryChannel, DeliveryResult] = {}

        # Determine which channels to use
        channels = update.channels
        if not channels:
            # Default to stakeholder preferences
            for stakeholder in stakeholders:
                channels.extend(stakeholder.preferred_channels)
            channels = list(set(channels))

        # Send to each channel concurrently
        tasks = []
        for channel in channels:
            handler = self._handlers.get(channel)
            if handler:
                task = self._send_via_channel(handler, update, stakeholders)
                tasks.append((channel, task))
            else:
                results[channel] = DeliveryResult(
                    channel=channel,
                    success=False,
                    status=DeliveryStatus.FAILED,
                    error=f"No handler for channel: {channel}",
                )

        # Await all channel deliveries
        if tasks:
            channel_results = await asyncio.gather(
                *[task for _, task in tasks],
                return_exceptions=True,
            )

            for (channel, _), result in zip(tasks, channel_results):
                if isinstance(result, Exception):
                    results[channel] = DeliveryResult(
                        channel=channel,
                        success=False,
                        status=DeliveryStatus.FAILED,
                        error=str(result),
                    )
                else:
                    results[channel] = result

        # Log audit entry
        await self._log_audit(update, stakeholders, results)

        # Update delivery status on the update object
        for channel, result in results.items():
            update.delivery_results[channel.value] = result.status

        # Set overall status
        if all(r.success for r in results.values()):
            update.status = DeliveryStatus.DELIVERED
        elif any(r.success for r in results.values()):
            update.status = DeliveryStatus.DELIVERED  # Partial success
        else:
            update.status = DeliveryStatus.FAILED

        update.sent_at = datetime.utcnow()

        return results

    async def _send_via_channel(
        self,
        handler: ChannelHandler,
        update: CommunicationUpdate,
        stakeholders: list[Stakeholder],
    ) -> DeliveryResult:
        """Send update via a specific channel handler."""
        try:
            return await handler.send(update, stakeholders)
        except Exception as e:
            logger.error(
                "channel_send_error",
                channel=handler.channel,
                error=str(e),
            )
            return DeliveryResult(
                channel=handler.channel,
                success=False,
                status=DeliveryStatus.FAILED,
                error=str(e),
            )

    async def _log_audit(
        self,
        update: CommunicationUpdate,
        stakeholders: list[Stakeholder],
        results: dict[DeliveryChannel, DeliveryResult],
    ) -> None:
        """Log audit entry for the communication."""
        for channel, result in results.items():
            entry = CommunicationAuditEntry(
                incident_id=update.incident_id,
                plan_id=update.plan_id,
                update_id=update.id,
                event_type="delivered" if result.success else "failed",
                channel=channel,
                audience_type=update.audience_type,
                recipient_count=result.recipient_count,
                success=result.success,
                error_message=result.error,
                details={
                    "message_id": result.message_id,
                    "channel_details": result.details,
                },
                triggered_by=update.created_by or "system",
                tenant_id=update.tenant_id,
            )
            self._audit_log.append(entry)

    async def get_audit_log(
        self,
        incident_id: str | None = None,
        update_id: str | None = None,
        channel: DeliveryChannel | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[CommunicationAuditEntry], int]:
        """Get communication audit log with filters."""
        entries = self._audit_log.copy()

        if incident_id:
            entries = [e for e in entries if e.incident_id == incident_id]

        if update_id:
            entries = [e for e in entries if e.update_id == update_id]

        if channel:
            entries = [e for e in entries if e.channel == channel]

        # Sort by timestamp descending
        entries.sort(key=lambda e: e.timestamp, reverse=True)

        total = len(entries)
        entries = entries[offset:offset + limit]

        return entries, total

    async def broadcast_to_all(
        self,
        update: CommunicationUpdate,
        stakeholders: list[Stakeholder],
        exclude_channels: list[DeliveryChannel] | None = None,
    ) -> dict[DeliveryChannel, DeliveryResult]:
        """Broadcast update to all available channels."""
        exclude = exclude_channels or []
        update.channels = [
            ch for ch in self._handlers.keys()
            if ch not in exclude
        ]
        return await self.send_update(update, stakeholders)

    def get_available_channels(self) -> list[DeliveryChannel]:
        """Get list of available (registered) channels."""
        return list(self._handlers.keys())


# Singleton instance
_delivery: ChannelDelivery | None = None


async def get_channel_delivery() -> ChannelDelivery:
    """Get the singleton channel delivery instance."""
    global _delivery
    if _delivery is None:
        _delivery = ChannelDelivery()
        await _delivery.initialize_default_handlers()
    return _delivery
