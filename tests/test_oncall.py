"""Tests for On-Call Roster integration."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.config import Settings
from src.integrations.oncall import OnCallAdapter, OnCallProvider
from src.models import OnCallPerson, OnCallRoster

# --- Fixtures ---


@pytest.fixture
def pagerduty_settings():
    """Settings configured for PagerDuty."""
    return Settings(
        pagerduty_api_key="pd-api-key-123",
        oncall_provider="auto",
        oncall_schedule_id="SCHEDULE123",
        oncall_schedule_map={"payments-api": "SCHEDULE_PAYMENTS"},
        oncall_enabled=True,
    )


@pytest.fixture
def opsgenie_settings():
    """Settings configured for Opsgenie."""
    return Settings(
        opsgenie_api_key="og-api-key-456",
        opsgenie_region="us",
        oncall_provider="auto",
        oncall_schedule_id="schedule-uuid-123",
        oncall_schedule_map={"auth-service": "schedule-auth-uuid"},
        oncall_enabled=True,
    )


@pytest.fixture
def pagerduty_adapter(pagerduty_settings):
    return OnCallAdapter(pagerduty_settings)


@pytest.fixture
def opsgenie_adapter(opsgenie_settings):
    return OnCallAdapter(opsgenie_settings)


# --- Provider Detection Tests ---


def test_detect_pagerduty_provider():
    """Test PagerDuty provider detection from credentials."""
    settings = Settings(pagerduty_api_key="pd-key", oncall_provider="auto")
    adapter = OnCallAdapter(settings)
    assert adapter.provider == OnCallProvider.PAGERDUTY


def test_detect_opsgenie_provider():
    """Test Opsgenie provider detection from credentials."""
    settings = Settings(opsgenie_api_key="og-key", oncall_provider="auto")
    adapter = OnCallAdapter(settings)
    assert adapter.provider == OnCallProvider.OPSGENIE


def test_explicit_pagerduty_provider():
    """Test explicit PagerDuty provider override."""
    settings = Settings(
        pagerduty_api_key="pd-key",
        opsgenie_api_key="og-key",
        oncall_provider="pagerduty",
    )
    adapter = OnCallAdapter(settings)
    assert adapter.provider == OnCallProvider.PAGERDUTY


def test_explicit_opsgenie_provider():
    """Test explicit Opsgenie provider override."""
    settings = Settings(
        pagerduty_api_key="pd-key",
        opsgenie_api_key="og-key",
        oncall_provider="opsgenie",
    )
    adapter = OnCallAdapter(settings)
    assert adapter.provider == OnCallProvider.OPSGENIE


def test_no_provider_configured():
    """Test when no on-call provider is configured."""
    settings = Settings(oncall_provider="auto")
    adapter = OnCallAdapter(settings)
    assert adapter.provider == OnCallProvider.NONE


# --- Schedule ID Resolution Tests ---


def test_resolve_schedule_id_explicit(pagerduty_adapter):
    """Test explicit schedule ID takes priority."""
    result = pagerduty_adapter._resolve_schedule_id(
        schedule_id="EXPLICIT_SCHEDULE",
        service_name="payments-api",
    )
    assert result == "EXPLICIT_SCHEDULE"


def test_resolve_schedule_id_from_map(pagerduty_adapter):
    """Test schedule ID resolution from service mapping."""
    result = pagerduty_adapter._resolve_schedule_id(
        schedule_id=None,
        service_name="payments-api",
    )
    assert result == "SCHEDULE_PAYMENTS"


def test_resolve_schedule_id_default(pagerduty_adapter):
    """Test fallback to default schedule ID."""
    result = pagerduty_adapter._resolve_schedule_id(
        schedule_id=None,
        service_name="unknown-service",
    )
    assert result == "SCHEDULE123"


def test_resolve_schedule_id_none():
    """Test when no schedule ID can be resolved."""
    settings = Settings(pagerduty_api_key="key", oncall_schedule_id="")
    adapter = OnCallAdapter(settings)
    result = adapter._resolve_schedule_id(schedule_id=None, service_name="unknown")
    assert result is None


# --- PagerDuty API Tests ---


@pytest.mark.asyncio
async def test_get_pagerduty_oncall_success(pagerduty_adapter):
    """Test successful PagerDuty on-call fetch."""
    mock_users_response = {
        "users": [
            {
                "id": "PUSER123",
                "name": "Jane Doe",
                "email": "jane@example.com",
                "avatar_url": "https://example.com/avatar.png",
                "contact_methods": [{"type": "phone_contact_method", "address": "+1234567890"}],
            },
            {
                "id": "PUSER456",
                "name": "John Smith",
                "email": "john@example.com",
                "contact_methods": [],
            },
        ]
    }

    mock_schedule_response = {
        "schedule": {
            "id": "SCHEDULE123",
            "name": "Primary On-Call",
        }
    }

    with patch.object(httpx.AsyncClient, "get") as mock_get:
        # Set up mock responses
        mock_response_users = MagicMock()
        mock_response_users.json.return_value = mock_users_response
        mock_response_users.raise_for_status = MagicMock()

        mock_response_schedule = MagicMock()
        mock_response_schedule.json.return_value = mock_schedule_response
        mock_response_schedule.raise_for_status = MagicMock()

        mock_get.side_effect = [mock_response_users, mock_response_schedule]

        roster = await pagerduty_adapter._get_pagerduty_oncall("SCHEDULE123")

    assert roster is not None
    assert roster.schedule_id == "SCHEDULE123"
    assert roster.schedule_name == "Primary On-Call"
    assert roster.provider == "pagerduty"
    assert len(roster.oncall_persons) == 2
    assert roster.oncall_persons[0].name == "Jane Doe"
    assert roster.oncall_persons[0].email == "jane@example.com"
    assert roster.oncall_persons[0].phone == "+1234567890"
    assert roster.oncall_persons[1].name == "John Smith"
    assert roster.oncall_persons[1].phone is None
    assert "pagerduty.com/schedules/SCHEDULE123" in roster.schedule_url


@pytest.mark.asyncio
async def test_get_pagerduty_oncall_empty(pagerduty_adapter):
    """Test PagerDuty on-call fetch with no users on-call."""
    mock_users_response = {"users": []}
    mock_schedule_response = {"schedule": {"id": "SCHEDULE123", "name": "Empty Schedule"}}

    with patch.object(httpx.AsyncClient, "get") as mock_get:
        mock_response_users = MagicMock()
        mock_response_users.json.return_value = mock_users_response
        mock_response_users.raise_for_status = MagicMock()

        mock_response_schedule = MagicMock()
        mock_response_schedule.json.return_value = mock_schedule_response
        mock_response_schedule.raise_for_status = MagicMock()

        mock_get.side_effect = [mock_response_users, mock_response_schedule]

        roster = await pagerduty_adapter._get_pagerduty_oncall("SCHEDULE123")

    assert roster is not None
    assert len(roster.oncall_persons) == 0
    assert roster.has_oncall is False


# --- Opsgenie API Tests ---


@pytest.mark.asyncio
async def test_get_opsgenie_oncall_success(opsgenie_adapter):
    """Test successful Opsgenie on-call fetch."""
    mock_oncall_response = {
        "data": {
            "onCallParticipants": [
                {
                    "id": "user-uuid-123",
                    "name": "alice@example.com",
                    "type": "user",
                },
                {
                    "id": "user-uuid-456",
                    "name": "bob@example.com",
                    "type": "user",
                },
            ]
        }
    }

    mock_schedule_response = {
        "data": {
            "id": "schedule-uuid-123",
            "name": "Platform Team On-Call",
        }
    }

    with patch.object(httpx.AsyncClient, "get") as mock_get:
        mock_response_oncall = MagicMock()
        mock_response_oncall.json.return_value = mock_oncall_response
        mock_response_oncall.raise_for_status = MagicMock()

        mock_response_schedule = MagicMock()
        mock_response_schedule.json.return_value = mock_schedule_response
        mock_response_schedule.raise_for_status = MagicMock()

        mock_get.side_effect = [mock_response_oncall, mock_response_schedule]

        roster = await opsgenie_adapter._get_opsgenie_oncall("schedule-uuid-123")

    assert roster is not None
    assert roster.schedule_id == "schedule-uuid-123"
    assert roster.schedule_name == "Platform Team On-Call"
    assert roster.provider == "opsgenie"
    assert len(roster.oncall_persons) == 2
    assert roster.oncall_persons[0].email == "alice@example.com"
    assert "opsgenie.com/schedule" in roster.schedule_url


# --- OnCallPerson Model Tests ---


def test_oncall_person_slack_mention_with_id():
    """Test Slack mention format with Slack user ID."""
    person = OnCallPerson(
        id="123",
        name="Jane Doe",
        slack_user_id="U12345678",
    )
    assert person.slack_mention == "<@U12345678>"


def test_oncall_person_slack_mention_without_id():
    """Test Slack mention fallback to name."""
    person = OnCallPerson(
        id="123",
        name="Jane Doe",
    )
    assert person.slack_mention == "Jane Doe"


def test_oncall_person_teams_mention_with_email():
    """Test Teams mention format with email."""
    person = OnCallPerson(
        id="123",
        name="Jane Doe",
        email="jane@example.com",
    )
    assert person.teams_mention == "<at>jane@example.com</at>"


def test_oncall_person_teams_mention_without_email():
    """Test Teams mention fallback to name."""
    person = OnCallPerson(
        id="123",
        name="Jane Doe",
    )
    assert person.teams_mention == "Jane Doe"


# --- OnCallRoster Model Tests ---


def test_oncall_roster_primary_oncall():
    """Test primary_oncall returns first person."""
    roster = OnCallRoster(
        schedule_id="123",
        schedule_name="Test",
        provider="pagerduty",
        oncall_persons=[
            OnCallPerson(id="1", name="First"),
            OnCallPerson(id="2", name="Second"),
        ],
        fetched_at=datetime.now(UTC),
    )
    assert roster.primary_oncall is not None
    assert roster.primary_oncall.name == "First"


def test_oncall_roster_primary_oncall_empty():
    """Test primary_oncall returns None when empty."""
    roster = OnCallRoster(
        schedule_id="123",
        schedule_name="Test",
        provider="pagerduty",
        oncall_persons=[],
        fetched_at=datetime.now(UTC),
    )
    assert roster.primary_oncall is None


def test_oncall_roster_oncall_names():
    """Test oncall_names returns list of names."""
    roster = OnCallRoster(
        schedule_id="123",
        schedule_name="Test",
        provider="pagerduty",
        oncall_persons=[
            OnCallPerson(id="1", name="Alice"),
            OnCallPerson(id="2", name="Bob"),
        ],
        fetched_at=datetime.now(UTC),
    )
    assert roster.oncall_names == ["Alice", "Bob"]


def test_oncall_roster_has_oncall_true():
    """Test has_oncall returns True when people on-call."""
    roster = OnCallRoster(
        schedule_id="123",
        schedule_name="Test",
        provider="pagerduty",
        oncall_persons=[OnCallPerson(id="1", name="Alice")],
        fetched_at=datetime.now(UTC),
    )
    assert roster.has_oncall is True


def test_oncall_roster_has_oncall_false():
    """Test has_oncall returns False when no one on-call."""
    roster = OnCallRoster(
        schedule_id="123",
        schedule_name="Test",
        provider="pagerduty",
        oncall_persons=[],
        fetched_at=datetime.now(UTC),
    )
    assert roster.has_oncall is False


# --- Integration Tests ---


@pytest.mark.asyncio
async def test_get_current_oncall_no_provider():
    """Test get_current_oncall returns None when no provider configured."""
    settings = Settings()
    adapter = OnCallAdapter(settings)
    result = await adapter.get_current_oncall(schedule_id="any")
    assert result is None


@pytest.mark.asyncio
async def test_get_current_oncall_no_schedule_id():
    """Test get_current_oncall returns None when no schedule ID resolved."""
    settings = Settings(pagerduty_api_key="key", oncall_schedule_id="")
    adapter = OnCallAdapter(settings)
    result = await adapter.get_current_oncall()
    assert result is None


@pytest.mark.asyncio
async def test_get_oncall_for_service(pagerduty_adapter):
    """Test get_oncall_for_service uses service mapping."""
    mock_users_response = {
        "users": [{"id": "1", "name": "Oncall Person", "email": "oncall@test.com"}]
    }
    mock_schedule_response = {"schedule": {"name": "Payments Schedule"}}

    with patch.object(httpx.AsyncClient, "get") as mock_get:
        mock_response_users = MagicMock()
        mock_response_users.json.return_value = mock_users_response
        mock_response_users.raise_for_status = MagicMock()

        mock_response_schedule = MagicMock()
        mock_response_schedule.json.return_value = mock_schedule_response
        mock_response_schedule.raise_for_status = MagicMock()

        mock_get.side_effect = [mock_response_users, mock_response_schedule]

        roster = await pagerduty_adapter.get_oncall_for_service("payments-api")

    assert roster is not None
    # Should use SCHEDULE_PAYMENTS from mapping
    assert roster.schedule_id == "SCHEDULE_PAYMENTS"


# --- List Schedules Tests ---


@pytest.mark.asyncio
async def test_list_pagerduty_schedules(pagerduty_adapter):
    """Test listing PagerDuty schedules."""
    mock_response = {
        "schedules": [
            {"id": "SCHED1", "name": "Primary"},
            {"id": "SCHED2", "name": "Secondary"},
        ]
    }

    with patch.object(httpx.AsyncClient, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        schedules = await pagerduty_adapter.list_schedules()

    assert len(schedules) == 2
    assert schedules[0]["name"] == "Primary"


@pytest.mark.asyncio
async def test_list_opsgenie_schedules(opsgenie_adapter):
    """Test listing Opsgenie schedules."""
    mock_response = {
        "data": [
            {"id": "sched-1", "name": "Platform Team"},
            {"id": "sched-2", "name": "Backend Team"},
        ]
    }

    with patch.object(httpx.AsyncClient, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        schedules = await opsgenie_adapter.list_schedules()

    assert len(schedules) == 2
    assert schedules[0]["name"] == "Platform Team"


# --- Error Handling Tests ---


@pytest.mark.asyncio
async def test_pagerduty_api_error_handling(pagerduty_adapter):
    """Test PagerDuty API error handling."""
    with patch.object(httpx.AsyncClient, "get") as mock_get:
        mock_get.side_effect = httpx.HTTPStatusError(
            "Not found",
            request=MagicMock(),
            response=MagicMock(status_code=404),
        )

        roster = await pagerduty_adapter.get_current_oncall(schedule_id="INVALID")

    assert roster is None


@pytest.mark.asyncio
async def test_opsgenie_api_error_handling(opsgenie_adapter):
    """Test Opsgenie API error handling."""
    with patch.object(httpx.AsyncClient, "get") as mock_get:
        mock_get.side_effect = httpx.ConnectTimeout("Connection failed")

        roster = await opsgenie_adapter.get_current_oncall(schedule_id="any")

    assert roster is None


# --- API Configuration Tests ---


def test_pagerduty_api_config(pagerduty_adapter):
    """Test PagerDuty API configuration."""
    assert pagerduty_adapter.api_base == "https://api.pagerduty.com"
    assert "Token token=" in pagerduty_adapter.headers["Authorization"]


def test_opsgenie_api_config_us(opsgenie_adapter):
    """Test Opsgenie US API configuration."""
    assert opsgenie_adapter.api_base == "https://api.opsgenie.com/v2"
    assert "GenieKey" in opsgenie_adapter.headers["Authorization"]


def test_opsgenie_api_config_eu():
    """Test Opsgenie EU API configuration."""
    settings = Settings(opsgenie_api_key="key", opsgenie_region="eu")
    adapter = OnCallAdapter(settings)
    assert adapter.api_base == "https://api.eu.opsgenie.com/v2"


# --- Phone Extraction Tests ---


def test_extract_phone_success(pagerduty_adapter):
    """Test phone extraction from PagerDuty user."""
    user = {
        "contact_methods": [
            {"type": "email_contact_method", "address": "test@example.com"},
            {"type": "phone_contact_method", "address": "+1234567890"},
        ]
    }
    assert pagerduty_adapter._extract_phone(user) == "+1234567890"


def test_extract_phone_no_phone(pagerduty_adapter):
    """Test phone extraction when no phone configured."""
    user = {
        "contact_methods": [
            {"type": "email_contact_method", "address": "test@example.com"},
        ]
    }
    assert pagerduty_adapter._extract_phone(user) is None


def test_extract_phone_empty_contacts(pagerduty_adapter):
    """Test phone extraction with empty contact methods."""
    user = {"contact_methods": []}
    assert pagerduty_adapter._extract_phone(user) is None
