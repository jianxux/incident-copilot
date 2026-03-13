"""Event collectors from various integration sources."""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .models import EventSeverity, EventSource, EventType, TimelineEvent


class EventCollector(ABC):
    """Base class for event collectors."""

    @property
    @abstractmethod
    def source(self) -> EventSource:
        """Return the event source for this collector."""
        pass

    @abstractmethod
    async def collect(
        self,
        incident_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        **kwargs,
    ) -> list[TimelineEvent]:
        """Collect events from the source."""
        pass


class PagerDutyCollector(EventCollector):
    """Collect events from PagerDuty."""

    source = EventSource.PAGERDUTY

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key

    async def collect(
        self,
        incident_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        pd_incident_id: str | None = None,
        **kwargs,
    ) -> list[TimelineEvent]:
        """Collect PagerDuty incident log entries."""
        events = []
        # In production, this would call PagerDuty API
        # For now, return structure for integration
        return events

    def _parse_log_entry(
        self, incident_id: str, entry: dict[str, Any]
    ) -> TimelineEvent:
        """Parse a PagerDuty log entry into a TimelineEvent."""
        entry_type = entry.get("type", "")

        event_type = EventType.MANUAL
        if "trigger" in entry_type:
            event_type = EventType.ALERT
        elif "acknowledge" in entry_type:
            event_type = EventType.STATUS_CHANGE
        elif "resolve" in entry_type:
            event_type = EventType.RESOLUTION
        elif "escalate" in entry_type:
            event_type = EventType.ESCALATION
        elif "assign" in entry_type:
            event_type = EventType.ASSIGNMENT
        elif "annotate" in entry_type:
            event_type = EventType.COMMENT

        return TimelineEvent(
            incident_id=incident_id,
            timestamp=datetime.fromisoformat(
                entry.get("created_at", datetime.now(UTC).isoformat())
            ),
            event_type=event_type,
            source=EventSource.PAGERDUTY,
            severity=self._map_severity(entry.get("urgency", "low")),
            title=entry.get("summary", "PagerDuty event"),
            description=entry.get("message"),
            actor=entry.get("agent", {}).get("summary"),
            metadata={"pd_id": entry.get("id")},
            raw_data=entry,
        )

    def _map_severity(self, urgency: str) -> EventSeverity:
        return EventSeverity.CRITICAL if urgency == "high" else EventSeverity.WARNING


class SlackCollector(EventCollector):
    """Collect events from Slack channels."""

    source = EventSource.SLACK

    def __init__(self, bot_token: str | None = None):
        self.bot_token = bot_token

    async def collect(
        self,
        incident_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        channel_id: str | None = None,
        **kwargs,
    ) -> list[TimelineEvent]:
        """Collect messages from incident Slack channel."""
        events = []
        # Would call Slack API conversations.history
        return events

    def _parse_message(
        self, incident_id: str, message: dict[str, Any]
    ) -> TimelineEvent:
        """Parse a Slack message into a TimelineEvent."""
        text = message.get("text", "")

        # Detect special message types
        event_type = EventType.COMMENT
        if any(kw in text.lower() for kw in ["deployed", "deploy", "release"]):
            event_type = EventType.DEPLOYMENT
        elif any(kw in text.lower() for kw in ["rollback", "reverted"]):
            event_type = EventType.ROLLBACK
        elif any(kw in text.lower() for kw in ["resolved", "fixed", "solved"]):
            event_type = EventType.RESOLUTION

        return TimelineEvent(
            incident_id=incident_id,
            timestamp=datetime.fromtimestamp(float(message.get("ts", 0))),
            event_type=event_type,
            source=EventSource.SLACK,
            severity=EventSeverity.INFO,
            title=text[:100] + "..." if len(text) > 100 else text,
            description=text,
            actor=message.get("user"),
            metadata={"channel": message.get("channel"), "ts": message.get("ts")},
            raw_data=message,
        )


class GitHubCollector(EventCollector):
    """Collect events from GitHub (deployments, PRs, etc.)."""

    source = EventSource.GITHUB

    def __init__(self, token: str | None = None):
        self.token = token

    async def collect(
        self,
        incident_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        repo: str | None = None,
        **kwargs,
    ) -> list[TimelineEvent]:
        """Collect GitHub deployments and related events."""
        events = []
        # Would call GitHub API for deployments, commits, PRs
        return events

    def _parse_deployment(
        self, incident_id: str, deployment: dict[str, Any]
    ) -> TimelineEvent:
        """Parse a GitHub deployment into a TimelineEvent."""
        return TimelineEvent(
            incident_id=incident_id,
            timestamp=datetime.fromisoformat(
                deployment.get("created_at", "").replace("Z", "+00:00")
            ),
            event_type=EventType.DEPLOYMENT,
            source=EventSource.GITHUB,
            severity=EventSeverity.INFO,
            title=f"Deployment: {deployment.get('environment', 'unknown')}",
            description=deployment.get("description"),
            actor=deployment.get("creator", {}).get("login"),
            metadata={
                "sha": deployment.get("sha"),
                "ref": deployment.get("ref"),
                "environment": deployment.get("environment"),
            },
            raw_data=deployment,
        )


