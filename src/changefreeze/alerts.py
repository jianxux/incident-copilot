"""Alerting for change freeze violations."""

import structlog

from ..config import Settings, get_settings
from .models import ChangeFreeze, FreezeException, FreezeViolation, ViolationSeverity
from .store import ChangeFreezeStore, changefreeze_store

logger = structlog.get_logger()


class FreezeAlertService:
    """
    Service for sending alerts about change freeze violations and events.
    
    Supports:
    - Slack notifications
    - Email notifications (via webhook)
    - Custom webhook notifications
    """

    def __init__(
        self,
        store: ChangeFreezeStore | None = None,
        settings: Settings | None = None,
    ):
        self.store = store or changefreeze_store
        self.settings = settings or get_settings()

    async def alert_violation(
        self,
        violation: FreezeViolation,
        freeze: ChangeFreeze | None = None,
    ) -> list[str]:
        """
        Send alerts for a freeze violation.
        
        Args:
            violation: The violation to alert on
            freeze: Optional freeze context (will fetch if not provided)
            
        Returns:
            List of channels that were notified
        """
        if violation.alert_sent:
            logger.debug(
                "violation_already_alerted",
                violation_id=violation.violation_id,
            )
            return violation.alert_channels

        # Get freeze context if not provided
        if not freeze:
            freeze = await self.store.get_freeze(violation.freeze_id)
        
        channels_notified = []

        # Send to Slack
        if self.settings.slack_bot_token:
            slack_channels = self._get_slack_channels(freeze)
            for channel in slack_channels:
                try:
                    await self._send_slack_alert(violation, freeze, channel)
                    channels_notified.append(f"slack:{channel}")
                except Exception as e:
                    logger.error(
                        "slack_alert_failed",
                        violation_id=violation.violation_id,
                        channel=channel,
                        error=str(e),
                    )

        # Send to Teams
        if self.settings.teams_webhook_url:
            try:
                await self._send_teams_alert(violation, freeze)
                channels_notified.append("teams:webhook")
            except Exception as e:
                logger.error(
                    "teams_alert_failed",
                    violation_id=violation.violation_id,
                    error=str(e),
                )

        # Mark as alerted
        if channels_notified:
            await self.store.mark_violation_alerted(
                violation_id=violation.violation_id,
                channels=channels_notified,
            )
            logger.info(
                "violation_alert_sent",
                violation_id=violation.violation_id,
                channels=channels_notified,
            )

        return channels_notified

    async def alert_freeze_starting(
        self,
        freeze: ChangeFreeze,
    ) -> list[str]:
        """Send notification that a freeze is starting."""
        channels_notified = []

        if self.settings.slack_bot_token:
            slack_channels = self._get_slack_channels(freeze)
            for channel in slack_channels:
                try:
                    await self._send_slack_freeze_notification(
                        freeze, channel, "starting"
                    )
                    channels_notified.append(f"slack:{channel}")
                except Exception as e:
                    logger.error(
                        "slack_freeze_notification_failed",
                        freeze_id=freeze.freeze_id,
                        channel=channel,
                        error=str(e),
                    )

        if self.settings.teams_webhook_url:
            try:
                await self._send_teams_freeze_notification(freeze, "starting")
                channels_notified.append("teams:webhook")
            except Exception as e:
                logger.error(
                    "teams_freeze_notification_failed",
                    freeze_id=freeze.freeze_id,
                    error=str(e),
                )

        return channels_notified

    async def alert_freeze_ending(
        self,
        freeze: ChangeFreeze,
    ) -> list[str]:
        """Send notification that a freeze is ending."""
        channels_notified = []

        if self.settings.slack_bot_token:
            slack_channels = self._get_slack_channels(freeze)
            for channel in slack_channels:
                try:
                    await self._send_slack_freeze_notification(
                        freeze, channel, "ending"
                    )
                    channels_notified.append(f"slack:{channel}")
                except Exception as e:
                    logger.error(
                        "slack_freeze_notification_failed",
                        freeze_id=freeze.freeze_id,
                        channel=channel,
                        error=str(e),
                    )

        if self.settings.teams_webhook_url:
            try:
                await self._send_teams_freeze_notification(freeze, "ending")
                channels_notified.append("teams:webhook")
            except Exception as e:
                logger.error(
                    "teams_freeze_notification_failed",
                    freeze_id=freeze.freeze_id,
                    error=str(e),
                )

        return channels_notified

    async def alert_exception_requested(
        self,
        exception: FreezeException,
        freeze: ChangeFreeze | None = None,
    ) -> list[str]:
        """Send notification about a new exception request."""
        if not freeze:
            freeze = await self.store.get_freeze(exception.freeze_id)

        channels_notified = []

        if self.settings.slack_bot_token:
            # Notify approvers
            for approver in (freeze.approvers if freeze else []):
                try:
                    await self._send_slack_exception_notification(
                        exception, freeze, approver, "requested"
                    )
                    channels_notified.append(f"slack:dm:{approver}")
                except Exception as e:
                    logger.error(
                        "slack_exception_notification_failed",
                        exception_id=exception.exception_id,
                        approver=approver,
                        error=str(e),
                    )

            # Also notify channels
            slack_channels = self._get_slack_channels(freeze)
            for channel in slack_channels:
                try:
                    await self._send_slack_exception_notification(
                        exception, freeze, channel, "requested"
                    )
                    channels_notified.append(f"slack:{channel}")
                except Exception as e:
                    logger.error(
                        "slack_exception_notification_failed",
                        exception_id=exception.exception_id,
                        channel=channel,
                        error=str(e),
                    )

        return channels_notified

    async def alert_exception_reviewed(
        self,
        exception: FreezeException,
        freeze: ChangeFreeze | None = None,
    ) -> list[str]:
        """Send notification about exception approval/rejection."""
        if not freeze:
            freeze = await self.store.get_freeze(exception.freeze_id)

        channels_notified = []

        if self.settings.slack_bot_token:
            # Notify the requester
            try:
                await self._send_slack_exception_notification(
                    exception, freeze, exception.requested_by, "reviewed"
                )
                channels_notified.append(f"slack:dm:{exception.requested_by}")
            except Exception as e:
                logger.error(
                    "slack_exception_notification_failed",
                    exception_id=exception.exception_id,
                    error=str(e),
                )

        return channels_notified

    def _get_slack_channels(self, freeze: ChangeFreeze | None) -> list[str]:
        """Get Slack channels to notify for a freeze."""
        channels = []
        
        if freeze and freeze.notification_channels:
            channels.extend([
                c for c in freeze.notification_channels
                if c.startswith("#") or c.startswith("C")
            ])
        
        if not channels and self.settings.slack_default_channel:
            channels.append(self.settings.slack_default_channel)
        
        return channels

    def _format_violation_message(
        self,
        violation: FreezeViolation,
        freeze: ChangeFreeze | None,
    ) -> dict:
        """Format a violation alert message for Slack."""
        severity_emoji = {
            ViolationSeverity.CRITICAL: "🚨",
            ViolationSeverity.HIGH: "⚠️",
            ViolationSeverity.MEDIUM: "⚡",
            ViolationSeverity.LOW: "ℹ️",
        }

        emoji = severity_emoji.get(violation.severity, "⚠️")
        freeze_name = freeze.name if freeze else violation.freeze_name or "Unknown"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Change Freeze Violation Detected",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Service:*\n{violation.service_name}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Environment:*\n{violation.environment}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Deployed By:*\n{violation.deployed_by}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:*\n{violation.severity.value.upper()}",
                    },
                ],
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Freeze:*\n{freeze_name}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Repository:*\n{violation.repository}",
                    },
                ],
            },
        ]

        if violation.commit_sha:
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Commit: `{violation.commit_sha[:8]}`",
                    }
                ],
            })

        if violation.commit_message:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Commit Message:*\n```{violation.commit_message[:200]}```",
                },
            })

        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Acknowledge",
                    },
                    "style": "primary",
                    "action_id": f"acknowledge_violation_{violation.violation_id}",
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "View Details",
                    },
                    "url": f"{self.settings.app_url}/api/changefreeze/violations/{violation.violation_id}",
                },
            ],
        })

        return {
            "blocks": blocks,
            "text": f"{emoji} Change Freeze Violation: {violation.service_name} deployed to {violation.environment} by {violation.deployed_by}",
        }

    async def _send_slack_alert(
        self,
        violation: FreezeViolation,
        freeze: ChangeFreeze | None,
        channel: str,
    ) -> None:
        """Send a Slack alert for a violation."""
        import httpx

        message = self._format_violation_message(violation, freeze)
        message["channel"] = channel

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {self.settings.slack_bot_token}",
                    "Content-Type": "application/json",
                },
                json=message,
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                raise Exception(f"Slack API error: {data.get('error')}")

    async def _send_teams_alert(
        self,
        violation: FreezeViolation,
        freeze: ChangeFreeze | None,
    ) -> None:
        """Send a Teams alert for a violation."""
        import httpx

        freeze_name = freeze.name if freeze else violation.freeze_name or "Unknown"

        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "FF0000" if violation.severity == ViolationSeverity.CRITICAL else "FFA500",
            "summary": f"Change Freeze Violation: {violation.service_name}",
            "sections": [
                {
                    "activityTitle": "🚨 Change Freeze Violation Detected",
                    "facts": [
                        {"name": "Service", "value": violation.service_name},
                        {"name": "Environment", "value": violation.environment},
                        {"name": "Deployed By", "value": violation.deployed_by},
                        {"name": "Severity", "value": violation.severity.value.upper()},
                        {"name": "Freeze", "value": freeze_name},
                        {"name": "Repository", "value": violation.repository},
                    ],
                    "markdown": True,
                }
            ],
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.settings.teams_webhook_url,
                json=card,
            )
            response.raise_for_status()

    async def _send_slack_freeze_notification(
        self,
        freeze: ChangeFreeze,
        channel: str,
        event_type: str,
    ) -> None:
        """Send a Slack notification about freeze starting/ending."""
        import httpx

        if event_type == "starting":
            emoji = "🧊"
            title = "Change Freeze Starting"
            color = "#0066CC"
        else:
            emoji = "☀️"
            title = "Change Freeze Ending"
            color = "#00CC66"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {title}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Name:*\n{freeze.name}"},
                    {"type": "mrkdwn", "text": f"*Scope:*\n{freeze.scope.value}"},
                    {"type": "mrkdwn", "text": f"*Starts:*\n{freeze.starts_at.isoformat()}"},
                    {"type": "mrkdwn", "text": f"*Ends:*\n{freeze.ends_at.isoformat()}"},
                ],
            },
        ]

        if freeze.description:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Description:*\n{freeze.description}"},
            })

        if freeze.services:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Affected Services:*\n{', '.join(freeze.services)}"},
            })

        message = {
            "channel": channel,
            "blocks": blocks,
            "text": f"{emoji} {title}: {freeze.name}",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {self.settings.slack_bot_token}",
                    "Content-Type": "application/json",
                },
                json=message,
            )
            response.raise_for_status()

    async def _send_teams_freeze_notification(
        self,
        freeze: ChangeFreeze,
        event_type: str,
    ) -> None:
        """Send a Teams notification about freeze starting/ending."""
        import httpx

        if event_type == "starting":
            title = "🧊 Change Freeze Starting"
            color = "0066CC"
        else:
            title = "☀️ Change Freeze Ending"
            color = "00CC66"

        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": color,
            "summary": title,
            "sections": [
                {
                    "activityTitle": title,
                    "facts": [
                        {"name": "Name", "value": freeze.name},
                        {"name": "Scope", "value": freeze.scope.value},
                        {"name": "Starts", "value": freeze.starts_at.isoformat()},
                        {"name": "Ends", "value": freeze.ends_at.isoformat()},
                    ],
                    "markdown": True,
                }
            ],
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.settings.teams_webhook_url,
                json=card,
            )
            response.raise_for_status()

    async def _send_slack_exception_notification(
        self,
        exception: FreezeException,
        freeze: ChangeFreeze | None,
        target: str,
        event_type: str,
    ) -> None:
        """Send a Slack notification about exception request/review."""
        import httpx

        freeze_name = freeze.name if freeze else "Unknown"

        if event_type == "requested":
            emoji = "📋"
            title = "Freeze Exception Requested"
            color = "#FFA500"
        else:
            if exception.status.value == "approved":
                emoji = "✅"
                title = "Freeze Exception Approved"
                color = "#00CC66"
            else:
                emoji = "❌"
                title = "Freeze Exception Rejected"
                color = "#CC0000"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {title}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Service:*\n{exception.service_name}"},
                    {"type": "mrkdwn", "text": f"*Environment:*\n{exception.environment}"},
                    {"type": "mrkdwn", "text": f"*Requested By:*\n{exception.requested_by}"},
                    {"type": "mrkdwn", "text": f"*Freeze:*\n{freeze_name}"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Reason:*\n{exception.reason}"},
            },
        ]

        if exception.is_emergency:
            blocks.append({
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"🚨 *Emergency Deployment* - Ticket: {exception.emergency_ticket_id}"},
                ],
            })

        if event_type == "requested":
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve"},
                        "style": "primary",
                        "action_id": f"approve_exception_{exception.exception_id}",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Reject"},
                        "style": "danger",
                        "action_id": f"reject_exception_{exception.exception_id}",
                    },
                ],
            })
        elif exception.review_notes:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Review Notes:*\n{exception.review_notes}"},
            })

        message = {
            "channel": target,
            "blocks": blocks,
            "text": f"{emoji} {title}: {exception.service_name}",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {self.settings.slack_bot_token}",
                    "Content-Type": "application/json",
                },
                json=message,
            )
            response.raise_for_status()


# Global alert service instance
freeze_alert_service = FreezeAlertService()
