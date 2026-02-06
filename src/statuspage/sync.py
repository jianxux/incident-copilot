"""Status page synchronization service.

Syncs internal incidents to public status pages, managing the lifecycle
of status page incidents based on internal incident state changes.
"""

from datetime import datetime
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
from .templates import StatusUpdateTemplates, get_templates

logger = structlog.get_logger()


class SyncResult(BaseModel):
    """Result of a sync operation."""

    success: bool
    incident_id: str | None = None
    status_incident_id: str | None = None
    action: str | None = None  # created, updated, resolved, skipped
    message: str | None = None
    error: str | None = None


class InternalIncident(BaseModel):
    """Internal incident representation for sync operations."""

    id: str
    title: str
    service_name: str
    severity: str
    status: str  # open, acknowledged, resolved
    description: str | None = None
    triggered_at: datetime
    resolved_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)


class StatusPageSync:
    """Service for syncing internal incidents to status pages."""

    def __init__(
        self,
        client: StatuspageClient | None = None,
        templates: StatusUpdateTemplates | None = None,
        component_mappings: list[ComponentMapping] | None = None,
    ):
        """Initialize sync service.

        Args:
            client: Statuspage client (uses singleton if not provided)
            templates: Status update templates (uses singleton if not provided)
            component_mappings: Service to component mappings
        """
        self.client = client or get_statuspage_client()
        self.templates = templates or get_templates()
        self.component_mappings = component_mappings or []

        # Track synced incidents (internal_id -> status_incident_id)
        self._synced_incidents: dict[str, str] = {}

        # Load mappings from settings if not provided
        if not self.component_mappings:
            self._load_mappings_from_settings()

    def _load_mappings_from_settings(self) -> None:
        """Load component mappings from settings."""
        settings = get_settings()
        mappings_config = getattr(settings, "statuspage_component_mappings", {})

        for service_name, mapping_data in mappings_config.items():
            if isinstance(mapping_data, str):
                # Simple format: service_name=component_id
                self.component_mappings.append(
                    ComponentMapping(
                        internal_service=service_name,
                        component_id=mapping_data,
                        page_id=self.client.default_page_id,
                    )
                )
            elif isinstance(mapping_data, dict):
                # Complex format with all fields
                self.component_mappings.append(
                    ComponentMapping(
                        internal_service=service_name,
                        **mapping_data,
                    )
                )

    def get_mapping_for_service(
        self, service_name: str
    ) -> ComponentMapping | None:
        """Get component mapping for a service.

        Args:
            service_name: Internal service name

        Returns:
            Component mapping if found
        """
        for mapping in self.component_mappings:
            if mapping.internal_service.lower() == service_name.lower():
                return mapping
        return None

    def add_mapping(self, mapping: ComponentMapping) -> None:
        """Add a component mapping.

        Args:
            mapping: Mapping to add
        """
        # Remove existing mapping for this service
        self.component_mappings = [
            m
            for m in self.component_mappings
            if m.internal_service.lower() != mapping.internal_service.lower()
        ]
        self.component_mappings.append(mapping)
        logger.info(
            "statuspage_mapping_added",
            service=mapping.internal_service,
            component_id=mapping.component_id,
        )

    def should_sync_incident(self, incident: InternalIncident) -> bool:
        """Determine if an incident should be synced to status page.

        Args:
            incident: Internal incident

        Returns:
            True if incident should be synced
        """
        mapping = self.get_mapping_for_service(incident.service_name)
        if not mapping:
            logger.debug(
                "statuspage_no_mapping",
                service=incident.service_name,
            )
            return False

        # Check severity threshold
        severity_order = ["low", "medium", "high", "critical"]
        incident_severity = incident.severity.lower()
        threshold = mapping.severity_threshold.lower()

        try:
            incident_level = severity_order.index(incident_severity)
            threshold_level = severity_order.index(threshold)
        except ValueError:
            # Handle P1/P2/etc format
            severity_p_map = {"p1": "critical", "p2": "high", "p3": "medium", "p4": "low"}
            incident_severity = severity_p_map.get(incident_severity, incident_severity)
            threshold = severity_p_map.get(threshold, threshold)
            try:
                incident_level = severity_order.index(incident_severity)
                threshold_level = severity_order.index(threshold)
            except ValueError:
                return False

        return incident_level >= threshold_level

    def _map_severity_to_impact(
        self, severity: str, mapping: ComponentMapping | None = None
    ) -> ComponentImpact:
        """Map internal severity to component impact.

        Args:
            severity: Internal severity level
            mapping: Optional mapping with custom impact mapping

        Returns:
            Component impact level
        """
        severity_lower = severity.lower()

        if mapping and mapping.impact_mapping:
            return mapping.impact_mapping.get(severity_lower, ComponentImpact.NONE)

        # Default mapping
        default_map = {
            "critical": ComponentImpact.CRITICAL,
            "p1": ComponentImpact.CRITICAL,
            "high": ComponentImpact.MAJOR,
            "p2": ComponentImpact.MAJOR,
            "medium": ComponentImpact.MINOR,
            "p3": ComponentImpact.MINOR,
            "low": ComponentImpact.NONE,
            "p4": ComponentImpact.NONE,
        }
        return default_map.get(severity_lower, ComponentImpact.NONE)

    def _impact_to_component_status(
        self, impact: ComponentImpact
    ) -> ComponentStatus:
        """Convert component impact to component status.

        Args:
            impact: Component impact level

        Returns:
            Component status
        """
        impact_to_status = {
            ComponentImpact.CRITICAL: ComponentStatus.MAJOR_OUTAGE,
            ComponentImpact.MAJOR: ComponentStatus.PARTIAL_OUTAGE,
            ComponentImpact.MINOR: ComponentStatus.DEGRADED_PERFORMANCE,
            ComponentImpact.NONE: ComponentStatus.OPERATIONAL,
        }
        return impact_to_status.get(impact, ComponentStatus.OPERATIONAL)

    def _impact_to_incident_impact(
        self, impact: ComponentImpact
    ) -> IncidentImpact:
        """Convert component impact to incident impact.

        Args:
            impact: Component impact

        Returns:
            Incident impact
        """
        return IncidentImpact(impact.value)

    async def sync_incident_created(
        self,
        incident: InternalIncident,
        custom_body: str | None = None,
        page_id: str | None = None,
    ) -> SyncResult:
        """Sync a new internal incident to status page.

        Args:
            incident: Internal incident
            custom_body: Optional custom message body (overrides template)
            page_id: Target page ID (uses default if not provided)

        Returns:
            Sync result
        """
        if not self.client.is_configured:
            return SyncResult(
                success=False,
                incident_id=incident.id,
                action="skipped",
                message="Statuspage not configured",
            )

        if not self.should_sync_incident(incident):
            return SyncResult(
                success=True,
                incident_id=incident.id,
                action="skipped",
                message="Incident does not meet sync criteria",
            )

        mapping = self.get_mapping_for_service(incident.service_name)
        if not mapping:
            return SyncResult(
                success=False,
                incident_id=incident.id,
                action="skipped",
                error="No component mapping found",
            )

        target_page_id = page_id or mapping.page_id

        try:
            # Determine impact
            impact = self._map_severity_to_impact(incident.severity, mapping)
            component_status = self._impact_to_component_status(impact)
            incident_impact = self._impact_to_incident_impact(impact)

            # Generate update body
            if custom_body:
                body = custom_body
            else:
                issue_type = self.templates.suggest_issue_type(
                    incident.title, incident.tags
                )
                body = self.templates.render_for_status(
                    IncidentStatus.INVESTIGATING,
                    {
                        "issue_type": issue_type,
                        "service_name": incident.service_name,
                    },
                )

            # Create status page incident
            status_incident = await self.client.create_incident(
                name=incident.title,
                status=IncidentStatus.INVESTIGATING,
                impact=incident_impact,
                body=body,
                component_ids=[mapping.component_id],
                component_statuses={mapping.component_id: component_status},
                page_id=target_page_id,
            )

            # Track the sync
            self._synced_incidents[incident.id] = status_incident.id

            logger.info(
                "statuspage_incident_synced",
                internal_id=incident.id,
                status_id=status_incident.id,
                shortlink=status_incident.shortlink,
            )

            return SyncResult(
                success=True,
                incident_id=incident.id,
                status_incident_id=status_incident.id,
                action="created",
                message=f"Created status page incident: {status_incident.shortlink}",
            )

        except Exception as e:
            logger.error(
                "statuspage_sync_failed",
                incident_id=incident.id,
                error=str(e),
            )
            return SyncResult(
                success=False,
                incident_id=incident.id,
                action="error",
                error=str(e),
            )

    async def sync_incident_updated(
        self,
        incident: InternalIncident,
        new_status: IncidentStatus,
        custom_body: str | None = None,
        page_id: str | None = None,
    ) -> SyncResult:
        """Sync an internal incident update to status page.

        Args:
            incident: Internal incident
            new_status: New status for the status page incident
            custom_body: Optional custom message body
            page_id: Target page ID

        Returns:
            Sync result
        """
        status_incident_id = self._synced_incidents.get(incident.id)
        if not status_incident_id:
            logger.warning(
                "statuspage_no_synced_incident",
                incident_id=incident.id,
            )
            return SyncResult(
                success=False,
                incident_id=incident.id,
                action="skipped",
                message="No synced status incident found",
            )

        mapping = self.get_mapping_for_service(incident.service_name)
        target_page_id = page_id or (mapping.page_id if mapping else None)

        try:
            # Generate update body if not provided
            if not custom_body:
                custom_body = self.templates.render_for_status(
                    new_status,
                    {"service_name": incident.service_name},
                )

            # Determine component status based on new incident status
            if new_status in (IncidentStatus.RESOLVED, IncidentStatus.COMPLETED):
                component_statuses = (
                    {mapping.component_id: ComponentStatus.OPERATIONAL}
                    if mapping
                    else None
                )
            else:
                # Keep existing impact-based status during incident
                impact = self._map_severity_to_impact(
                    incident.severity, mapping
                )
                component_status = self._impact_to_component_status(impact)
                component_statuses = (
                    {mapping.component_id: component_status} if mapping else None
                )

            # Update status page incident
            updated = await self.client.update_incident(
                incident_id=status_incident_id,
                status=new_status,
                body=custom_body,
                component_statuses=component_statuses,
                page_id=target_page_id,
            )

            logger.info(
                "statuspage_incident_updated",
                internal_id=incident.id,
                status_id=status_incident_id,
                new_status=new_status.value,
            )

            return SyncResult(
                success=True,
                incident_id=incident.id,
                status_incident_id=status_incident_id,
                action="updated",
                message=f"Updated to {new_status.value}",
            )

        except Exception as e:
            logger.error(
                "statuspage_update_failed",
                incident_id=incident.id,
                status_id=status_incident_id,
                error=str(e),
            )
            return SyncResult(
                success=False,
                incident_id=incident.id,
                status_incident_id=status_incident_id,
                action="error",
                error=str(e),
            )

    async def sync_incident_resolved(
        self,
        incident: InternalIncident,
        resolution_message: str | None = None,
        page_id: str | None = None,
    ) -> SyncResult:
        """Sync incident resolution to status page.

        Args:
            incident: Internal incident
            resolution_message: Custom resolution message
            page_id: Target page ID

        Returns:
            Sync result
        """
        status_incident_id = self._synced_incidents.get(incident.id)
        if not status_incident_id:
            return SyncResult(
                success=False,
                incident_id=incident.id,
                action="skipped",
                message="No synced status incident found",
            )

        mapping = self.get_mapping_for_service(incident.service_name)
        target_page_id = page_id or (mapping.page_id if mapping else None)

        # Calculate duration if we have timestamps
        duration = None
        if incident.triggered_at and incident.resolved_at:
            delta = incident.resolved_at - incident.triggered_at
            hours = delta.total_seconds() / 3600
            if hours >= 1:
                duration = f"{hours:.1f} hours"
            else:
                minutes = delta.total_seconds() / 60
                duration = f"{minutes:.0f} minutes"

        try:
            # Generate resolution message
            if not resolution_message:
                variables = {"service_name": incident.service_name}
                if duration:
                    variables["duration"] = duration
                    variables["resolution_summary"] = (
                        "The issue has been identified and fixed."
                    )
                    resolution_message = self.templates.render_template(
                        "resolved_detailed", variables
                    )
                else:
                    resolution_message = self.templates.render_for_status(
                        IncidentStatus.RESOLVED, variables
                    )

            # Resolve the status page incident
            resolved = await self.client.resolve_incident(
                incident_id=status_incident_id,
                body=resolution_message,
                page_id=target_page_id,
            )

            # Clean up tracking
            del self._synced_incidents[incident.id]

            logger.info(
                "statuspage_incident_resolved",
                internal_id=incident.id,
                status_id=status_incident_id,
            )

            return SyncResult(
                success=True,
                incident_id=incident.id,
                status_incident_id=status_incident_id,
                action="resolved",
                message="Incident resolved on status page",
            )

        except Exception as e:
            logger.error(
                "statuspage_resolve_failed",
                incident_id=incident.id,
                status_id=status_incident_id,
                error=str(e),
            )
            return SyncResult(
                success=False,
                incident_id=incident.id,
                status_incident_id=status_incident_id,
                action="error",
                error=str(e),
            )

    async def get_synced_status_incident(
        self, internal_incident_id: str, page_id: str | None = None
    ) -> StatusIncident | None:
        """Get the status page incident synced to an internal incident.

        Args:
            internal_incident_id: Internal incident ID
            page_id: Page ID to search

        Returns:
            Status page incident if found
        """
        status_incident_id = self._synced_incidents.get(internal_incident_id)
        if not status_incident_id:
            return None

        try:
            return await self.client.get_incident(status_incident_id, page_id)
        except Exception:
            return None

    def register_synced_incident(
        self, internal_id: str, status_incident_id: str
    ) -> None:
        """Register an existing sync relationship.

        Args:
            internal_id: Internal incident ID
            status_incident_id: Status page incident ID
        """
        self._synced_incidents[internal_id] = status_incident_id

    def unregister_synced_incident(self, internal_id: str) -> bool:
        """Unregister a sync relationship.

        Args:
            internal_id: Internal incident ID

        Returns:
            True if unregistered, False if not found
        """
        if internal_id in self._synced_incidents:
            del self._synced_incidents[internal_id]
            return True
        return False


# Module-level sync instance
_status_sync: StatusPageSync | None = None


def get_status_sync() -> StatusPageSync:
    """Get the status sync singleton."""
    global _status_sync
    if _status_sync is None:
        _status_sync = StatusPageSync()
    return _status_sync
