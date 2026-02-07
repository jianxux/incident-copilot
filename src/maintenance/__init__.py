"""
Maintenance Windows Module - Scheduled maintenance with alert suppression.

Features:
- One-time and recurring windows (RRULE)
- Scope: service, team, infrastructure, global
- Alert suppression during maintenance
- Automatic incident annotation
- Approval workflow
- Stakeholder notifications
- iCal calendar export
- Overlap detection
- Extended maintenance handling
"""

from .models import (
    ScopeType,
    MaintenanceStatus,
    NotificationType,
    MaintenanceScope,
    MaintenanceSchedule,
    MaintenanceWindow,
    ApprovalRecord,
    MaintenanceWindowCreate,
    MaintenanceWindowUpdate,
    ExtendMaintenanceRequest,
    MaintenanceNotification,
    OverlapWarning,
)
from .service import MaintenanceService, get_maintenance_service
from .scheduler import MaintenanceScheduler, RecurrenceInstance
from .routes import router

__all__ = [
    "ScopeType",
    "MaintenanceStatus",
    "NotificationType",
    "MaintenanceScope",
    "MaintenanceSchedule",
    "MaintenanceWindow",
    "ApprovalRecord",
    "MaintenanceWindowCreate",
    "MaintenanceWindowUpdate",
    "ExtendMaintenanceRequest",
    "MaintenanceNotification",
    "OverlapWarning",
    "MaintenanceService",
    "get_maintenance_service",
    "MaintenanceScheduler",
    "RecurrenceInstance",
    "router",
]
