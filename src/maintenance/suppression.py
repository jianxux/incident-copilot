"""Alert suppression during maintenance windows."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from .checker import MaintenanceCheckResult, MaintenanceChecker, maintenance_checker
from .models import SuppressionAction
from .store import MaintenanceStore, maintenance_store

logger = structlog.get_logger()


class SuppressionResult:
    """Result of processing an alert through suppression logic."""

    def __init__(
        self,
        alert_id: str,
        service: str,
        action_taken: SuppressionAction,
        suppressed: bool = False,
        annotated: bool = False,
        logged: bool = False,
        delivered: bool = True,
        maintenance_windows: list[str] | None = None,
        annotations: dict[str, Any] | None = None,
        reason: str | None = None,
    ):
        self.alert_id = alert_id
        self.service = service
        self.action_taken = action_taken
        self.suppressed = suppressed
        self.annotated = annotated
        self.logged = logged
        self.delivered = delivered
        self.maintenance_windows = maintenance_windows or []
        self.annotations = annotations or {}
        self.reason = reason

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "alert_id": self.alert_id,
            "service": self.service,
            "action_taken": self.action_taken.value,
            "suppressed": self.suppressed,
            "annotated": self.annotated,
            "logged": self.logged,
            "delivered": self.delivered,
            "maintenance_windows": self.maintenance_windows,
            "annotations": self.annotations,
            "reason": self.reason,
        }


class AlertSuppressor:
    """Handles alert suppression and annotation during maintenance windows."""

    def __init__(
        self,
        store: MaintenanceStore | None = None,
        checker: MaintenanceChecker | None = None,
    ):
        self.store = store or maintenance_store
        self.checker = checker or maintenance_checker

    async def process_alert(
        self,
        alert_id: str,
        service: str,
        alert_type: str | None = None,
        environment: str | None = None,
        tenant_id: str | None = None,
        alert_data: dict[str, Any] | None = None,
    ) -> SuppressionResult:
        """Process an incoming alert through maintenance suppression logic.
        
        Args:
            alert_id: Unique identifier for the alert
            service: Service name the alert is for
            alert_type: Type of alert (e.g., "high_latency", "error_rate")
            environment: Environment (e.g., "prod", "staging")
            tenant_id: Tenant ID for multi-tenant deployments
            alert_data: Original alert payload for annotation
            
        Returns:
            SuppressionResult indicating what action was taken
        """
        # Check maintenance status
        check_result = await self.checker.check_alert(
            alert_id=alert_id,
            service=service,
            alert_type=alert_type,
            environment=environment,
            tenant_id=tenant_id,
        )
        
        if not check_result.in_maintenance:
            # Not in maintenance, deliver normally
            return SuppressionResult(
                alert_id=alert_id,
                service=service,
                action_taken=SuppressionAction.NONE,
                delivered=True,
                reason="No active maintenance window",
            )
        
        # Check for emergency override
        if check_result.has_override:
            logger.info(
                "alert_delivered_due_to_override",
                alert_id=alert_id,
                service=service,
                override_reason=check_result.override_reason,
            )
            return SuppressionResult(
                alert_id=alert_id,
                service=service,
                action_taken=SuppressionAction.NONE,
                delivered=True,
                maintenance_windows=[w.id for w in check_result.windows],
                reason=f"Emergency override: {check_result.override_reason}",
            )
        
        # Process based on suppression action
        window_ids = [w.id for w in check_result.windows]
        
        if check_result.should_suppress:
            result = await self._suppress_alert(
                alert_id, service, window_ids, tenant_id
            )
        elif check_result.should_log_only:
            result = await self._log_only_alert(
                alert_id, service, window_ids, tenant_id, alert_data
            )
        elif check_result.should_annotate:
            result = await self._annotate_alert(
                alert_id, service, window_ids, check_result.windows, alert_data
            )
        else:
            # No suppression action, deliver normally
            result = SuppressionResult(
                alert_id=alert_id,
                service=service,
                action_taken=SuppressionAction.NONE,
                delivered=True,
                maintenance_windows=window_ids,
                reason="Maintenance window has no suppression action",
            )
        
        return result

    async def _suppress_alert(
        self,
        alert_id: str,
        service: str,
        window_ids: list[str],
        tenant_id: str | None,
    ) -> SuppressionResult:
        """Completely suppress an alert."""
        # Log the suppression
        for window_id in window_ids:
            await self.store.log_suppression(
                window_id=window_id,
                alert_id=alert_id,
                service=service,
                action="suppressed",
                tenant_id=tenant_id,
            )
        
        logger.info(
            "alert_suppressed",
            alert_id=alert_id,
            service=service,
            maintenance_windows=window_ids,
        )
        
        return SuppressionResult(
            alert_id=alert_id,
            service=service,
            action_taken=SuppressionAction.SUPPRESS,
            suppressed=True,
            delivered=False,
            maintenance_windows=window_ids,
            reason="Alert suppressed due to active maintenance window",
        )

    async def _log_only_alert(
        self,
        alert_id: str,
        service: str,
        window_ids: list[str],
        tenant_id: str | None,
        alert_data: dict[str, Any] | None,
    ) -> SuppressionResult:
        """Log alert but don't send notifications."""
        # Log the alert
        for window_id in window_ids:
            await self.store.log_suppression(
                window_id=window_id,
                alert_id=alert_id,
                service=service,
                action="logged_only",
                tenant_id=tenant_id,
            )
        
        logger.info(
            "alert_logged_only",
            alert_id=alert_id,
            service=service,
            maintenance_windows=window_ids,
            alert_data=alert_data,
        )
        
        return SuppressionResult(
            alert_id=alert_id,
            service=service,
            action_taken=SuppressionAction.LOG_ONLY,
            logged=True,
            delivered=False,
            maintenance_windows=window_ids,
            reason="Alert logged but notifications suppressed during maintenance",
        )

    async def _annotate_alert(
        self,
        alert_id: str,
        service: str,
        window_ids: list[str],
        windows: list,
        alert_data: dict[str, Any] | None,
    ) -> SuppressionResult:
        """Annotate alert with maintenance information and deliver."""
        # Build annotations
        annotations = {
            "maintenance": True,
            "maintenance_windows": window_ids,
            "maintenance_titles": [w.title for w in windows],
            "maintenance_end_times": [w.end_time.isoformat() for w in windows],
        }
        
        # Calculate when maintenance ends
        if windows:
            latest_end = max(w.end_time for w in windows)
            annotations["maintenance_ends_at"] = latest_end.isoformat()
            
            # Human-readable time until maintenance ends
            delta = latest_end - datetime.utcnow()
            if delta.total_seconds() > 0:
                hours, remainder = divmod(int(delta.total_seconds()), 3600)
                minutes = remainder // 60
                if hours > 0:
                    annotations["maintenance_ends_in"] = f"{hours}h {minutes}m"
                else:
                    annotations["maintenance_ends_in"] = f"{minutes}m"
        
        # Log the annotation
        for window_id in window_ids:
            await self.store.log_suppression(
                window_id=window_id,
                alert_id=alert_id,
                service=service,
                action="annotated",
                tenant_id=windows[0].tenant_id if windows else None,
            )
        
        logger.info(
            "alert_annotated",
            alert_id=alert_id,
            service=service,
            maintenance_windows=window_ids,
        )
        
        return SuppressionResult(
            alert_id=alert_id,
            service=service,
            action_taken=SuppressionAction.ANNOTATE,
            annotated=True,
            delivered=True,
            maintenance_windows=window_ids,
            annotations=annotations,
            reason="Alert delivered with maintenance annotations",
        )

    async def get_suppression_stats(
        self,
        window_id: str | None = None,
        service: str | None = None,
        tenant_id: str | None = None,
        since_hours: int = 24,
    ) -> dict[str, Any]:
        """Get suppression statistics.
        
        Args:
            window_id: Filter by maintenance window
            service: Filter by service
            tenant_id: Filter by tenant
            since_hours: Look back period in hours
            
        Returns:
            Dictionary with suppression statistics
        """
        # Get audit log entries
        entries = await self.store.get_audit_log(
            window_id=window_id,
            limit=1000,
        )
        
        # Filter by time
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(hours=since_hours)
        entries = [e for e in entries if e.timestamp >= cutoff]
        
        # Filter by service if specified
        if service:
            entries = [e for e in entries if e.service == service]
        
        # Filter by tenant if specified
        if tenant_id:
            entries = [e for e in entries if e.tenant_id == tenant_id]
        
        # Calculate stats
        stats = {
            "total_alerts": 0,
            "suppressed": 0,
            "annotated": 0,
            "logged_only": 0,
            "by_service": {},
            "by_window": {},
        }
        
        for entry in entries:
            if entry.action.startswith("alert_"):
                stats["total_alerts"] += 1
                
                action = entry.action.replace("alert_", "")
                if action == "suppressed":
                    stats["suppressed"] += 1
                elif action == "annotated":
                    stats["annotated"] += 1
                elif action == "logged_only":
                    stats["logged_only"] += 1
                
                # By service
                if entry.service:
                    if entry.service not in stats["by_service"]:
                        stats["by_service"][entry.service] = 0
                    stats["by_service"][entry.service] += 1
                
                # By window
                if entry.maintenance_window_id:
                    if entry.maintenance_window_id not in stats["by_window"]:
                        stats["by_window"][entry.maintenance_window_id] = 0
                    stats["by_window"][entry.maintenance_window_id] += 1
        
        return stats

    async def get_suppressed_alerts(
        self,
        window_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get list of alerts suppressed by a maintenance window.
        
        Args:
            window_id: Maintenance window ID
            limit: Maximum number of alerts to return
            
        Returns:
            List of suppressed alert details
        """
        entries = await self.store.get_audit_log(
            window_id=window_id,
            limit=limit,
        )
        
        # Filter for alert-related entries
        alerts = []
        for entry in entries:
            if entry.action.startswith("alert_"):
                alerts.append({
                    "alert_id": entry.alert_id,
                    "service": entry.service,
                    "action": entry.action.replace("alert_", ""),
                    "timestamp": entry.timestamp.isoformat(),
                    "details": entry.details,
                })
        
        return alerts

    async def should_deliver_alert(
        self,
        service: str,
        alert_type: str | None = None,
        environment: str | None = None,
        tenant_id: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """Quick check if an alert should be delivered.
        
        This is a convenience method for simple yes/no decisions.
        
        Args:
            service: Service name
            alert_type: Optional alert type
            environment: Optional environment
            tenant_id: Optional tenant ID
            
        Returns:
            Tuple of (should_deliver, context_dict)
        """
        check_result = await self.checker.check_alert(
            alert_id="check",  # Dummy ID for quick check
            service=service,
            alert_type=alert_type,
            environment=environment,
            tenant_id=tenant_id,
        )
        
        context = check_result.to_dict()
        
        if not check_result.in_maintenance:
            return True, context
        
        if check_result.has_override:
            return True, context
        
        # Only suppress if action is SUPPRESS
        should_deliver = check_result.suppression_action != SuppressionAction.SUPPRESS
        
        return should_deliver, context


# Global suppressor instance
alert_suppressor = AlertSuppressor()
