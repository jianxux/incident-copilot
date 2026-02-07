"""Delivery adapters for sending reports via various channels."""

import asyncio
import json
import smtplib
import ssl
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import httpx
import structlog

from ..config import Settings, get_settings
from .models import DeliveryChannel, DeliveryConfig, ReportContent

logger = structlog.get_logger()


class DeliveryAdapter(ABC):
    """Base class for delivery adapters."""

    @abstractmethod
    async def deliver(
        self,
        content: ReportContent,
        config: DeliveryConfig,
    ) -> dict[str, Any]:
        """
        Deliver a report.

        Returns a dict with delivery result information.
        """
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the adapter is properly configured."""
        pass


class EmailDeliveryAdapter(DeliveryAdapter):
    """
    Email delivery adapter supporting SMTP and AWS SES.

    Sends HTML reports via email with Markdown as fallback.
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        # Email settings - these would be added to config.py
        self.smtp_host = getattr(self.settings, "smtp_host", "")
        self.smtp_port = getattr(self.settings, "smtp_port", 587)
        self.smtp_username = getattr(self.settings, "smtp_username", "")
        self.smtp_password = getattr(self.settings, "smtp_password", "")
        self.smtp_use_tls = getattr(self.settings, "smtp_use_tls", True)
        self.smtp_from_email = getattr(self.settings, "smtp_from_email", "")
        self.smtp_from_name = getattr(
            self.settings, "smtp_from_name", "Incident Copilot"
        )

        # AWS SES settings
        self.ses_region = getattr(self.settings, "ses_region", self.settings.aws_region)
        self.ses_from_email = getattr(self.settings, "ses_from_email", "")
        self.use_ses = getattr(self.settings, "email_provider", "smtp") == "ses"

    def is_configured(self) -> bool:
        """Check if email is configured."""
        if self.use_ses:
            return bool(self.ses_region and self.ses_from_email)
        return bool(self.smtp_host and self.smtp_from_email)

    async def deliver(
        self,
        content: ReportContent,
        config: DeliveryConfig,
    ) -> dict[str, Any]:
        """Deliver report via email."""
        if not config.recipients:
            return {
                "success": False,
                "error": "No recipients specified",
                "channel": "email",
            }

        if not self.is_configured():
            return {
                "success": False,
                "error": "Email not configured",
                "channel": "email",
            }

        try:
            if self.use_ses:
                result = await self._send_via_ses(content, config)
            else:
                result = await self._send_via_smtp(content, config)

            logger.info(
                "email_delivered",
                recipients=config.recipients,
                subject=self._get_subject(content, config),
            )
            return result

        except Exception as e:
            logger.error("email_delivery_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "channel": "email",
            }

    def _get_subject(self, content: ReportContent, config: DeliveryConfig) -> str:
        """Generate email subject."""
        if config.subject_template:
            return config.subject_template.format(
                title=content.title,
                period_start=content.period_start.strftime("%Y-%m-%d"),
                period_end=content.period_end.strftime("%Y-%m-%d"),
            )
        return content.title

    def _build_message(
        self,
        content: ReportContent,
        config: DeliveryConfig,
    ) -> MIMEMultipart:
        """Build email message with HTML and plain text parts."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = self._get_subject(content, config)
        msg["From"] = (
            f"{self.smtp_from_name} <{self.smtp_from_email or self.ses_from_email}>"
        )
        msg["To"] = ", ".join(config.recipients)

        # Plain text version (Markdown)
        if content.markdown:
            text_part = MIMEText(content.markdown, "plain", "utf-8")
            msg.attach(text_part)

        # HTML version
        if content.html:
            html_part = MIMEText(content.html, "html", "utf-8")
            msg.attach(html_part)

        return msg

    async def _send_via_smtp(
        self,
        content: ReportContent,
        config: DeliveryConfig,
    ) -> dict[str, Any]:
        """Send email via SMTP."""
        msg = self._build_message(content, config)

        # Run SMTP send in thread pool to not block
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            self._smtp_send_sync,
            msg,
            config.recipients,
        )

        return {
            "success": True,
            "channel": "email",
            "provider": "smtp",
            "recipients": config.recipients,
            "subject": msg["Subject"],
        }

    def _smtp_send_sync(self, msg: MIMEMultipart, recipients: list[str]) -> None:
        """Synchronous SMTP send (run in executor)."""
        context = ssl.create_default_context() if self.smtp_use_tls else None

        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            if self.smtp_use_tls:
                server.starttls(context=context)
            if self.smtp_username and self.smtp_password:
                server.login(self.smtp_username, self.smtp_password)
            server.sendmail(self.smtp_from_email, recipients, msg.as_string())

    async def _send_via_ses(
        self,
        content: ReportContent,
        config: DeliveryConfig,
    ) -> dict[str, Any]:
        """Send email via AWS SES."""
        try:
            import boto3
        except ImportError:
            return {
                "success": False,
                "error": "boto3 not installed",
                "channel": "email",
            }

        subject = self._get_subject(content, config)

        # Build SES message
        message = {
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {},
        }

        if content.html:
            message["Body"]["Html"] = {"Data": content.html, "Charset": "UTF-8"}
        if content.markdown:
            message["Body"]["Text"] = {"Data": content.markdown, "Charset": "UTF-8"}

        # Run SES send in thread pool
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            self._ses_send_sync,
            config.recipients,
            message,
        )

        return {
            "success": True,
            "channel": "email",
            "provider": "ses",
            "recipients": config.recipients,
            "subject": subject,
        }

    def _ses_send_sync(self, recipients: list[str], message: dict) -> None:
        """Synchronous SES send (run in executor)."""
        import boto3

        client = boto3.client("ses", region_name=self.ses_region)
        client.send_email(
            Source=self.ses_from_email,
            Destination={"ToAddresses": recipients},
            Message=message,
        )


class SlackDeliveryAdapter(DeliveryAdapter):
    """
    Slack delivery adapter supporting webhook and API posting.

    Sends reports as formatted Slack messages with blocks.
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.bot_token = self.settings.slack_bot_token
        self.default_channel = self.settings.slack_default_channel

    def is_configured(self) -> bool:
        """Check if Slack is configured."""
        return bool(self.bot_token)

    async def deliver(
        self,
        content: ReportContent,
        config: DeliveryConfig,
    ) -> dict[str, Any]:
        """Deliver report to Slack."""
        # Determine delivery method
        if config.slack_webhook_url:
            return await self._send_via_webhook(content, config)
        elif self.bot_token:
            return await self._send_via_api(content, config)
        else:
            return {
                "success": False,
                "error": "No Slack configuration (webhook or bot token)",
                "channel": "slack",
            }

    async def _send_via_webhook(
        self,
        content: ReportContent,
        config: DeliveryConfig,
    ) -> dict[str, Any]:
        """Send report via Slack webhook."""
        blocks = self._build_blocks(content)

        payload = {
            "text": content.title,  # Fallback text
            "blocks": blocks,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                config.slack_webhook_url,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()

        logger.info("slack_webhook_delivered", title=content.title)

        return {
            "success": True,
            "channel": "slack",
            "method": "webhook",
        }

    async def _send_via_api(
        self,
        content: ReportContent,
        config: DeliveryConfig,
    ) -> dict[str, Any]:
        """Send report via Slack API."""
        channel = config.slack_channel or self.default_channel

        if not channel:
            return {
                "success": False,
                "error": "No Slack channel specified",
                "channel": "slack",
            }

        blocks = self._build_blocks(content)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {self.bot_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "channel": channel,
                    "text": content.title,
                    "blocks": blocks,
                    "thread_ts": config.thread_ts,
                    "unfurl_links": False,
                },
                timeout=30,
            )

            data = response.json()
            if not data.get("ok"):
                error = data.get("error", "Unknown error")
                logger.error("slack_api_error", error=error)
                return {
                    "success": False,
                    "error": error,
                    "channel": "slack",
                }

        logger.info(
            "slack_api_delivered",
            channel=channel,
            title=content.title,
        )

        return {
            "success": True,
            "channel": "slack",
            "method": "api",
            "slack_channel": channel,
            "ts": data.get("ts"),
        }

    def _build_blocks(self, content: ReportContent) -> list[dict]:
        """Build Slack Block Kit blocks from report content."""
        blocks = []

        # Header
        blocks.append(
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": content.title[:150],
                    "emoji": True,
                },
            }
        )

        # Subtitle/period
        if content.subtitle:
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"*{content.subtitle}* | {content.period_start.strftime('%Y-%m-%d')} to {content.period_end.strftime('%Y-%m-%d')}",
                        }
                    ],
                }
            )

        blocks.append({"type": "divider"})

        # Executive summary
        if content.executive_summary:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"📋 *Summary*\n{content.executive_summary[:2000]}",
                    },
                }
            )

        # Metrics summary
        if content.metrics:
            metrics = content.metrics
            metrics_text = (
                f"• *Total Incidents:* {metrics.total_incidents}\n"
                f"• *Mean MTTR:* {self._format_duration(metrics.mean_mttr_minutes)}\n"
                f"• *Trend:* {metrics.trend}"
            )
            if metrics.incident_count_change_percent is not None:
                change = metrics.incident_count_change_percent
                emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                metrics_text += f"\n• *Change:* {emoji} {change:+.1f}%"

            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"📊 *Key Metrics*\n{metrics_text}",
                    },
                }
            )

        # Incidents summary (top 5)
        if content.incidents:
            incident_lines = ["🚨 *Recent Incidents*"]
            for inc in content.incidents[:5]:
                emoji = self._severity_emoji(inc.severity)
                duration = self._format_duration(inc.duration_minutes)
                incident_lines.append(
                    f"• {emoji} *{inc.service_name}*: {inc.title[:50]}{'...' if len(inc.title) > 50 else ''} ({duration})"
                )

            if len(content.incidents) > 5:
                incident_lines.append(f"_...and {len(content.incidents) - 5} more_")

            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "\n".join(incident_lines),
                    },
                }
            )

        # AI insights (first 3)
        if content.ai_insights:
            insights_text = "💡 *AI Insights*\n"
            for insight in content.ai_insights[:3]:
                insights_text += (
                    f"• {insight[:200]}{'...' if len(insight) > 200 else ''}\n"
                )

            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": insights_text,
                    },
                }
            )

        # Recommendations (first 3)
        if content.ai_recommendations:
            recs_text = "✅ *Recommendations*\n"
            for rec in content.ai_recommendations[:3]:
                recs_text += f"• {rec[:200]}{'...' if len(rec) > 200 else ''}\n"

            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": recs_text,
                    },
                }
            )

        # Footer
        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"_Generated by Incident Copilot at {content.generated_at.strftime('%Y-%m-%d %H:%M UTC')}_",
                    }
                ],
            }
        )

        return blocks

    @staticmethod
    def _format_duration(minutes: float | None) -> str:
        """Format duration in minutes to human readable."""
        if minutes is None:
            return "N/A"
        if minutes < 1:
            return f"{int(minutes * 60)}s"
        if minutes < 60:
            return f"{int(minutes)}m"
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        return f"{hours}h {mins}m" if mins else f"{hours}h"

    @staticmethod
    def _severity_emoji(severity: str) -> str:
        """Get emoji for severity level."""
        emojis = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
            "info": "🔵",
        }
        return emojis.get(severity.lower(), "⚪")


