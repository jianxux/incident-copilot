"""Comprehensive tests for the Incident Communication Hub."""

from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.comms import (
    AudienceType,
    ChannelDelivery,
    CommunicationPlan,
    CommunicationUpdate,
    DeliveryChannel,
    DeliveryStatus,
    EmailChannel,
    SlackChannel,
    SMSChannel,
    Stakeholder,
    StakeholderGroup,
    StatusPageChannel,
    UpdatePriority,
    UpdateScheduler,
)
from src.comms.models import (
    BroadcastUpdateRequest,
    CreateCommunicationPlanRequest,
    CreateStakeholderGroupRequest,
    CreateStakeholderRequest,
    SendUpdateRequest,
)
from src.comms.routes import router
from src.comms.templates import (
    BUILTIN_TEMPLATES,
    CommunicationTemplate,
    TemplateLibrary,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_stakeholder() -> Stakeholder:
    """Create a sample stakeholder."""
    return Stakeholder(
        id="stake-001",
        name="John Smith",
        email="john.smith@example.com",
        phone="+1-555-0100",
        slack_user_id="U12345678",
        audience_type=AudienceType.TECHNICAL,
        preferred_channels=[DeliveryChannel.SLACK, DeliveryChannel.EMAIL],
        notification_threshold=UpdatePriority.NORMAL,
        role="SRE",
        department="Engineering",
        subscribed_services=["payments-api", "auth-service"],
        subscribed_severity_levels=["critical", "high"],
    )


@pytest.fixture
def executive_stakeholder() -> Stakeholder:
    """Create an executive stakeholder."""
    return Stakeholder(
        id="stake-002",
        name="Jane Doe",
        email="jane.doe@example.com",
        audience_type=AudienceType.EXECUTIVE,
        preferred_channels=[DeliveryChannel.EMAIL],
        notification_threshold=UpdatePriority.HIGH,
        role="VP Engineering",
        department="Executive",
    )


@pytest.fixture
def customer_stakeholder() -> Stakeholder:
    """Create a customer stakeholder."""
    return Stakeholder(
        id="stake-003",
        name="Acme Corp",
        email="support@acme.com",
        audience_type=AudienceType.CUSTOMER,
        preferred_channels=[DeliveryChannel.EMAIL],
        notification_threshold=UpdatePriority.CRITICAL,
        organization="Acme Corporation",
    )


@pytest.fixture
def sample_stakeholder_group(sample_stakeholder, executive_stakeholder) -> StakeholderGroup:
    """Create a sample stakeholder group."""
    return StakeholderGroup(
        id="group-001",
        name="Incident Response Team",
        description="Primary incident response team",
        stakeholder_ids=[sample_stakeholder.id, executive_stakeholder.id],
        audience_type=AudienceType.TECHNICAL,
        default_channels=[DeliveryChannel.SLACK],
        subscribed_services=["payments-api"],
    )


@pytest.fixture
def sample_plan(sample_stakeholder) -> CommunicationPlan:
    """Create a sample communication plan."""
    return CommunicationPlan(
        id="plan-001",
        incident_id="inc-001",
        incident_title="Database connection timeout",
        severity="critical",
        stakeholder_ids=[sample_stakeholder.id],
        auto_reminder_enabled=True,
        auto_reminder_interval_minutes=15,
    )


@pytest.fixture
def sample_update(sample_plan) -> CommunicationUpdate:
    """Create a sample communication update."""
    return CommunicationUpdate(
        id="update-001",
        incident_id=sample_plan.incident_id,
        plan_id=sample_plan.id,
        subject="Incident Update: Database Connection Timeout",
        body="We are investigating database connection issues...",
        audience_type=AudienceType.TECHNICAL,
        channels=[DeliveryChannel.SLACK, DeliveryChannel.EMAIL],
        priority=UpdatePriority.HIGH,
    )


@pytest.fixture
async def template_library() -> TemplateLibrary:
    """Create an initialized template library."""
    library = TemplateLibrary()
    await library.initialize()
    return library


@pytest.fixture
async def scheduler() -> UpdateScheduler:
    """Create an update scheduler."""
    scheduler = UpdateScheduler(check_interval_seconds=1)
    yield scheduler
    if scheduler._running:
        await scheduler.stop()


@pytest.fixture
async def channel_delivery() -> ChannelDelivery:
    """Create a channel delivery service."""
    delivery = ChannelDelivery()
    await delivery.initialize_default_handlers()
    return delivery


@pytest.fixture
def test_app() -> FastAPI:
    """Create a test FastAPI app."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(test_app) -> TestClient:
    """Create a test client."""
    return TestClient(test_app)


# ============================================================================
# Stakeholder Model Tests
# ============================================================================


class TestStakeholderModel:
    """Tests for the Stakeholder model."""

    def test_stakeholder_creation(self, sample_stakeholder):
        """Test stakeholder is created with correct attributes."""
        assert sample_stakeholder.name == "John Smith"
        assert sample_stakeholder.email == "john.smith@example.com"
        assert sample_stakeholder.audience_type == AudienceType.TECHNICAL
        assert DeliveryChannel.SLACK in sample_stakeholder.preferred_channels

    def test_stakeholder_contact_info(self, sample_stakeholder):
        """Test contact_info property."""
        contact = sample_stakeholder.contact_info
        assert contact["email"] == "john.smith@example.com"
        assert contact["phone"] == "+1-555-0100"
        assert contact["slack"] == "U12345678"

    def test_stakeholder_defaults(self):
        """Test stakeholder default values."""
        stakeholder = Stakeholder(name="Test User")
        assert stakeholder.is_active is True
        assert stakeholder.audience_type == AudienceType.STAKEHOLDER
        assert DeliveryChannel.EMAIL in stakeholder.preferred_channels

    def test_stakeholder_subscriptions(self, sample_stakeholder):
        """Test service subscriptions."""
        assert "payments-api" in sample_stakeholder.subscribed_services
        assert "critical" in sample_stakeholder.subscribed_severity_levels


class TestStakeholderGroupModel:
    """Tests for the StakeholderGroup model."""

    def test_group_creation(self, sample_stakeholder_group):
        """Test group is created with correct attributes."""
        assert sample_stakeholder_group.name == "Incident Response Team"
        assert len(sample_stakeholder_group.stakeholder_ids) == 2

    def test_group_defaults(self):
        """Test group default values."""
        group = StakeholderGroup(name="Test Group")
        assert group.is_active is True
        assert len(group.stakeholder_ids) == 0


# ============================================================================
# Communication Plan Tests
# ============================================================================


class TestCommunicationPlanModel:
    """Tests for the CommunicationPlan model."""

    def test_plan_creation(self, sample_plan):
        """Test plan is created with correct attributes."""
        assert sample_plan.incident_id == "inc-001"
        assert sample_plan.severity == "critical"
        assert sample_plan.auto_reminder_enabled is True

    def test_plan_minutes_since_update_none(self, sample_plan):
        """Test minutes_since_last_update when no updates sent."""
        assert sample_plan.minutes_since_last_update is None

    def test_plan_minutes_since_update(self, sample_plan):
        """Test minutes_since_last_update calculation."""
        sample_plan.last_update_at = datetime.utcnow() - timedelta(minutes=10)
        minutes = sample_plan.minutes_since_last_update
        assert 9 <= minutes <= 11

    def test_plan_needs_reminder_no_updates(self, sample_plan):
        """Test needs_update_reminder with no updates."""
        # Set creation time to 20 minutes ago (> 15 min interval)
        sample_plan.created_at = datetime.utcnow() - timedelta(minutes=20)
        assert sample_plan.needs_update_reminder is True

    def test_plan_needs_reminder_recent_update(self, sample_plan):
        """Test needs_update_reminder with recent update."""
        sample_plan.last_update_at = datetime.utcnow() - timedelta(minutes=5)
        assert sample_plan.needs_update_reminder is False

    def test_plan_needs_reminder_disabled(self, sample_plan):
        """Test needs_update_reminder when disabled."""
        sample_plan.auto_reminder_enabled = False
        sample_plan.last_update_at = datetime.utcnow() - timedelta(minutes=30)
        assert sample_plan.needs_update_reminder is False


class TestCommunicationUpdateModel:
    """Tests for the CommunicationUpdate model."""

    def test_update_creation(self, sample_update):
        """Test update is created with correct attributes."""
        assert sample_update.subject == "Incident Update: Database Connection Timeout"
        assert sample_update.priority == UpdatePriority.HIGH
        assert sample_update.status == DeliveryStatus.PENDING

    def test_update_is_sent(self, sample_update):
        """Test is_sent property."""
        assert sample_update.is_sent is False

        sample_update.status = DeliveryStatus.DELIVERED
        assert sample_update.is_sent is True

    def test_successful_channels(self, sample_update):
        """Test successful_channels property."""
        sample_update.delivery_results = {
            "slack": DeliveryStatus.DELIVERED,
            "email": DeliveryStatus.FAILED,
        }
        channels = sample_update.successful_channels
        assert "slack" in channels
        assert "email" not in channels


# ============================================================================
# Template Library Tests
# ============================================================================


class TestTemplateLibrary:
    """Tests for the template library."""

    @pytest.mark.asyncio
    async def test_library_initialization(self, template_library):
        """Test library initializes with builtin templates."""
        templates, total = await template_library.list_templates()
        assert total == len(BUILTIN_TEMPLATES)
        assert total > 0

    @pytest.mark.asyncio
    async def test_get_template(self, template_library):
        """Test getting a template by ID."""
        template = await template_library.get_template("builtin-tech-initial")
        assert template is not None
        assert template.audience_type == AudienceType.TECHNICAL

    @pytest.mark.asyncio
    async def test_get_template_not_found(self, template_library):
        """Test getting non-existent template."""
        template = await template_library.get_template("nonexistent")
        assert template is None

    @pytest.mark.asyncio
    async def test_list_templates_by_audience(self, template_library):
        """Test filtering templates by audience type."""
        templates, total = await template_library.list_templates(
            audience_type=AudienceType.CUSTOMER
        )
        assert total > 0
        assert all(t.audience_type == AudienceType.CUSTOMER for t in templates)

    @pytest.mark.asyncio
    async def test_list_templates_by_category(self, template_library):
        """Test filtering templates by category."""
        templates, total = await template_library.list_templates(category="initial")
        assert total > 0
        assert all(t.category == "initial" for t in templates)

    @pytest.mark.asyncio
    async def test_render_template(self, template_library):
        """Test rendering a template with variables."""
        variables = {
            "incident_id": "INC-001",
            "incident_title": "Database outage",
            "severity": "critical",
            "service": "payments-api",
            "status": "investigating",
            "impact": "Payment processing delayed",
            "started_at": "2024-01-15 14:30 UTC",
            "update_time": "2024-01-15 15:00 UTC",
            "next_update": "30 minutes",
            "responder": "Jane Smith",
            "root_cause": "TBD",
            "resolution": "TBD",
            "action_items": "TBD",
        }

        rendered = await template_library.render_template(
            "builtin-tech-initial",
            variables,
        )

        assert rendered is not None
        assert "INC-001" in rendered.subject
        assert "payments-api" in rendered.body
        assert rendered.audience_type == AudienceType.TECHNICAL

    @pytest.mark.asyncio
    async def test_render_template_missing_variable(self, template_library):
        """Test rendering with missing required variable."""
        # Missing most required variables
        rendered = await template_library.render_template(
            "builtin-tech-initial",
            {"foo": "bar"},
        )
        assert rendered is None

    @pytest.mark.asyncio
    async def test_create_custom_template(self, template_library):
        """Test creating a custom template."""
        custom = CommunicationTemplate(
            name="Custom Template",
            audience_type=AudienceType.TECHNICAL,
            subject_template="Custom: {incident_title}",
            body_template="Custom body for {service}",
        )

        created = await template_library.create_template(custom)
        assert created.id is not None
        assert created.is_builtin is False

        # Verify it's retrievable
        retrieved = await template_library.get_template(created.id)
        assert retrieved is not None
        assert retrieved.name == "Custom Template"

    @pytest.mark.asyncio
    async def test_cannot_delete_builtin_template(self, template_library):
        """Test that builtin templates cannot be deleted."""
        deleted = await template_library.delete_template("builtin-tech-initial")
        assert deleted is False

        # Verify it still exists
        template = await template_library.get_template("builtin-tech-initial")
        assert template is not None

    @pytest.mark.asyncio
    async def test_get_templates_for_audience(self, template_library):
        """Test getting all templates for an audience."""
        templates = await template_library.get_templates_for_audience(
            AudienceType.EXECUTIVE
        )
        assert len(templates) > 0
        assert all(t.audience_type == AudienceType.EXECUTIVE for t in templates)

    @pytest.mark.asyncio
    async def test_get_template_for_category(self, template_library):
        """Test getting default template for audience and category."""
        template = await template_library.get_template_for_category(
            AudienceType.CUSTOMER,
            "resolved",
        )
        assert template is not None
        assert template.audience_type == AudienceType.CUSTOMER
        assert template.category == "resolved"


# ============================================================================
# Channel Delivery Tests
# ============================================================================


class TestSlackChannel:
    """Tests for Slack channel delivery."""

    @pytest.mark.asyncio
    async def test_slack_send(self, sample_update, sample_stakeholder):
        """Test sending via Slack."""
        channel = SlackChannel(bot_token="test-token")
        result = await channel.send(sample_update, [sample_stakeholder])

        assert result.success is True
        assert result.status == DeliveryStatus.DELIVERED
        assert result.channel == DeliveryChannel.SLACK

    @pytest.mark.asyncio
    async def test_slack_send_to_channel(self):
        """Test posting to a Slack channel."""
        channel = SlackChannel(bot_token="test-token")
        result = await channel.send_to_channel(
            "#incidents",
            "Test Subject",
            "Test body",
        )

        assert result.success is True
        assert "#incidents" in result.details.get("channel", "")


class TestEmailChannel:
    """Tests for Email channel delivery."""

    @pytest.mark.asyncio
    async def test_email_send(self, sample_update, sample_stakeholder):
        """Test sending via Email."""
        channel = EmailChannel(smtp_host="smtp.example.com")
        result = await channel.send(sample_update, [sample_stakeholder])

        assert result.success is True
        assert result.status == DeliveryStatus.DELIVERED
        assert result.recipient_count == 1

    @pytest.mark.asyncio
    async def test_email_no_recipients(self, sample_update):
        """Test email with no valid recipients."""
        channel = EmailChannel(smtp_host="smtp.example.com")
        stakeholder = Stakeholder(name="No Email", phone="+1-555-0100")

        result = await channel.send(sample_update, [stakeholder])

        assert result.success is False
        assert result.status == DeliveryStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_email_send_individual(self):
        """Test sending individual email."""
        channel = EmailChannel(smtp_host="smtp.example.com")
        result = await channel.send_individual(
            to_address="test@example.com",
            subject="Test",
            body="Test body",
            body_html="<p>Test body</p>",
        )

        assert result.success is True
        assert result.recipient_count == 1


class TestSMSChannel:
    """Tests for SMS channel delivery."""

    @pytest.mark.asyncio
    async def test_sms_send(self, sample_update, sample_stakeholder):
        """Test sending via SMS."""
        channel = SMSChannel(
            account_sid="test-sid",
            auth_token="test-token",
            from_number="+1-555-0000",
        )
        result = await channel.send(sample_update, [sample_stakeholder])

        assert result.success is True
        assert result.channel == DeliveryChannel.SMS

    @pytest.mark.asyncio
    async def test_sms_no_phone_numbers(self, sample_update):
        """Test SMS with no valid phone numbers."""
        channel = SMSChannel(
            account_sid="test-sid",
            auth_token="test-token",
            from_number="+1-555-0000",
        )
        stakeholder = Stakeholder(name="No Phone", email="test@example.com")

        result = await channel.send(sample_update, [stakeholder])

        assert result.success is False
        assert result.status == DeliveryStatus.SKIPPED


class TestStatusPageChannel:
    """Tests for Status Page channel delivery."""

    @pytest.mark.asyncio
    async def test_statuspage_send(self, sample_update, sample_stakeholder):
        """Test posting to status page."""
        channel = StatusPageChannel(api_key="test-key", page_id="page-001")
        result = await channel.send(sample_update, [sample_stakeholder])

        assert result.success is True
        assert result.channel == DeliveryChannel.STATUS_PAGE

    @pytest.mark.asyncio
    async def test_statuspage_create_incident(self):
        """Test creating a status page incident."""
        channel = StatusPageChannel(api_key="test-key", page_id="page-001")
        result = await channel.create_incident(
            name="Test Incident",
            body="Investigating an issue",
            status="investigating",
            impact="minor",
        )

        assert result.success is True
        assert result.message_id is not None  # Incident ID

    @pytest.mark.asyncio
    async def test_statuspage_update_incident(self):
        """Test updating a status page incident."""
        channel = StatusPageChannel(api_key="test-key", page_id="page-001")
        result = await channel.update_incident(
            incident_id="inc-abc123",
            body="Issue has been identified",
            status="identified",
        )

        assert result.success is True


class TestChannelDelivery:
    """Tests for the ChannelDelivery orchestrator."""

    @pytest.mark.asyncio
    async def test_send_update_multiple_channels(
        self, channel_delivery, sample_update, sample_stakeholder
    ):
        """Test sending to multiple channels."""
        sample_update.channels = [DeliveryChannel.SLACK, DeliveryChannel.EMAIL]
        results = await channel_delivery.send_update(
            sample_update, [sample_stakeholder]
        )

        assert len(results) == 2
        assert DeliveryChannel.SLACK in results
        assert DeliveryChannel.EMAIL in results

    @pytest.mark.asyncio
    async def test_send_update_uses_stakeholder_preferences(
        self, channel_delivery, sample_update, sample_stakeholder
    ):
        """Test that stakeholder preferences are used when no channels specified."""
        sample_update.channels = []  # No channels specified
        results = await channel_delivery.send_update(
            sample_update, [sample_stakeholder]
        )

        # Should use stakeholder's preferred channels
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_audit_log(
        self, channel_delivery, sample_update, sample_stakeholder
    ):
        """Test audit log is recorded."""
        await channel_delivery.send_update(sample_update, [sample_stakeholder])

        entries, total = await channel_delivery.get_audit_log(
            incident_id=sample_update.incident_id
        )

        assert total > 0
        assert entries[0].incident_id == sample_update.incident_id

    @pytest.mark.asyncio
    async def test_get_available_channels(self, channel_delivery):
        """Test getting available channels."""
        channels = channel_delivery.get_available_channels()
        assert DeliveryChannel.SLACK in channels
        assert DeliveryChannel.EMAIL in channels


# ============================================================================
# Update Scheduler Tests
# ============================================================================


class TestUpdateScheduler:
    """Tests for the update scheduler."""

    @pytest.mark.asyncio
    async def test_scheduler_starts_and_stops(self, scheduler):
        """Test scheduler lifecycle."""
        await scheduler.start()
        stats = scheduler.get_stats()
        assert stats["running"] is True

        await scheduler.stop()
        stats = scheduler.get_stats()
        assert stats["running"] is False

    @pytest.mark.asyncio
    async def test_register_plan(self, scheduler, sample_plan):
        """Test registering a plan for monitoring."""
        await scheduler.register_plan(sample_plan)

        plans = await scheduler.list_active_plans()
        assert len(plans) == 1
        assert plans[0].id == sample_plan.id

    @pytest.mark.asyncio
    async def test_unregister_plan(self, scheduler, sample_plan):
        """Test unregistering a plan."""
        await scheduler.register_plan(sample_plan)
        await scheduler.unregister_plan(sample_plan.id)

        plans = await scheduler.list_active_plans()
        assert len(plans) == 0

    @pytest.mark.asyncio
    async def test_record_update_sent(self, scheduler, sample_plan):
        """Test recording that an update was sent."""
        await scheduler.register_plan(sample_plan)

        original_count = sample_plan.total_updates_sent
        await scheduler.record_update_sent(sample_plan.id)

        plan = await scheduler.get_plan(sample_plan.id)
        assert plan.total_updates_sent == original_count + 1
        assert plan.last_update_at is not None

    @pytest.mark.asyncio
    async def test_pause_and_resume_reminders(self, scheduler, sample_plan):
        """Test pausing and resuming reminders."""
        await scheduler.register_plan(sample_plan)

        # Pause
        success = await scheduler.pause_reminders(sample_plan.id)
        assert success is True

        plan = await scheduler.get_plan(sample_plan.id)
        assert plan.auto_reminder_enabled is False

        # Resume
        success = await scheduler.resume_reminders(sample_plan.id)
        assert success is True

        plan = await scheduler.get_plan(sample_plan.id)
        assert plan.auto_reminder_enabled is True

    @pytest.mark.asyncio
    async def test_set_reminder_interval(self, scheduler, sample_plan):
        """Test setting reminder interval."""
        await scheduler.register_plan(sample_plan)

        success = await scheduler.set_reminder_interval(sample_plan.id, 30)
        assert success is True

        plan = await scheduler.get_plan(sample_plan.id)
        assert plan.auto_reminder_interval_minutes == 30

    @pytest.mark.asyncio
    async def test_check_and_send_reminders(self, scheduler, sample_plan):
        """Test checking and sending reminders."""
        # Set up an overdue plan
        sample_plan.created_at = datetime.utcnow() - timedelta(minutes=20)
        await scheduler.register_plan(sample_plan)

        callback_called = []

        def on_reminder(reminder):
            callback_called.append(reminder)

        scheduler.on_reminder(on_reminder)

        reminders_sent = await scheduler.check_and_send_reminders()
        assert reminders_sent >= 1
        assert len(callback_called) >= 1

    @pytest.mark.asyncio
    async def test_get_overdue_plans(self, scheduler, sample_plan):
        """Test getting overdue plans."""
        sample_plan.created_at = datetime.utcnow() - timedelta(minutes=20)
        await scheduler.register_plan(sample_plan)

        overdue = await scheduler.get_overdue_plans()
        assert len(overdue) == 1
        assert overdue[0].id == sample_plan.id

    @pytest.mark.asyncio
    async def test_reminder_history(self, scheduler, sample_plan):
        """Test getting reminder history."""
        sample_plan.created_at = datetime.utcnow() - timedelta(minutes=20)
        await scheduler.register_plan(sample_plan)

        await scheduler.check_and_send_reminders()

        reminders, total = await scheduler.get_reminder_history(
            plan_id=sample_plan.id
        )
        assert total >= 1

    @pytest.mark.asyncio
    async def test_acknowledge_reminder(self, scheduler, sample_plan):
        """Test acknowledging a reminder."""
        sample_plan.created_at = datetime.utcnow() - timedelta(minutes=20)
        await scheduler.register_plan(sample_plan)

        await scheduler.check_and_send_reminders()

        reminders, _ = await scheduler.get_reminder_history()
        if reminders:
            reminder = reminders[0]
            acknowledged = await scheduler.acknowledge_reminder(
                reminder.id, "user-123"
            )
            assert acknowledged is not None
            assert acknowledged.acknowledged_by == "user-123"


# ============================================================================
# API Route Tests
# ============================================================================


class TestStakeholderAPI:
    """Tests for stakeholder API endpoints."""

    def test_create_stakeholder(self, client):
        """Test POST /api/v1/comms/stakeholders."""
        data = {
            "name": "Test User",
            "email": "test@example.com",
            "audience_type": "technical",
            "preferred_channels": ["slack", "email"],
        }

        response = client.post("/api/v1/comms/stakeholders", json=data)
        assert response.status_code == 201

        result = response.json()
        assert result["name"] == "Test User"
        assert result["email"] == "test@example.com"
        assert "id" in result

    def test_list_stakeholders(self, client):
        """Test GET /api/v1/comms/stakeholders."""
        # Create a stakeholder first
        client.post(
            "/api/v1/comms/stakeholders",
            json={"name": "Test User", "email": "test@example.com"},
        )

        response = client.get("/api/v1/comms/stakeholders")
        assert response.status_code == 200

        result = response.json()
        assert "stakeholders" in result
        assert "total" in result

    def test_get_stakeholder(self, client):
        """Test GET /api/v1/comms/stakeholders/{id}."""
        # Create first
        create_resp = client.post(
            "/api/v1/comms/stakeholders",
            json={"name": "Test User"},
        )
        stakeholder_id = create_resp.json()["id"]

        # Get
        response = client.get(f"/api/v1/comms/stakeholders/{stakeholder_id}")
        assert response.status_code == 200
        assert response.json()["id"] == stakeholder_id

    def test_get_stakeholder_not_found(self, client):
        """Test GET /api/v1/comms/stakeholders/{id} with invalid ID."""
        response = client.get("/api/v1/comms/stakeholders/nonexistent")
        assert response.status_code == 404

    def test_update_stakeholder(self, client):
        """Test PATCH /api/v1/comms/stakeholders/{id}."""
        # Create first
        create_resp = client.post(
            "/api/v1/comms/stakeholders",
            json={"name": "Test User"},
        )
        stakeholder_id = create_resp.json()["id"]

        # Update
        response = client.patch(
            f"/api/v1/comms/stakeholders/{stakeholder_id}",
            json={"name": "Updated Name", "role": "Engineer"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"
        assert response.json()["role"] == "Engineer"

    def test_delete_stakeholder(self, client):
        """Test DELETE /api/v1/comms/stakeholders/{id}."""
        # Create first
        create_resp = client.post(
            "/api/v1/comms/stakeholders",
            json={"name": "Test User"},
        )
        stakeholder_id = create_resp.json()["id"]

        # Delete
        response = client.delete(f"/api/v1/comms/stakeholders/{stakeholder_id}")
        assert response.status_code == 204

        # Verify deleted
        response = client.get(f"/api/v1/comms/stakeholders/{stakeholder_id}")
        assert response.status_code == 404


class TestCommunicationPlanAPI:
    """Tests for communication plan API endpoints."""

    def test_create_plan(self, client):
        """Test POST /api/v1/comms/plans."""
        data = {
            "incident_id": "inc-001",
            "incident_title": "Test Incident",
            "severity": "high",
            "auto_reminder_enabled": True,
            "auto_reminder_interval_minutes": 15,
        }

        response = client.post("/api/v1/comms/plans", json=data)
        assert response.status_code == 201

        result = response.json()
        assert result["incident_id"] == "inc-001"
        assert result["auto_reminder_enabled"] is True

    def test_list_plans(self, client):
        """Test GET /api/v1/comms/plans."""
        # Create a plan first
        client.post(
            "/api/v1/comms/plans",
            json={
                "incident_id": "inc-002",
                "incident_title": "Test",
                "severity": "high",
            },
        )

        response = client.get("/api/v1/comms/plans")
        assert response.status_code == 200
        assert "plans" in response.json()

    def test_get_plan(self, client):
        """Test GET /api/v1/comms/plans/{id}."""
        # Create first
        create_resp = client.post(
            "/api/v1/comms/plans",
            json={
                "incident_id": "inc-003",
                "incident_title": "Test",
                "severity": "high",
            },
        )
        plan_id = create_resp.json()["id"]

        response = client.get(f"/api/v1/comms/plans/{plan_id}")
        assert response.status_code == 200

    def test_close_plan(self, client):
        """Test POST /api/v1/comms/plans/{id}/close."""
        # Create first
        create_resp = client.post(
            "/api/v1/comms/plans",
            json={
                "incident_id": "inc-004",
                "incident_title": "Test",
                "severity": "high",
            },
        )
        plan_id = create_resp.json()["id"]

        response = client.post(f"/api/v1/comms/plans/{plan_id}/close")
        assert response.status_code == 200
        assert response.json()["is_active"] is False


class TestSendUpdateAPI:
    """Tests for send update API endpoints."""

    def test_send_update(self, client):
        """Test POST /api/v1/comms/updates/send."""
        data = {
            "incident_id": "inc-001",
            "subject": "Test Update",
            "body": "This is a test update.",
            "audience_types": ["technical"],
            "channels": ["slack"],
            "priority": "normal",
        }

        response = client.post("/api/v1/comms/updates/send", json=data)
        assert response.status_code == 200

        result = response.json()
        assert result["subject"] == "Test Update"
        assert "id" in result


class TestTemplateAPI:
    """Tests for template API endpoints."""

    def test_list_templates(self, client):
        """Test GET /api/v1/comms/templates."""
        response = client.get("/api/v1/comms/templates")
        assert response.status_code == 200

        result = response.json()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_list_templates_by_audience(self, client):
        """Test filtering templates by audience."""
        response = client.get(
            "/api/v1/comms/templates",
            params={"audience_type": "customer"},
        )
        assert response.status_code == 200

    def test_get_template(self, client):
        """Test GET /api/v1/comms/templates/{id}."""
        response = client.get("/api/v1/comms/templates/builtin-tech-initial")
        assert response.status_code == 200
        assert response.json()["id"] == "builtin-tech-initial"

    def test_get_template_not_found(self, client):
        """Test GET /api/v1/comms/templates/{id} with invalid ID."""
        response = client.get("/api/v1/comms/templates/nonexistent")
        assert response.status_code == 404

    def test_render_template(self, client):
        """Test POST /api/v1/comms/templates/{id}/render."""
        variables = {
            "incident_id": "INC-001",
            "incident_title": "Database outage",
            "severity": "critical",
            "service": "payments-api",
            "status": "investigating",
            "impact": "Payment processing delayed",
            "started_at": "2024-01-15 14:30 UTC",
            "update_time": "2024-01-15 15:00 UTC",
            "next_update": "30 minutes",
            "responder": "Jane Smith",
            "root_cause": "TBD",
            "resolution": "TBD",
            "action_items": "TBD",
        }

        response = client.post(
            "/api/v1/comms/templates/builtin-tech-initial/render",
            json=variables,
        )
        assert response.status_code == 200

        result = response.json()
        assert "INC-001" in result["subject"]


class TestReminderAPI:
    """Tests for reminder API endpoints."""

    def test_pause_reminders(self, client):
        """Test POST /api/v1/comms/plans/{id}/reminders/pause."""
        # Create a plan first
        create_resp = client.post(
            "/api/v1/comms/plans",
            json={
                "incident_id": "inc-reminder-1",
                "incident_title": "Test",
                "severity": "high",
            },
        )
        plan_id = create_resp.json()["id"]

        response = client.post(f"/api/v1/comms/plans/{plan_id}/reminders/pause")
        assert response.status_code == 200
        assert response.json()["status"] == "paused"

    def test_resume_reminders(self, client):
        """Test POST /api/v1/comms/plans/{id}/reminders/resume."""
        # Create and pause first
        create_resp = client.post(
            "/api/v1/comms/plans",
            json={
                "incident_id": "inc-reminder-2",
                "incident_title": "Test",
                "severity": "high",
            },
        )
        plan_id = create_resp.json()["id"]
        client.post(f"/api/v1/comms/plans/{plan_id}/reminders/pause")

        response = client.post(f"/api/v1/comms/plans/{plan_id}/reminders/resume")
        assert response.status_code == 200
        assert response.json()["status"] == "resumed"

    def test_set_reminder_interval(self, client):
        """Test POST /api/v1/comms/plans/{id}/reminders/interval."""
        # Create a plan first
        create_resp = client.post(
            "/api/v1/comms/plans",
            json={
                "incident_id": "inc-reminder-3",
                "incident_title": "Test",
                "severity": "high",
            },
        )
        plan_id = create_resp.json()["id"]

        response = client.post(
            f"/api/v1/comms/plans/{plan_id}/reminders/interval",
            params={"interval_minutes": 30},
        )
        assert response.status_code == 200
        assert response.json()["interval_minutes"] == 30


class TestAuditAPI:
    """Tests for audit log API endpoints."""

    def test_get_audit_log(self, client):
        """Test GET /api/v1/comms/audit."""
        response = client.get("/api/v1/comms/audit")
        assert response.status_code == 200

        result = response.json()
        assert "entries" in result
        assert "total" in result


class TestStatsAPI:
    """Tests for statistics API endpoints."""

    def test_get_stats(self, client):
        """Test GET /api/v1/comms/stats."""
        response = client.get("/api/v1/comms/stats")
        assert response.status_code == 200

        result = response.json()
        assert "total_stakeholders" in result
        assert "available_channels" in result
        assert "scheduler" in result

    def test_get_overdue_plans(self, client):
        """Test GET /api/v1/comms/stats/overdue-plans."""
        response = client.get("/api/v1/comms/stats/overdue-plans")
        assert response.status_code == 200

        result = response.json()
        assert "count" in result
        assert "plans" in result


# ============================================================================
# Integration Tests
# ============================================================================


class TestCommunicationIntegration:
    """Integration tests for the complete communication flow."""

    @pytest.mark.asyncio
    async def test_full_communication_flow(
        self,
        template_library,
        channel_delivery,
        scheduler,
        sample_stakeholder,
        executive_stakeholder,
    ):
        """Test complete flow from plan creation to update delivery."""
        # 1. Create stakeholders (already have fixtures)

        # 2. Create a communication plan
        plan = CommunicationPlan(
            incident_id="int-test-001",
            incident_title="Integration Test Incident",
            severity="critical",
            stakeholder_ids=[sample_stakeholder.id, executive_stakeholder.id],
            auto_reminder_enabled=True,
            auto_reminder_interval_minutes=15,
        )

        # 3. Register plan with scheduler
        await scheduler.register_plan(plan)

        # 4. Render a template for technical audience
        variables = {
            "incident_id": plan.incident_id,
            "incident_title": plan.incident_title,
            "severity": plan.severity,
            "service": "test-service",
            "status": "investigating",
            "impact": "Service degradation",
            "started_at": datetime.utcnow().isoformat(),
            "update_time": datetime.utcnow().isoformat(),
            "next_update": "15 minutes",
            "responder": "Test Responder",
            "root_cause": "TBD",
            "resolution": "TBD",
            "action_items": "Investigating",
        }

        rendered = await template_library.render_template(
            "builtin-tech-initial",
            variables,
        )
        assert rendered is not None

        # 5. Create and send an update
        update = CommunicationUpdate(
            incident_id=plan.incident_id,
            plan_id=plan.id,
            subject=rendered.subject,
            body=rendered.body,
            body_html=rendered.body_html,
            audience_type=AudienceType.TECHNICAL,
            channels=[DeliveryChannel.SLACK, DeliveryChannel.EMAIL],
            priority=UpdatePriority.HIGH,
        )

        results = await channel_delivery.send_update(
            update,
            [sample_stakeholder],
        )

        # 6. Verify delivery
        assert len(results) == 2
        assert all(r.success for r in results.values())

        # 7. Record update in scheduler
        await scheduler.record_update_sent(plan.id)

        # 8. Verify plan was updated
        updated_plan = await scheduler.get_plan(plan.id)
        assert updated_plan.total_updates_sent == 1
        assert updated_plan.last_update_at is not None

        # 9. Check audit log
        entries, total = await channel_delivery.get_audit_log(
            incident_id=plan.incident_id
        )
        assert total >= 2  # One per channel

    @pytest.mark.asyncio
    async def test_multi_audience_communication(
        self,
        template_library,
        channel_delivery,
        sample_stakeholder,
        executive_stakeholder,
        customer_stakeholder,
    ):
        """Test sending different messages to different audiences."""
        incident_id = "multi-aud-001"

        variables = {
            "incident_id": incident_id,
            "incident_title": "Multi-audience Test",
            "severity": "high",
            "service": "test-service",
            "status": "investigating",
            "impact": "Service degradation",
            "started_at": "2024-01-15 14:30 UTC",
            "update_time": "2024-01-15 15:00 UTC",
            "next_update": "30 minutes",
            "responder": "Test Team",
            "root_cause": "TBD",
            "resolution": "TBD",
            "action_items": "TBD",
        }

        # Send to technical audience
        tech_rendered = await template_library.render_template(
            "builtin-tech-initial",
            variables,
        )
        tech_update = CommunicationUpdate(
            incident_id=incident_id,
            subject=tech_rendered.subject,
            body=tech_rendered.body,
            audience_type=AudienceType.TECHNICAL,
            channels=[DeliveryChannel.SLACK],
        )
        tech_results = await channel_delivery.send_update(
            tech_update, [sample_stakeholder]
        )
        assert tech_results[DeliveryChannel.SLACK].success

        # Send to executive audience
        exec_rendered = await template_library.render_template(
            "builtin-exec-initial",
            variables,
        )
        exec_update = CommunicationUpdate(
            incident_id=incident_id,
            subject=exec_rendered.subject,
            body=exec_rendered.body,
            audience_type=AudienceType.EXECUTIVE,
            channels=[DeliveryChannel.EMAIL],
        )
        exec_results = await channel_delivery.send_update(
            exec_update, [executive_stakeholder]
        )
        assert exec_results[DeliveryChannel.EMAIL].success

        # Send to customer audience
        cust_rendered = await template_library.render_template(
            "builtin-customer-initial",
            variables,
        )
        cust_update = CommunicationUpdate(
            incident_id=incident_id,
            subject=cust_rendered.subject,
            body=cust_rendered.body,
            audience_type=AudienceType.CUSTOMER,
            channels=[DeliveryChannel.EMAIL],
        )
        cust_results = await channel_delivery.send_update(
            cust_update, [customer_stakeholder]
        )
        assert cust_results[DeliveryChannel.EMAIL].success

        # Verify different messages were sent
        assert "🚨" in tech_rendered.subject  # Technical has emoji
        assert "Executive" in exec_rendered.body
        assert "Dear Valued Customer" in cust_rendered.body
