"""Status page automation for automatic incident management.

Automatically creates, updates, and resolves status page incidents
based on internal incident severity and state changes.
"""

from datetime import datetime, timedelta
from typing import Any

import structlog
from pydantic import BaseModel, Field

from ..config import get_settings
from .client import StatuspageClient, get_statuspage_client
from .models import (
    ComponentImpact,
    ComponentMapping,
    ComponentStatus,
    IncidentImpact,
    IncidentStatus,
    StatusIncident,
)
from .sync import InternalIncident, StatusPageSync, SyncResult, get_status_sync
from .templates import StatusUpdateTemplates, get_templates

logger = structlog.get_logger()


class AutomationConfig(BaseModel):
    """Configuration for status page automation."""

    enabled: bool = True
    auto_create_for_severities: list[str] = Field(
        default_factory=lambda: ["critical", "high", "p1", "p2"]
    )
    auto_update_enabled: bool = True
    auto_resolve_enabled: bool = True
    notification_delay_seconds: int = Field(
        60, description="Delay before sending notifications"
    )
    require_acknowledgement: bool = Field(
        False, description="Only create status incident after internal ack"
    )
    group_related_incidents: bool = Field(
        True, description="Group related incidents into single status incident"
    )
    grouping_window_minutes: int = Field(
        5, description="Time window for grouping related incidents"
    )


class PendingStatusIncident(BaseModel):
    """A pending status incident waiting to be created."""

    internal_incidents: list[str] = Field(default_factory=list)
    service_name: str
    severity: str
    title: str
    scheduled_for: datetime
    created: bool = False


