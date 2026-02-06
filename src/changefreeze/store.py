"""In-memory store for Change Freeze data."""

import asyncio
from datetime import datetime

from .models import (
    ApprovalStatus,
    ChangeFreeze,
    DeploymentEvent,
    FreezeException,
    FreezeStatus,
    FreezeViolation,
)


class ChangeFreezeStore:
    """
    Thread-safe in-memory store for change freeze data.

    Designed to be replaced with a database backend later.
    """

    def __init__(self, max_items: int = 10000):
        self._freezes: dict[str, ChangeFreeze] = {}
        self._exceptions: dict[str, FreezeException] = {}
        self._deployments: dict[str, DeploymentEvent] = {}
        self._violations: dict[str, FreezeViolation] = {}
        self._max_items = max_items
        self._lock = asyncio.Lock()

    # --- Freeze Operations ---

    async def save_freeze(self, freeze: ChangeFreeze) -> ChangeFreeze:
        """Save or update a change freeze."""
        async with self._lock:
            freeze.updated_at = datetime.utcnow()
            self._freezes[freeze.freeze_id] = freeze
            self._trim_dict(self._freezes)
            return freeze

    async def get_freeze(self, freeze_id: str) -> ChangeFreeze | None:
        """Get a freeze by ID."""
        return self._freezes.get(freeze_id)

    async def delete_freeze(self, freeze_id: str) -> bool:
        """Delete a freeze by ID."""
        async with self._lock:
            if freeze_id in self._freezes:
                del self._freezes[freeze_id]
                return True
            return False

    async def get_active_freezes(
        self,
        at_time: datetime | None = None,
        service_name: str | None = None,
        environment: str | None = None,
    ) -> list[ChangeFreeze]:
        """Get all currently active freezes, optionally filtered."""
        check_time = at_time or datetime.utcnow()
        results = []
        
        for freeze in self._freezes.values():
            if not freeze.is_active(check_time):
                continue
            if service_name and not freeze.affects_service(service_name):
                continue
            if environment and not freeze.affects_environment(environment):
                continue
            results.append(freeze)
        
        results.sort(key=lambda x: x.starts_at, reverse=True)
        return results

    async def get_all_freezes(
        self,
        status: FreezeStatus | None = None,
        include_completed: bool = False,
        limit: int = 100,
    ) -> list[ChangeFreeze]:
        """Get all freezes with optional filtering."""
        results = []
        
        for freeze in self._freezes.values():
            if status and freeze.status != status:
                continue
            if not include_completed and freeze.status == FreezeStatus.COMPLETED:
                continue
            results.append(freeze)
        
        results.sort(key=lambda x: x.starts_at, reverse=True)
        return results[:limit]

    async def update_freeze_status(
        self, freeze_id: str, status: FreezeStatus
    ) -> ChangeFreeze | None:
        """Update the status of a freeze."""
        async with self._lock:
            if freeze_id in self._freezes:
                freeze = self._freezes[freeze_id]
                freeze.status = status
                freeze.updated_at = datetime.utcnow()
                return freeze
            return None

    async def cancel_freeze(
        self,
        freeze_id: str,
        cancelled_by: str,
        reason: str | None = None,
    ) -> ChangeFreeze | None:
        """Cancel a freeze."""
        async with self._lock:
            if freeze_id in self._freezes:
                freeze = self._freezes[freeze_id]
                freeze.status = FreezeStatus.CANCELLED
                freeze.cancelled_at = datetime.utcnow()
                freeze.cancelled_by = cancelled_by
                freeze.cancellation_reason = reason
                freeze.updated_at = datetime.utcnow()
                return freeze
            return None

    # --- Exception Operations ---

    async def save_exception(self, exception: FreezeException) -> FreezeException:
        """Save or update a freeze exception."""
        async with self._lock:
            self._exceptions[exception.exception_id] = exception
            self._trim_dict(self._exceptions)
            
            # Update freeze statistics
            if exception.freeze_id in self._freezes:
                freeze = self._freezes[exception.freeze_id]
                freeze.total_exceptions_requested = len([
                    e for e in self._exceptions.values()
                    if e.freeze_id == exception.freeze_id
                ])
                freeze.total_exceptions_approved = len([
                    e for e in self._exceptions.values()
                    if e.freeze_id == exception.freeze_id
                    and e.status == ApprovalStatus.APPROVED
                ])
            
            return exception

    async def get_exception(self, exception_id: str) -> FreezeException | None:
        """Get an exception by ID."""
        return self._exceptions.get(exception_id)

    async def get_exceptions_for_freeze(
        self,
        freeze_id: str,
        status: ApprovalStatus | None = None,
    ) -> list[FreezeException]:
        """Get all exceptions for a specific freeze."""
        results = []
        
        for exception in self._exceptions.values():
            if exception.freeze_id != freeze_id:
                continue
            if status and exception.status != status:
                continue
            results.append(exception)
        
        results.sort(key=lambda x: x.requested_at, reverse=True)
        return results

    async def get_valid_exceptions(
        self,
        freeze_id: str,
        service_name: str,
        environment: str = "production",
        at_time: datetime | None = None,
    ) -> list[FreezeException]:
        """Get valid exceptions for a specific service deployment."""
        check_time = at_time or datetime.utcnow()
        results = []
        
        for exception in self._exceptions.values():
            if exception.freeze_id != freeze_id:
                continue
            if exception.service_name != service_name:
                continue
            if exception.environment.lower() != environment.lower():
                continue
            if not exception.is_valid(check_time):
                continue
            results.append(exception)
        
        return results

    async def get_pending_exceptions(
        self, approver: str | None = None
    ) -> list[FreezeException]:
        """Get all pending exception requests."""
        results = []
        
        for exception in self._exceptions.values():
            if exception.status != ApprovalStatus.PENDING:
                continue
            results.append(exception)
        
        results.sort(key=lambda x: x.requested_at)
        return results

    async def approve_exception(
        self,
        exception_id: str,
        reviewed_by: str,
        notes: str | None = None,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> FreezeException | None:
        """Approve an exception request."""
        async with self._lock:
            if exception_id in self._exceptions:
                exception = self._exceptions[exception_id]
                exception.status = ApprovalStatus.APPROVED
                exception.reviewed_by = reviewed_by
                exception.reviewed_at = datetime.utcnow()
                exception.review_notes = notes
                if valid_from:
                    exception.valid_from = valid_from
                if valid_until:
                    exception.valid_until = valid_until
                
                # Update freeze statistics
                if exception.freeze_id in self._freezes:
                    freeze = self._freezes[exception.freeze_id]
                    freeze.total_exceptions_approved += 1
                
                return exception
            return None

    async def reject_exception(
        self,
        exception_id: str,
        reviewed_by: str,
        notes: str | None = None,
    ) -> FreezeException | None:
        """Reject an exception request."""
        async with self._lock:
            if exception_id in self._exceptions:
                exception = self._exceptions[exception_id]
                exception.status = ApprovalStatus.REJECTED
                exception.reviewed_by = reviewed_by
                exception.reviewed_at = datetime.utcnow()
                exception.review_notes = notes
                return exception
            return None

    # --- Deployment Event Operations ---

    async def save_deployment(self, event: DeploymentEvent) -> DeploymentEvent:
        """Save a deployment event."""
        async with self._lock:
            self._deployments[event.event_id] = event
            self._trim_dict(self._deployments)
            return event

    async def get_deployment(self, event_id: str) -> DeploymentEvent | None:
        """Get a deployment event by ID."""
        return self._deployments.get(event_id)

    async def get_deployments_during_freeze(
        self,
        freeze_id: str,
        limit: int = 100,
    ) -> list[DeploymentEvent]:
        """Get all deployments that occurred during a specific freeze."""
        results = []
        
        for event in self._deployments.values():
            if event.freeze_id == freeze_id:
                results.append(event)
        
        results.sort(key=lambda x: x.deployed_at, reverse=True)
        return results[:limit]

    async def get_recent_deployments(
        self,
        service_name: str | None = None,
        environment: str | None = None,
        limit: int = 50,
    ) -> list[DeploymentEvent]:
        """Get recent deployment events."""
        results = []
        
        for event in self._deployments.values():
            if service_name and event.service_name != service_name:
                continue
            if environment and event.environment.lower() != environment.lower():
                continue
            results.append(event)
        
        results.sort(key=lambda x: x.deployed_at, reverse=True)
        return results[:limit]

    # --- Violation Operations ---

    async def save_violation(self, violation: FreezeViolation) -> FreezeViolation:
        """Save a freeze violation."""
        async with self._lock:
            self._violations[violation.violation_id] = violation
            self._trim_dict(self._violations)
            
            # Update freeze statistics
            if violation.freeze_id in self._freezes:
                freeze = self._freezes[violation.freeze_id]
                freeze.total_violations = len([
                    v for v in self._violations.values()
                    if v.freeze_id == violation.freeze_id
                ])
            
            return violation

    async def get_violation(self, violation_id: str) -> FreezeViolation | None:
        """Get a violation by ID."""
        return self._violations.get(violation_id)

    async def get_violations_for_freeze(
        self,
        freeze_id: str,
        acknowledged: bool | None = None,
        limit: int = 100,
    ) -> list[FreezeViolation]:
        """Get all violations for a specific freeze."""
        results = []
        
        for violation in self._violations.values():
            if violation.freeze_id != freeze_id:
                continue
            if acknowledged is not None and violation.acknowledged != acknowledged:
                continue
            results.append(violation)
        
        results.sort(key=lambda x: x.detected_at, reverse=True)
        return results[:limit]

    async def get_all_violations(
        self,
        acknowledged: bool | None = None,
        service_name: str | None = None,
        limit: int = 100,
    ) -> list[FreezeViolation]:
        """Get all violations with optional filtering."""
        results = []
        
        for violation in self._violations.values():
            if acknowledged is not None and violation.acknowledged != acknowledged:
                continue
            if service_name and violation.service_name != service_name:
                continue
            results.append(violation)
        
        results.sort(key=lambda x: x.detected_at, reverse=True)
        return results[:limit]

    async def acknowledge_violation(
        self,
        violation_id: str,
        acknowledged_by: str,
        reason: str | None = None,
    ) -> FreezeViolation | None:
        """Acknowledge a violation."""
        async with self._lock:
            if violation_id in self._violations:
                violation = self._violations[violation_id]
                violation.acknowledged = True
                violation.acknowledged_by = acknowledged_by
                violation.acknowledged_at = datetime.utcnow()
                violation.acknowledgement_reason = reason
                return violation
            return None

    async def mark_violation_alerted(
        self,
        violation_id: str,
        channels: list[str],
    ) -> FreezeViolation | None:
        """Mark that alert was sent for a violation."""
        async with self._lock:
            if violation_id in self._violations:
                violation = self._violations[violation_id]
                violation.alert_sent = True
                violation.alert_sent_at = datetime.utcnow()
                violation.alert_channels = channels
                return violation
            return None

    # --- Status Check ---

    async def check_freeze_status(
        self,
        service_name: str,
        environment: str = "production",
        at_time: datetime | None = None,
    ) -> tuple[bool, list[ChangeFreeze], list[FreezeException]]:
        """
        Check if a service can deploy.
        
        Returns:
            Tuple of (is_frozen, active_freezes, valid_exceptions)
        """
        active_freezes = await self.get_active_freezes(
            at_time=at_time,
            service_name=service_name,
            environment=environment,
        )
        
        valid_exceptions = []
        for freeze in active_freezes:
            exceptions = await self.get_valid_exceptions(
                freeze_id=freeze.freeze_id,
                service_name=service_name,
                environment=environment,
                at_time=at_time,
            )
            valid_exceptions.extend(exceptions)
        
        return (len(active_freezes) > 0, active_freezes, valid_exceptions)

    # --- Utility Methods ---

    def _trim_dict(self, d: dict) -> None:
        """Trim dictionary to max size by removing oldest items."""
        if len(d) > self._max_items:
            items_to_remove = len(d) - self._max_items
            keys_to_remove = list(d.keys())[:items_to_remove]
            for key in keys_to_remove:
                del d[key]

    async def clear(self) -> None:
        """Clear all stored data (for testing)."""
        async with self._lock:
            self._freezes.clear()
            self._exceptions.clear()
            self._deployments.clear()
            self._violations.clear()

    async def get_stats(self) -> dict:
        """Get storage statistics."""
        unacknowledged_violations = len([
            v for v in self._violations.values() if not v.acknowledged
        ])
        pending_exceptions = len([
            e for e in self._exceptions.values()
            if e.status == ApprovalStatus.PENDING
        ])
        active_freezes = len([
            f for f in self._freezes.values() if f.is_active()
        ])
        
        return {
            "total_freezes": len(self._freezes),
            "active_freezes": active_freezes,
            "total_exceptions": len(self._exceptions),
            "pending_exceptions": pending_exceptions,
            "total_deployments": len(self._deployments),
            "total_violations": len(self._violations),
            "unacknowledged_violations": unacknowledged_violations,
        }


# Global change freeze store instance
changefreeze_store = ChangeFreezeStore()
