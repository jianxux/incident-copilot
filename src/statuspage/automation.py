"""Status Page Automation - Auto-update based on incident status."""

import logging
from typing import Any, Callable

from .models import (
    SEVERITY_TO_COMPONENT_STATUS,
    SEVERITY_TO_IMPACT,
    ComponentStatus,
    IncidentImpact,
    IncidentStatus,
    StatusPageIncident,
    StatusUpdate,
)
from .service import StatusPageService, get_statuspage_service

logger = logging.getLogger(__name__)

# Status update templates with context placeholders
STATUS_TEMPLATES = {
    "investigating": "We are currently investigating reports of {issue_type}. Our team is actively working to identify the root cause. We will provide updates as we learn more.",
    "investigating_simple": "We are currently investigating this issue. More updates will be provided as we learn more.",
    "identified": "We have identified the issue affecting {affected_services}. Our team is implementing a fix. Expected resolution time: {eta}.",
    "identified_simple": "We have identified the issue and are working on a fix.",
    "monitoring": "A fix has been implemented and we are monitoring the results. Services should begin recovering. We will confirm resolution shortly.",
    "monitoring_simple": "A fix has been implemented and we are monitoring the results.",
    "resolved": "This incident has been resolved. The issue was caused by {root_cause}. We apologize for any inconvenience this may have caused.",
    "resolved_simple": "This incident has been resolved. We apologize for any inconvenience.",
    "maintenance_scheduled": "Scheduled maintenance is planned for {start_time} to {end_time}. {affected_services} may experience brief interruptions.",
    "maintenance_start": "Scheduled maintenance is now in progress. Some services may be temporarily unavailable.",
    "maintenance_end": "Scheduled maintenance has been completed. All services should now be operating normally.",
    "severity_upgrade": "This incident has been escalated to {severity} severity. Additional resources have been allocated to expedite resolution.",
    "severity_downgrade": "This incident has been downgraded to {severity} severity as impact has been reduced.",
}

# Map internal status names to IncidentStatus
STATUS_MAP = {
    "investigating": IncidentStatus.INVESTIGATING,
    "identified": IncidentStatus.IDENTIFIED,
    "monitoring": IncidentStatus.MONITORING,
    "resolved": IncidentStatus.RESOLVED,
    "in_progress": IncidentStatus.IN_PROGRESS,
    "scheduled": IncidentStatus.SCHEDULED,
    "completed": IncidentStatus.COMPLETED,
}