class StatusPageAutomation:
    """Automation service for status page management."""

    def __init__(
        self,
        client: StatuspageClient | None = None,
        sync: StatusPageSync | None = None,
        templates: StatusUpdateTemplates | None = None,
        config: AutomationConfig | None = None,
    ):
        """Initialize automation.

        Args:
            client: Statuspage client
            sync: Status page sync service
            templates: Status update templates
            config: Automation configuration
        """
        self.client = client or get_statuspage_client()
        self.sync = sync or get_status_sync()
        self.templates = templates or get_templates()
        self.config = config or AutomationConfig()

        # Pending incidents for grouping
        self._pending: dict[str, PendingStatusIncident] = {}

        # Manual override tracking
        self._manual_override: set[str] = set()

    def set_manual_override(self, internal_incident_id: str) -> None:
        """Enable manual override for an incident (disables auto-updates).

        Args:
            internal_incident_id: Internal incident ID
        """
        self._manual_override.add(internal_incident_id)
        logger.info(
            "statuspage_manual_override_enabled",
            incident_id=internal_incident_id,
        )

    def clear_manual_override(self, internal_incident_id: str) -> None:
        """Clear manual override for an incident.

        Args:
            internal_incident_id: Internal incident ID
        """
        self._manual_override.discard(internal_incident_id)
        logger.info(
            "statuspage_manual_override_cleared",
            incident_id=internal_incident_id,
        )

    def has_manual_override(self, internal_incident_id: str) -> bool:
        """Check if an incident has manual override enabled.

        Args:
            internal_incident_id: Internal incident ID

        Returns:
            True if manual override is enabled
        """
        return internal_incident_id in self._manual_override

    def should_auto_create(self, severity: str) -> bool:
        """Check if an incident should auto-create a status incident.

        Args:
            severity: Incident severity

        Returns:
            True if should auto-create
        """
        if not self.config.enabled:
            return False

        severity_lower = severity.lower()
        return severity_lower in [
            s.lower() for s in self.config.auto_create_for_severities
        ]

    def _get_pending_key(self, service_name: str) -> str:
        """Get the key for pending incidents by service."""
        return f"pending:{service_name.lower()}"

    async def on_incident_created(
        self,
        incident_id: str,
        title: str,
        service_name: str,
        severity: str,
        description: str | None = None,
        tags: list[str] | None = None,
        triggered_at: datetime | None = None,
    ) -> SyncResult:
        """Handle creation of a new internal incident.

        Args:
            incident_id: Internal incident ID
            title: Incident title
            service_name: Affected service name
            severity: Incident severity
            description: Incident description
            tags: Incident tags
            triggered_at: When the incident was triggered

        Returns:
            Sync result
        """
        if not self.config.enabled or not self.should_auto_create(severity):
            return SyncResult(
                success=True,
                incident_id=incident_id,
                action="skipped",
                message="Auto-creation not enabled for this severity",
            )

        internal_incident = InternalIncident(
            id=incident_id,
            title=title,
            service_name=service_name,
            severity=severity,
            status="open",
            description=description,
            triggered_at=triggered_at or datetime.utcnow(),
            tags=tags or [],
        )

        # Check for grouping with existing pending incidents
        if self.config.group_related_incidents:
            pending_key = self._get_pending_key(service_name)
            pending = self._pending.get(pending_key)

            if pending and not pending.created:
                # Check if within grouping window
                now = datetime.utcnow()
                if now < pending.scheduled_for:
                    # Add to existing group
                    pending.internal_incidents.append(incident_id)

                    # Update severity if higher
                    severity_order = ["low", "medium", "high", "critical"]
                    p_map = {"p1": "critical", "p2": "high", "p3": "medium", "p4": "low"}
                    current_sev = p_map.get(pending.severity.lower(), pending.severity.lower())
                    new_sev = p_map.get(severity.lower(), severity.lower())

                    try:
                        if severity_order.index(new_sev) > severity_order.index(current_sev):
                            pending.severity = severity
                    except ValueError:
                        pass

                    logger.info(
                        "statuspage_incident_grouped",
                        incident_id=incident_id,
                        group_size=len(pending.internal_incidents),
                    )

                    return SyncResult(
                        success=True,
                        incident_id=incident_id,
                        action="grouped",
                        message=f"Grouped with {len(pending.internal_incidents) - 1} other incidents",
                    )

            # Create new pending group
            self._pending[pending_key] = PendingStatusIncident(
                internal_incidents=[incident_id],
                service_name=service_name,
                severity=severity,
                title=title,
                scheduled_for=datetime.utcnow() + timedelta(
                    seconds=self.config.notification_delay_seconds
                ),
            )

            logger.info(
                "statuspage_incident_pending",
                incident_id=incident_id,
                scheduled_for=self._pending[pending_key].scheduled_for.isoformat(),
            )

            return SyncResult(
                success=True,
                incident_id=incident_id,
                action="pending",
                message=f"Scheduled for creation in {self.config.notification_delay_seconds}s",
            )

        # No grouping - create immediately
        return await self.sync.sync_incident_created(internal_incident)

    async def process_pending_incidents(self) -> list[SyncResult]:
        """Process any pending incidents that are ready.

        This should be called periodically (e.g., every 30 seconds).

        Returns:
            List of sync results for processed incidents
        """
        results = []
        now = datetime.utcnow()

        keys_to_remove = []

        for key, pending in self._pending.items():
            if pending.created:
                continue

            if now >= pending.scheduled_for:
                # Time to create the status incident
                result = await self._create_grouped_incident(pending)
                results.append(result)
                pending.created = True

                if result.success:
                    # Register sync for all grouped incidents
                    for internal_id in pending.internal_incidents:
                        self.sync.register_synced_incident(
                            internal_id, result.status_incident_id
                        )

                keys_to_remove.append(key)

        # Clean up processed pending incidents
        for key in keys_to_remove:
            del self._pending[key]

        return results

    async def _create_grouped_incident(
        self, pending: PendingStatusIncident
    ) -> SyncResult:
        """Create a status incident for a group of internal incidents.

        Args:
            pending: Pending status incident

        Returns:
            Sync result
        """
        incident_count = len(pending.internal_incidents)

        # Adjust title for grouped incidents
        if incident_count > 1:
            title = f"{pending.title} (and {incident_count - 1} related alerts)"
        else:
            title = pending.title

        internal_incident = InternalIncident(
            id=pending.internal_incidents[0],  # Use first incident as primary
            title=title,
            service_name=pending.service_name,
            severity=pending.severity,
            status="open",
            triggered_at=pending.scheduled_for - timedelta(
                seconds=self.config.notification_delay_seconds
            ),
        )

        logger.info(
            "statuspage_creating_grouped_incident",
            incident_count=incident_count,
            service=pending.service_name,
        )

        return await self.sync.sync_incident_created(internal_incident)

    async def on_incident_acknowledged(
        self,
        incident_id: str,
        acknowledged_by: str | None = None,
    ) -> SyncResult:
        """Handle incident acknowledgement.

        Args:
            incident_id: Internal incident ID
            acknowledged_by: Who acknowledged the incident

        Returns:
            Sync result
        """
        # If require_acknowledgement is enabled and we haven't created yet,
        # this is the trigger to create
        if self.config.require_acknowledgement:
            # Check if we have a pending incident that includes this one
            for pending in self._pending.values():
                if incident_id in pending.internal_incidents and not pending.created:
                    # Create immediately upon acknowledgement
                    pending.scheduled_for = datetime.utcnow()

        # Update the status page incident if exists
        status_incident = await self.sync.get_synced_status_incident(incident_id)
        if status_incident and not self.has_manual_override(incident_id):
            # Add an update about acknowledgement
            body = f"Our team has acknowledged this issue and is actively investigating."
            if acknowledged_by:
                body = f"This issue has been acknowledged by our engineering team and is under active investigation."

            internal_incident = InternalIncident(
                id=incident_id,
                title=status_incident.name,
                service_name="",  # Not needed for update
                severity="",
                status="acknowledged",
                triggered_at=status_incident.created_at or datetime.utcnow(),
            )

            return await self.sync.sync_incident_updated(
                internal_incident,
                IncidentStatus.IDENTIFIED,
                custom_body=body,
            )

        return SyncResult(
            success=True,
            incident_id=incident_id,
            action="skipped",
            message="No status incident to update",
        )

    async def on_incident_updated(
        self,
        incident_id: str,
        title: str,
        service_name: str,
        severity: str,
        status: str,
        update_message: str | None = None,
    ) -> SyncResult:
        """Handle internal incident update.

        Args:
            incident_id: Internal incident ID
            title: Current incident title
            service_name: Affected service name
            severity: Current severity
            status: Current internal status
            update_message: Optional update message

        Returns:
            Sync result
        """
        if not self.config.auto_update_enabled:
            return SyncResult(
                success=True,
                incident_id=incident_id,
                action="skipped",
                message="Auto-update disabled",
            )

        if self.has_manual_override(incident_id):
            return SyncResult(
                success=True,
                incident_id=incident_id,
                action="skipped",
                message="Manual override enabled",
            )

        status_incident = await self.sync.get_synced_status_incident(incident_id)
        if not status_incident:
            return SyncResult(
                success=True,
                incident_id=incident_id,
                action="skipped",
                message="No synced status incident",
            )

        # Map internal status to status page status
        status_map = {
            "open": IncidentStatus.INVESTIGATING,
            "investigating": IncidentStatus.INVESTIGATING,
            "acknowledged": IncidentStatus.IDENTIFIED,
            "identified": IncidentStatus.IDENTIFIED,
            "mitigating": IncidentStatus.MONITORING,
            "monitoring": IncidentStatus.MONITORING,
            "resolved": IncidentStatus.RESOLVED,
            "closed": IncidentStatus.RESOLVED,
        }

        new_status = status_map.get(status.lower())
        if not new_status:
            return SyncResult(
                success=True,
                incident_id=incident_id,
                action="skipped",
                message=f"Unknown status: {status}",
            )

        # Only update if status is different
        if new_status == status_incident.status:
            return SyncResult(
                success=True,
                incident_id=incident_id,
                action="skipped",
                message="Status unchanged",
            )

        internal_incident = InternalIncident(
            id=incident_id,
            title=title,
            service_name=service_name,
            severity=severity,
            status=status,
            triggered_at=status_incident.created_at or datetime.utcnow(),
        )

        return await self.sync.sync_incident_updated(
            internal_incident,
            new_status,
            custom_body=update_message,
        )

    async def on_incident_resolved(
        self,
        incident_id: str,
        title: str,
        service_name: str,
        severity: str,
        resolution_message: str | None = None,
        resolved_at: datetime | None = None,
        triggered_at: datetime | None = None,
    ) -> SyncResult:
        """Handle internal incident resolution.

        Args:
            incident_id: Internal incident ID
            title: Incident title
            service_name: Affected service name
            severity: Incident severity
            resolution_message: Custom resolution message
            resolved_at: When the incident was resolved
            triggered_at: When the incident was triggered

        Returns:
            Sync result
        """
        # Always clear manual override on resolution - incident is done
        had_override = self.has_manual_override(incident_id)
        self.clear_manual_override(incident_id)

        if not self.config.auto_resolve_enabled:
            return SyncResult(
                success=True,
                incident_id=incident_id,
                action="skipped",
                message="Auto-resolve disabled",
            )

        if had_override:
            return SyncResult(
                success=True,
                incident_id=incident_id,
                action="skipped",
                message="Manual override was enabled - resolve manually",
            )

        # Check if we have a pending incident that hasn't been created yet
        for key, pending in list(self._pending.items()):
            if incident_id in pending.internal_incidents:
                pending.internal_incidents.remove(incident_id)
                if not pending.internal_incidents:
                    del self._pending[key]
                return SyncResult(
                    success=True,
                    incident_id=incident_id,
                    action="cancelled",
                    message="Pending incident cancelled before creation",
                )

        internal_incident = InternalIncident(
            id=incident_id,
            title=title,
            service_name=service_name,
            severity=severity,
            status="resolved",
            triggered_at=triggered_at or datetime.utcnow(),
            resolved_at=resolved_at or datetime.utcnow(),
        )

        result = await self.sync.sync_incident_resolved(
            internal_incident,
            resolution_message=resolution_message,
        )

        return result

    async def force_create_status_incident(
        self,
        incident_id: str,
        title: str,
        service_name: str,
        severity: str,
        body: str,
        page_id: str | None = None,
    ) -> SyncResult:
        """Force creation of a status incident (bypasses automation rules).

        Args:
            incident_id: Internal incident ID
            title: Incident title
            service_name: Affected service name
            severity: Incident severity
            body: Initial update body
            page_id: Target page ID

        Returns:
            Sync result
        """
        internal_incident = InternalIncident(
            id=incident_id,
            title=title,
            service_name=service_name,
            severity=severity,
            status="open",
            triggered_at=datetime.utcnow(),
        )

        return await self.sync.sync_incident_created(
            internal_incident,
            custom_body=body,
            page_id=page_id,
        )

    async def post_custom_update(
        self,
        incident_id: str,
        status: IncidentStatus,
        body: str,
        page_id: str | None = None,
    ) -> SyncResult:
        """Post a custom update to a status incident.

        Args:
            incident_id: Internal incident ID
            status: New status
            body: Update body
            page_id: Target page ID

        Returns:
            Sync result
        """
        status_incident_id = self.sync._synced_incidents.get(incident_id)
        if not status_incident_id:
            return SyncResult(
                success=False,
                incident_id=incident_id,
                action="error",
                error="No synced status incident found",
            )

        try:
            updated = await self.client.update_incident(
                incident_id=status_incident_id,
                status=status,
                body=body,
                page_id=page_id,
            )

            return SyncResult(
                success=True,
                incident_id=incident_id,
                status_incident_id=status_incident_id,
                action="updated",
                message=f"Posted custom update with status {status.value}",
            )

        except Exception as e:
            return SyncResult(
                success=False,
                incident_id=incident_id,
                status_incident_id=status_incident_id,
                action="error",
                error=str(e),
            )