class DatadogCollector(EventCollector):
    """Collect events from Datadog."""

    source = EventSource.DATADOG

    def __init__(self, api_key: str | None = None, app_key: str | None = None):
        self.api_key = api_key
        self.app_key = app_key

    async def collect(
        self,
        incident_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        query: str | None = None,
        **kwargs,
    ) -> list[TimelineEvent]:
        """Collect Datadog events and alerts."""
        events = []
        # Would call Datadog Events API
        return events

    def _parse_event(self, incident_id: str, dd_event: dict[str, Any]) -> TimelineEvent:
        """Parse a Datadog event into a TimelineEvent."""
        alert_type = dd_event.get("alert_type", "info")
        severity = {
            "error": EventSeverity.ERROR,
            "warning": EventSeverity.WARNING,
            "success": EventSeverity.INFO,
            "info": EventSeverity.INFO,
        }.get(alert_type, EventSeverity.INFO)

        return TimelineEvent(
            incident_id=incident_id,
            timestamp=datetime.fromtimestamp(dd_event.get("date_happened", 0)),
            event_type=(
                EventType.ALERT
                if alert_type in ("error", "warning")
                else EventType.METRIC_ANOMALY
            ),
            source=EventSource.DATADOG,
            severity=severity,
            title=dd_event.get("title", "Datadog event"),
            description=dd_event.get("text"),
            actor=dd_event.get("host"),
            tags=dd_event.get("tags", []),
            metadata={"dd_id": dd_event.get("id")},
            raw_data=dd_event,
        )


class PrometheusCollector(EventCollector):
    """Collect alerts from Prometheus/Alertmanager."""

    source = EventSource.PROMETHEUS

    def __init__(self, alertmanager_url: str | None = None):
        self.alertmanager_url = alertmanager_url

    async def collect(
        self,
        incident_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        **kwargs,
    ) -> list[TimelineEvent]:
        """Collect Prometheus alerts."""
        events = []
        # Would call Alertmanager API
        return events

    def _parse_alert(self, incident_id: str, alert: dict[str, Any]) -> TimelineEvent:
        """Parse a Prometheus alert into a TimelineEvent."""
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        severity = labels.get("severity", "warning")

        return TimelineEvent(
            incident_id=incident_id,
            timestamp=datetime.fromisoformat(
                alert.get("startsAt", "").replace("Z", "+00:00")
            ),
            event_type=EventType.ALERT,
            source=EventSource.PROMETHEUS,
            severity=(
                EventSeverity.CRITICAL
                if severity == "critical"
                else EventSeverity.WARNING
            ),
            title=labels.get("alertname", "Prometheus alert"),
            description=annotations.get("description") or annotations.get("summary"),
            actor=labels.get("instance"),
            tags=list(labels.keys()),
            metadata={"labels": labels, "fingerprint": alert.get("fingerprint")},
            raw_data=alert,
        )


class KubernetesCollector(EventCollector):
    """Collect events from Kubernetes."""

    source = EventSource.KUBERNETES

    async def collect(
        self,
        incident_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        namespace: str | None = None,
        **kwargs,
    ) -> list[TimelineEvent]:
        """Collect Kubernetes events."""
        events = []
        # Would use kubernetes client
        return events

    def _parse_k8s_event(
        self, incident_id: str, k8s_event: dict[str, Any]
    ) -> TimelineEvent:
        """Parse a Kubernetes event into a TimelineEvent."""
        event_type_map = {"Normal": EventType.ACTION_TAKEN, "Warning": EventType.ALERT}
        severity_map = {"Normal": EventSeverity.INFO, "Warning": EventSeverity.WARNING}

        k8s_type = k8s_event.get("type", "Normal")

        return TimelineEvent(
            incident_id=incident_id,
            timestamp=datetime.fromisoformat(
                k8s_event.get("lastTimestamp", "").replace("Z", "+00:00")
            ),
            event_type=event_type_map.get(k8s_type, EventType.MANUAL),
            source=EventSource.KUBERNETES,
            severity=severity_map.get(k8s_type, EventSeverity.INFO),
            title=f"{k8s_event.get('reason', 'Event')}: {k8s_event.get('involvedObject', {}).get('name', '')}",
            description=k8s_event.get("message"),
            actor=k8s_event.get("source", {}).get("component"),
            metadata={
                "namespace": k8s_event.get("involvedObject", {}).get("namespace"),
                "kind": k8s_event.get("involvedObject", {}).get("kind"),
                "count": k8s_event.get("count", 1),
            },
            raw_data=k8s_event,
        )


class CompositeCollector:
    """Aggregates multiple collectors to build complete timeline."""

    def __init__(self, collectors: list[EventCollector] | None = None):
        self.collectors = collectors or []

    def add_collector(self, collector: EventCollector) -> None:
        """Add a collector to the composite."""
        self.collectors.append(collector)

    async def collect_all(
        self,
        incident_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        **kwargs,
    ) -> list[TimelineEvent]:
        """Collect events from all registered collectors."""
        all_events = []

        for collector in self.collectors:
            try:
                events = await collector.collect(
                    incident_id=incident_id,
                    start_time=start_time,
                    end_time=end_time,
                    **kwargs,
                )
                all_events.extend(events)
            except Exception as e:
                # Log error but continue with other collectors
                all_events.append(
                    TimelineEvent(
                        id=uuid4(),
                        incident_id=incident_id,
                        timestamp=datetime.now(UTC),
                        event_type=EventType.MANUAL,
                        source=EventSource.SYSTEM,
                        severity=EventSeverity.WARNING,
                        title=f"Failed to collect from {collector.source.value}",
                        description=str(e),
                        tags=["collection_error"],
                    )
                )

        # Sort by timestamp
        all_events.sort(key=lambda e: e.timestamp)
        return all_events


def create_default_collector() -> CompositeCollector:
    """Create a collector with all available sources."""
    return CompositeCollector(
        [
            PagerDutyCollector(),
            SlackCollector(),
            GitHubCollector(),
            DatadogCollector(),
            PrometheusCollector(),
            KubernetesCollector(),
        ]
    )
