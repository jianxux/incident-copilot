"""Built-in incident templates."""

from .models import (
    IncidentTemplate,
    InitialAction,
    MatchPattern,
    StakeholderRole,
    TemplateCategory,
    TemplateField,
    FieldType,
)


def _t(
    id: str,
    name: str,
    desc: str,
    cat: TemplateCategory,
    title: str,
    sev: str,
    runbooks: list[str],
    actions: list[InitialAction],
    stakeholders: list[StakeholderRole],
    fields: list[TemplateField],
    patterns: list[MatchPattern],
    tags: list[str],
) -> IncidentTemplate:
    """Helper to create a built-in template."""
    return IncidentTemplate(
        id=id,
        name=name,
        description=desc,
        category=cat,
        title_pattern=title,
        severity_default=sev,
        runbook_urls=runbooks,
        initial_actions=actions,
        stakeholders=stakeholders,
        fields=fields,
        match_patterns=patterns,
        is_builtin=True,
        tags=tags,
    )


DATABASE_OUTAGE = _t(
    "builtin-database-outage",
    "Database Outage",
    "Database connectivity or performance issues",
    TemplateCategory.DATABASE,
    "[DB] {service} - {issue_type}",
    "critical",
    ["https://runbooks.example.com/database/connection-issues"],
    [
        InitialAction(
            order=1, title="Check database cluster health", estimated_minutes=2
        ),
        InitialAction(
            order=2, title="Verify connection pool status", estimated_minutes=2
        ),
        InitialAction(order=3, title="Check replication lag", estimated_minutes=3),
        InitialAction(
            order=4,
            title="Initiate failover if primary down",
            assignee_role="dba_oncall",
        ),
    ],
    [
        StakeholderRole(
            role="dba_oncall", notification_channel="pagerduty", required=True
        ),
        StakeholderRole(
            role="platform_lead",
            notification_channel="slack",
            escalation_delay_minutes=15,
        ),
    ],
    [
        TemplateField(name="database_name", label="Database Name", required=True),
        TemplateField(
            name="issue_type",
            label="Issue Type",
            field_type=FieldType.SELECT,
            options=[
                "Connection Timeout",
                "High Latency",
                "Replication Lag",
                "Disk Full",
                "OOM",
            ],
        ),
    ],
    [
        MatchPattern(field="title", operator="contains", value="database", weight=2.0),
        MatchPattern(field="title", operator="contains", value="postgres", weight=2.5),
        MatchPattern(field="title", operator="contains", value="mysql", weight=2.5),
        MatchPattern(field="tags", operator="contains", value="database", weight=1.5),
    ],
    ["database", "infrastructure", "critical"],
)

DEPLOYMENT_FAILURE = _t(
    "builtin-deployment-failure",
    "Deployment Failure",
    "Failed or problematic deployments",
    TemplateCategory.DEPLOYMENT,
    "[Deploy] {service} deployment {status}",
    "high",
    ["https://runbooks.example.com/deployment/rollback-procedure"],
    [
        InitialAction(
            order=1, title="Identify failing deployment", estimated_minutes=2
        ),
        InitialAction(order=2, title="Check deployment logs", estimated_minutes=3),
        InitialAction(
            order=3, title="Evaluate rollback vs fix-forward", estimated_minutes=5
        ),
        InitialAction(
            order=4,
            title="Execute rollback if needed",
            assignee_role="oncall",
            estimated_minutes=10,
        ),
    ],
    [
        StakeholderRole(role="oncall", notification_channel="pagerduty", required=True),
        StakeholderRole(role="release_manager", notification_channel="slack"),
    ],
    [
        TemplateField(
            name="service", label="Service", field_type=FieldType.SERVICE, required=True
        ),
        TemplateField(
            name="status",
            label="Status",
            field_type=FieldType.SELECT,
            options=["failed", "stuck", "degraded", "partial"],
        ),
        TemplateField(name="commit_sha", label="Commit SHA", placeholder="abc123"),
    ],
    [
        MatchPattern(field="title", operator="contains", value="deploy", weight=2.5),
        MatchPattern(field="title", operator="contains", value="rollback", weight=2.0),
        MatchPattern(field="source", operator="equals", value="argocd", weight=2.0),
    ],
    ["deployment", "ci-cd"],
)

