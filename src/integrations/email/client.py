"""Email client implementations for SMTP, SendGrid, and AWS SES."""

import smtplib
import ssl
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import structlog

from .models import (
    EmailConfig,
    EmailMessage,
    EmailProvider,
    SendResult,
    SESConfig,
    SendGridConfig,
    SMTPConfig,
)

logger = structlog.get_logger()


class EmailClient(ABC):
    """Abstract base class for email clients."""

    @abstractmethod
    async def send(self, message: EmailMessage, config: EmailConfig) -> SendResult:
        """Send an email message."""
        pass

    @abstractmethod
    async def test_connection(self, config: EmailConfig) -> SendResult:
        """Test the email connection."""
        pass


class SMTPClient(EmailClient):
    """SMTP email client."""

    async def send(self, message: EmailMessage, config: EmailConfig) -> SendResult:
        """Send email via SMTP."""
        if not config.smtp:
            return SendResult(
                success=False,
                provider=EmailProvider.SMTP,
                error="SMTP configuration not provided",
            )

        try:
            msg = self._build_message(message, config)

            # Create SMTP connection
            if config.smtp.use_ssl:
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(
                    config.smtp.host, config.smtp.port, context=context
                )
            else:
                server = smtplib.SMTP(config.smtp.host, config.smtp.port)
                if config.smtp.use_tls:
                    server.starttls()

            # Authenticate if credentials provided
            if config.smtp.username and config.smtp.password:
                server.login(config.smtp.username, config.smtp.password)

            # Send email
            all_recipients = (
                [r.email for r in message.to]
                + [r.email for r in message.cc]
                + [r.email for r in message.bcc]
            )

            server.sendmail(
                message.from_email or config.from_email,
                all_recipients,
                msg.as_string(),
            )
            server.quit()

            logger.info(
                "smtp_email_sent",
                to=[r.email for r in message.to],
                subject=message.subject,
            )

            return SendResult(
                success=True,
                provider=EmailProvider.SMTP,
                message_id=msg["Message-ID"],
                metadata={"recipients": len(all_recipients)},
            )

        except smtplib.SMTPAuthenticationError as e:
            logger.error("smtp_auth_error", error=str(e))
            return SendResult(
                success=False,
                provider=EmailProvider.SMTP,
                error=f"SMTP authentication failed: {e}",
            )
        except smtplib.SMTPException as e:
            logger.error("smtp_error", error=str(e))
            return SendResult(
                success=False,
                provider=EmailProvider.SMTP,
                error=f"SMTP error: {e}",
            )
        except Exception as e:
            logger.error("smtp_unexpected_error", error=str(e))
            return SendResult(
                success=False,
                provider=EmailProvider.SMTP,
                error=f"Unexpected error: {e}",
            )

    async def test_connection(self, config: EmailConfig) -> SendResult:
        """Test SMTP connection."""
        if not config.smtp:
            return SendResult(
                success=False,
                provider=EmailProvider.SMTP,
                error="SMTP configuration not provided",
            )

        try:
            if config.smtp.use_ssl:
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(
                    config.smtp.host, config.smtp.port, context=context
                )
            else:
                server = smtplib.SMTP(
                    config.smtp.host, config.smtp.port, timeout=config.smtp.timeout
                )
                if config.smtp.use_tls:
                    server.starttls()

            if config.smtp.username and config.smtp.password:
                server.login(config.smtp.username, config.smtp.password)

            server.noop()
            server.quit()

            return SendResult(
                success=True,
                provider=EmailProvider.SMTP,
                metadata={"host": config.smtp.host, "port": config.smtp.port},
            )

        except Exception as e:
            return SendResult(
                success=False,
                provider=EmailProvider.SMTP,
                error=str(e),
            )

    def _build_message(
        self, message: EmailMessage, config: EmailConfig
    ) -> MIMEMultipart:
        """Build MIME message."""
        msg = MIMEMultipart("alternative")

        # Set headers
        from_addr = message.from_email or config.from_email
        from_name = message.from_name or config.from_name
        msg["From"] = f"{from_name} <{from_addr}>" if from_name else from_addr
        msg["To"] = ", ".join([r.formatted for r in message.to])
        msg["Subject"] = message.subject

        if message.cc:
            msg["Cc"] = ", ".join([r.formatted for r in message.cc])

        if message.reply_to or config.reply_to:
            msg["Reply-To"] = message.reply_to or config.reply_to

        # Add custom headers
        for key, value in message.headers.items():
            msg[key] = value

        # Attach text and HTML parts
        text_part = MIMEText(message.text_body, "plain", "utf-8")
        html_part = MIMEText(message.html_body, "html", "utf-8")

        msg.attach(text_part)
        msg.attach(html_part)

        return msg


