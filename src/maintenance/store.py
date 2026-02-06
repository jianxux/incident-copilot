"""Storage for maintenance windows."""

from __future__ import annotations

from datetime import datetime
from typing import AsyncIterator

import structlog

from .models import (
    EmergencyOverride,
    MaintenanceAuditEntry,
    MaintenanceQuery,
    MaintenanceStatus,
    MaintenanceWindow,
    MaintenanceWindowCreate,
    MaintenanceWindowUpdate,
)

logger = structlog.get_logger()


class MaintenanceStore:
    """In-memory store for maintenance windows.
    
    In production, this would be backed by a database. The interface
    is designed to be easily swapped out for a PostgreSQL or Redis implementation.
    """

    def __init__(self):
        self._windows: dict[str, MaintenanceWindow] = {}
        self._overrides: dict[str, EmergencyOverride] = {}
        self._audit_log: list[MaintenanceAuditEntry] = []
        self._max_audit_entries = 10000

    async def create(
        self,
        request: MaintenanceWindowCreate,
        *,
        created_by: str | None = None,
        tenant_id: str | None = None,
    ) -> MaintenanceWindow:
        """Create a new maintenance window."""
        window = MaintenanceWindow(
            title=request.title,
            description=request.description,
            services=request.services,
            environments=request.environments,
            alert_types=request.alert_types,
            is_global=request.is_global,
            start_time=request.start_time,
            end_time=request.end_time,
            recurring=request.recurring,
            suppression_action=request.suppression_action,
            notifications=request.notifications or MaintenanceWindow.model_fields["notifications"].default_factory(),
            tags=request.tags,
            change_ticket_url=request.change_ticket_url,
            change_ticket_id=request.change_ticket_id,
            metadata=request.metadata,
            created_by=created_by,
            tenant_id=tenant_id,
        )
        
        # Check if it should be active now
        now = datetime.utcnow()
        if window.start_time <= now <= window.end_time:
            window.status = MaintenanceStatus.ACTIVE
        
        self._windows[window.id] = window
        
        # Audit log
        await self._log_audit(
            action="created",
            maintenance_window_id=window.id,
            user_id=created_by,
            tenant_id=tenant_id,
            details={"title": window.title, "start_time": window.start_time.isoformat()},
        )
        
        logger.info(
            "maintenance_window_created",
            window_id=window.id,
            title=window.title,
            services=window.services,
            is_global=window.is_global,
        )
        
        return window

    async def get(self, window_id: str) -> MaintenanceWindow | None:
        """Get a maintenance window by ID."""
        window = self._windows.get(window_id)
        if window:
            # Update status based on current time
            await self._update_window_status(window)
        return window

    async def update(
        self,
        window_id: str,
        updates: MaintenanceWindowUpdate,
        *,
        updated_by: str | None = None,
    ) -> MaintenanceWindow | None:
        """Update an existing maintenance window."""
        window = self._windows.get(window_id)
        if not window:
            return None
        
        update_data = updates.model_dump(exclude_unset=True)
        changed_fields = []
        
        for field, value in update_data.items():
            if value is not None and getattr(window, field) != value:
                setattr(window, field, value)
                changed_fields.append(field)
        
        if changed_fields:
            window.updated_at = datetime.utcnow()
            
            # Re-check status
            await self._update_window_status(window)
            
            # Audit log
            await self._log_audit(
                action="updated",
                maintenance_window_id=window.id,
                user_id=updated_by,
                tenant_id=window.tenant_id,
                details={"changed_fields": changed_fields},
            )
            
            logger.info(
                "maintenance_window_updated",
                window_id=window.id,
                changed_fields=changed_fields,
            )
        
        return window

    async def delete(self, window_id: str, *, deleted_by: str | None = None) -> bool:
        """Delete a maintenance window."""
        window = self._windows.pop(window_id, None)
        if window:
            # Also remove any overrides
            self._overrides = {
                k: v for k, v in self._overrides.items()
                if v.maintenance_window_id != window_id
            }
            
            await self._log_audit(
                action="deleted",
                maintenance_window_id=window_id,
                user_id=deleted_by,
                tenant_id=window.tenant_id,
                details={"title": window.title},
            )
            
            logger.info("maintenance_window_deleted", window_id=window_id)
            return True
        return False

    async def cancel(
        self,
        window_id: str,
        *,
        cancelled_by: str | None = None,
        reason: str | None = None,
    ) -> MaintenanceWindow | None:
        """Cancel a maintenance window."""
        window = self._windows.get(window_id)
        if not window:
            return None
        
        if window.status in (MaintenanceStatus.COMPLETED, MaintenanceStatus.CANCELLED):
            return window  # Already finished
        
        window.status = MaintenanceStatus.CANCELLED
        window.updated_at = datetime.utcnow()
        
        await self._log_audit(
            action="cancelled",
            maintenance_window_id=window_id,
            user_id=cancelled_by,
            tenant_id=window.tenant_id,
            details={"reason": reason},
        )
        
        logger.info(
            "maintenance_window_cancelled",
            window_id=window_id,
            cancelled_by=cancelled_by,
        )
        
        return window

    async def list(self, query: MaintenanceQuery | None = None) -> list[MaintenanceWindow]:
        """List maintenance windows with optional filtering."""
        windows = list(self._windows.values())
        
        # Update status for all windows
        for window in windows:
            await self._update_window_status(window)
        
        if query:
            # Apply filters
            if query.tenant_id:
                windows = [w for w in windows if w.tenant_id == query.tenant_id]
            
            if query.status:
                windows = [w for w in windows if w.status == query.status]
            
            if query.service:
                windows = [w for w in windows if w.affects_service(query.service)]
            
            if query.environment:
                windows = [
                    w for w in windows if w.affects_environment(query.environment)
                ]
            
            if query.start_after:
                windows = [w for w in windows if w.start_time >= query.start_after]
            
            if query.start_before:
                windows = [w for w in windows if w.start_time <= query.start_before]
            
            if query.is_active is not None:
                windows = [w for w in windows if w.is_active == query.is_active]
            
            if query.is_global is not None:
                windows = [w for w in windows if w.is_global == query.is_global]
            
            if query.tags:
                windows = [
                    w for w in windows
                    if any(tag in w.tags for tag in query.tags)
                ]
            
            if not query.include_recurring:
                windows = [w for w in windows if not w.is_recurring]
            
            # Apply pagination
            windows = windows[query.offset:query.offset + query.limit]
        
        # Sort by start time
        windows.sort(key=lambda w: w.start_time)
        
        return windows

    async def get_active_windows(
        self,
        service: str | None = None,
        environment: str | None = None,
        tenant_id: str | None = None,
    ) -> list[MaintenanceWindow]:
        """Get all currently active maintenance windows."""
        query = MaintenanceQuery(
            tenant_id=tenant_id,
            is_active=True,
            service=service,
            environment=environment,
        )
        return await self.list(query)

    async def get_upcoming_windows(
        self,
        within_hours: int = 24,
        tenant_id: str | None = None,
    ) -> list[MaintenanceWindow]:
        """Get maintenance windows starting within the specified hours."""
        now = datetime.utcnow()
        from datetime import timedelta
        
        query = MaintenanceQuery(
            tenant_id=tenant_id,
            status=MaintenanceStatus.SCHEDULED,
            start_after=now,
            start_before=now + timedelta(hours=within_hours),
        )
        return await self.list(query)

    # --- Emergency Overrides ---

    async def create_override(
        self,
        override: EmergencyOverride,
    ) -> EmergencyOverride:
        """Create an emergency override for a maintenance window."""
        # Verify the window exists
        window = await self.get(override.maintenance_window_id)
        if not window:
            raise ValueError(f"Maintenance window {override.maintenance_window_id} not found")
        
        self._overrides[override.id] = override
        
        await self._log_audit(
            action="emergency_override_created",
            maintenance_window_id=override.maintenance_window_id,
            user_id=override.created_by,
            tenant_id=window.tenant_id,
            details={
                "override_id": override.id,
                "reason": override.reason,
                "services": override.services,
            },
        )
        
        logger.warning(
            "emergency_override_created",
            override_id=override.id,
            window_id=override.maintenance_window_id,
            reason=override.reason,
            created_by=override.created_by,
        )
        
        return override

    async def get_override(self, override_id: str) -> EmergencyOverride | None:
        """Get an emergency override by ID."""
        return self._overrides.get(override_id)

    async def get_active_overrides(
        self,
        window_id: str,
    ) -> list[EmergencyOverride]:
        """Get all active overrides for a maintenance window."""
        return [
            o for o in self._overrides.values()
            if o.maintenance_window_id == window_id and o.is_active
        ]

    async def revoke_override(
        self,
        override_id: str,
        *,
        revoked_by: str | None = None,
    ) -> EmergencyOverride | None:
        """Revoke an emergency override."""
        override = self._overrides.get(override_id)
        if not override:
            return None
        
        override.is_active = False
        override.revoked_at = datetime.utcnow()
        override.revoked_by = revoked_by
        
        window = await self.get(override.maintenance_window_id)
        
        await self._log_audit(
            action="emergency_override_revoked",
            maintenance_window_id=override.maintenance_window_id,
            user_id=revoked_by,
            tenant_id=window.tenant_id if window else None,
            details={"override_id": override_id},
        )
        
        logger.info(
            "emergency_override_revoked",
            override_id=override_id,
            revoked_by=revoked_by,
        )
        
        return override

    async def check_override_active(
        self,
        window_id: str,
        service: str | None = None,
    ) -> bool:
        """Check if there's an active override for a window/service."""
        overrides = await self.get_active_overrides(window_id)
        for override in overrides:
            # Check if auto-revoke time has passed
            if override.auto_revoke_minutes:
                from datetime import timedelta
                expiry = override.created_at + timedelta(minutes=override.auto_revoke_minutes)
                if datetime.utcnow() > expiry:
                    await self.revoke_override(override.id, revoked_by="system_auto_revoke")
                    continue
            
            # Check if override applies to this service
            if not override.services or (service and service in override.services):
                return True
        return False

    # --- Audit Log ---

    async def _log_audit(
        self,
        action: str,
        maintenance_window_id: str | None = None,
        alert_id: str | None = None,
        service: str | None = None,
        user_id: str | None = None,
        tenant_id: str | None = None,
        details: dict | None = None,
    ) -> MaintenanceAuditEntry:
        """Create an audit log entry."""
        entry = MaintenanceAuditEntry(
            action=action,
            maintenance_window_id=maintenance_window_id,
            alert_id=alert_id,
            service=service,
            user_id=user_id,
            tenant_id=tenant_id,
            details=details or {},
        )
        
        self._audit_log.append(entry)
        
        # Trim old entries if we exceed max
        if len(self._audit_log) > self._max_audit_entries:
            self._audit_log = self._audit_log[-self._max_audit_entries:]
        
        return entry

    async def log_suppression(
        self,
        window_id: str,
        alert_id: str,
        service: str,
        action: str,
        tenant_id: str | None = None,
    ) -> MaintenanceAuditEntry:
        """Log an alert suppression action."""
        return await self._log_audit(
            action=f"alert_{action}",
            maintenance_window_id=window_id,
            alert_id=alert_id,
            service=service,
            tenant_id=tenant_id,
            details={"suppression_type": action},
        )

    async def get_audit_log(
        self,
        window_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MaintenanceAuditEntry]:
        """Get audit log entries, optionally filtered by window."""
        entries = self._audit_log
        
        if window_id:
            entries = [e for e in entries if e.maintenance_window_id == window_id]
        
        # Sort by timestamp descending
        entries = sorted(entries, key=lambda e: e.timestamp, reverse=True)
        
        return entries[offset:offset + limit]

    # --- Status Management ---

    async def _update_window_status(self, window: MaintenanceWindow) -> None:
        """Update a window's status based on current time."""
        if window.status in (MaintenanceStatus.CANCELLED, MaintenanceStatus.OVERRIDDEN):
            return  # Don't auto-update terminal states
        
        now = datetime.utcnow()
        
        if now < window.start_time:
            if window.status != MaintenanceStatus.SCHEDULED:
                window.status = MaintenanceStatus.SCHEDULED
                window.updated_at = now
        elif now <= window.end_time:
            if window.status != MaintenanceStatus.ACTIVE:
                window.status = MaintenanceStatus.ACTIVE
                window.updated_at = now
                await self._log_audit(
                    action="started",
                    maintenance_window_id=window.id,
                    tenant_id=window.tenant_id,
                )
        else:
            if window.status != MaintenanceStatus.COMPLETED:
                window.status = MaintenanceStatus.COMPLETED
                window.updated_at = now
                await self._log_audit(
                    action="completed",
                    maintenance_window_id=window.id,
                    tenant_id=window.tenant_id,
                )

    async def activate_window(self, window_id: str) -> MaintenanceWindow | None:
        """Manually activate a maintenance window."""
        window = await self.get(window_id)
        if not window:
            return None
        
        window.status = MaintenanceStatus.ACTIVE
        window.updated_at = datetime.utcnow()
        
        await self._log_audit(
            action="manually_activated",
            maintenance_window_id=window_id,
            tenant_id=window.tenant_id,
        )
        
        return window

    async def complete_window(self, window_id: str) -> MaintenanceWindow | None:
        """Manually complete a maintenance window."""
        window = await self.get(window_id)
        if not window:
            return None
        
        window.status = MaintenanceStatus.COMPLETED
        window.updated_at = datetime.utcnow()
        
        await self._log_audit(
            action="manually_completed",
            maintenance_window_id=window_id,
            tenant_id=window.tenant_id,
        )
        
        return window

    # --- Cleanup ---

    async def clear(self) -> None:
        """Clear all data (for testing)."""
        self._windows.clear()
        self._overrides.clear()
        self._audit_log.clear()

    async def cleanup_old_windows(self, older_than_days: int = 30) -> int:
        """Remove completed/cancelled windows older than specified days."""
        from datetime import timedelta
        
        cutoff = datetime.utcnow() - timedelta(days=older_than_days)
        count = 0
        
        to_remove = [
            window_id
            for window_id, window in self._windows.items()
            if window.status in (MaintenanceStatus.COMPLETED, MaintenanceStatus.CANCELLED)
            and window.end_time < cutoff
        ]
        
        for window_id in to_remove:
            del self._windows[window_id]
            count += 1
        
        if count:
            logger.info("maintenance_windows_cleaned_up", count=count)
        
        return count


# Global store instance
maintenance_store = MaintenanceStore()
