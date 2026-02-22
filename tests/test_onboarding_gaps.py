import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from src.auth.models import UserRole
from src.auth.service import auth_service
from src.onboarding.analytics import OnboardingAnalytics
from src.onboarding.checklist import CHECKLIST_STEPS, OPTIONAL_STEPS
from src.onboarding.db_store import ChecklistStore, migrate_onboarding_checklist
from src.onboarding.email_verification import EmailVerificationService
from src.onboarding.invites import InviteService, InviteStatus


@pytest.mark.asyncio
async def test_checklist_db_defaults(tmp_path):
    db_path = tmp_path / "onboarding.db"
    store = ChecklistStore(db_path=db_path)

    checklist = await store.get("tenant-1")

    assert checklist.tenant_id == "tenant-1"
    assert all(not checklist.completed[step] for step in CHECKLIST_STEPS)
    assert checklist.progress == 0.0


@pytest.mark.asyncio
async def test_checklist_db_set_step_updates(tmp_path):
    db_path = tmp_path / "onboarding.db"
    store = ChecklistStore(db_path=db_path)

    checklist = await store.set_step("tenant-1", "connect_slack", True)

    assert checklist.completed["connect_slack"] is True
    required = [s for s in CHECKLIST_STEPS if s not in OPTIONAL_STEPS]
    assert checklist.progress == pytest.approx(1 / len(required))


@pytest.mark.asyncio
async def test_checklist_db_persistence(tmp_path):
    db_path = tmp_path / "onboarding.db"
    store = ChecklistStore(db_path=db_path)
    await store.set_step("tenant-1", "add_services", True)

    store2 = ChecklistStore(db_path=db_path)
    checklist = await store2.get("tenant-1")

    assert checklist.completed["add_services"] is True


@pytest.mark.asyncio
async def test_checklist_db_unknown_step_raises(tmp_path):
    db_path = tmp_path / "onboarding.db"
    store = ChecklistStore(db_path=db_path)

    with pytest.raises(ValueError):
        await store.set_step("tenant-1", "unknown-step", True)


@pytest.mark.asyncio
async def test_checklist_db_migration_helper(tmp_path):
    db_path = tmp_path / "onboarding.db"

    await migrate_onboarding_checklist(db_path=db_path)

    store = ChecklistStore(db_path=db_path)
    checklist = await store.get("tenant-1")
    assert checklist.tenant_id == "tenant-1"


@pytest.mark.asyncio
async def test_invite_send_and_verify():
    service = InviteService()
    tenant = await auth_service.create_tenant(
        name="Invite Tenant",
        slug=f"invite-{asyncio.get_running_loop().time()}".replace(".", "-"),
    )
    token = await service.send_invite(
        email="invitee@example.com",
        tenant_id=tenant.id,
        role=UserRole.MEMBER,
        invited_by="user-1",
    )

    record = await service.verify_invite(token)

    assert record.email == "invitee@example.com"
    assert record.status == InviteStatus.PENDING


@pytest.mark.asyncio
async def test_invite_expiry_marks_expired():
    service = InviteService()
    tenant = await auth_service.create_tenant(
        name="Expiry Tenant",
        slug=f"expiry-{asyncio.get_running_loop().time()}".replace(".", "-"),
    )
    token = await service.send_invite(
        email="expired@example.com",
        tenant_id=tenant.id,
        role=UserRole.MEMBER,
        invited_by="user-2",
    )

    service._invites_by_token[token].expires_at = datetime.now(UTC) - timedelta(
        seconds=5
    )
    record = await service.verify_invite(token)

    assert record.status == InviteStatus.EXPIRED


@pytest.mark.asyncio
async def test_invite_accept_creates_user():
    service = InviteService()
    tenant = await auth_service.create_tenant(
        name="Accept Tenant",
        slug=f"accept-{asyncio.get_running_loop().time()}".replace(".", "-"),
    )
    token = await service.send_invite(
        email="accept@example.com",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
        invited_by="user-3",
    )

    user = await service.accept_invite(
        token,
        {"name": "Invited User", "password": "pass123"},
    )

    assert user.email == "accept@example.com"
    assert user.role == UserRole.ADMIN


@pytest.mark.asyncio
async def test_invite_accept_rejects_expired():
    service = InviteService()
    tenant = await auth_service.create_tenant(
        name="Reject Tenant",
        slug=f"reject-{asyncio.get_running_loop().time()}".replace(".", "-"),
    )
    token = await service.send_invite(
        email="reject@example.com",
        tenant_id=tenant.id,
        role=UserRole.MEMBER,
        invited_by="user-4",
    )

    service._invites_by_token[token].expires_at = datetime.now(UTC) - timedelta(
        seconds=5
    )

    with pytest.raises(ValueError):
        await service.accept_invite(token, {"name": "Late User"})