class SendGridClient(EmailClient):
    """SendGrid API email client."""

    async def send(self, message: EmailMessage, config: EmailConfig) -> SendResult:
        """Send email via SendGrid API."""
        if not config.sendgrid:
            return SendResult(
                success=False,
                provider=EmailProvider.SENDGRID,
                error="SendGrid configuration not provided",
            )

        try:
            # Import sendgrid only when needed
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import (
                Bcc,
                Cc,
                Content,
                Email,
                Mail,
                ReplyTo,
                To,
            )

            sg = SendGridAPIClient(api_key=config.sendgrid.api_key)

            # Build message
            from_email = Email(
                message.from_email or config.from_email,
                message.from_name or config.from_name,
            )

            to_emails = [To(r.email, r.name) for r in message.to]

            mail = Mail(
                from_email=from_email,
                to_emails=to_emails,
                subject=message.subject,
            )

            # Add CC and BCC
            if message.cc:
                for r in message.cc:
                    mail.add_cc(Cc(r.email, r.name))

            if message.bcc:
                for r in message.bcc:
                    mail.add_bcc(Bcc(r.email, r.name))

            # Add content
            mail.add_content(Content("text/plain", message.text_body))
            mail.add_content(Content("text/html", message.html_body))

            # Add reply-to
            if message.reply_to or config.reply_to:
                mail.reply_to = ReplyTo(message.reply_to or config.reply_to)

            # Add custom headers
            for key, value in message.headers.items():
                mail.add_header({key: value})

            # Sandbox mode
            if config.sendgrid.sandbox_mode:
                mail.mail_settings = {"sandbox_mode": {"enable": True}}

            # Send
            response = sg.send(mail)

            message_id = response.headers.get("X-Message-Id")

            logger.info(
                "sendgrid_email_sent",
                to=[r.email for r in message.to],
                subject=message.subject,
                status_code=response.status_code,
            )

            return SendResult(
                success=response.status_code in (200, 202),
                provider=EmailProvider.SENDGRID,
                message_id=message_id,
                metadata={"status_code": response.status_code},
            )

        except ImportError:
            return SendResult(
                success=False,
                provider=EmailProvider.SENDGRID,
                error="SendGrid library not installed. Run: pip install sendgrid",
            )
        except Exception as e:
            logger.error("sendgrid_error", error=str(e))
            return SendResult(
                success=False,
                provider=EmailProvider.SENDGRID,
                error=str(e),
            )

    async def test_connection(self, config: EmailConfig) -> SendResult:
        """Test SendGrid connection by checking API key validity."""
        if not config.sendgrid:
            return SendResult(
                success=False,
                provider=EmailProvider.SENDGRID,
                error="SendGrid configuration not provided",
            )

        try:
            from sendgrid import SendGridAPIClient

            sg = SendGridAPIClient(api_key=config.sendgrid.api_key)
            # Get API key info to validate
            response = sg.client.api_keys.get()

            return SendResult(
                success=response.status_code == 200,
                provider=EmailProvider.SENDGRID,
                metadata={"status_code": response.status_code},
            )

        except ImportError:
            return SendResult(
                success=False,
                provider=EmailProvider.SENDGRID,
                error="SendGrid library not installed",
            )
        except Exception as e:
            return SendResult(
                success=False,
                provider=EmailProvider.SENDGRID,
                error=str(e),
            )


