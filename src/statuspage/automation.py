"""Status Page Automation - Auto-update based on incident status."""

import logging
from datetime import datetime
from typing import Any, Callable

from .models import (
    ComponentStatus,
    IncidentImpact,
    IncidentStatus,
    SEVERITY_TO_COMPONENT_STATUS,
    SEVERITY_TO_IMPACT,
    StatusPageIncident,
    StatusUpdate,
)
from .service import StatusPageService, get_statuspage_service

logger = logging.getLogger(__name__)


# Status update templates
STATUS_TEMPLATES = {
    "investigating": (
        "We are currently investigating this issue. "
        "More updates will be provided as we learn more."
    ),
    "identified": (
        "We have identified the issue and are working on a fix. "
        "We will provide updates as the situation progresses."
    ),
    "monitoring": (
        "A fix has been implemented and we are monitoring the results. "
        "We will provide a final update once the issue is confirmed resolved."
    ),
    "resolved": (
        "This incident has been resolved. "
        "We apologize for any inconvenience this may have caused."
    ),
    "maintenance_start": (
        "Scheduled maintenance is now in progress. "
        "Some services may be temporarily unavailable."
    ),
    "maintenance_end": (
        "Scheduled maintenance has been completed. "
        "All services should now be operating normally."
    ),
}


