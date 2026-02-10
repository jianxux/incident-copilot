"""Delivery helpers for on-call handoff summaries."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import structlog

from ..config import Settings
from ..notifications.channels import create_channel
from ..notifications.models import (
    ChannelType,
    NotificationChannel,
    NotificationPayload,
    NotificationType,
    Severity,
)
from .models import HandoffConfig, HandoffDeliveryChannel, HandoffSummary

logger = structlog.get_logger()


class HandoffDeliveryService:
    """Deliver handoff summaries to Slack/Teams/Email/In-app."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def deliver(
        self,
        summary: HandoffSummary,
        config: HandoffConfig,
        base_url: str | None = None,
    ) -> list[dict]:
        """Deliver a summary based on a HandoffConfig."""

        results: list[dict] = []
        for ch in config.delivery_channels:
            try:
                if ch == HandoffDeliveryChannel.SLACK and config.slack_target:
                    res = await self._send_slack(summary, config.slack_target, base_url)
                    results.append({"channel": "slack", **res})
                elif ch == HandoffDeliveryChannel.TEAMS and (
                    config.teams_webhook_url or self.settings.teams_webhook_url
                ):
                    res = await self._send_teams(
                        summary,
                        config.teams_webhook_url or self.settings.teams_webhook_url,
                        base_url,
                    )
                    results.append({"channel": "teams", **res})
                elif ch == HandoffDeliveryChannel.EMAIL and config.email_target:
                    res = await self._send_email(summary, config.email_target, base_url)
                    results.append({"channel": "email", **res})
                elif ch == HandoffDeliveryChannel.IN_APP:
                    results.append(
                        {
                            "channel": "in_app",
                            "success": True,
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
            except Exception as e:
                logger.warning("handoff_delivery_failed", channel=str(ch), error=str(e))
                results.append({"channel": str(ch), "success": False, "error": str(e)})

        return results

    async def _send_slack(
        self, summary: HandoffSummary, slack_target: str, base_url: str | None
    ) -> dict:
        if not (self.settings.slack_bot_token or slack_target.startswith("https://")):
            # Without a bot token, SlackChannel will treat address as webhook.
            # Allow webhook-only by letting the target be a webhook URL.
            pass

        handoff_url = (
            f"{base_url.rstrip('/')}/api/v1/oncall/handoff/latest" if base_url else ""
        )

        payload = NotificationPayload(
            id=str(uuid4()),
            type=NotificationType.DIGEST,
            severity=Severity.P3,
            title=summary.title,
            message=summary.brief_markdown[:3900],
            data={"handoff_url": handoff_url, "handoff_id": summary.id},
        )

        channel_cfg = NotificationChannel(
            type=ChannelType.SLACK,
            address=slack_target,
            enabled=True,
            settings={
                # If slack_target is a user/channel id, use bot token flow
                "bot_token": self.settings.slack_bot_token or None,
                "channel": slack_target,
                "webhook_url": (
                    slack_target if slack_target.startswith("https://") else None
                ),
            },
        )

        channel = create_channel(channel_cfg)
        try:
            result = await channel.send(payload)
            return {"success": True, "result": result}
        finally:
            await channel.close()

    async def _send_teams(
        self, summary: HandoffSummary, webhook_url: str, base_url: str | None
    ) -> dict:
        # Teams is handled as a webhook for now.
        handoff_url = (
            f"{base_url.rstrip('/')}/api/v1/oncall/handoff/latest" if base_url else ""
        )

        payload = NotificationPayload(
            id=str(uuid4()),
            type=NotificationType.DIGEST,
            severity=Severity.P3,
            title=summary.title,
            message=summary.brief_markdown,
            data={"handoff_url": handoff_url, "handoff_id": summary.id},
        )

        channel_cfg = NotificationChannel(
            type=ChannelType.WEBHOOK,
            address=webhook_url,
            enabled=True,
            settings={
                "headers": {"Content-Type": "application/json"},
            },
        )

        channel = create_channel(channel_cfg)
        try:
            result = await channel.send(payload)
            return {"success": True, "result": result}
        finally:
            await channel.close()

    async def _send_email(
        self, summary: HandoffSummary, email: str, base_url: str | None
    ) -> dict:
        handoff_url = (
            f"{base_url.rstrip('/')}/api/v1/oncall/handoff/latest" if base_url else ""
        )
        payload = NotificationPayload(
            id=str(uuid4()),
            type=NotificationType.DIGEST,
            severity=Severity.P3,
            title=summary.title,
            message=summary.brief_markdown,
            data={"handoff_url": handoff_url, "handoff_id": summary.id},
        )

        channel_cfg = NotificationChannel(
            type=ChannelType.EMAIL,
            address=email,
            enabled=True,
            settings={},
        )

        channel = create_channel(channel_cfg)
        try:
            result = await channel.send(payload)
            return {"success": True, "result": result}
        finally:
            await channel.close()
