"""Maintenance window checker for alerts and services."""

from datetime import datetime, timedelta
from typing import Any

import structlog

from .models import (
    MaintenanceStatus,
    MaintenanceWindow,
    RecurrencePattern,
    SuppressionAction,
)
from .store import MaintenanceStore, maintenance_store

logger = structlog.get_logger()


class MaintenanceCheckResult:
    """Result of checking if something is in maintenance."""

    def __init__(
        self,
        in_maintenance: bool,
        windows: list[MaintenanceWindow] | None = None,
        suppression_action: SuppressionAction = SuppressionAction.NONE,
        has_override: bool = False,
        override_reason: str | None = None,
    ):
        self.in_maintenance = in_maintenance
        self.windows = windows or []
        self.suppression_action = suppression_action
        self.has_override = has_override
        self.override_reason = override_reason

    @property
    def should_suppress(self) -> bool:
        """Check if alerts should be suppressed."""
        if self.has_override:
            return False
        return (
            self.in_maintenance
            and self.suppression_action == SuppressionAction.SUPPRESS
        )

    @property
    def should_annotate(self) -> bool:
        """Check if alerts should be annotated."""
        if self.has_override:
            return False
        return (
            self.in_maintenance
            and self.suppression_action == SuppressionAction.ANNOTATE
        )

    @property
    def should_log_only(self) -> bool:
        """Check if alerts should be logged only."""
        if self.has_override:
            return False
        return (
            self.in_maintenance
            and self.suppression_action == SuppressionAction.LOG_ONLY
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "in_maintenance": self.in_maintenance,
            "window_count": len(self.windows),
            "window_ids": [w.id for w in self.windows],
            "suppression_action": self.suppression_action.value,
            "has_override": self.has_override,
            "override_reason": self.override_reason,
        }


