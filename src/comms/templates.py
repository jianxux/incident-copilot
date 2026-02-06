"""Communication templates for different audiences.

Provides pre-built and customizable templates for:
- Technical teams (detailed, actionable)
- Executives (high-level, impact-focused)
- Customers (empathetic, clear, solution-oriented)
- Support teams (customer-facing details)
- Public status updates (concise, professional)
"""

import secrets
from datetime import datetime
from typing import Any

import structlog
from pydantic import BaseModel, Field

from .models import AudienceType

logger = structlog.get_logger()


class TemplateVariable(BaseModel):
    """A variable that can be substituted in templates."""

    name: str
    description: str
    required: bool = False
    default: str | None = None
    example: str | None = None


class CommunicationTemplate(BaseModel):
    """A communication template for incident updates."""

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(12))
    name: str
    description: str | None = None

    # Target audience
    audience_type: AudienceType

    # Template content (supports {variable} substitution)
    subject_template: str
    body_template: str
    body_html_template: str | None = None

    # Available variables
    variables: list[TemplateVariable] = Field(default_factory=list)

    # Categorization
    category: str | None = None  # e.g., "initial", "update", "resolved"
    severity_levels: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    # Metadata
    is_builtin: bool = False
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    tenant_id: str | None = None
    use_count: int = 0


class RenderedTemplate(BaseModel):
    """A rendered template with variables substituted."""

    template_id: str
    subject: str
    body: str
    body_html: str | None = None
    audience_type: AudienceType
    rendered_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# Built-in Templates
# ============================================================================

# Standard variables available in all templates
STANDARD_VARIABLES = [
    TemplateVariable(
        name="incident_id",
        description="Unique incident identifier",
        required=True,
        example="INC-2024-001",
    ),
    TemplateVariable(
        name="incident_title",
        description="Incident title/summary",
        required=True,
        example="Database connectivity issues",
    ),
    TemplateVariable(
        name="severity",
        description="Incident severity level",
        required=True,
        example="critical",
    ),
    TemplateVariable(
        name="service",
        description="Affected service name",
        required=False,
        example="payments-api",
    ),
    TemplateVariable(
        name="status",
        description="Current incident status",
        required=False,
        default="investigating",
        example="investigating",
    ),
    TemplateVariable(
        name="impact",
        description="Description of customer/business impact",
        required=False,
        example="Customers may experience delays in payment processing",
    ),
    TemplateVariable(
        name="started_at",
        description="When the incident started",
        required=False,
        example="2024-01-15 14:30 UTC",
    ),
    TemplateVariable(
        name="update_time",
        description="Time of this update",
        required=False,
        example="2024-01-15 15:00 UTC",
    ),
    TemplateVariable(
        name="next_update",
        description="When to expect next update",
        required=False,
        default="30 minutes",
        example="30 minutes",
    ),
    TemplateVariable(
        name="responder",
        description="Name of incident responder",
        required=False,
        example="Jane Smith",
    ),
    TemplateVariable(
        name="root_cause",
        description="Root cause if identified",
        required=False,
        example="Database connection pool exhaustion",
    ),
    TemplateVariable(
        name="resolution",
        description="Resolution actions taken",
        required=False,
        example="Increased connection pool size and restarted affected services",
    ),
    TemplateVariable(
        name="action_items",
        description="Follow-up action items",
        required=False,
        example="- Review connection pool sizing\\n- Add monitoring alerts",
    ),
]


