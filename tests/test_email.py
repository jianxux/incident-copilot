"""Tests for email notification integration."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.integrations.email import (
    DigestFrequency,
    EmailConfig,
    EmailMessage,
    EmailNotificationService,
    EmailProvider,
    EmailRecipient,
    EmailTemplateRenderer,
    SendResult,
)
from src.integrations.email.client import (
    SendGridClient,
    SESClient,
    SMTPClient,
    get_email_client,
)
from src.integrations.email.models import (
    DigestData,
    IncidentDigestItem,
    SendGridConfig,
    SESConfig,
    SMTPConfig,
)
from src.integrations.email.service import DigestScheduler
from src.main import app
from src.models import ContextCard, Severity


@pytest.fixture
def sample_email_config():
    """Sample email configuration."""
    return EmailConfig(
        tenant_id="test-tenant",
        enabled=True,
        provider=EmailProvider.SMTP,
        from_email="noreply@example.com",
        from_name="Incident Copilot",
        default_recipients=[EmailRecipient(email="oncall@example.com", name="On-Call Team")],
        smtp=SMTPConfig(
            host="smtp.example.com",
            port=587,
            username="user",
            password="pass",
            use_tls=True,
        ),
        brand_color="#2563eb",
    )


@pytest.fixture
def sample_sendgrid_config():
    """Sample SendGrid configuration."""
    return EmailConfig(
        tenant_id="test-tenant",
        enabled=True,
        provider=EmailProvider.SENDGRID,
        from_email="noreply@example.com",
        from_name="Incident Copilot",
        default_recipients=[EmailRecipient(email="oncall@example.com", name="On-Call Team")],
        sendgrid=SendGridConfig(api_key="SG.test_api_key"),
    )


@pytest.fixture
def sample_ses_config():
    """Sample AWS SES configuration."""
    return EmailConfig(
        tenant_id="test-tenant",
        enabled=True,
        provider=EmailProvider.SES,
        from_email="noreply@example.com",
        from_name="Incident Copilot",
        default_recipients=[EmailRecipient(email="oncall@example.com", name="On-Call Team")],
        ses=SESConfig(
            region="us-east-1",
            access_key_id="AKIATEST",
            secret_access_key="secret",
        ),
    )


@pytest.fixture
def sample_context_card():
    """Sample context card for testing."""
    return ContextCard(
        incident_id="INC-001",
        title="High CPU Usage on Production Server",
        severity=Severity.HIGH,
        service_name="api-gateway",
        triggered_at=datetime.utcnow(),
        alert_url="https://pagerduty.com/incidents/ABC123",
        owners=["platform-team"],
        runbook_url="https://wiki.example.com/runbooks/cpu-usage",
        dashboard_url="https://grafana.example.com/d/cpu",
    )


@pytest.fixture
def sample_digest_data():
    """Sample digest data for testing."""
    now = datetime.utcnow()
    return DigestData(
        tenant_id="test-tenant",
        period_start=now - timedelta(days=1),
        period_end=now,
        incidents=[
            IncidentDigestItem(
                incident_id="INC-001",
                title="High CPU Usage",
                service_name="api-gateway",
                severity="high",
                triggered_at=now - timedelta(hours=12),
                resolved_at=now - timedelta(hours=10),
                status="resolved",
            ),
            IncidentDigestItem(
                incident_id="INC-002",
                title="Database Connection Timeout",
                service_name="user-service",
                severity="critical",
                triggered_at=now - timedelta(hours=6),
                status="open",
            ),
        ],
        total_incidents=2,
        critical_count=1,
        high_count=1,
        medium_count=0,
        low_count=0,
        mttr_minutes=120.0,
        services_affected=["api-gateway", "user-service"],
    )


class TestEmailRecipient:
    """Tests for EmailRecipient model."""

    def test_formatted_with_name(self):
        recipient = EmailRecipient(email="test@example.com", name="Test User")
        assert recipient.formatted == "Test User <test@example.com>"

    def test_formatted_without_name(self):
        recipient = EmailRecipient(email="test@example.com")
        assert recipient.formatted == "test@example.com"


class TestEmailConfig:
    """Tests for EmailConfig model."""

    def test_valid_brand_color(self, sample_email_config):
        assert sample_email_config.brand_color == "#2563eb"

    def test_invalid_brand_color(self):
        with pytest.raises(ValueError):
            EmailConfig(
                tenant_id="test",
                from_email="test@example.com",
                brand_color="invalid",
            )


class TestEmailClients:
    """Tests for email clients."""

    def test_get_smtp_client(self):
        client = get_email_client(EmailProvider.SMTP)
        assert isinstance(client, SMTPClient)

    def test_get_sendgrid_client(self):
        client = get_email_client(EmailProvider.SENDGRID)
        assert isinstance(client, SendGridClient)

    def test_get_ses_client(self):
        client = get_email_client(EmailProvider.SES)
        assert isinstance(client, SESClient)

    @pytest.mark.asyncio
    async def test_smtp_send_without_config(self):
        """Test SMTP send without configuration."""
        client = SMTPClient()
        config = EmailConfig(
            tenant_id="test",
            from_email="test@example.com",
            provider=EmailProvider.SMTP,
            # No smtp config
        )
        message = EmailMessage(
            to=[EmailRecipient(email="to@example.com")],
            subject="Test",
            html_body="<p>Test</p>",
            text_body="Test",
        )

        result = await client.send(message, config)
        assert not result.success
        assert "SMTP configuration not provided" in result.error

    @pytest.mark.asyncio
    async def test_sendgrid_send_without_config(self):
        """Test SendGrid send without configuration."""
        client = SendGridClient()
        config = EmailConfig(
            tenant_id="test",
            from_email="test@example.com",
            provider=EmailProvider.SENDGRID,
            # No sendgrid config
        )
        message = EmailMessage(
            to=[EmailRecipient(email="to@example.com")],
            subject="Test",
            html_body="<p>Test</p>",
            text_body="Test",
        )

        result = await client.send(message, config)
        assert not result.success
        assert "SendGrid configuration not provided" in result.error

    @pytest.mark.asyncio
    async def test_ses_send_without_config(self):
        """Test SES send without configuration."""
        client = SESClient()
        config = EmailConfig(
            tenant_id="test",
            from_email="test@example.com",
            provider=EmailProvider.SES,
            # No ses config
        )
        message = EmailMessage(
            to=[EmailRecipient(email="to@example.com")],
            subject="Test",
            html_body="<p>Test</p>",
            text_body="Test",
        )

        result = await client.send(message, config)
        assert not result.success
        assert "SES configuration not provided" in result.error


class TestEmailTemplateRenderer:
    """Tests for email template rendering."""

    def test_severity_color(self):
        assert EmailTemplateRenderer._severity_color("critical") == "#dc2626"
        assert EmailTemplateRenderer._severity_color("high") == "#ea580c"
        assert EmailTemplateRenderer._severity_color("medium") == "#ca8a04"
        assert EmailTemplateRenderer._severity_color("low") == "#16a34a"
        assert EmailTemplateRenderer._severity_color("info") == "#2563eb"
        assert EmailTemplateRenderer._severity_color("unknown") == "#6b7280"

    def test_severity_emoji(self):
        assert EmailTemplateRenderer._severity_emoji("critical") == "🔴"
        assert EmailTemplateRenderer._severity_emoji("high") == "🟠"
        assert EmailTemplateRenderer._severity_emoji("medium") == "🟡"
        assert EmailTemplateRenderer._severity_emoji("low") == "🟢"
        assert EmailTemplateRenderer._severity_emoji("info") == "🔵"

    def test_format_duration(self):
        assert EmailTemplateRenderer._format_duration(30) == "30m"
        assert EmailTemplateRenderer._format_duration(90) == "1h 30m"
        assert EmailTemplateRenderer._format_duration(1500) == "1d 1h"
        assert EmailTemplateRenderer._format_duration(None) == "N/A"

    def test_truncate_text(self):
        assert EmailTemplateRenderer._truncate_text("short", 10) == "short"
        assert EmailTemplateRenderer._truncate_text("this is a long text", 10) == "this is..."

    def test_get_subject_context_card(self, sample_context_card):
        renderer = EmailTemplateRenderer()
        from src.integrations.email.models import EmailTemplateType

        subject = renderer.get_subject(EmailTemplateType.CONTEXT_CARD, card=sample_context_card)
        assert "🟠 HIGH" in subject
        assert "api-gateway" in subject

    def test_get_subject_digest(self, sample_digest_data):
        renderer = EmailTemplateRenderer()
        from src.integrations.email.models import EmailTemplateType

        subject = renderer.get_subject(EmailTemplateType.DIGEST_DAILY, data=sample_digest_data)
        assert "Daily Incident Report" in subject

    def test_get_subject_test(self):
        renderer = EmailTemplateRenderer()
        from src.integrations.email.models import EmailTemplateType

        subject = renderer.get_subject(EmailTemplateType.TEST)
        assert "Test Email" in subject

    def test_render_test_email(self, sample_email_config):
        renderer = EmailTemplateRenderer()
        html_body, text_body = renderer.render_test(sample_email_config)

        assert "Test Email" in html_body or "test" in html_body.lower()
        assert "Configuration" in html_body or "configuration" in html_body.lower()
        assert len(text_body) > 0

    def test_list_templates(self):
        renderer = EmailTemplateRenderer()
        templates = renderer.list_templates()

        assert isinstance(templates, list)
        # Should have at least the base templates
        template_ids = [t["id"] for t in templates]
        assert "context_card" in template_ids
        assert "digest" in template_ids
        assert "test" in template_ids


class TestEmailNotificationService:
    """Tests for EmailNotificationService."""

    @pytest.mark.asyncio
    async def test_send_context_card_disabled(self, sample_email_config, sample_context_card):
        """Test sending when disabled."""
        sample_email_config.enabled = False
        service = EmailNotificationService(sample_email_config)

        result = await service.send_context_card(sample_context_card)

        assert not result.success
        assert "disabled" in result.error.lower()

    @pytest.mark.asyncio
    async def test_send_context_card_no_recipients(self, sample_email_config, sample_context_card):
        """Test sending with no recipients."""
        sample_email_config.default_recipients = []
        service = EmailNotificationService(sample_email_config)

        result = await service.send_context_card(sample_context_card, recipients=[])

        assert not result.success
        assert "recipients" in result.error.lower()

    @pytest.mark.asyncio
    async def test_send_test_email_no_recipients(self, sample_email_config):
        """Test sending test email with no recipients."""
        sample_email_config.default_recipients = []
        service = EmailNotificationService(sample_email_config)

        result = await service.send_test_email()

        assert not result.success
        assert "recipient" in result.error.lower()

    @pytest.mark.asyncio
    async def test_send_digest_disabled(self, sample_email_config, sample_digest_data):
        """Test sending digest when disabled."""
        sample_email_config.digest_enabled = False
        service = EmailNotificationService(sample_email_config)

        result = await service.send_digest(sample_digest_data)

        assert not result.success
        assert "disabled" in result.error.lower()


class TestDigestScheduler:
    """Tests for DigestScheduler."""

    def test_should_send_digest_disabled(self, sample_email_config):
        """Test when digest is disabled."""
        sample_email_config.digest_enabled = False
        scheduler = DigestScheduler(sample_email_config)

        assert not scheduler.should_send_digest()

    def test_should_send_digest_frequency_disabled(self, sample_email_config):
        """Test when frequency is disabled."""
        sample_email_config.digest_enabled = True
        sample_email_config.digest_frequency = DigestFrequency.DISABLED
        scheduler = DigestScheduler(sample_email_config)

        assert not scheduler.should_send_digest()

    def test_get_digest_period_daily(self, sample_email_config):
        """Test getting daily digest period."""
        sample_email_config.digest_frequency = DigestFrequency.DAILY
        scheduler = DigestScheduler(sample_email_config)

        start, end = scheduler.get_digest_period()
        assert (end - start).days == 1

    def test_get_digest_period_weekly(self, sample_email_config):
        """Test getting weekly digest period."""
        sample_email_config.digest_frequency = DigestFrequency.WEEKLY
        scheduler = DigestScheduler(sample_email_config)

        start, end = scheduler.get_digest_period()
        assert (end - start).days == 7

    def test_build_digest_data(self, sample_email_config):
        """Test building digest data from incidents."""
        sample_email_config.digest_frequency = DigestFrequency.DAILY
        scheduler = DigestScheduler(sample_email_config)

        incidents = [
            {
                "incident_id": "INC-001",
                "title": "Test Incident",
                "service_name": "test-service",
                "severity": "high",
                "triggered_at": datetime.utcnow(),
                "status": "open",
            },
            {
                "incident_id": "INC-002",
                "title": "Another Incident",
                "service_name": "other-service",
                "severity": "critical",
                "triggered_at": datetime.utcnow(),
                "resolved_at": datetime.utcnow(),
                "status": "resolved",
            },
        ]

        data = scheduler.build_digest_data(incidents)

        assert data.total_incidents == 2
        assert data.critical_count == 1
        assert data.high_count == 1
        assert len(data.services_affected) == 2


class TestEmailAPI:
    """Tests for email API endpoints."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_get_config_not_found(self, client):
        """Test getting config when none exists."""
        # Clear any existing config
        from src.api.email import _config_store

        _config_store.clear()

        response = client.get("/api/notifications/email/config")
        assert response.status_code == 404

    def test_create_config(self, client):
        """Test creating email configuration."""
        from src.api.email import _config_store

        _config_store.clear()

        config_data = {
            "enabled": True,
            "provider": "smtp",
            "from_email": "noreply@example.com",
            "from_name": "Incident Copilot",
            "default_recipients": [{"email": "oncall@example.com", "name": "On-Call Team"}],
            "smtp": {
                "host": "smtp.example.com",
                "port": 587,
                "username": "user",
                "password": "pass",
            },
        }

        response = client.put("/api/notifications/email/config", json=config_data)
        assert response.status_code == 200

        data = response.json()
        assert data["enabled"] is True
        assert data["provider"] == "smtp"
        assert data["from_email"] == "noreply@example.com"
        assert data["smtp_configured"] is True

    def test_create_config_missing_smtp(self, client):
        """Test creating SMTP config without SMTP settings."""
        from src.api.email import _config_store

        _config_store.clear()

        config_data = {
            "enabled": True,
            "provider": "smtp",
            "from_email": "noreply@example.com",
            # Missing smtp config
        }

        response = client.put("/api/notifications/email/config", json=config_data)
        assert response.status_code == 400
        assert "SMTP configuration required" in response.json()["detail"]

    def test_list_templates(self, client):
        """Test listing email templates."""
        response = client.get("/api/notifications/email/templates")
        assert response.status_code == 200

        templates = response.json()
        assert isinstance(templates, list)
        assert len(templates) > 0

    def test_preview_test_template(self, client):
        """Test previewing test template."""
        # First create a config
        from src.api.email import _config_store

        _config_store.clear()

        config_data = {
            "enabled": True,
            "provider": "smtp",
            "from_email": "noreply@example.com",
            "smtp": {"host": "smtp.example.com", "port": 587},
        }
        client.put("/api/notifications/email/config", json=config_data)

        response = client.get("/api/notifications/email/templates/test/preview")
        assert response.status_code == 200

        data = response.json()
        assert "html" in data
        assert "text" in data
        assert "subject" in data

    def test_delete_config(self, client):
        """Test deleting email configuration."""
        from src.api.email import _config_store

        _config_store.clear()

        # First create a config
        config_data = {
            "enabled": True,
            "provider": "smtp",
            "from_email": "noreply@example.com",
            "smtp": {"host": "smtp.example.com", "port": 587},
        }
        client.put("/api/notifications/email/config", json=config_data)

        # Then delete it
        response = client.delete("/api/notifications/email/config")
        assert response.status_code == 200

        # Verify it's gone
        response = client.get("/api/notifications/email/config")
        assert response.status_code == 404

    def test_connection_test_no_config(self, client):
        """Test connection test without config."""
        from src.api.email import _config_store

        _config_store.clear()

        response = client.post("/api/notifications/email/connection-test")
        assert response.status_code == 404


class TestEmailMessage:
    """Tests for EmailMessage model."""

    def test_email_message_creation(self):
        message = EmailMessage(
            to=[EmailRecipient(email="to@example.com", name="To User")],
            cc=[EmailRecipient(email="cc@example.com")],
            subject="Test Subject",
            html_body="<p>HTML Body</p>",
            text_body="Text Body",
            tags=["test", "notification"],
            metadata={"incident_id": "INC-001"},
        )

        assert len(message.to) == 1
        assert len(message.cc) == 1
        assert message.subject == "Test Subject"
        assert message.tags == ["test", "notification"]
        assert message.metadata["incident_id"] == "INC-001"


class TestSendResult:
    """Tests for SendResult model."""

    def test_send_result_success(self):
        result = SendResult(
            success=True,
            provider=EmailProvider.SMTP,
            message_id="msg-123",
        )

        assert result.success is True
        assert result.message_id == "msg-123"
        assert result.error is None

    def test_send_result_failure(self):
        result = SendResult(
            success=False,
            provider=EmailProvider.SMTP,
            error="Connection refused",
        )

        assert result.success is False
        assert result.error == "Connection refused"