class MaintenanceChecker:
    """Check if services or alerts are within maintenance windows."""

    def __init__(self, store: MaintenanceStore | None = None):
        self.store = store or maintenance_store

    async def check_service(
        self,
        service: str,
        environment: str | None = None,
        tenant_id: str | None = None,
        at_time: datetime | None = None,
    ) -> MaintenanceCheckResult:
        """Check if a service is currently in maintenance.
        
        Args:
            service: The service name to check
            environment: Optional environment filter (prod, staging, etc.)
            tenant_id: Optional tenant ID for multi-tenant deployments
            at_time: Optional time to check (defaults to now)
            
        Returns:
            MaintenanceCheckResult with maintenance status and details
        """
        check_time = at_time or datetime.utcnow()
        
        # Get all active windows
        active_windows = await self.store.get_active_windows(
            service=service,
            environment=environment,
            tenant_id=tenant_id,
        )
        
        # Also check recurring windows
        matching_windows = []
        
        for window in active_windows:
            # Verify the window is actually active at the check time
            if not self._is_window_active_at(window, check_time):
                continue
            
            # Check if service matches
            if not window.affects_service(service):
                continue
            
            # Check if environment matches
            if environment and not window.affects_environment(environment):
                continue
            
            # Check for emergency override
            has_override = await self.store.check_override_active(
                window.id, service=service
            )
            
            if has_override:
                logger.info(
                    "maintenance_check_override_active",
                    service=service,
                    window_id=window.id,
                )
                return MaintenanceCheckResult(
                    in_maintenance=True,
                    windows=[window],
                    suppression_action=SuppressionAction.NONE,
                    has_override=True,
                    override_reason="Emergency override active",
                )
            
            matching_windows.append(window)
        
        if not matching_windows:
            return MaintenanceCheckResult(in_maintenance=False)
        
        # Determine the most restrictive suppression action
        # Priority: SUPPRESS > LOG_ONLY > ANNOTATE > NONE
        action_priority = {
            SuppressionAction.SUPPRESS: 4,
            SuppressionAction.LOG_ONLY: 3,
            SuppressionAction.ANNOTATE: 2,
            SuppressionAction.NONE: 1,
        }
        
        best_action = max(
            [w.suppression_action for w in matching_windows],
            key=lambda a: action_priority[a],
        )
        
        logger.debug(
            "maintenance_check_result",
            service=service,
            in_maintenance=True,
            window_count=len(matching_windows),
            suppression_action=best_action.value,
        )
        
        return MaintenanceCheckResult(
            in_maintenance=True,
            windows=matching_windows,
            suppression_action=best_action,
        )

    async def check_alert(
        self,
        alert_id: str,
        service: str,
        alert_type: str | None = None,
        environment: str | None = None,
        tenant_id: str | None = None,
        at_time: datetime | None = None,
    ) -> MaintenanceCheckResult:
        """Check if an alert should be suppressed due to maintenance.
        
        Args:
            alert_id: The alert ID
            service: The service the alert is for
            alert_type: Optional alert type (e.g., "high_latency", "error_rate")
            environment: Optional environment
            tenant_id: Optional tenant ID
            at_time: Optional time to check
            
        Returns:
            MaintenanceCheckResult with suppression details
        """
        check_time = at_time or datetime.utcnow()
        
        # First check service-level maintenance
        result = await self.check_service(
            service=service,
            environment=environment,
            tenant_id=tenant_id,
            at_time=check_time,
        )
        
        if not result.in_maintenance:
            return result
        
        # If there's an override, alerts should pass through
        if result.has_override:
            return result
        
        # Filter windows by alert type if specified
        if alert_type:
            filtered_windows = []
            for window in result.windows:
                # Empty alert_types means all alerts
                if not window.alert_types:
                    filtered_windows.append(window)
                elif alert_type.lower() in [at.lower() for at in window.alert_types]:
                    filtered_windows.append(window)
            
            if not filtered_windows:
                return MaintenanceCheckResult(in_maintenance=False)
            
            result.windows = filtered_windows
        
        return result

    async def check_global_maintenance(
        self,
        tenant_id: str | None = None,
        at_time: datetime | None = None,
    ) -> MaintenanceCheckResult:
        """Check if there's a global maintenance window active.
        
        Args:
            tenant_id: Optional tenant ID
            at_time: Optional time to check
            
        Returns:
            MaintenanceCheckResult for global maintenance
        """
        check_time = at_time or datetime.utcnow()
        
        # Get all active windows
        from .models import MaintenanceQuery
        
        query = MaintenanceQuery(
            tenant_id=tenant_id,
            is_global=True,
            is_active=True,
        )
        
        windows = await self.store.list(query)
        
        # Filter for actually active at check time
        active_windows = [
            w for w in windows
            if self._is_window_active_at(w, check_time)
        ]
        
        if not active_windows:
            return MaintenanceCheckResult(in_maintenance=False)
        
        # Check for overrides
        for window in active_windows:
            has_override = await self.store.check_override_active(window.id)
            if has_override:
                return MaintenanceCheckResult(
                    in_maintenance=True,
                    windows=[window],
                    suppression_action=SuppressionAction.NONE,
                    has_override=True,
                    override_reason="Emergency override active for global maintenance",
                )
        
        # Get the most restrictive action
        action_priority = {
            SuppressionAction.SUPPRESS: 4,
            SuppressionAction.LOG_ONLY: 3,
            SuppressionAction.ANNOTATE: 2,
            SuppressionAction.NONE: 1,
        }
        
        best_action = max(
            [w.suppression_action for w in active_windows],
            key=lambda a: action_priority[a],
        )
        
        return MaintenanceCheckResult(
            in_maintenance=True,
            windows=active_windows,
            suppression_action=best_action,
        )

    async def get_maintenance_info(
        self,
        service: str,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Get detailed maintenance information for a service.
        
        Returns current status, upcoming windows, and recent history.
        """
        now = datetime.utcnow()
        
        # Current maintenance
        current = await self.check_service(
            service=service,
            tenant_id=tenant_id,
        )
        
        # Upcoming maintenance
        upcoming = await self.store.get_upcoming_windows(
            within_hours=72,
            tenant_id=tenant_id,
        )
        upcoming = [w for w in upcoming if w.affects_service(service)]
        
        # Recent completed
        from .models import MaintenanceQuery
        
        recent_query = MaintenanceQuery(
            tenant_id=tenant_id,
            service=service,
            status=MaintenanceStatus.COMPLETED,
            limit=5,
        )
        recent = await self.store.list(recent_query)
        
        return {
            "service": service,
            "is_in_maintenance": current.in_maintenance,
            "current_windows": [
                {
                    "id": w.id,
                    "title": w.title,
                    "end_time": w.end_time.isoformat(),
                    "suppression_action": w.suppression_action.value,
                }
                for w in current.windows
            ],
            "has_override": current.has_override,
            "upcoming_windows": [
                {
                    "id": w.id,
                    "title": w.title,
                    "start_time": w.start_time.isoformat(),
                    "end_time": w.end_time.isoformat(),
                }
                for w in upcoming[:5]
            ],
            "recent_maintenance": [
                {
                    "id": w.id,
                    "title": w.title,
                    "end_time": w.end_time.isoformat(),
                }
                for w in recent
            ],
        }

    def _is_window_active_at(
        self,
        window: MaintenanceWindow,
        check_time: datetime,
    ) -> bool:
        """Check if a window is active at a specific time."""
        if window.status in (
            MaintenanceStatus.CANCELLED,
            MaintenanceStatus.OVERRIDDEN,
        ):
            return False
        
        # For one-time windows, simple range check
        if not window.is_recurring:
            return window.start_time <= check_time <= window.end_time
        
        # For recurring windows, calculate the current occurrence
        return self._check_recurring_window(window, check_time)

    def _check_recurring_window(
        self,
        window: MaintenanceWindow,
        check_time: datetime,
    ) -> bool:
        """Check if a recurring window is active at the given time."""
        if not window.recurring:
            return False
        
        schedule = window.recurring
        
        # Check if past recurrence end date
        if schedule.recurrence_end_date and check_time > schedule.recurrence_end_date:
            return False
        
        # Check if in excluded dates
        for excluded in schedule.excluded_dates:
            if check_time.date() == excluded.date():
                return False
        
        # Parse start time
        try:
            hour, minute = map(int, schedule.start_time.split(":"))
        except (ValueError, IndexError):
            hour, minute = 0, 0
        
        duration = timedelta(minutes=schedule.duration_minutes)
        
        # Check based on pattern
        if schedule.pattern == RecurrencePattern.DAILY:
            # Check if current time is within the daily window
            window_start = check_time.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            window_end = window_start + duration
            return window_start <= check_time <= window_end
        
        elif schedule.pattern == RecurrencePattern.WEEKLY:
            # Check if today is one of the scheduled days
            if check_time.weekday() not in schedule.days_of_week:
                return False
            window_start = check_time.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            window_end = window_start + duration
            return window_start <= check_time <= window_end
        
        elif schedule.pattern == RecurrencePattern.MONTHLY:
            # Check if today is the scheduled day of month
            day = schedule.day_of_month or 1
            if day == -1:
                # Last day of month
                import calendar
                day = calendar.monthrange(check_time.year, check_time.month)[1]
            if check_time.day != day:
                return False
            window_start = check_time.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            window_end = window_start + duration
            return window_start <= check_time <= window_end
        
        elif schedule.pattern == RecurrencePattern.BIWEEKLY:
            # Check if this is a valid biweekly occurrence
            # Use the original start_time as reference
            weeks_since_start = (check_time - window.start_time).days // 7
            if weeks_since_start % 2 != 0:
                return False
            if check_time.weekday() not in schedule.days_of_week:
                return False
            window_start = check_time.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            window_end = window_start + duration
            return window_start <= check_time <= window_end
        
        # For other patterns (quarterly, yearly, custom), 
        # fall back to checking against the original window times
        return window.start_time <= check_time <= window.end_time

    async def get_next_maintenance(
        self,
        service: str,
        tenant_id: str | None = None,
    ) -> MaintenanceWindow | None:
        """Get the next scheduled maintenance for a service."""
        upcoming = await self.store.get_upcoming_windows(
            within_hours=720,  # 30 days
            tenant_id=tenant_id,
        )
        
        for window in upcoming:
            if window.affects_service(service):
                return window
        
        return None


# Global checker instance
maintenance_checker = MaintenanceChecker()