# Technical Team Templates
TECHNICAL_INITIAL_TEMPLATE = CommunicationTemplate(
    id="builtin-tech-initial",
    name="Technical - Initial Alert",
    description="Initial notification for technical team",
    audience_type=AudienceType.TECHNICAL,
    category="initial",
    subject_template="🚨 [{severity}] {incident_title} - {service}",
    body_template="""**Incident Alert**

**ID:** {incident_id}
**Severity:** {severity}
**Service:** {service}
**Status:** {status}
**Started:** {started_at}

**Summary:**
{incident_title}

**Impact:**
{impact}

**Current Actions:**
- Incident commander assigned
- Initial investigation in progress
- Runbooks being consulted

**Next Update:** {next_update}

---
_Please join the incident channel for real-time updates._""",
    body_html_template="""
<div style="font-family: sans-serif; max-width: 600px;">
    <div style="background: #dc3545; color: white; padding: 12px; border-radius: 4px 4px 0 0;">
        <h2 style="margin: 0;">🚨 Incident Alert</h2>
    </div>
    <div style="border: 1px solid #ddd; padding: 16px; border-radius: 0 0 4px 4px;">
        <table style="width: 100%; border-collapse: collapse;">
            <tr><td style="padding: 4px 8px; font-weight: bold;">ID:</td><td>{incident_id}</td></tr>
            <tr><td style="padding: 4px 8px; font-weight: bold;">Severity:</td><td>{severity}</td></tr>
            <tr><td style="padding: 4px 8px; font-weight: bold;">Service:</td><td>{service}</td></tr>
            <tr><td style="padding: 4px 8px; font-weight: bold;">Status:</td><td>{status}</td></tr>
            <tr><td style="padding: 4px 8px; font-weight: bold;">Started:</td><td>{started_at}</td></tr>
        </table>
        <h3>Summary</h3>
        <p>{incident_title}</p>
        <h3>Impact</h3>
        <p>{impact}</p>
        <h3>Current Actions</h3>
        <ul>
            <li>Incident commander assigned</li>
            <li>Initial investigation in progress</li>
            <li>Runbooks being consulted</li>
        </ul>
        <p><strong>Next Update:</strong> {next_update}</p>
    </div>
</div>""",
    variables=STANDARD_VARIABLES,
    is_builtin=True,
    severity_levels=["critical", "high", "medium"],
    tags=["initial", "alert"],
)

TECHNICAL_UPDATE_TEMPLATE = CommunicationTemplate(
    id="builtin-tech-update",
    name="Technical - Status Update",
    description="Progress update for technical team",
    audience_type=AudienceType.TECHNICAL,
    category="update",
    subject_template="📊 [{severity}] Update: {incident_title}",
    body_template="""**Incident Update**

**ID:** {incident_id}
**Status:** {status}
**Update Time:** {update_time}

**Current Status:**
{incident_title}

**Investigation Findings:**
{root_cause}

**Actions Taken:**
{resolution}

**Next Steps:**
{action_items}

**Next Update:** {next_update}""",
    variables=STANDARD_VARIABLES,
    is_builtin=True,
    severity_levels=["critical", "high", "medium", "low"],
    tags=["update", "progress"],
)

TECHNICAL_RESOLVED_TEMPLATE = CommunicationTemplate(
    id="builtin-tech-resolved",
    name="Technical - Resolved",
    description="Resolution notification for technical team",
    audience_type=AudienceType.TECHNICAL,
    category="resolved",
    subject_template="✅ [RESOLVED] {incident_title}",
    body_template="""**Incident Resolved**

**ID:** {incident_id}
**Service:** {service}
**Duration:** {started_at} - {update_time}

**Summary:**
{incident_title}

**Root Cause:**
{root_cause}

**Resolution:**
{resolution}

**Follow-up Actions:**
{action_items}

---
_A postmortem will be scheduled within 48 hours._""",
    variables=STANDARD_VARIABLES,
    is_builtin=True,
    tags=["resolved", "closed"],
)

