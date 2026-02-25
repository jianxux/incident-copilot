"""Email notification service."""

from datetime import datetime, timedelta, UTC
from typing import Any

import structlog

from ...models import ContextCard
from .client import get_email_client
from .models import (
    DigestData,
    DigestFrequency,
    EmailConfig,
    EmailMessage,
    EmailRecipient,
    EmailTemplateType,
    IncidentDigestItem,
    SendResult,
)
from .templates import EmailTemplateRenderer

logger = structlog.get_logger()


class EmailNotificationService:
    """Service for sending email notifications."""

    def __init__(self, config: EmailConfig):
        self.config = config
        self.renderer = EmailTemplateRenderer()

    async def send_context_card(
        self,
        card: ContextCard,
        recipients: list[EmailRecipient] | None = None,
        cc: list[EmailRecipient] | None = None,
        bcc: list[EmailRecipient] | None = None,
    ) -> SendResult:
        """Send a context card notification email.

        Args:
            card: The context card to send
            recipients: Override recipients (defaults to config.default_recipients)
            cc: CC recipients
            bcc: BCC recipients

        Returns:
            SendResult with success/failure info
        """
        if not self.config.enabled:
            return SendResult(
                success=False,
                provider=self.config.provider,
                error="Email notifications are disabled",
            )

        # Use default recipients if not specified
        to_recipients = recipients or self.config.default_recipients
        if not to_recipients:
            return SendResult(
                success=False,
                provider=self.config.provider,
                error="No recipients specified",
            )

        # Render email
        html_body, text_body = self.renderer.render_context_card(card, self.config)
        subject = self.renderer.get_subject(EmailTemplateType.CONTEXT_CARD, card=card)

        # Build message
        message = EmailMessage(
            to=to_recipients,
            cc=cc or [],
            bcc=bcc or [],
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            tags=["incident", card.severity.value, card.service_name],
            metadata={
                "incident_id": card.incident_id,
                "service": card.service_name,
                "severity": card.severity.value,
            },
        )

        # Send
        client = get_email_client(self.config.provider)
        result = await client.send(message, self.config)

        logger.info(
            (
                "context_card_email_sent"
                if result.success
                else "context_card_email_failed"
            ),
            incident_id=card.incident_id,
            recipients=[r.email for r in to_recipients],
            provider=self.config.provider.value,
            success=result.success,
            error=result.error,
        )

        return result

    async def send_digest(
        self,
        data: DigestData,
        recipients: list[EmailRecipient] | None = None,
        weekly: bool = False,
    ) -> SendResult:
        """Send a digest email.

        Args:
            data: Digest data with incidents summary
            recipients: Override recipients (defaults to config.digest_recipients)
            weekly: True for weekly digest, False for daily

        Returns:
            SendResult with success/failure info
        """
        if not self.config.enabled:
            return SendResult(
                success=False,
                provider=self.config.provider,
                error="Email notifications are disabled",
            )

        if not self.config.digest_enabled:
            return SendResult(
                success=False,
                provider=self.config.provider,
                error="Digest emails are disabled",
            )

        # Use digest recipients if not specified
        to_recipients = recipients or self.config.digest_recipients
        if not to_recipients:
            return SendResult(
                success=False,
                provider=self.config.provider,
                error="No digest recipients configured",
            )

        # Render email
        html_body, text_body = self.renderer.render_digest(data, self.config, weekly)
        template_type = (
            EmailTemplateType.DIGEST_WEEKLY
            if weekly
            else EmailTemplateType.DIGEST_DAILY
        )
        subject = self.renderer.get_subject(template_type, data=data)

        # Build message
        message = EmailMessage(
            to=to_recipients,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            tags=["digest", "weekly" if weekly else "daily"],
            metadata={
                "tenant_id": data.tenant_id,
                "period_start": data.period_start.isoformat(),
                "period_end": data.period_end.isoformat(),
                "total_incidents": data.total_incidents,
            },
        )

        # Send
        client = get_email_client(self.config.provider)
        result = await client.send(message, self.config)

        logger.info(
            "digest_email_sent" if result.success else "digest_email_failed",
            tenant_id=data.tenant_id,
            recipients=[r.email for r in to_recipients],
            weekly=weekly,
            total_incidents=data.total_incidents,
            success=result.success,
            error=result.error,
        )

        return result

    async def send_test_email(
        self, recipient: EmailRecipient | None = None
    ) -> SendResult:
        """Send a test email to verify configuration.

        Args:
            recipient: Test recipient (defaults to first default recipient)

        Returns:
            SendResult with success/failure info
        """
        # Determine recipient
        if recipient:
            to_recipients = [recipient]
        elif self.config.default_recipients:
            to_recipients = [self.config.default_recipients[0]]
        else:
            return SendResult(
                success=False,
                provider=self.config.provider,
                error="No recipient specified and no default recipients configured",
            )

        # Render test email
        html_body, text_body = self.renderer.render_test(self.config)
        subject = self.renderer.get_subject(EmailTemplateType.TEST)

        # Build message
        message = EmailMessage(
            to=to_recipients,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            tags=["test"],
            metadata={"test": True, "timestamp": datetime.now(UTC).isoformat()},
        )

        # Send
        client = get_email_client(self.config.provider)
        result = await client.send(message, self.config)

        logger.info(
            "test_email_sent" if result.success else "test_email_failed",
            recipient=to_recipients[0].email,
            provider=self.config.provider.value,
            success=result.success,
            error=result.error,
        )

        return result

    async def test_connection(self) -> SendResult:
        """Test the email provider connection.

        Returns:
            SendResult with connection status
        """
        client = get_email_client(self.config.provider)
        result = await client.test_connection(self.config)

        logger.info(
            "email_connection_test",
            provider=self.config.provider.value,
            success=result.success,
            error=result.error,
        )

        return result

    async def send_custom(
        self,
        subject: str,
        html_body: str,
        text_body: str,
        recipients: list[EmailRecipient],
        cc: list[EmailRecipient] | None = None,
        bcc: list[EmailRecipient] | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send a custom email.

        Args:
            subject: Email subject
            html_body: HTML body
            text_body: Plain text body
            recipients: To recipients
            cc: CC recipients
            bcc: BCC recipients
            tags: Email tags
            metadata: Additional metadata

        Returns:
            SendResult with success/failure info
        """
        if not self.config.enabled:
            return SendResult(
                success=False,
                provider=self.config.provider,
                error="Email notifications are disabled",
            )

        if not recipients:
            return SendResult(
                success=False,
                provider=self.config.provider,
                error="No recipients specified",
            )

        message = EmailMessage(
            to=recipients,
            cc=cc or [],
            bcc=bcc or [],
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            tags=tags or [],
            metadata=metadata or {},
        )

        client = get_email_client(self.config.provider)
        result = await client.send(message, self.config)

        logger.info(
            "custom_email_sent" if result.success else "custom_email_failed",
            recipients=[r.email for r in recipients],
            subject=subject,
            success=result.success,
            error=result.error,
        )

        return result


class DigestScheduler:
    """Scheduler for digest emails."""

    def __init__(self, config: EmailConfig):
        self.config = config

    def should_send_digest(self, last_sent: datetime | None = None) -> bool:
        """Check if it's time to send a digest.

        Args:
            last_sent: When the last digest was sent

        Returns:
            True if digest should be sent now
        """
        if not self.config.digest_enabled:
            return False

        if self.config.digest_frequency == DigestFrequency.DISABLED:
            return False

        now = datetime.now(UTC)

        # Check if it's the right hour
        if now.hour != self.config.digest_hour:
            return False

        # For weekly, check if it's the right day
        if self.config.digest_frequency == DigestFrequency.WEEKLY:
            # Python weekday: Monday=0, Sunday=6
            # Our config: Monday=1, Sunday=7
            if now.weekday() + 1 != self.config.digest_day:
                return False

        # Check if we already sent today/this period
        if last_sent:
            if self.config.digest_frequency == DigestFrequency.DAILY:
                if last_sent.date() == now.date():
                    return False
            elif self.config.digest_frequency == DigestFrequency.WEEKLY:
                # Check if sent in the same week
                last_week = last_sent.isocalendar()[1]
                this_week = now.isocalendar()[1]
                if last_week == this_week and last_sent.year == now.year:
                    return False

        return True

    def get_digest_period(self) -> tuple[datetime, datetime]:
        """Get the period for the current digest.

        Returns:
            Tuple of (start, end) datetime for the digest period
        """
        now = datetime.now(UTC)
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if self.config.digest_frequency == DigestFrequency.DAILY:
            start = end - timedelta(days=1)
        elif self.config.digest_frequency == DigestFrequency.WEEKLY:
            start = end - timedelta(days=7)
        else:
            # Default to last 24 hours
            start = end - timedelta(days=1)

        return start, end

    def build_digest_data(
        self,
        incidents: list[dict[str, Any]],
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> DigestData:
        """Build digest data from incident list.

        Args:
            incidents: List of incident dictionaries
            period_start: Override start of period
            period_end: Override end of period

        Returns:
            DigestData for rendering
        """
        if not period_start or not period_end:
            period_start, period_end = self.get_digest_period()

        # Convert incidents to digest items
        digest_items = []
        services = set()
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        resolve_times = []

        for inc in incidents:
            item = IncidentDigestItem(
                incident_id=inc.get("incident_id", inc.get("id", "")),
                title=inc.get("title", "Unknown"),
                service_name=inc.get("service_name", inc.get("service", "Unknown")),
                severity=inc.get("severity", "medium"),
                triggered_at=inc.get("triggered_at", datetime.now(UTC)),
                resolved_at=inc.get("resolved_at"),
                status=inc.get("status", "open"),
                url=inc.get("url"),
            )
            digest_items.append(item)
            services.add(item.service_name)

            # Count severities
            sev = item.severity.lower()
            if sev in severity_counts:
                severity_counts[sev] += 1

            # Calculate resolve time
            if item.resolved_at and item.triggered_at:
                resolve_time = (
                    item.resolved_at - item.triggered_at
                ).total_seconds() / 60
                resolve_times.append(resolve_time)

        # Calculate MTTR
        mttr = sum(resolve_times) / len(resolve_times) if resolve_times else None

        return DigestData(
            tenant_id=self.config.tenant_id,
            period_start=period_start,
            period_end=period_end,
            incidents=digest_items,
            total_incidents=len(digest_items),
            critical_count=severity_counts["critical"],
            high_count=severity_counts["high"],
            medium_count=severity_counts["medium"],
            low_count=severity_counts["low"],
            mttr_minutes=mttr,
            services_affected=sorted(services),
        )