class WebhookDeliveryAdapter(DeliveryAdapter):
    """
    Generic webhook delivery adapter.

    Sends report data to arbitrary HTTP endpoints.
    """

    def is_configured(self) -> bool:
        """Webhook is configured per-delivery."""
        return True

    async def deliver(
        self,
        content: ReportContent,
        config: DeliveryConfig,
    ) -> dict[str, Any]:
        """Deliver report via webhook."""
        if not config.webhook_url:
            return {
                "success": False,
                "error": "No webhook URL specified",
                "channel": "webhook",
            }

        # Build payload
        payload = {
            "report_type": content.report_type.value,
            "title": content.title,
            "period_start": content.period_start.isoformat(),
            "period_end": content.period_end.isoformat(),
            "generated_at": content.generated_at.isoformat(),
            "executive_summary": content.executive_summary,
            "markdown": content.markdown,
            "html": content.html,
            "metrics": content.metrics.model_dump() if content.metrics else None,
            "incidents": [i.model_dump() for i in content.incidents],
            "ai_insights": content.ai_insights,
            "ai_recommendations": content.ai_recommendations,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=config.webhook_method,
                    url=config.webhook_url,
                    headers={
                        "Content-Type": "application/json",
                        **config.webhook_headers,
                    },
                    json=payload,
                    timeout=60,
                )
                response.raise_for_status()

            logger.info(
                "webhook_delivered",
                url=config.webhook_url,
                status=response.status_code,
            )

            return {
                "success": True,
                "channel": "webhook",
                "url": config.webhook_url,
                "status_code": response.status_code,
            }

        except Exception as e:
            logger.error("webhook_delivery_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "channel": "webhook",
            }