# Executive Templates
EXECUTIVE_INITIAL_TEMPLATE = CommunicationTemplate(
    id="builtin-exec-initial",
    name="Executive - Initial Brief",
    description="Initial briefing for executives",
    audience_type=AudienceType.EXECUTIVE,
    category="initial",
    subject_template="⚠️ {severity} Incident: {service} - Executive Brief",
    body_template="""**Executive Incident Brief**

**Severity:** {severity}
**Service:** {service}
**Started:** {started_at}

**What's Happening:**
{incident_title}

**Business Impact:**
{impact}

**Response Status:**
- Incident team mobilized
- Investigation underway
- Customer communications being prepared

**Next Update:** {next_update}

_Contact: Incident Commander available for questions_""",
    variables=STANDARD_VARIABLES,
    is_builtin=True,
    severity_levels=["critical", "high"],
    tags=["initial", "executive"],
)

EXECUTIVE_UPDATE_TEMPLATE = CommunicationTemplate(
    id="builtin-exec-update",
    name="Executive - Status Update",
    description="Status update for executives",
    audience_type=AudienceType.EXECUTIVE,
    category="update",
    subject_template="📋 {severity} Incident Update: {service}",
    body_template="""**Executive Update**

**Status:** {status}
**Time:** {update_time}

**Current Situation:**
{incident_title}

**Impact Assessment:**
{impact}

**Key Actions:**
{resolution}

**Timeline to Resolution:** {next_update}

_Escalation path active if needed_""",
    variables=STANDARD_VARIABLES,
    is_builtin=True,
    severity_levels=["critical", "high"],
    tags=["update", "executive"],
)

EXECUTIVE_RESOLVED_TEMPLATE = CommunicationTemplate(
    id="builtin-exec-resolved",
    name="Executive - Resolution Summary",
    description="Resolution summary for executives",
    audience_type=AudienceType.EXECUTIVE,
    category="resolved",
    subject_template="✅ Incident Resolved: {service}",
    body_template="""**Incident Resolution Summary**

**Service:** {service}
**Total Duration:** {started_at} - {update_time}

**What Happened:**
{incident_title}

**Root Cause:**
{root_cause}

**Business Impact:**
{impact}

**Resolution:**
{resolution}

**Prevention Measures:**
{action_items}

_Detailed postmortem available upon request_""",
    variables=STANDARD_VARIABLES,
    is_builtin=True,
    tags=["resolved", "executive"],
)

# Customer Templates
CUSTOMER_INITIAL_TEMPLATE = CommunicationTemplate(
    id="builtin-customer-initial",
    name="Customer - Initial Notice",
    description="Initial customer notification",
    audience_type=AudienceType.CUSTOMER,
    category="initial",
    subject_template="Service Notice: We're investigating an issue with {service}",
    body_template="""Dear Valued Customer,

We are currently investigating an issue that may affect {service}.

**What's Happening:**
{incident_title}

**What This Means for You:**
{impact}

**What We're Doing:**
Our engineering team is actively working to resolve this issue. We understand how important our service is to your business and are treating this with the highest priority.

**Next Update:**
We will provide an update within {next_update}.

We apologize for any inconvenience this may cause.

Best regards,
The Support Team""",
    body_html_template="""
<div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
    <div style="background: #f8f9fa; padding: 20px; border-radius: 8px;">
        <h2 style="color: #333; margin-top: 0;">Service Notice</h2>
        <p>Dear Valued Customer,</p>
        <p>We are currently investigating an issue that may affect <strong>{service}</strong>.</p>
        
        <div style="background: white; padding: 16px; border-radius: 4px; margin: 16px 0;">
            <h3 style="margin-top: 0; color: #666;">What's Happening</h3>
            <p>{incident_title}</p>
            
            <h3 style="color: #666;">What This Means for You</h3>
            <p>{impact}</p>
        </div>
        
        <h3 style="color: #666;">What We're Doing</h3>
        <p>Our engineering team is actively working to resolve this issue. We understand how important our service is to your business and are treating this with the highest priority.</p>
        
        <p><strong>Next Update:</strong> We will provide an update within {next_update}.</p>
        
        <p>We apologize for any inconvenience this may cause.</p>
        
        <p>Best regards,<br>The Support Team</p>
    </div>
</div>""",
    variables=STANDARD_VARIABLES,
    is_builtin=True,
    severity_levels=["critical", "high"],
    tags=["initial", "customer"],
)

