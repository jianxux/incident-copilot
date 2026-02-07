"""Maintenance Windows - Service Layer"""
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
import logging
from .models import (
    MaintenanceWindow, MaintenanceWindowCreate, MaintenanceWindowUpdate,
    MaintenanceStatus, MaintenanceScope, ScopeType, ApprovalRecord,
    ExtendMaintenanceRequest, MaintenanceNotification, NotificationType, OverlapWarning
)

logger = logging.getLogger(__name__)


class MaintenanceService:
    """Service for managing maintenance windows."""
    
    def __init__(self):
        self._windows: dict[UUID, MaintenanceWindow] = {}
        self._notification_handlers: list[callable] = []
    
    def register_notification_handler(self, handler: callable) -> None:
        self._notification_handlers.append(handler)
    
    async def _notify(self, window: MaintenanceWindow, ntype: NotificationType, message: str) -> None:
        notification = MaintenanceNotification(
            window_id=window.id, notification_type=ntype,
            recipients=window.stakeholders, message=message, scheduled_for=datetime.utcnow()
        )
        notification.sent_at = datetime.utcnow()
        for handler in self._notification_handlers:
            try:
                await handler(notification)
            except Exception as e:
                logger.error(f"Notification failed: {e}")
    
    async def create_window(self, request: MaintenanceWindowCreate, created_by: str) -> MaintenanceWindow:
        window = MaintenanceWindow(
            title=request.title, description=request.description, scope=request.scope,
            schedule=request.schedule, created_by=created_by, requires_approval=request.requires_approval,
            required_approvers=request.required_approvers, stakeholders=request.stakeholders,
            notification_minutes_before=request.notification_minutes_before,
            status=MaintenanceStatus.PENDING_APPROVAL if request.requires_approval else MaintenanceStatus.SCHEDULED
        )
        self._windows[window.id] = window
        if window.stakeholders:
            await self._notify(window, NotificationType.SCHEDULED, 
                f"Maintenance scheduled: {window.title} ({window.schedule.start_time} - {window.schedule.end_time})")
        return window
    
    async def get_window(self, window_id: UUID) -> Optional[MaintenanceWindow]:
        return self._windows.get(window_id)
    
    async def update_window(self, window_id: UUID, request: MaintenanceWindowUpdate) -> Optional[MaintenanceWindow]:
        window = self._windows.get(window_id)
        if not window:
            return None
        if window.status in (MaintenanceStatus.IN_PROGRESS, MaintenanceStatus.COMPLETED):
            raise ValueError("Cannot update active/completed windows")
        for field, value in request.model_dump(exclude_unset=True).items():
            setattr(window, field, value)
        window.updated_at = datetime.utcnow()
        return window
    
    async def delete_window(self, window_id: UUID) -> bool:
        window = self._windows.get(window_id)
        if not window:
            return False
        if window.status == MaintenanceStatus.IN_PROGRESS:
            raise ValueError("Cannot delete active window")
        del self._windows[window_id]
        return True
    
    async def list_windows(self, status: Optional[MaintenanceStatus] = None, scope_type: Optional[ScopeType] = None,
                           from_time: Optional[datetime] = None, to_time: Optional[datetime] = None, limit: int = 50) -> list[MaintenanceWindow]:
        windows = list(self._windows.values())
        if status:
            windows = [w for w in windows if w.status == status]
        if scope_type:
            windows = [w for w in windows if w.scope.scope_type == scope_type]
        if from_time:
            windows = [w for w in windows if w.schedule.end_time >= from_time]
        if to_time:
            windows = [w for w in windows if w.schedule.start_time <= to_time]
        return sorted(windows, key=lambda w: w.schedule.start_time)[:limit]
    
    async def is_in_maintenance(self, scope_type: ScopeType, identifier: str, at_time: Optional[datetime] = None) -> tuple[bool, Optional[MaintenanceWindow]]:
        now = at_time or datetime.utcnow()
        for window in self._windows.values():
            if window.is_active(now) and window.scope.matches(scope_type, identifier):
                return True, window
        return False, None
    
    async def get_active_windows(self, at_time: Optional[datetime] = None) -> list[MaintenanceWindow]:
        now = at_time or datetime.utcnow()
        return [w for w in self._windows.values() if w.is_active(now)]
    
    async def get_upcoming_windows(self, hours: int = 24) -> list[MaintenanceWindow]:
        now, future = datetime.utcnow(), datetime.utcnow() + timedelta(hours=hours)
        return sorted([w for w in self._windows.values() 
            if w.status in (MaintenanceStatus.SCHEDULED,) and now <= w.schedule.start_time <= future],
            key=lambda w: w.schedule.start_time)
    
    async def should_suppress_alert(self, scope_type: ScopeType, identifier: str, at_time: Optional[datetime] = None) -> tuple[bool, Optional[str]]:
        in_maint, window = await self.is_in_maintenance(scope_type, identifier, at_time)
        if in_maint and window and window.scope.suppress_alerts:
            return True, f"Suppressed: {window.title}"
        return False, None
    
    async def suppress_alerts(self, alerts: list[dict], at_time: Optional[datetime] = None) -> list[dict]:
        for alert in alerts:
            suppress, reason = await self.should_suppress_alert(ScopeType(alert.get("scope_type", "service")), alert.get("identifier", ""), at_time)
            alert["suppressed"], alert["suppression_reason"] = suppress, reason
        return alerts
    
    async def annotate_incident(self, incident_id: str, scope_type: ScopeType, identifier: str) -> Optional[str]:
        in_maint, window = await self.is_in_maintenance(scope_type, identifier)
        if in_maint and window:
            annotation = f"[MAINTENANCE] During: {window.title}"
            window.related_incident_ids.append(incident_id)
            window.annotations.append(f"Incident {incident_id} at {datetime.utcnow().isoformat()}")
            return annotation
        return None
    
    async def approve(self, window_id: UUID, approver_id: str, comment: Optional[str] = None) -> MaintenanceWindow:
        window = self._windows.get(window_id)
        if not window or window.status != MaintenanceStatus.PENDING_APPROVAL:
            raise ValueError("Window not found or wrong status")
        window.approvals.append(ApprovalRecord(approver_id=approver_id, approved=True, comment=comment))
        if window.is_approved():
            window.status = MaintenanceStatus.SCHEDULED if window.schedule.start_time > datetime.utcnow() else MaintenanceStatus.IN_PROGRESS
        window.updated_at = datetime.utcnow()
        return window
    
    async def reject(self, window_id: UUID, approver_id: str, reason: str) -> MaintenanceWindow:
        window = self._windows.get(window_id)
        if not window:
            raise ValueError("Window not found")
        window.approvals.append(ApprovalRecord(approver_id=approver_id, approved=False, comment=reason))
        window.status = MaintenanceStatus.CANCELLED
        window.updated_at = datetime.utcnow()
        await self._notify(window, NotificationType.CANCELLED, f"Rejected: {reason}")
        return window
    
    async def start_maintenance(self, window_id: UUID) -> MaintenanceWindow:
        window = self._windows.get(window_id)
        if not window or window.status not in (MaintenanceStatus.SCHEDULED,):
            raise ValueError("Cannot start")
        window.status = MaintenanceStatus.IN_PROGRESS
        window.updated_at = datetime.utcnow()
        await self._notify(window, NotificationType.STARTED, f"Started: {window.title}")
        return window
    
    async def complete_maintenance(self, window_id: UUID) -> MaintenanceWindow:
        window = self._windows.get(window_id)
        if not window:
            raise ValueError("Window not found")
        window.status = MaintenanceStatus.COMPLETED
        window.updated_at = datetime.utcnow()
        await self._notify(window, NotificationType.COMPLETED, f"Completed: {window.title}")
        return window
    
    async def cancel_maintenance(self, window_id: UUID, reason: str) -> MaintenanceWindow:
        window = self._windows.get(window_id)
        if not window:
            raise ValueError("Window not found")
        window.status = MaintenanceStatus.CANCELLED
        window.annotations.append(f"Cancelled: {reason}")
        window.updated_at = datetime.utcnow()
        await self._notify(window, NotificationType.CANCELLED, f"Cancelled: {window.title} - {reason}")
        return window
    
    async def extend_maintenance(self, window_id: UUID, request: ExtendMaintenanceRequest) -> MaintenanceWindow:
        window = self._windows.get(window_id)
        if not window or window.status != MaintenanceStatus.IN_PROGRESS:
            raise ValueError("Can only extend active windows")
        if window.extension_count >= 3:
            raise ValueError("Max extensions reached")
        if not window.original_end_time:
            window.original_end_time = window.schedule.end_time
        window.schedule.end_time += timedelta(minutes=request.extend_minutes)
        window.extension_count += 1
        window.extension_reason = request.reason
        window.status = MaintenanceStatus.EXTENDED
        window.updated_at = datetime.utcnow()
        await self._notify(window, NotificationType.EXTENDED, f"Extended {request.extend_minutes}min: {request.reason}")
        return window
    
    async def detect_overlaps(self, window: MaintenanceWindow) -> list[OverlapWarning]:
        overlaps = []
        for other in self._windows.values():
            if other.id == window.id or other.status in (MaintenanceStatus.CANCELLED, MaintenanceStatus.COMPLETED):
                continue
            if not (window.schedule.start_time < other.schedule.end_time and window.schedule.end_time > other.schedule.start_time):
                continue
            shared = self._shared_scope(window.scope, other.scope)
            if shared:
                overlaps.append(OverlapWarning(
                    window_id=window.id, overlapping_window_id=other.id,
                    overlap_start=max(window.schedule.start_time, other.schedule.start_time),
                    overlap_end=min(window.schedule.end_time, other.schedule.end_time), shared_scope=shared))
        return overlaps
    
    def _shared_scope(self, s1: MaintenanceScope, s2: MaintenanceScope) -> list[str]:
        if s1.scope_type == ScopeType.GLOBAL or s2.scope_type == ScopeType.GLOBAL:
            return ["GLOBAL"]
        if s1.scope_type != s2.scope_type:
            return []
        i1, i2 = set(s1.identifiers) or {"*"}, set(s2.identifiers) or {"*"}
        return list(i1 & i2) if "*" not in i1 and "*" not in i2 else ["ALL"]
    
    async def process_scheduled_windows(self) -> list[MaintenanceWindow]:
        now, processed = datetime.utcnow(), []
        for window in self._windows.values():
            if window.status == MaintenanceStatus.SCHEDULED and window.schedule.start_time <= now and window.is_approved():
                await self.start_maintenance(window.id)
                processed.append(window)
            elif window.status in (MaintenanceStatus.IN_PROGRESS, MaintenanceStatus.EXTENDED) and window.schedule.end_time <= now:
                await self.complete_maintenance(window.id)
                processed.append(window)
        return processed


_service: Optional[MaintenanceService] = None

def get_maintenance_service() -> MaintenanceService:
    global _service
    if _service is None:
        _service = MaintenanceService()
    return _service