SECURITY_INCIDENT = _t(
    "builtin-security-incident",
    "Security Incident",
    "Security-related incidents requiring immediate response",
    TemplateCategory.SECURITY,
    "[SECURITY] {incident_type} - {severity_level}",
    "critical",
    ["https://runbooks.example.com/security/incident-response"],
    [
        InitialAction(order=1, title="Assess scope and impact", estimated_minutes=10),
        InitialAction(
            order=2, title="Initiate containment measures", estimated_minutes=5
        ),
        InitialAction(order=3, title="Preserve evidence and logs", estimated_minutes=5),
        InitialAction(
            order=4,
            title="Notify security team lead",
            assignee_role="incident_commander",
        ),
    ],
    [
        StakeholderRole(
            role="security_oncall", notification_channel="pagerduty", required=True
        ),
        StakeholderRole(
            role="security_lead", notification_channel="pagerduty", required=True
        ),
        StakeholderRole(
            role="legal", notification_channel="email", escalation_delay_minutes=30
        ),
    ],
    [
        TemplateField(
            name="incident_type",
            label="Incident Type",
            field_type=FieldType.SELECT,
            required=True,
            options=[
                "Data Breach",
                "Unauthorized Access",
                "Malware",
                "DDoS",
                "Phishing",
            ],
        ),
        TemplateField(
            name="severity_level",
            label="Security Severity",
            field_type=FieldType.SELECT,
            options=["P0 - Critical", "P1 - High", "P2 - Medium", "P3 - Low"],
        ),
    ],
    [
        MatchPattern(field="title", operator="contains", value="security", weight=3.0),
        MatchPattern(field="title", operator="contains", value="breach", weight=3.0),
        MatchPattern(
            field="source", operator="equals", value="crowdstrike", weight=2.0
        ),
    ],
    ["security", "critical", "compliance"],
)

API_OUTAGE = _t(
    "builtin-api-outage",
    "API/Service Outage",
    "API or microservice outages",
    TemplateCategory.APPLICATION,
    "[Outage] {service} - {symptom}",
    "high",
    ["https://runbooks.example.com/services/general-troubleshooting"],
    [
        InitialAction(
            order=1, title="Check service health endpoints", estimated_minutes=2
        ),
        InitialAction(
            order=2, title="Review error rates and latency", estimated_minutes=3
        ),
        InitialAction(
            order=3, title="Check upstream dependencies", estimated_minutes=5
        ),
        InitialAction(
            order=4, title="Scale up if resource constrained", estimated_minutes=5
        ),
    ],
    [
        StakeholderRole(role="oncall", notification_channel="pagerduty", required=True),
        StakeholderRole(
            role="service_owner",
            notification_channel="slack",
            escalation_delay_minutes=10,
        ),
    ],
    [
        TemplateField(
            name="service", label="Service", field_type=FieldType.SERVICE, required=True
        ),
        TemplateField(
            name="symptom",
            label="Symptom",
            field_type=FieldType.SELECT,
            options=["5xx Errors", "Timeout", "High Latency", "Connection Refused"],
        ),
    ],
    [
        MatchPattern(field="title", operator="contains", value="outage", weight=2.5),
        MatchPattern(field="title", operator="contains", value="5xx", weight=2.0),
        MatchPattern(field="title", operator="contains", value="timeout", weight=1.5),
    ],
    ["api", "service", "outage"],
)

NETWORK_ISSUE = _t(
    "builtin-network-issue",
    "Network Issue",
    "Network connectivity and routing problems",
    TemplateCategory.NETWORK,
    "[Network] {issue_type} - {affected_region}",
    "high",
    ["https://runbooks.example.com/network/connectivity-issues"],
    [
        InitialAction(
            order=1, title="Identify affected network segment", estimated_minutes=5
        ),
        InitialAction(
            order=2, title="Check cloud provider status", estimated_minutes=2
        ),
        InitialAction(order=3, title="Check DNS resolution", estimated_minutes=3),
    ],
    [
        StakeholderRole(
            role="network_oncall", notification_channel="pagerduty", required=True
        )
    ],
    [
        TemplateField(
            name="issue_type",
            label="Issue Type",
            field_type=FieldType.SELECT,
            options=["Connectivity Loss", "High Latency", "Packet Loss", "DNS Failure"],
        ),
        TemplateField(
            name="affected_region",
            label="Affected Region",
            field_type=FieldType.SELECT,
            options=["us-east-1", "us-west-2", "eu-west-1", "global"],
        ),
    ],
    [
        MatchPattern(field="title", operator="contains", value="network", weight=2.0),
        MatchPattern(field="title", operator="contains", value="dns", weight=1.5),
        MatchPattern(
            field="title", operator="contains", value="connectivity", weight=1.5
        ),
    ],
    ["network", "infrastructure"],
)