CUSTOMER_UPDATE_TEMPLATE = CommunicationTemplate(
    id="builtin-customer-update",
    name="Customer - Status Update",
    description="Status update for customers",
    audience_type=AudienceType.CUSTOMER,
    category="update",
    subject_template="Update: {service} Service Status",
    body_template="""Dear Valued Customer,

We wanted to provide you with an update on the {service} issue we're addressing.

**Current Status:** {status}

**Progress Update:**
{resolution}

**Expected Timeline:**
We anticipate providing another update within {next_update}.

Thank you for your patience and understanding.

Best regards,
The Support Team""",
    variables=STANDARD_VARIABLES,
    is_builtin=True,
    tags=["update", "customer"],
)

CUSTOMER_RESOLVED_TEMPLATE = CommunicationTemplate(
    id="builtin-customer-resolved",
    name="Customer - Issue Resolved",
    description="Resolution notification for customers",
    audience_type=AudienceType.CUSTOMER,
    category="resolved",
    subject_template="Resolved: {service} is back to normal",
    body_template="""Dear Valued Customer,

We're pleased to inform you that the issue affecting {service} has been resolved.

**What Happened:**
{incident_title}

**Resolution:**
{resolution}

**Service Status:**
All systems are now operating normally.

We sincerely apologize for any inconvenience this may have caused. We have taken steps to prevent similar issues in the future.

If you have any questions or continue to experience issues, please don't hesitate to contact our support team.

Thank you for your patience and continued trust in our services.

Best regards,
The Support Team""",
    variables=STANDARD_VARIABLES,
    is_builtin=True,
    tags=["resolved", "customer"],
)

# Status Page Templates
STATUS_PAGE_INVESTIGATING_TEMPLATE = CommunicationTemplate(
    id="builtin-status-investigating",
    name="Status Page - Investigating",
    description="Public status page - investigating",
    audience_type=AudienceType.PUBLIC,
    category="initial",
    subject_template="Investigating issues with {service}",
    body_template="""We are currently investigating reports of issues with {service}.

Users may experience {impact}.

Our team is actively working on this issue. We will provide updates as we learn more.""",
    variables=STANDARD_VARIABLES,
    is_builtin=True,
    tags=["status-page", "investigating"],
)

STATUS_PAGE_IDENTIFIED_TEMPLATE = CommunicationTemplate(
    id="builtin-status-identified",
    name="Status Page - Identified",
    description="Public status page - issue identified",
    audience_type=AudienceType.PUBLIC,
    category="update",
    subject_template="Issue identified with {service}",
    body_template="""We have identified the issue affecting {service}.

{root_cause}

Our team is implementing a fix. We expect to have an update within {next_update}.""",
    variables=STANDARD_VARIABLES,
    is_builtin=True,
    tags=["status-page", "identified"],
)

STATUS_PAGE_MONITORING_TEMPLATE = CommunicationTemplate(
    id="builtin-status-monitoring",
    name="Status Page - Monitoring",
    description="Public status page - monitoring fix",
    audience_type=AudienceType.PUBLIC,
    category="update",
    subject_template="Monitoring fix for {service}",
    body_template="""A fix has been implemented for the {service} issue.

We are currently monitoring the situation to ensure stability.

If you continue to experience issues, please contact support.""",
    variables=STANDARD_VARIABLES,
    is_builtin=True,
    tags=["status-page", "monitoring"],
)

STATUS_PAGE_RESOLVED_TEMPLATE = CommunicationTemplate(
    id="builtin-status-resolved",
    name="Status Page - Resolved",
    description="Public status page - resolved",
    audience_type=AudienceType.PUBLIC,
    category="resolved",
    subject_template="{service} - Issue Resolved",
    body_template="""The issue affecting {service} has been resolved.

All systems are operating normally.

We apologize for any inconvenience caused.""",
    variables=STANDARD_VARIABLES,
    is_builtin=True,
    tags=["status-page", "resolved"],
)

