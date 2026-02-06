"""Maintenance Windows module for Incident Copilot.

This module provides functionality for managing scheduled maintenance windows,
suppressing alerts during maintenance periods, and providing calendar integration
for dashboard visibility.

Key components:
- MaintenanceWindow: One-time or recurring maintenance windows
- MaintenanceStore: CRUD operations for maintenance windows
- MaintenanceChecker: Check if services/alerts are in maintenance
- AlertSuppressor: Suppress or annotate alerts during maintenance
"""

from .models import (
    MaintenanceWindow,
    MaintenanceWindowCreate,
    MaintenanceWindowUpdate,
    MaintenanceStatus,
    RecurrencePattern,
    RecurringSchedule,
    SuppressionAction,
    MaintenanceAuditEntry,
    MaintenanceNotification,
    NotificationType,
    EmergencyOverride,
)
from .store import MaintenanceStore, maintenance_store
from .checker import MaintenanceChecker, maintenance_checker
from .suppression import AlertSuppressor, SuppressionResult, alert_suppressor

__all__ = [
    # Models
    "MaintenanceWindow",
    "MaintenanceWindowCreate",
    "MaintenanceWindowUpdate",
    "MaintenanceStatus",
    "RecurrencePattern",
    "RecurringSchedule",
    "SuppressionAction",
    "MaintenanceAuditEntry",
    "MaintenanceNotification",
    "NotificationType",
    "EmergencyOverride",
    # Store
    "MaintenanceStore",
    "maintenance_store",
    # Checker
    "MaintenanceChecker",
    "maintenance_checker",
    # Suppression
    "AlertSuppressor",
    "SuppressionResult",
    "alert_suppressor",
]