THIRD_PARTY_OUTAGE = _t(
    "builtin-third-party-outage",
    "Third-Party Service Outage",
    "External vendor/service outages",
    TemplateCategory.THIRD_PARTY,
    "[Vendor] {vendor_name} - {impact}",
    "medium",
    ["https://runbooks.example.com/vendors/outage-response"],
    [
        InitialAction(order=1, title="Confirm vendor status page", estimated_minutes=2),
        InitialAction(
            order=2, title="Identify affected internal services", estimated_minutes=5
        ),
        InitialAction(order=3, title="Evaluate fallback options", estimated_minutes=10),
    ],
    [StakeholderRole(role="oncall", notification_channel="slack", required=True)],
    [
        TemplateField(name="vendor_name", label="Vendor Name", required=True),
        TemplateField(
            name="impact",
            label="Impact",
            field_type=FieldType.SELECT,
            options=[
                "Complete Outage",
                "Degraded Performance",
                "Partial Functionality",
            ],
        ),
    ],
    [
        MatchPattern(field="title", operator="contains", value="vendor", weight=2.0),
        MatchPattern(
            field="title", operator="contains", value="third-party", weight=2.0
        ),
        MatchPattern(field="source", operator="equals", value="statuspage", weight=1.5),
    ],
    ["vendor", "third-party", "external"],
)

INFRASTRUCTURE_SCALING = _t(
    "builtin-infrastructure-scaling",
    "Infrastructure Scaling Issue",
    "Capacity and scaling problems",
    TemplateCategory.INFRASTRUCTURE,
    "[Capacity] {resource_type} exhaustion - {service}",
    "high",
    ["https://runbooks.example.com/infrastructure/scaling"],
    [
        InitialAction(
            order=1, title="Identify resource bottleneck", estimated_minutes=3
        ),
        InitialAction(order=2, title="Check autoscaling status", estimated_minutes=2),
        InitialAction(order=3, title="Manual scale-up if needed", estimated_minutes=5),
    ],
    [
        StakeholderRole(
            role="platform_oncall", notification_channel="pagerduty", required=True
        )
    ],
    [
        TemplateField(
            name="resource_type",
            label="Resource Type",
            field_type=FieldType.SELECT,
            required=True,
            options=["CPU", "Memory", "Disk", "Connections", "Pods"],
        ),
        TemplateField(name="service", label="Service", field_type=FieldType.SERVICE),
    ],
    [
        MatchPattern(field="title", operator="contains", value="cpu", weight=1.5),
        MatchPattern(field="title", operator="contains", value="memory", weight=1.5),
        MatchPattern(field="title", operator="contains", value="scaling", weight=2.0),
        MatchPattern(field="title", operator="contains", value="oom", weight=2.0),
    ],
    ["infrastructure", "scaling", "capacity"],
)

BUILTIN_TEMPLATES: list[IncidentTemplate] = [
    DATABASE_OUTAGE,
    DEPLOYMENT_FAILURE,
    SECURITY_INCIDENT,
    API_OUTAGE,
    NETWORK_ISSUE,
    THIRD_PARTY_OUTAGE,
    INFRASTRUCTURE_SCALING,
]


def get_builtin_templates() -> list[IncidentTemplate]:
    """Get all built-in templates."""
    return BUILTIN_TEMPLATES.copy()


def get_builtin_template(template_id: str) -> IncidentTemplate | None:
    """Get a specific built-in template by ID."""
    for template in BUILTIN_TEMPLATES:
        if template.id == template_id:
            return template.model_copy(deep=True)
    return None