class SESClient(EmailClient):
    """AWS SES email client."""

    async def send(self, message: EmailMessage, config: EmailConfig) -> SendResult:
        """Send email via AWS SES."""
        if not config.ses:
            return SendResult(
                success=False,
                provider=EmailProvider.SES,
                error="SES configuration not provided",
            )

        try:
            import boto3

            # Create SES client
            client_kwargs: dict[str, Any] = {"region_name": config.ses.region}

            if config.ses.access_key_id and config.ses.secret_access_key:
                client_kwargs["aws_access_key_id"] = config.ses.access_key_id
                client_kwargs["aws_secret_access_key"] = config.ses.secret_access_key

            ses = boto3.client("ses", **client_kwargs)

            # Build destination
            destination: dict[str, list[str]] = {
                "ToAddresses": [r.email for r in message.to]
            }

            if message.cc:
                destination["CcAddresses"] = [r.email for r in message.cc]
            if message.bcc:
                destination["BccAddresses"] = [r.email for r in message.bcc]

            # Build message
            from_addr = message.from_email or config.from_email
            from_name = message.from_name or config.from_name
            source = f"{from_name} <{from_addr}>" if from_name else from_addr

            email_message: dict[str, Any] = {
                "Subject": {"Data": message.subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": message.text_body, "Charset": "UTF-8"},
                    "Html": {"Data": message.html_body, "Charset": "UTF-8"},
                },
            }

            send_kwargs: dict[str, Any] = {
                "Source": source,
                "Destination": destination,
                "Message": email_message,
            }

            if message.reply_to or config.reply_to:
                send_kwargs["ReplyToAddresses"] = [message.reply_to or config.reply_to]

            if config.ses.configuration_set:
                send_kwargs["ConfigurationSetName"] = config.ses.configuration_set

            # Send
            response = ses.send_email(**send_kwargs)

            message_id = response.get("MessageId")

            logger.info(
                "ses_email_sent",
                to=[r.email for r in message.to],
                subject=message.subject,
                message_id=message_id,
            )

            return SendResult(
                success=True,
                provider=EmailProvider.SES,
                message_id=message_id,
                metadata={"response_metadata": response.get("ResponseMetadata", {})},
            )

        except ImportError:
            return SendResult(
                success=False,
                provider=EmailProvider.SES,
                error="boto3 library not installed. Run: pip install boto3",
            )
        except Exception as e:
            logger.error("ses_error", error=str(e))
            return SendResult(
                success=False,
                provider=EmailProvider.SES,
                error=str(e),
            )

    async def test_connection(self, config: EmailConfig) -> SendResult:
        """Test SES connection by checking send quota."""
        if not config.ses:
            return SendResult(
                success=False,
                provider=EmailProvider.SES,
                error="SES configuration not provided",
            )

        try:
            import boto3

            client_kwargs: dict[str, Any] = {"region_name": config.ses.region}

            if config.ses.access_key_id and config.ses.secret_access_key:
                client_kwargs["aws_access_key_id"] = config.ses.access_key_id
                client_kwargs["aws_secret_access_key"] = config.ses.secret_access_key

            ses = boto3.client("ses", **client_kwargs)
            quota = ses.get_send_quota()

            return SendResult(
                success=True,
                provider=EmailProvider.SES,
                metadata={
                    "max_24_hour_send": quota.get("Max24HourSend"),
                    "sent_last_24_hours": quota.get("SentLast24Hours"),
                    "max_send_rate": quota.get("MaxSendRate"),
                },
            )

        except ImportError:
            return SendResult(
                success=False,
                provider=EmailProvider.SES,
                error="boto3 library not installed",
            )
        except Exception as e:
            return SendResult(
                success=False,
                provider=EmailProvider.SES,
                error=str(e),
            )


def get_email_client(provider: EmailProvider) -> EmailClient:
    """Get the appropriate email client for a provider."""
    clients = {
        EmailProvider.SMTP: SMTPClient,
        EmailProvider.SENDGRID: SendGridClient,
        EmailProvider.SES: SESClient,
    }
    return clients[provider]()
