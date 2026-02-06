"""Status update templates for public incident communication.

Provides templated messages for different incident stages to ensure
consistent, professional public communication during incidents.
"""

from enum import Enum
from string import Template

import structlog
from pydantic import BaseModel, Field

from .models import ComponentImpact, IncidentStatus

logger = structlog.get_logger()


class TemplateCategory(str, Enum):
    """Categories of status update templates."""

    INVESTIGATING = "investigating"
    IDENTIFIED = "identified"
    MONITORING = "monitoring"
    RESOLVED = "resolved"
    MAINTENANCE_SCHEDULED = "maintenance_scheduled"
    MAINTENANCE_IN_PROGRESS = "maintenance_in_progress"
    MAINTENANCE_COMPLETED = "maintenance_completed"


class UpdateTemplate(BaseModel):
    """A status update template."""

    id: str
    name: str
    category: TemplateCategory
    template: str
    description: str | None = None
    variables: list[str] = Field(
        default_factory=list, description="Required template variables"
    )
    is_default: bool = False


# Default templates for each incident stage
DEFAULT_TEMPLATES: dict[TemplateCategory, list[UpdateTemplate]] = {
    TemplateCategory.INVESTIGATING: [
        UpdateTemplate(
            id="investigating_default",
            name="Default - Investigating",
            category=TemplateCategory.INVESTIGATING,
            template=(
                "We are currently investigating reports of $issue_type affecting "
                "$service_name. Our team has been alerted and is actively looking "
                "into this issue. We will provide updates as we learn more."
            ),
            variables=["issue_type", "service_name"],
            is_default=True,
        ),
        UpdateTemplate(
            id="investigating_error_rate",
            name="Error Rate - Investigating",
            category=TemplateCategory.INVESTIGATING,
            template=(
                "We are investigating increased error rates affecting $service_name. "
                "Some users may experience errors or degraded performance. "
                "Our engineering team is actively working to identify the root cause."
            ),
            variables=["service_name"],
        ),
        UpdateTemplate(
            id="investigating_latency",
            name="Latency - Investigating",
            category=TemplateCategory.INVESTIGATING,
            template=(
                "We are investigating elevated latency affecting $service_name. "
                "Users may experience slower than normal response times. "
                "Our team is working to identify and resolve the issue."
            ),
            variables=["service_name"],
        ),
        UpdateTemplate(
            id="investigating_availability",
            name="Availability - Investigating",
            category=TemplateCategory.INVESTIGATING,
            template=(
                "We are aware of availability issues affecting $service_name and "
                "are actively investigating. Some users may be unable to access "
                "the service. We apologize for the inconvenience and will provide "
                "updates shortly."
            ),
            variables=["service_name"],
        ),
    ],
    TemplateCategory.IDENTIFIED: [
        UpdateTemplate(
            id="identified_default",
            name="Default - Identified",
            category=TemplateCategory.IDENTIFIED,
            template=(
                "We have identified the cause of the issue affecting $service_name. "
                "$root_cause_summary Our team is implementing a fix and we expect "
                "to have this resolved shortly."
            ),
            variables=["service_name", "root_cause_summary"],
            is_default=True,
        ),
        UpdateTemplate(
            id="identified_infrastructure",
            name="Infrastructure - Identified",
            category=TemplateCategory.IDENTIFIED,
            template=(
                "The issue affecting $service_name has been identified as an "
                "infrastructure problem with $component. Our team is working on "
                "remediation and we expect services to recover within $eta."
            ),
            variables=["service_name", "component", "eta"],
        ),
        UpdateTemplate(
            id="identified_third_party",
            name="Third Party - Identified",
            category=TemplateCategory.IDENTIFIED,
            template=(
                "We have identified that the issue affecting $service_name is "
                "caused by a problem with an upstream provider ($provider). "
                "We are in contact with them and monitoring for resolution."
            ),
            variables=["service_name", "provider"],
        ),
    ],
    TemplateCategory.MONITORING: [
        UpdateTemplate(
            id="monitoring_default",
            name="Default - Monitoring",
            category=TemplateCategory.MONITORING,
            template=(
                "A fix has been implemented for the issue affecting $service_name. "
                "We are monitoring the situation to ensure stability. "
                "Service performance appears to be returning to normal."
            ),
            variables=["service_name"],
            is_default=True,
        ),
        UpdateTemplate(
            id="monitoring_rollback",
            name="Rollback - Monitoring",
            category=TemplateCategory.MONITORING,
            template=(
                "We have rolled back a recent change that was causing issues with "
                "$service_name. We are monitoring to confirm services have returned "
                "to normal operation."
            ),
            variables=["service_name"],
        ),
        UpdateTemplate(
            id="monitoring_partial",
            name="Partial Recovery - Monitoring",
            category=TemplateCategory.MONITORING,
            template=(
                "We have implemented a partial fix for the issue affecting "
                "$service_name. Most functionality has been restored. We are "
                "continuing to monitor and work on fully resolving the issue."
            ),
            variables=["service_name"],
        ),
    ],
    TemplateCategory.RESOLVED: [
        UpdateTemplate(
            id="resolved_default",
            name="Default - Resolved",
            category=TemplateCategory.RESOLVED,
            template=(
                "The issue affecting $service_name has been resolved. All services "
                "are operating normally. We apologize for any inconvenience and "
                "thank you for your patience."
            ),
            variables=["service_name"],
            is_default=True,
        ),
        UpdateTemplate(
            id="resolved_detailed",
            name="Detailed - Resolved",
            category=TemplateCategory.RESOLVED,
            template=(
                "The issue affecting $service_name has been fully resolved. "
                "$resolution_summary The total duration of impact was approximately "
                "$duration. We apologize for the disruption and are taking steps "
                "to prevent similar issues in the future."
            ),
            variables=["service_name", "resolution_summary", "duration"],
        ),
        UpdateTemplate(
            id="resolved_brief",
            name="Brief - Resolved",
            category=TemplateCategory.RESOLVED,
            template=(
                "This incident has been resolved. All systems are operating normally."
            ),
            variables=[],
        ),
    ],
    TemplateCategory.MAINTENANCE_SCHEDULED: [
        UpdateTemplate(
            id="maintenance_scheduled_default",
            name="Default - Maintenance Scheduled",
            category=TemplateCategory.MAINTENANCE_SCHEDULED,
            template=(
                "Scheduled maintenance for $service_name will take place on "
                "$scheduled_date from $start_time to $end_time $timezone. "
                "During this window, $expected_impact. We will provide updates "
                "when maintenance begins and completes."
            ),
            variables=[
                "service_name",
                "scheduled_date",
                "start_time",
                "end_time",
                "timezone",
                "expected_impact",
            ],
            is_default=True,
        ),
    ],
    TemplateCategory.MAINTENANCE_IN_PROGRESS: [
        UpdateTemplate(
            id="maintenance_in_progress_default",
            name="Default - Maintenance In Progress",
            category=TemplateCategory.MAINTENANCE_IN_PROGRESS,
            template=(
                "Scheduled maintenance on $service_name has begun. "
                "$expected_impact We expect maintenance to complete by $end_time."
            ),
            variables=["service_name", "expected_impact", "end_time"],
            is_default=True,
        ),
    ],
    TemplateCategory.MAINTENANCE_COMPLETED: [
        UpdateTemplate(
            id="maintenance_completed_default",
            name="Default - Maintenance Completed",
            category=TemplateCategory.MAINTENANCE_COMPLETED,
            template=(
                "Scheduled maintenance on $service_name has been completed. "
                "All services are operating normally. Thank you for your patience."
            ),
            variables=["service_name"],
            is_default=True,
        ),
    ],
}