# Support Team Templates
SUPPORT_INITIAL_TEMPLATE = CommunicationTemplate(
    id="builtin-support-initial",
    name="Support - Initial Brief",
    description="Initial briefing for support team",
    audience_type=AudienceType.SUPPORT,
    category="initial",
    subject_template="[Support Brief] {severity} - {incident_title}",
    body_template="""**Support Team Brief**

**Incident:** {incident_id}
**Severity:** {severity}
**Service:** {service}
**Status:** {status}

**Issue Summary:**
{incident_title}

**Customer Impact:**
{impact}

**Talking Points for Customers:**
- We are aware of the issue and actively working on it
- Engineering team is investigating
- Next update expected in {next_update}

**Workarounds:**
- None available at this time

**Escalation:**
- Direct customer escalations to incident channel
- Do NOT promise specific resolution times

**FAQ:**
Q: When will this be fixed?
A: Our team is actively working on this. We'll provide updates as soon as we have more information.

Q: Is my data safe?
A: Yes, this issue does not affect data integrity.""",
    variables=STANDARD_VARIABLES,
    is_builtin=True,
    severity_levels=["critical", "high", "medium"],
    tags=["support", "initial"],
)

SUPPORT_RESOLVED_TEMPLATE = CommunicationTemplate(
    id="builtin-support-resolved",
    name="Support - Resolution Brief",
    description="Resolution brief for support team",
    audience_type=AudienceType.SUPPORT,
    category="resolved",
    subject_template="[RESOLVED] {incident_title} - Support Update",
    body_template="""**Support Team - Resolution Update**

**Status:** RESOLVED
**Service:** {service}
**Resolution Time:** {update_time}

**What Happened:**
{root_cause}

**Resolution:**
{resolution}

**Customer Communication:**
- Customers can be informed the issue is resolved
- If customers still experience issues, have them clear cache/retry
- Escalate persistent issues to engineering

**Talking Points:**
- The issue has been fully resolved
- All functionality should be restored
- We apologize for any inconvenience

**Post-Incident:**
- Postmortem will be shared within 48 hours
- Customer credits (if applicable) will be processed separately""",
    variables=STANDARD_VARIABLES,
    is_builtin=True,
    tags=["support", "resolved"],
)


# All built-in templates
BUILTIN_TEMPLATES = [
    TECHNICAL_INITIAL_TEMPLATE,
    TECHNICAL_UPDATE_TEMPLATE,
    TECHNICAL_RESOLVED_TEMPLATE,
    EXECUTIVE_INITIAL_TEMPLATE,
    EXECUTIVE_UPDATE_TEMPLATE,
    EXECUTIVE_RESOLVED_TEMPLATE,
    CUSTOMER_INITIAL_TEMPLATE,
    CUSTOMER_UPDATE_TEMPLATE,
    CUSTOMER_RESOLVED_TEMPLATE,
    STATUS_PAGE_INVESTIGATING_TEMPLATE,
    STATUS_PAGE_IDENTIFIED_TEMPLATE,
    STATUS_PAGE_MONITORING_TEMPLATE,
    STATUS_PAGE_RESOLVED_TEMPLATE,
    SUPPORT_INITIAL_TEMPLATE,
    SUPPORT_RESOLVED_TEMPLATE,
]