class S3DeliveryAdapter(DeliveryAdapter):
    """
    AWS S3 delivery adapter.

    Uploads reports to S3 for archival and sharing.
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.region = self.settings.aws_region

    def is_configured(self) -> bool:
        """Check if S3 is configured."""
        return bool(self.region)

    async def deliver(
        self,
        content: ReportContent,
        config: DeliveryConfig,
    ) -> dict[str, Any]:
        """Upload report to S3."""
        if not config.s3_bucket:
            return {
                "success": False,
                "error": "No S3 bucket specified",
                "channel": "s3",
            }

        try:
            import boto3
        except ImportError:
            return {
                "success": False,
                "error": "boto3 not installed",
                "channel": "s3",
            }

        # Generate S3 key
        timestamp = content.generated_at.strftime("%Y/%m/%d/%H%M%S")
        base_key = (
            config.s3_key_prefix.rstrip("/") if config.s3_key_prefix else "reports"
        )
        report_type = content.report_type.value

        try:
            loop = asyncio.get_event_loop()
            results = {"files": []}

            # Upload HTML version
            if content.html:
                html_key = f"{base_key}/{report_type}/{timestamp}/report.html"
                await loop.run_in_executor(
                    None,
                    self._s3_upload_sync,
                    config.s3_bucket,
                    html_key,
                    content.html,
                    "text/html",
                )
                results["files"].append(html_key)

            # Upload Markdown version
            if content.markdown:
                md_key = f"{base_key}/{report_type}/{timestamp}/report.md"
                await loop.run_in_executor(
                    None,
                    self._s3_upload_sync,
                    config.s3_bucket,
                    md_key,
                    content.markdown,
                    "text/markdown",
                )
                results["files"].append(md_key)

            # Upload JSON data
            if content.json_data:
                json_key = f"{base_key}/{report_type}/{timestamp}/data.json"
                await loop.run_in_executor(
                    None,
                    self._s3_upload_sync,
                    config.s3_bucket,
                    json_key,
                    json.dumps(content.json_data, indent=2, default=str),
                    "application/json",
                )
                results["files"].append(json_key)

            logger.info(
                "s3_delivered",
                bucket=config.s3_bucket,
                files=results["files"],
            )

            return {
                "success": True,
                "channel": "s3",
                "bucket": config.s3_bucket,
                **results,
            }

        except Exception as e:
            logger.error("s3_delivery_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "channel": "s3",
            }

    def _s3_upload_sync(
        self,
        bucket: str,
        key: str,
        body: str,
        content_type: str,
    ) -> None:
        """Synchronous S3 upload (run in executor)."""
        import boto3

        client = boto3.client("s3", region_name=self.region)
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType=content_type,
        )


class ReportDeliveryService:
    """
    Main service for delivering reports through configured channels.

    Coordinates multiple delivery adapters and aggregates results.
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.adapters: dict[DeliveryChannel, DeliveryAdapter] = {
            DeliveryChannel.EMAIL: EmailDeliveryAdapter(self.settings),
            DeliveryChannel.SLACK: SlackDeliveryAdapter(self.settings),
            DeliveryChannel.WEBHOOK: WebhookDeliveryAdapter(),
            DeliveryChannel.S3: S3DeliveryAdapter(self.settings),
        }

    async def deliver(
        self,
        content: ReportContent,
        delivery_configs: list[DeliveryConfig],
        skip_disabled: bool = True,
    ) -> dict[str, dict[str, Any]]:
        """
        Deliver a report to all configured channels.

        Returns a dict mapping channel names to delivery results.
        """
        results = {}

        for config in delivery_configs:
            if skip_disabled and not config.enabled:
                results[config.channel.value] = {
                    "success": False,
                    "skipped": True,
                    "reason": "disabled",
                }
                continue

            adapter = self.adapters.get(config.channel)
            if not adapter:
                results[config.channel.value] = {
                    "success": False,
                    "error": f"Unknown channel: {config.channel}",
                }
                continue

            try:
                result = await adapter.deliver(content, config)
                results[config.channel.value] = result
            except Exception as e:
                logger.error(
                    "delivery_failed",
                    channel=config.channel.value,
                    error=str(e),
                )
                results[config.channel.value] = {
                    "success": False,
                    "error": str(e),
                }

        # Log summary
        successful = sum(1 for r in results.values() if r.get("success"))
        logger.info(
            "delivery_complete",
            total_channels=len(delivery_configs),
            successful=successful,
        )

        return results

    def get_configured_channels(self) -> list[DeliveryChannel]:
        """Get list of properly configured delivery channels."""
        return [
            channel
            for channel, adapter in self.adapters.items()
            if adapter.is_configured()
        ]
