"""
Incident Timeline Module

Provides chronological timeline tracking for incidents with:
- Event collection from multiple sources (PagerDuty, Slack, GitHub, etc.)
- Manual event addition and annotation
- Timeline gaps detection
- Export for postmortems in multiple formats
"""

from .models import (
    EventType,
    EventSource,
    EventSeverity,
    TimelineEvent,
    TimelineEntry,
    TimelineFilter,
    TimelineGap,
    TimelineSummary,
    TimelineExport,
)

from .service import (
    TimelineService,
    get_timeline_service,
)

from .collectors import (
    EventCollector,
    PagerDutyCollector,
    SlackCollector,
    GitHubCollector,
    DatadogCollector,
    PrometheusCollector,
    KubernetesCollector,
    CompositeCollector,
    create_default_collector,
)

from .export import (
    ExportFormat,
    TimelineExporter,
)

from .routes import router

__all__ = [
    # Models
    "EventType",
    "EventSource",
    "EventSeverity",
    "TimelineEvent",
    "TimelineEntry",
    "TimelineFilter",
    "TimelineGap",
    "TimelineSummary",
    "TimelineExport",
    # Service
    "TimelineService",
    "get_timeline_service",
    # Collectors
    "EventCollector",
    "PagerDutyCollector",
    "SlackCollector",
    "GitHubCollector",
    "DatadogCollector",
    "PrometheusCollector",
    "KubernetesCollector",
    "CompositeCollector",
    "create_default_collector",
    # Export
    "ExportFormat",
    "TimelineExporter",
    # Routes
    "router",
]