class TemplateLibrary:
    """Library of communication templates."""

    def __init__(self) -> None:
        self._templates: dict[str, CommunicationTemplate] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize with built-in templates."""
        if self._initialized:
            return

        for template in BUILTIN_TEMPLATES:
            self._templates[template.id] = template

        self._initialized = True
        logger.info("template_library_initialized", template_count=len(self._templates))

    async def get_template(self, template_id: str) -> CommunicationTemplate | None:
        """Get a template by ID."""
        return self._templates.get(template_id)

    async def list_templates(
        self,
        audience_type: AudienceType | None = None,
        category: str | None = None,
        include_builtin: bool = True,
        tenant_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[CommunicationTemplate], int]:
        """List templates with optional filters."""
        templates = list(self._templates.values())

        # Filter by audience type
        if audience_type:
            templates = [t for t in templates if t.audience_type == audience_type]

        # Filter by category
        if category:
            templates = [t for t in templates if t.category == category]

        # Filter built-in
        if not include_builtin:
            templates = [t for t in templates if not t.is_builtin]

        # Filter by tenant
        if tenant_id:
            templates = [
                t for t in templates
                if t.tenant_id == tenant_id or t.is_builtin
            ]

        # Filter active only
        templates = [t for t in templates if t.is_active]

        total = len(templates)
        templates = templates[offset:offset + limit]

        return templates, total

    async def create_template(
        self, template: CommunicationTemplate
    ) -> CommunicationTemplate:
        """Create a new custom template."""
        template.is_builtin = False
        template.created_at = datetime.utcnow()
        template.updated_at = datetime.utcnow()
        self._templates[template.id] = template
        logger.info("template_created", template_id=template.id, name=template.name)
        return template

    async def update_template(
        self, template_id: str, updates: dict[str, Any]
    ) -> CommunicationTemplate | None:
        """Update an existing template."""
        template = self._templates.get(template_id)
        if not template:
            return None

        if template.is_builtin:
            logger.warning("cannot_update_builtin_template", template_id=template_id)
            return None

        for key, value in updates.items():
            if hasattr(template, key):
                setattr(template, key, value)

        template.updated_at = datetime.utcnow()
        self._templates[template_id] = template
        logger.info("template_updated", template_id=template_id)
        return template

    async def delete_template(self, template_id: str) -> bool:
        """Delete a custom template."""
        template = self._templates.get(template_id)
        if not template:
            return False

        if template.is_builtin:
            logger.warning("cannot_delete_builtin_template", template_id=template_id)
            return False

        del self._templates[template_id]
        logger.info("template_deleted", template_id=template_id)
        return True

    async def render_template(
        self,
        template_id: str,
        variables: dict[str, Any],
    ) -> RenderedTemplate | None:
        """Render a template with provided variables."""
        template = self._templates.get(template_id)
        if not template:
            logger.warning("template_not_found", template_id=template_id)
            return None

        try:
            # Render subject and body with variable substitution
            subject = template.subject_template.format(**variables)
            body = template.body_template.format(**variables)

            body_html = None
            if template.body_html_template:
                body_html = template.body_html_template.format(**variables)

            # Increment usage count
            template.use_count += 1

            return RenderedTemplate(
                template_id=template_id,
                subject=subject,
                body=body,
                body_html=body_html,
                audience_type=template.audience_type,
            )

        except KeyError as e:
            logger.error(
                "template_render_error",
                template_id=template_id,
                missing_variable=str(e),
            )
            return None

    async def get_templates_for_audience(
        self, audience_type: AudienceType
    ) -> list[CommunicationTemplate]:
        """Get all templates for a specific audience type."""
        return [
            t for t in self._templates.values()
            if t.audience_type == audience_type and t.is_active
        ]

    async def get_template_for_category(
        self,
        audience_type: AudienceType,
        category: str,
    ) -> CommunicationTemplate | None:
        """Get the default template for an audience and category."""
        for template in self._templates.values():
            if (
                template.audience_type == audience_type
                and template.category == category
                and template.is_active
                and template.is_builtin
            ):
                return template
        return None


# Singleton instance
_template_library: TemplateLibrary | None = None


async def get_template_library() -> TemplateLibrary:
    """Get the singleton template library instance."""
    global _template_library
    if _template_library is None:
        _template_library = TemplateLibrary()
        await _template_library.initialize()
    return _template_library