# Module-level automation instance
_status_automation: StatusPageAutomation | None = None


def get_status_automation() -> StatusPageAutomation:
    """Get the status automation singleton."""
    global _status_automation
    if _status_automation is None:
        _status_automation = StatusPageAutomation()
    return _status_automation


# Convenience functions for common operations


async def auto_create_status_incident(
    incident_id: str,
    title: str,
    service_name: str,
    severity: str,
    description: str | None = None,
    tags: list[str] | None = None,
) -> SyncResult:
    """Automatically create a status incident for an internal incident.

    Args:
        incident_id: Internal incident ID
        title: Incident title
        service_name: Affected service name
        severity: Incident severity
        description: Incident description
        tags: Incident tags

    Returns:
        Sync result
    """
    automation = get_status_automation()
    return await automation.on_incident_created(
        incident_id=incident_id,
        title=title,
        service_name=service_name,
        severity=severity,
        description=description,
        tags=tags,
    )


async def auto_update_status_incident(
    incident_id: str,
    title: str,
    service_name: str,
    severity: str,
    status: str,
    update_message: str | None = None,
) -> SyncResult:
    """Automatically update a status incident based on internal incident state.

    Args:
        incident_id: Internal incident ID
        title: Current incident title
        service_name: Affected service name
        severity: Current severity
        status: Current internal status
        update_message: Optional update message

    Returns:
        Sync result
    """
    automation = get_status_automation()
    return await automation.on_incident_updated(
        incident_id=incident_id,
        title=title,
        service_name=service_name,
        severity=severity,
        status=status,
        update_message=update_message,
    )