class StatusPageAutomation:
    """Automates status page updates based on incident lifecycle."""

    def __init__(self, service: StatusPageService | None = None):
        self.service = service or get_statuspage_service()
        self._hooks: dict[str, list[Callable]] = {
            "incident_created": [],
            "incident_updated": [],
            "incident_resolved": [],
            "component_updated": [],
        }

    def register_hook(self, event: str, callback: Callable) -> None:
        """Register a callback for an automation event."""
        if event in self._hooks:
            self._hooks[event].append(callback)

    async def _trigger_hooks(self, event: str, **kwargs: Any) -> None:
        """Trigger all registered hooks for an event."""
        for callback in self._hooks.get(event, []):
            try:
                result = callback(**kwargs)
                if hasattr(result, "__await__"):
                    await result
            except Exception as e:
                logger.error(f"Hook error for {event}: {e}")

    def generate_update_message(
        self,
        template_key: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Generate status update message from template."""
        template = STATUS_TEMPLATES.get(template_key, "Status update in progress.")
        if context:
            try:
                return template.format(**context)
            except KeyError:
                return template
        return template

    async def on_incident_created(
        self,
        incident_id: str,
        title: str,
        description: str,
        severity: str,
        affected_services: list[str],
    ) -> dict[str, StatusPageIncident]:
        """Handle new incident creation - create on all status pages."""
        impact = SEVERITY_TO_IMPACT.get(severity.lower(), IncidentImpact.MINOR)
        component_status = SEVERITY_TO_COMPONENT_STATUS.get(
            severity.lower(), ComponentStatus.DEGRADED
        )

        incident = StatusPageIncident(
            name=title,
            message=description or self.generate_update_message("investigating"),
            status=IncidentStatus.INVESTIGATING,
            impact=impact,
            component_ids=affected_services,
            component_status=component_status,
        )

        results = await self.service.create_incident_all(incident, incident_id)
        await self._trigger_hooks(
            "incident_created",
            incident_id=incident_id,
            results=results,
        )
        logger.info(f"Created incident {incident_id} on {len(results)} status pages")
        return results

    async def on_incident_status_change(
        self,
        incident_id: str,
        new_status: str,
        message: str | None = None,
    ) -> dict[str, StatusPageIncident]:
        """Handle incident status change."""
        status_mapping = {
            "investigating": IncidentStatus.INVESTIGATING,
            "identified": IncidentStatus.IDENTIFIED,
            "monitoring": IncidentStatus.MONITORING,
            "resolved": IncidentStatus.RESOLVED,
            "in_progress": IncidentStatus.IN_PROGRESS,
        }

        incident_status = status_mapping.get(new_status.lower(), IncidentStatus.INVESTIGATING)

        if incident_status == IncidentStatus.RESOLVED:
            return await self.on_incident_resolved(incident_id, message)

        update = StatusUpdate(
            incident_id=incident_id,
            status=incident_status,
            message=message or self.generate_update_message(new_status.lower()),
        )

        results = await self.service.update_incident_all(incident_id, update)
        await self._trigger_hooks(
            "incident_updated",
            incident_id=incident_id,
            status=new_status,
            results=results,
        )
        logger.info(f"Updated incident {incident_id} to {new_status}")
        return results

    async def on_incident_resolved(
        self,
        incident_id: str,
        message: str | None = None,
    ) -> dict[str, StatusPageIncident]:
        """Handle incident resolution."""
        resolution_message = message or self.generate_update_message("resolved")
        results = await self.service.resolve_incident_all(incident_id, resolution_message)
        await self._trigger_hooks(
            "incident_resolved",
            incident_id=incident_id,
            results=results,
        )
        logger.info(f"Resolved incident {incident_id} on {len(results)} status pages")
        return results

    async def on_severity_change(
        self,
        incident_id: str,
        new_severity: str,
        message: str | None = None,
    ) -> dict[str, StatusPageIncident]:
        """Handle incident severity change."""
        component_status = SEVERITY_TO_COMPONENT_STATUS.get(
            new_severity.lower(), ComponentStatus.DEGRADED
        )

        update_message = message or (
            f"Incident severity has been updated to {new_severity}. "
            "Our team continues to work on resolution."
        )

        update = StatusUpdate(
            incident_id=incident_id,
            status=IncidentStatus.IDENTIFIED,
            message=update_message,
        )

        results = await self.service.update_incident_all(incident_id, update)
        logger.info(f"Updated incident {incident_id} severity to {new_severity}")
        return results

    async def on_service_status_change(
        self,
        service_id: str,
        status: str,
    ) -> dict[str, Any]:
        """Handle service status change - update component status."""
        status_mapping = {
            "healthy": ComponentStatus.OPERATIONAL,
            "operational": ComponentStatus.OPERATIONAL,
            "degraded": ComponentStatus.DEGRADED,
            "partial_outage": ComponentStatus.PARTIAL_OUTAGE,
            "major_outage": ComponentStatus.MAJOR_OUTAGE,
            "maintenance": ComponentStatus.MAINTENANCE,
        }

        component_status = status_mapping.get(status.lower(), ComponentStatus.OPERATIONAL)
        results = await self.service.update_service_status(service_id, component_status)
        await self._trigger_hooks(
            "component_updated",
            service_id=service_id,
            status=status,
            results=results,
        )
        logger.info(f"Updated service {service_id} status to {status}")
        return results

    async def sync_incident_from_internal(
        self,
        internal_incident: dict[str, Any],
    ) -> dict[str, StatusPageIncident]:
        """Sync an internal incident to all status pages."""
        incident_id = internal_incident.get("id", "")
        status = internal_incident.get("status", "investigating")
        severity = internal_incident.get("severity", "medium")

        # Check if incident already exists on status pages
        existing = self.service.get_incident_external_id(incident_id, list(self.service._configs.keys())[0]) if self.service._configs else None

        if existing:
            return await self.on_incident_status_change(
                incident_id,
                status,
                internal_incident.get("latest_update"),
            )
        else:
            return await self.on_incident_created(
                incident_id=incident_id,
                title=internal_incident.get("title", "Incident"),
                description=internal_incident.get("description", ""),
                severity=severity,
                affected_services=internal_incident.get("affected_services", []),
            )


# Singleton instance
_automation: StatusPageAutomation | None = None


def get_statuspage_automation() -> StatusPageAutomation:
    """Get or create automation singleton."""
    global _automation
    if _automation is None:
        _automation = StatusPageAutomation()
    return _automation
