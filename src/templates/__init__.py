"""Incident Templates module for pre-defined and custom incident templates."""

from .models import (
    AppliedTemplate,
    FieldType,
    IncidentTemplate,
    InitialAction,
    MatchPattern,
    StakeholderRole,
    TemplateAnalytics,
    TemplateCategory,
    TemplateCreateRequest,
    TemplateExport,
    TemplateField,
    TemplateMatch,
    TemplateUpdateRequest,
    TemplateVersion,
)
from .defaults import (
    BUILTIN_TEMPLATES,
    get_builtin_template,
    get_builtin_templates,
    DATABASE_OUTAGE,
    DEPLOYMENT_FAILURE,
    SECURITY_INCIDENT,
    API_OUTAGE,
    NETWORK_ISSUE,
    THIRD_PARTY_OUTAGE,
    INFRASTRUCTURE_SCALING,
)
from .matcher import AlertData, TemplateMatcher, suggest_templates
from .service import TemplateService, get_template_service
from .routes import router

__all__ = [
    # Models
    "AppliedTemplate",
    "FieldType",
    "IncidentTemplate",
    "InitialAction",
    "MatchPattern",
    "StakeholderRole",
    "TemplateAnalytics",
    "TemplateCategory",
    "TemplateCreateRequest",
    "TemplateExport",
    "TemplateField",
    "TemplateMatch",
    "TemplateUpdateRequest",
    "TemplateVersion",
    # Defaults
    "BUILTIN_TEMPLATES",
    "get_builtin_template",
    "get_builtin_templates",
    "DATABASE_OUTAGE",
    "DEPLOYMENT_FAILURE",
    "SECURITY_INCIDENT",
    "API_OUTAGE",
    "NETWORK_ISSUE",
    "THIRD_PARTY_OUTAGE",
    "INFRASTRUCTURE_SCALING",
    # Matcher
    "AlertData",
    "TemplateMatcher",
    "suggest_templates",
    # Service
    "TemplateService",
    "get_template_service",
    # Routes
    "router",
]