@pytest.mark.asyncio
async def test_invite_list_pending():
    service = InviteService()
    tenant = await auth_service.create_tenant(
        name="Pending Tenant",
        slug=f"pending-{asyncio.get_running_loop().time()}".replace(".", "-"),
    )
    await service.send_invite(
        email="pending@example.com",
        tenant_id=tenant.id,
        role=UserRole.MEMBER,
        invited_by="user-5",
    )

    pending = await service.list_pending(tenant.id)

    assert len(pending) == 1
    assert pending[0].email == "pending@example.com"


@pytest.mark.asyncio
async def test_email_verification_send_and_confirm():
    service = EmailVerificationService()
    tenant = await auth_service.create_tenant(
        name="Verify Tenant",
        slug=f"verify-{asyncio.get_running_loop().time()}".replace(".", "-"),
    )
    user = await auth_service.create_user(
        email="verify@example.com",
        name="Verify User",
        tenant_id=tenant.id,
    )

    token = await service.send_verification_email(user.id, user.email)
    verified = await service.verify_email(token)

    assert verified is True
    assert user.email_verified is True


@pytest.mark.asyncio
async def test_email_verification_expired():
    service = EmailVerificationService()
    tenant = await auth_service.create_tenant(
        name="Expired Tenant",
        slug=f"verify-exp-{asyncio.get_running_loop().time()}".replace(".", "-"),
    )
    user = await auth_service.create_user(
        email="verify-exp@example.com",
        name="Expired User",
        tenant_id=tenant.id,
    )

    token = await service.send_verification_email(user.id, user.email)
    service._tokens[token].expires_at = datetime.now(UTC) - timedelta(seconds=5)

    verified = await service.verify_email(token)

    assert verified is False
    assert user.email_verified is False


@pytest.mark.asyncio
async def test_email_verification_invalid_token():
    service = EmailVerificationService()

    verified = await service.verify_email("missing-token")

    assert verified is False


def test_analytics_track_event():
    analytics = OnboardingAnalytics()

    event = analytics.track_event("tenant-1", "step_started", "create_account", {})

    assert event.tenant_id == "tenant-1"
    assert event.event_type == "step_started"


def test_analytics_funnel_report():
    analytics = OnboardingAnalytics()

    analytics.track_event("tenant-1", "step_started", "create_account", {})
    analytics.track_event("tenant-1", "step_completed", "create_account", {})
    analytics.track_event("tenant-2", "step_started", "create_account", {})

    report = analytics.get_funnel((None, None))

    first_step = report.steps[0]
    assert first_step.step == "create_account"
    assert first_step.started == 2
    assert first_step.completed == 1


def test_analytics_time_to_first_context_card():
    analytics = OnboardingAnalytics()

    start = datetime.now(UTC)
    event_start = analytics.track_event(
        "tenant-1", "step_started", "create_account", {}
    )
    event_start.occurred_at = start
    event_context = analytics.track_event("tenant-1", "context_card_created", None, {})
    event_context.occurred_at = start + timedelta(minutes=5)

    duration = analytics.get_time_to_first_context_card("tenant-1")

    assert duration is not None
    assert duration.total_seconds() == 300


def test_analytics_drop_off_report():
    analytics = OnboardingAnalytics()

    analytics.track_event("tenant-1", "step_completed", "create_account", {})
    analytics.track_event("tenant-2", "step_completed", "create_account", {})
    analytics.track_event("tenant-2", "step_completed", "connect_alerting", {})

    report = analytics.get_drop_off_report((None, None))

    steps = {item.step: item.count for item in report}
    assert steps.get("connect_alerting") == 1
    assert steps.get("connect_slack") == 1


def test_analytics_average_time_to_value():
    analytics = OnboardingAnalytics()

    start = datetime.now(UTC)
    event1_start = analytics.track_event(
        "tenant-1", "step_started", "create_account", {}
    )
    event1_start.occurred_at = start
    event1_context = analytics.track_event("tenant-1", "context_card_created", None, {})
    event1_context.occurred_at = start + timedelta(seconds=30)

    event2_start = analytics.track_event(
        "tenant-2", "step_started", "create_account", {}
    )
    event2_start.occurred_at = start
    event2_context = analytics.track_event("tenant-2", "context_card_created", None, {})
    event2_context.occurred_at = start + timedelta(seconds=90)

    average = analytics.get_average_time_to_value()

    assert average is not None
    assert average.total_seconds() == 60
