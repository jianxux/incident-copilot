"""
Change Tracking Integration - Track deployments, config changes, and feature flags.

This module provides:
- Change event models (deployments, config changes, feature flags)
- Collectors for GitHub, GitLab, ArgoCD, LaunchDarkly
- Change correlation with incidents
- Change freeze management
- Rollback tracking
- Impact scoring

Usage:
    from integrations.changes import (
        ChangeTrackingService,
        get_change_service,
        GitHubCollector,
        router,
    )

    # Register collectors
    service = get_change_service()
    service.register_collector(GitHubCollector(token="...", org="myorg"))

    # Include routes
    app.include_router(router)
"""

from .collectors import (
    ArgoCDCollector,
    GitHubCollector,
    GitLabCollector,
    LaunchDarklyCollector,
)
from .models import (
    ChangeCorrelation,
    ChangeEvent,
    ChangeFreeze,
    ChangeSource,
    ChangeStatus,
    ChangeTimeline,
    ChangeType,
    ConfigChange,
    Deployment,
    FeatureFlag,
    RiskLevel,
)
from .routes import router
from .service import (
    ChangeCollector,
    ChangeTrackingService,
    get_change_service,
)

__all__ = [
    # Enums
    "ChangeType",
    "ChangeStatus",
    "ChangeSource",
    "RiskLevel",
    # Models
    "ChangeEvent",
    "Deployment",
    "ConfigChange",
    "FeatureFlag",
    "ChangeFreeze",
    "ChangeCorrelation",
    "ChangeTimeline",
    # Service
    "ChangeTrackingService",
    "ChangeCollector",
    "get_change_service",
    # Collectors
    "GitHubCollector",
    "GitLabCollector",
    "ArgoCDCollector",
    "LaunchDarklyCollector",
    # Routes
    "router",
]
