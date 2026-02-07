"""SLA Tracking Module for Incident Copilot.

Provides SLA policy management, timer tracking, breach detection,
and compliance reporting.

Features:
- P1/P2/P3/P4 severity-based SLA targets
- Response and resolution time tracking
- Business hours support (pause SLA outside work hours)
- Automatic breach detection with escalation
- SLA compliance metrics and reporting

Quick Start:
    from src.sla import (
        SLAService,
        SLAStore,
        SLAPolicy,
        SLASeverity,
        SLAType,
        router as sla_router,
    )

    # Create store and service
    store = SLAStore(redis_client=redis, db_pool=db)
    service = SLAService(store)

    # Start timer for an incident
    policy = await store.get_policy("default-policy")
    await service.start_timer(
        incident_id="INC-123",
        policy=policy,
        severity=SLASeverity.P1,
        sla_type=SLAType.RESPONSE,
    )

    # Check status
    status = await service.get_incident_status("INC-123", policy)
    print(f"Response SLA: {status.response_timer.percent_elapsed}% elapsed")

    # Include API routes in your FastAPI app
    app.include_router(sla_router)
"""

# Models
from .models import (
    BusinessHours,
    DEFAULT_SLA_TARGETS,
    EscalationLevel,
    SLABreach,
    SLAIncidentStatus,
    SLAMetrics,
    SLANotification,
    SLAPolicy,
    SLASeverity,
    SLAStatus,
    SLATarget,
    SLATimer,
    SLAType,
)

# Service
from .service import SLAService, create_sla_notification

# Store
from .store import SCHEMA_SQL, SLAStore

# Routes
from .routes import router

# Scheduler
from .scheduler import (
    SLAScheduler,
    SLASchedulerManager,
    create_sla_scheduler,
    email_notification_sender,
    multi_channel_sender,
    slack_notification_sender,
)

__all__ = [
    # Models
    "BusinessHours",
    "DEFAULT_SLA_TARGETS",
    "EscalationLevel",
    "SLABreach",
    "SLAIncidentStatus",
    "SLAMetrics",
    "SLANotification",
    "SLAPolicy",
    "SLASeverity",
    "SLAStatus",
    "SLATarget",
    "SLATimer",
    "SLAType",
    # Service
    "SLAService",
    "create_sla_notification",
    # Store
    "SLAStore",
    "SCHEMA_SQL",
    # Routes
    "router",
    # Scheduler
    "SLAScheduler",
    "SLASchedulerManager",
    "create_sla_scheduler",
    "email_notification_sender",
    "slack_notification_sender",
    "multi_channel_sender",
]

__version__ = "1.0.0"