# Issue type suggestions based on alert characteristics
ISSUE_TYPE_MAP: dict[str, str] = {
    "error": "increased error rates",
    "error_rate": "increased error rates",
    "latency": "elevated response times",
    "slow": "elevated response times",
    "availability": "availability issues",
    "unavailable": "availability issues",
    "timeout": "timeout errors",
    "5xx": "server errors",
    "4xx": "request failures",
    "memory": "performance degradation",
    "cpu": "performance degradation",
    "disk": "storage issues",
    "network": "connectivity issues",
    "database": "database performance issues",
    "api": "API issues",
}


class StatusUpdateTemplates:
    """Service for managing and applying status update templates."""

    def __init__(self, custom_templates: list[UpdateTemplate] | None = None):
        """Initialize templates.

        Args:
            custom_templates: Optional list of custom templates to add
        """
        self._templates: dict[str, UpdateTemplate] = {}

        # Load default templates
        for category_templates in DEFAULT_TEMPLATES.values():
            for template in category_templates:
                self._templates[template.id] = template

        # Load custom templates
        if custom_templates:
            for template in custom_templates:
                self._templates[template.id] = template

    def get_template(self, template_id: str) -> UpdateTemplate | None:
        """Get a template by ID.

        Args:
            template_id: Template ID

        Returns:
            Template if found, None otherwise
        """
        return self._templates.get(template_id)

    def get_templates_by_category(
        self, category: TemplateCategory
    ) -> list[UpdateTemplate]:
        """Get all templates for a category.

        Args:
            category: Template category

        Returns:
            List of templates in the category
        """
        return [t for t in self._templates.values() if t.category == category]

    def get_default_template(
        self, category: TemplateCategory
    ) -> UpdateTemplate | None:
        """Get the default template for a category.

        Args:
            category: Template category

        Returns:
            Default template if found
        """
        for template in self._templates.values():
            if template.category == category and template.is_default:
                return template
        return None

    def list_all_templates(self) -> list[UpdateTemplate]:
        """List all available templates.

        Returns:
            List of all templates
        """
        return list(self._templates.values())

    def render_template(
        self,
        template_id: str,
        variables: dict[str, str],
    ) -> str:
        """Render a template with the provided variables.

        Args:
            template_id: Template ID to render
            variables: Variable values to substitute

        Returns:
            Rendered template text

        Raises:
            ValueError: If template not found or required variables missing
        """
        template = self.get_template(template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")

        # Check for missing required variables
        missing = [v for v in template.variables if v not in variables]
        if missing:
            logger.warning(
                "template_missing_variables",
                template_id=template_id,
                missing=missing,
            )
            # Provide defaults for missing variables
            for var in missing:
                variables[var] = f"[{var}]"

        try:
            return Template(template.template).safe_substitute(variables)
        except Exception as e:
            logger.error(
                "template_render_error",
                template_id=template_id,
                error=str(e),
            )
            raise ValueError(f"Failed to render template: {e}")

    def render_for_status(
        self,
        status: IncidentStatus,
        variables: dict[str, str],
        template_id: str | None = None,
    ) -> str:
        """Render a template appropriate for the given status.

        Args:
            status: Current incident status
            variables: Variable values to substitute
            template_id: Optional specific template ID (uses default if not provided)

        Returns:
            Rendered template text
        """
        category_map = {
            IncidentStatus.INVESTIGATING: TemplateCategory.INVESTIGATING,
            IncidentStatus.IDENTIFIED: TemplateCategory.IDENTIFIED,
            IncidentStatus.MONITORING: TemplateCategory.MONITORING,
            IncidentStatus.RESOLVED: TemplateCategory.RESOLVED,
            IncidentStatus.SCHEDULED: TemplateCategory.MAINTENANCE_SCHEDULED,
            IncidentStatus.IN_PROGRESS: TemplateCategory.MAINTENANCE_IN_PROGRESS,
            IncidentStatus.COMPLETED: TemplateCategory.MAINTENANCE_COMPLETED,
            IncidentStatus.VERIFYING: TemplateCategory.MONITORING,
        }

        if template_id:
            return self.render_template(template_id, variables)

        category = category_map.get(status)
        if not category:
            logger.warning("unknown_status_for_template", status=status)
            return ""

        default_template = self.get_default_template(category)
        if not default_template:
            logger.warning("no_default_template", category=category)
            return ""

        return self.render_template(default_template.id, variables)

    def suggest_issue_type(self, alert_title: str, alert_tags: list[str]) -> str:
        """Suggest an issue type based on alert characteristics.

        Args:
            alert_title: Alert title/summary
            alert_tags: Alert tags

        Returns:
            Suggested issue type description
        """
        # Check tags first
        for tag in alert_tags:
            tag_lower = tag.lower()
            for key, issue_type in ISSUE_TYPE_MAP.items():
                if key in tag_lower:
                    return issue_type

        # Check title
        title_lower = alert_title.lower()
        for key, issue_type in ISSUE_TYPE_MAP.items():
            if key in title_lower:
                return issue_type

        # Default
        return "service issues"

    def suggest_impact(
        self, severity: str, error_details: str | None = None
    ) -> ComponentImpact:
        """Suggest component impact based on severity.

        Args:
            severity: Internal severity level
            error_details: Optional error details for context

        Returns:
            Suggested component impact
        """
        severity_lower = severity.lower()

        if severity_lower in ("critical", "sev1", "p1"):
            return ComponentImpact.CRITICAL
        elif severity_lower in ("high", "sev2", "p2"):
            return ComponentImpact.MAJOR
        elif severity_lower in ("medium", "sev3", "p3"):
            return ComponentImpact.MINOR
        else:
            return ComponentImpact.NONE

    def add_template(self, template: UpdateTemplate) -> None:
        """Add a custom template.

        Args:
            template: Template to add
        """
        self._templates[template.id] = template
        logger.info("template_added", template_id=template.id, name=template.name)

    def remove_template(self, template_id: str) -> bool:
        """Remove a template.

        Args:
            template_id: Template ID to remove

        Returns:
            True if removed, False if not found
        """
        if template_id in self._templates:
            del self._templates[template_id]
            logger.info("template_removed", template_id=template_id)
            return True
        return False


# Module-level templates instance
_templates: StatusUpdateTemplates | None = None


def get_templates() -> StatusUpdateTemplates:
    """Get the templates singleton."""
    global _templates
    if _templates is None:
        _templates = StatusUpdateTemplates()
    return _templates
