"""Integration adapters for external services."""

from .cloudwatch import CloudWatchAdapter
from .datadog import DatadogAdapter
from .github import GitHubAdapter
from .jira import JiraClient, create_incident_ticket, update_incident_resolved
from .pagerduty import PagerDutyAdapter
from .slack import SlackAdapter

__all__ = [
    "PagerDutyAdapter",
    "GitHubAdapter",
    "DatadogAdapter",
    "CloudWatchAdapter",
    "SlackAdapter",
    "JiraClient",
    "create_incident_ticket",
    "update_incident_resolved",
]