# Map service health to component status
COMPONENT_MAP = {
    "healthy": ComponentStatus.OPERATIONAL,
    "operational": ComponentStatus.OPERATIONAL,
    "degraded": ComponentStatus.DEGRADED,
    "partial_outage": ComponentStatus.PARTIAL_OUTAGE,
    "major_outage": ComponentStatus.MAJOR_OUTAGE,
    "maintenance": ComponentStatus.MAINTENANCE,
    "down": ComponentStatus.MAJOR_OUTAGE,
    "slow": ComponentStatus.DEGRADED,
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
            "maintenance_started": [],
            "maintenance_completed": [],
        }
        self._custom_templates: dict[str, str] = {}

    def register_hook(self, event: str, callback: Callable) -> None:
        """Register a callback for automation events."""
        if event in self._hooks:
            self._hooks[event].append(callback)

    def unregister_hook(self, event: str, callback: Callable) -> bool:
        """Unregister a callback."""
        if event in self._hooks and callback in self._hooks[event]:
            self._hooks[event].remove(callback)
            return True
        return False

    def add_template(self, key: str, template: str) -> None:
        """Add or override a status template."""
        self._custom_templates[key] = template

    async def _trigger_hooks(self, event: str, **kwargs: Any) -> None:
        """Trigger all registered hooks for an event."""
        for cb in self._hooks.get(event, []):
            try:
                result = cb(**kwargs)
                if hasattr(result, "__await__"):
                    await result
            except Exception as e:
                logger.error(f"Hook error for {event}: {e}")

    def generate_message(
        self, key: str, context: dict[str, Any] | None = None, use_simple: bool = True
    ) -> str:
        """Generate status update message from template."""
        # Check custom templates first
        if key in self._custom_templates:
            template = self._custom_templates[key]
        elif use_simple and f"{key}_simple" in STATUS_TEMPLATES:
            template = STATUS_TEMPLATES[f"{key}_simple"]
        else:
            template = STATUS_TEMPLATES.get(key, "Status update in progress.")

        if context:
            try:
                return template.format(**context)
            except KeyError:
                # Fall back to simple template if context missing
                return STATUS_TEMPLATES.get(f"{key}_simple", template)
        return template

    async def on_incident_created(
        self,
        incident_id: str,
        title: str,
        description: str,
        severity: str,
        affected_services: list[str],
        context: dict[str, Any] | None = None,
    ) -> dict[str, StatusPageIncident]:
        """Handle new incident creation - create on all status pages."""
        impact = SEVERITY_TO_IMPACT.get(severity.lower(), IncidentImpact.MINOR)
        component_status = SEVERITY_TO_COMPONENT_STATUS.get(
            severity.lower(), ComponentStatus.DEGRADED
        )
        message = description or self.generate_message("investigating", context)

        incident = StatusPageIncident(
            name=title,
            message=message,
            status=IncidentStatus.INVESTIGATING,
            impact=impact,
            component_ids=affected_services,
            component_status=component_status,
        )

        results = await self.service.create_incident_all(incident, incident_id)
        await self._trigger_hooks(
            "incident_created", incident_id=incident_id, results=results
        )
        logger.info(f"Created incident {incident_id} on {len(results)} status pages")
        return results

    async def on_incident_status_change(
        self,
        incident_id: str,
        new_status: str,
        message: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, StatusPageIncident]:
        """Handle incident status change."""
        status = STATUS_MAP.get(new_status.lower(), IncidentStatus.INVESTIGATING)

        if status == IncidentStatus.RESOLVED:
            return await self.on_incident_resolved(incident_id, message, context)

        update = StatusUpdate(
            incident_id=incident_id,
            status=status,
            message=message or self.generate_message(new_status.lower(), context),
        )

        results = await self.service.update_incident_all(incident_id, update)
        await self._trigger_hooks(
            "incident_updated",
            incident_id=incident_id,
            status=new_status,
            results=results,
        )
        logger.info(f"Updated incident {incident_id} to status: {new_status}")
        return results

    async def on_incident_resolved(
        self,
        incident_id: str,
        message: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, StatusPageIncident]:
        """Handle incident resolution."""
        resolution_message = message or self.generate_message("resolved", context)
        results = await self.service.resolve_incident_all(
            incident_id, resolution_message
        )
        await self._trigger_hooks(
            "incident_resolved", incident_id=incident_id, results=results
        )
        logger.info(f"Resolved incident {incident_id} on {len(results)} status pages")
        return results

    async def on_severity_change(
        self,
        incident_id: str,
        new_severity: str,
        old_severity: str | None = None,
        message: str | None = None,
    ) -> dict[str, StatusPageIncident]:
        """Handle incident severity change."""
        context = {"severity": new_severity}
        template_key = (
            "severity_upgrade"
            if self._is_severity_upgrade(old_severity, new_severity)
            else "severity_downgrade"
        )
        update_message = message or self.generate_message(template_key, context)

        update = StatusUpdate(
            incident_id=incident_id,
            status=IncidentStatus.IDENTIFIED,
            message=update_message,
        )

        results = await self.service.update_incident_all(incident_id, update)
        logger.info(f"Updated incident {incident_id} severity to {new_severity}")
        return results

    def _is_severity_upgrade(self, old: str | None, new: str) -> bool:
        """Check if severity was upgraded."""
        severity_order = [
            "low",
            "medium",
            "high",
            "critical",
            "sev4",
            "sev3",
            "sev2",
            "sev1",
        ]
        if not old:
            return True
        old_idx = (
            severity_order.index(old.lower()) if old.lower() in severity_order else 0
        )
        new_idx = (
            severity_order.index(new.lower()) if new.lower() in severity_order else 0
        )
        return new_idx > old_idx

    async def on_service_status_change(
        self,
        service_id: str,
        status: str,
    ) -> dict[str, Any]:
        """Handle service status change - update component status."""
        component_status = COMPONENT_MAP.get(
            status.lower(), ComponentStatus.OPERATIONAL
        )
        results = await self.service.update_service_status(service_id, component_status)
        await self._trigger_hooks(
            "component_updated", service_id=service_id, status=status, results=results
        )
        logger.info(f"Updated service {service_id} status to {status}")
        return results

    async def sync_incident(
        self, internal_incident: dict[str, Any]
    ) -> dict[str, StatusPageIncident]:
        """Sync an internal incident to all status pages."""
        incident_id = internal_incident.get("id", "")
        status = internal_incident.get("status", "investigating")

        # Check if incident already exists on any status page
        configs = list(self.service._configs.keys())
        if configs and self.service.get_incident_external_id(incident_id, configs[0]):
            return await self.on_incident_status_change(
                incident_id,
                status,
                internal_incident.get("latest_update"),
            )

        return await self.on_incident_created(
            incident_id=incident_id,
            title=internal_incident.get("title", "Incident"),
            description=internal_incident.get("description", ""),
            severity=internal_incident.get("severity", "medium"),
            affected_services=internal_incident.get("affected_services", []),
        )

    async def bulk_update_services(
        self, status_map: dict[str, str]
    ) -> dict[str, dict[str, Any]]:
        """Update multiple services at once."""
        results = {}
        for service_id, status in status_map.items():
            results[service_id] = await self.on_service_status_change(
                service_id, status
            )
        return results


# Singleton instance
_automation: StatusPageAutomation | None = None


def get_statuspage_automation() -> StatusPageAutomation:
    """Get or create automation singleton."""
    global _automation
    if _automation is None:
        _automation = StatusPageAutomation()
    return _automation
