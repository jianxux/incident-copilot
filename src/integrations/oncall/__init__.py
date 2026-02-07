"""On-Call Scheduling Integration for Incident Copilot.

Provides schedule sync from PagerDuty and Opsgenie, who-is-on-call lookups,
schedule overrides, rotation visualization, and handoff notifications.

Usage:
    from integrations.oncall import OnCallService, router

    # Initialize service with provider API keys
    service = OnCallService(
        pagerduty_key="your-pd-key",
        opsgenie_key="your-og-key"
    )

    # Who is on-call?
    user = await service.who_is_oncall("schedule_id")

    # Create an override
    override = await service.create_override(
        schedule_id="schedule_id",
        override_user=user,
        start_time=datetime.now(),
        end_time=datetime.now() + timedelta(hours=4),
        reason="Doctor appointment"
    )

    # Mount FastAPI routes
    app.include_router(router)
"""

from .models import (
    HandoffNotification,
    OnCallHistoryEntry,
    OnCallOverride,
    OnCallSchedule,
    OnCallShift,
    OnCallUser,
    OverrideStatus,
    ProviderType,
    Rotation,
    RotationType,
    ScheduleSyncResult,
)
from .providers import OpsgenieProvider, PagerDutyProvider
from .routes import init_service, router
from .service import OnCallService

__all__ = [
    # Models
    "OnCallSchedule",
    "OnCallShift",
    "OnCallUser",
    "OnCallOverride",
    "Rotation",
    "RotationType",
    "ProviderType",
    "OverrideStatus",
    "HandoffNotification",
    "OnCallHistoryEntry",
    "ScheduleSyncResult",
    # Service
    "OnCallService",
    # Routes
    "router",
    "init_service",
    # Providers
    "PagerDutyProvider",
    "OpsgenieProvider",
]
