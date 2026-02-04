"""Anomaly detection for incidents."""

import hashlib
from collections import defaultdict
from datetime import datetime, timedelta

import structlog

from ..analytics.models import IncidentMetrics
from .models import (
    AnomalyDetection,
    AnomalyType,
    CascadingFailure,
    IncidentSpike,
    Severity,
)

logger = structlog.get_logger()


class AnomalyDetector:
    """Detects anomalies in incident data."""

    def __init__(
        self,
        spike_threshold: float = 2.0,  # Times above baseline
        cascade_window_minutes: int = 15,
        unusual_hour_threshold: float = 0.05,  # 5% of incidents expected
    ):
        self.spike_threshold = spike_threshold
        self.cascade_window_minutes = cascade_window_minutes
        self.unusual_hour_threshold = unusual_hour_threshold

    async def detect_spikes(
        self,
        incidents: list[IncidentMetrics],
        window_hours: int = 4,
    ) -> list[IncidentSpike]:
        """
        Detect spikes in incident count.

        Compares each time window against the baseline to find periods
        with unusually high incident activity.
        """
        if len(incidents) < 10:
            return []

        # Sort incidents by time
        sorted_incidents = sorted(incidents, key=lambda x: x.triggered_at)

        # Calculate baseline (average incidents per window)
        total_duration = (
            sorted_incidents[-1].triggered_at - sorted_incidents[0].triggered_at
        )
        total_windows = max(1, total_duration.total_seconds() / (window_hours * 3600))
        baseline = len(incidents) / total_windows

        if baseline < 0.5:  # Too few incidents overall
            return []

        # Slide window and detect spikes
        spikes = []
        window_delta = timedelta(hours=window_hours)

        # Group incidents by window
        current_window_start = sorted_incidents[0].triggered_at
        current_window_incidents = []

        for incident in sorted_incidents:
            if incident.triggered_at < current_window_start + window_delta:
                current_window_incidents.append(incident)
            else:
                # Check if current window is a spike
                if current_window_incidents:
                    spike_factor = len(current_window_incidents) / baseline
                    if spike_factor >= self.spike_threshold:
                        services = list(
                            set(i.service_name for i in current_window_incidents)
                        )
                        spike = IncidentSpike(
                            spike_id=self._generate_id(
                                f"spike_{current_window_start}"
                            ),
                            detected_at=current_window_start,
                            window_hours=window_hours,
                            incident_count=len(current_window_incidents),
                            baseline_count=baseline,
                            spike_factor=spike_factor,
                            affected_services=services,
                            affected_incident_ids=[
                                i.incident_id for i in current_window_incidents
                            ],
                        )
                        spikes.append(spike)

                # Start new window
                current_window_start = incident.triggered_at
                current_window_incidents = [incident]

        # Check final window
        if current_window_incidents:
            spike_factor = len(current_window_incidents) / baseline
            if spike_factor >= self.spike_threshold:
                services = list(
                    set(i.service_name for i in current_window_incidents)
                )
                spike = IncidentSpike(
                    spike_id=self._generate_id(f"spike_{current_window_start}"),
                    detected_at=current_window_start,
                    window_hours=window_hours,
                    incident_count=len(current_window_incidents),
                    baseline_count=baseline,
                    spike_factor=spike_factor,
                    affected_services=services,
                    affected_incident_ids=[
                        i.incident_id for i in current_window_incidents
                    ],
                )
                spikes.append(spike)

        logger.info("spikes_detected", count=len(spikes))
        return spikes

    async def detect_cascading_failures(
        self,
        incidents: list[IncidentMetrics],
    ) -> list[CascadingFailure]:
        """
        Detect cascading failures across services.

        Identifies when an incident in one service is quickly followed
        by incidents in other services.
        """
        if len(incidents) < 3:
            return []

        # Sort by time
        sorted_incidents = sorted(incidents, key=lambda x: x.triggered_at)
        window = timedelta(minutes=self.cascade_window_minutes)

        cascades = []
        processed_incidents = set()

        for i, trigger_incident in enumerate(sorted_incidents):
            if trigger_incident.incident_id in processed_incidents:
                continue

            # Look for incidents following this one within the window
            cascade_incidents = [trigger_incident]
            cascade_services = {trigger_incident.service_name}

            for follow_incident in sorted_incidents[i + 1 :]:
                time_diff = follow_incident.triggered_at - trigger_incident.triggered_at

                if time_diff > window:
                    break

                if follow_incident.service_name not in cascade_services:
                    cascade_incidents.append(follow_incident)
                    cascade_services.add(follow_incident.service_name)

            # If we have multiple services affected, it might be a cascade
            if len(cascade_services) >= 3:
                cascade = CascadingFailure(
                    cascade_id=self._generate_id(
                        f"cascade_{trigger_incident.incident_id}"
                    ),
                    detected_at=trigger_incident.triggered_at,
                    trigger_service=trigger_incident.service_name,
                    trigger_incident_id=trigger_incident.incident_id,
                    affected_services=list(cascade_services),
                    affected_incident_ids=[i.incident_id for i in cascade_incidents],
                    cascade_window_minutes=self.cascade_window_minutes,
                    total_incidents=len(cascade_incidents),
                )
                cascades.append(cascade)

                # Mark incidents as processed
                for inc in cascade_incidents:
                    processed_incidents.add(inc.incident_id)

        logger.info("cascading_failures_detected", count=len(cascades))
        return cascades

    async def detect_unusual_times(
        self,
        incidents: list[IncidentMetrics],
    ) -> list[AnomalyDetection]:
        """
        Detect incidents occurring at unusual times.

        Flags incidents that occur during off-hours when few incidents
        are typically expected (e.g., 3 AM on weekends).
        """
        if not incidents:
            return []

        # Define unusual hours (late night / early morning)
        unusual_hours = {0, 1, 2, 3, 4, 5}  # Midnight to 6 AM

        # Count incidents per hour to establish baseline
        hour_counts = defaultdict(int)
        for incident in incidents:
            hour_counts[incident.triggered_at.hour] += 1

        total = len(incidents)
        anomalies = []

        for incident in incidents:
            hour = incident.triggered_at.hour
            day = incident.triggered_at.weekday()

            # Check if unusual time
            is_unusual_hour = hour in unusual_hours
            is_weekend = day >= 5  # Saturday or Sunday

            # Calculate how unusual this time is
            hour_frequency = hour_counts[hour] / total if total else 0

            if is_unusual_hour or (is_weekend and hour_frequency < self.unusual_hour_threshold):
                severity = Severity.INFO
                if is_unusual_hour and is_weekend:
                    severity = Severity.MEDIUM

                anomaly_type = AnomalyType.UNUSUAL_HOUR if is_unusual_hour else AnomalyType.UNUSUAL_DAY

                time_str = incident.triggered_at.strftime("%H:%M")
                day_str = incident.triggered_at.strftime("%A")

                anomaly = AnomalyDetection(
                    anomaly_id=self._generate_id(f"unusual_{incident.incident_id}"),
                    anomaly_type=anomaly_type,
                    detected_at=incident.triggered_at,
                    severity=severity,
                    description=f"Incident at unusual time: {time_str} on {day_str}",
                    affected_services=[incident.service_name],
                    affected_incident_ids=[incident.incident_id],
                    metric_value=hour_frequency * 100,
                    baseline_value=self.unusual_hour_threshold * 100,
                )
                anomalies.append(anomaly)

        logger.info("unusual_time_anomalies_detected", count=len(anomalies))
        return anomalies

    async def detect_all_anomalies(
        self,
        incidents: list[IncidentMetrics],
    ) -> list[AnomalyDetection]:
        """
        Run all anomaly detection algorithms.

        Combines spikes, cascades, and unusual times into a unified
        list of anomalies.
        """
        anomalies = []

        # Detect spikes
        spikes = await self.detect_spikes(incidents)
        for spike in spikes:
            anomaly = AnomalyDetection(
                anomaly_id=spike.spike_id,
                anomaly_type=AnomalyType.SPIKE,
                detected_at=spike.detected_at,
                severity=Severity.HIGH if spike.spike_factor > 3 else Severity.MEDIUM,
                description=f"Incident spike: {spike.incident_count} incidents in {spike.window_hours}h "
                f"({spike.spike_factor:.1f}x baseline)",
                affected_services=spike.affected_services,
                affected_incident_ids=spike.affected_incident_ids,
                metric_value=spike.incident_count,
                baseline_value=spike.baseline_count,
                deviation_percent=(spike.spike_factor - 1) * 100,
            )
            anomalies.append(anomaly)

        # Detect cascades
        cascades = await self.detect_cascading_failures(incidents)
        for cascade in cascades:
            anomaly = AnomalyDetection(
                anomaly_id=cascade.cascade_id,
                anomaly_type=AnomalyType.CASCADING,
                detected_at=cascade.detected_at,
                severity=Severity.CRITICAL if len(cascade.affected_services) > 4 else Severity.HIGH,
                description=f"Cascading failure: {len(cascade.affected_services)} services affected "
                f"starting from {cascade.trigger_service}",
                affected_services=cascade.affected_services,
                affected_incident_ids=cascade.affected_incident_ids,
                metric_value=len(cascade.affected_services),
            )
            anomalies.append(anomaly)

        # Detect unusual times (sample only critical/high severity)
        unusual = await self.detect_unusual_times(
            [i for i in incidents if i.severity in ("critical", "high")]
        )
        anomalies.extend(unusual)

        return sorted(anomalies, key=lambda x: x.detected_at, reverse=True)

    def _generate_id(self, base: str) -> str:
        """Generate a deterministic ID."""
        return hashlib.md5(base.encode()).hexdigest()[:12]
