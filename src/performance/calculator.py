"""Calculate MTTR, MTTA, incident volume, and on-call load distribution."""

from datetime import datetime, timedelta
from statistics import mean, stdev

import structlog

from .models import (
    BurnoutIndicator,
    IncidentVolume,
    OnCallStats,
    SLACompliance,
    TeamMetrics,
    TimeDistribution,
    TimeGranularity,
    WorkloadDistribution,
)

logger = structlog.get_logger()


class PerformanceCalculator:
    """Calculate performance metrics from incident data."""

    # Default SLA targets in minutes by severity
    DEFAULT_SLA_TARGETS = {
        "critical": 15,
        "high": 30,
        "medium": 60,
        "low": 240,
    }

    # Burnout thresholds
    PAGE_THRESHOLD_WEEKLY = 50
    OFF_HOURS_PAGE_THRESHOLD_WEEKLY = 10
    CONSECUTIVE_ONCALL_THRESHOLD_DAYS = 7

    def __init__(self, sla_targets: dict[str, int] | None = None):
        """Initialize calculator with optional custom SLA targets."""
        self.sla_targets = sla_targets or self.DEFAULT_SLA_TARGETS

    def calculate_team_metrics(
        self,
        incidents: list[dict],
        period_start: datetime,
        period_end: datetime,
        team_name: str | None = None,
        service_name: str | None = None,
        previous_metrics: "TeamMetrics | None" = None,
    ) -> TeamMetrics:
        """
        Calculate team-level performance metrics.

        Args:
            incidents: List of incident dicts with keys:
                - id, title, severity, service_name, team_name
                - triggered_at, acknowledged_at, resolved_at
            period_start: Start of the period
            period_end: End of the period
            team_name: Optional team filter
            service_name: Optional service filter
            previous_metrics: Previous period metrics for comparison

        Returns:
            TeamMetrics with MTTR, MTTA, counts, and SLA metrics
        """
        # Filter incidents by period and optional filters
        filtered = self._filter_incidents(
            incidents, period_start, period_end, team_name, service_name
        )

        if not filtered:
            return TeamMetrics(
                team_name=team_name,
                service_name=service_name,
                period_start=period_start,
                period_end=period_end,
            )

        # Calculate MTTR (Mean Time to Resolve)
        resolution_times = []
        for inc in filtered:
            triggered = self._parse_datetime(inc.get("triggered_at"))
            resolved = self._parse_datetime(inc.get("resolved_at"))
            if triggered and resolved:
                resolution_times.append((resolved - triggered).total_seconds() / 60)

        mttr = mean(resolution_times) if resolution_times else None

        # Calculate MTTA (Mean Time to Acknowledge)
        ack_times = []
        for inc in filtered:
            triggered = self._parse_datetime(inc.get("triggered_at"))
            acked = self._parse_datetime(inc.get("acknowledged_at"))
            if triggered and acked:
                ack_times.append((acked - triggered).total_seconds() / 60)

        mtta = mean(ack_times) if ack_times else None

        # Count by severity
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for inc in filtered:
            sev = inc.get("severity", "medium").lower()
            if sev in severity_counts:
                severity_counts[sev] += 1

        # Count resolved vs open
        resolved_count = sum(1 for inc in filtered if inc.get("resolved_at"))
        open_count = len(filtered) - resolved_count

        # SLA compliance
        sla_met = 0
        sla_breached = 0
        for inc in filtered:
            if self._is_sla_met(inc):
                sla_met += 1
            else:
                sla_breached += 1

        sla_compliance = (sla_met / len(filtered) * 100) if filtered else None

        # Calculate changes from previous period
        mttr_change = None
        mtta_change = None
        count_change = None

        if previous_metrics:
            if mttr and previous_metrics.mttr_minutes:
                mttr_change = (
                    (mttr - previous_metrics.mttr_minutes)
                    / previous_metrics.mttr_minutes
                    * 100
                )
            if mtta and previous_metrics.mtta_minutes:
                mtta_change = (
                    (mtta - previous_metrics.mtta_minutes)
                    / previous_metrics.mtta_minutes
                    * 100
                )
            if previous_metrics.total_incidents > 0:
                count_change = (
                    (len(filtered) - previous_metrics.total_incidents)
                    / previous_metrics.total_incidents
                    * 100
                )

        logger.info(
            "team_metrics_calculated",
            team=team_name,
            service=service_name,
            total_incidents=len(filtered),
            mttr_minutes=mttr,
            mtta_minutes=mtta,
        )

        return TeamMetrics(
            team_name=team_name,
            service_name=service_name,
            period_start=period_start,
            period_end=period_end,
            mttr_minutes=mttr,
            mtta_minutes=mtta,
            total_incidents=len(filtered),
            resolved_incidents=resolved_count,
            open_incidents=open_count,
            critical_count=severity_counts["critical"],
            high_count=severity_counts["high"],
            medium_count=severity_counts["medium"],
            low_count=severity_counts["low"],
            sla_met_count=sla_met,
            sla_breached_count=sla_breached,
            sla_compliance_percent=sla_compliance,
            mttr_change_percent=mttr_change,
            mtta_change_percent=mtta_change,
            incident_count_change_percent=count_change,
        )

    def calculate_oncall_stats(
        self,
        incidents: list[dict],
        responder_id: str,
        responder_name: str,
        period_start: datetime,
        period_end: datetime,
        responder_email: str | None = None,
        team_name: str | None = None,
        oncall_hours: float | None = None,
    ) -> OnCallStats:
        """
        Calculate on-call statistics for a single responder.

        Args:
            incidents: List of incidents assigned to/handled by this responder
            responder_id: Unique responder ID
            responder_name: Display name
            period_start: Start of period
            period_end: End of period
            responder_email: Optional email
            team_name: Optional team name
            oncall_hours: Optional total on-call hours in period

        Returns:
            OnCallStats with page counts, response times, and distribution
        """
        # Filter to incidents handled by this responder
        my_incidents = [
            inc
            for inc in incidents
            if responder_id in inc.get("assigned_to", [])
            or responder_id == inc.get("responder_id")
            or responder_name in inc.get("assigned_to", [])
        ]

        # Filter by time period
        my_incidents = self._filter_incidents(my_incidents, period_start, period_end)

        # Count acknowledgments and escalations
        acked = sum(1 for inc in my_incidents if inc.get("acknowledged_at"))
        escalated = sum(1 for inc in my_incidents if inc.get("escalated"))
        reassigned = sum(1 for inc in my_incidents if inc.get("reassigned"))

        # Calculate response times
        ack_times = []
        resolution_times = []
        for inc in my_incidents:
            triggered = self._parse_datetime(inc.get("triggered_at"))
            if triggered:
                ack_time = self._parse_datetime(inc.get("acknowledged_at"))
                if ack_time:
                    ack_times.append((ack_time - triggered).total_seconds() / 60)

                resolved = self._parse_datetime(inc.get("resolved_at"))
                if resolved:
                    resolution_times.append(
                        (resolved - triggered).total_seconds() / 60
                    )

        # Incident breakdown by severity
        by_severity: dict[str, int] = {}
        for inc in my_incidents:
            sev = inc.get("severity", "medium").lower()
            by_severity[sev] = by_severity.get(sev, 0) + 1

        # Incident breakdown by hour
        by_hour: dict[int, int] = {h: 0 for h in range(24)}
        for inc in my_incidents:
            triggered = self._parse_datetime(inc.get("triggered_at"))
            if triggered:
                by_hour[triggered.hour] += 1

        # Off-hours analysis
        off_hours = 0
        weekend = 0
        night = 0
        for inc in my_incidents:
            triggered = self._parse_datetime(inc.get("triggered_at"))
            if triggered:
                if self._is_off_hours(triggered):
                    off_hours += 1
                if triggered.weekday() >= 5:
                    weekend += 1
                if triggered.hour < 6 or triggered.hour >= 22:
                    night += 1

        # Quality metrics
        false_positives = sum(
            1
            for inc in my_incidents
            if inc.get("root_cause") == "false_positive"
            or inc.get("status") == "false_alarm"
        )
        auto_resolved = sum(
            1 for inc in my_incidents if inc.get("resolution_type") == "auto"
        )

        logger.info(
            "oncall_stats_calculated",
            responder_id=responder_id,
            total_pages=len(my_incidents),
            off_hours_pages=off_hours,
        )

        return OnCallStats(
            responder_id=responder_id,
            responder_name=responder_name,
            responder_email=responder_email,
            team_name=team_name,
            period_start=period_start,
            period_end=period_end,
            total_pages=len(my_incidents),
            pages_acknowledged=acked,
            pages_escalated=escalated,
            pages_reassigned=reassigned,
            avg_ack_time_minutes=mean(ack_times) if ack_times else None,
            avg_resolution_time_minutes=(
                mean(resolution_times) if resolution_times else None
            ),
            total_oncall_hours=oncall_hours,
            incidents_by_severity=by_severity,
            incidents_by_hour=by_hour,
            off_hours_pages=off_hours,
            weekend_pages=weekend,
            night_pages=night,
            false_positive_count=false_positives,
            auto_resolved_count=auto_resolved,
        )

    def calculate_incident_volume(
        self,
        incidents: list[dict],
        period_start: datetime,
        period_end: datetime,
        granularity: TimeGranularity = TimeGranularity.DAILY,
    ) -> IncidentVolume:
        """
        Calculate incident volume distribution.

        Args:
            incidents: List of incident dicts
            period_start: Start of period
            period_end: End of period
            granularity: Time granularity for breakdown

        Returns:
            IncidentVolume with distribution by time, severity, service
        """
        filtered = self._filter_incidents(incidents, period_start, period_end)

        # Initialize counters
        by_hour: dict[int, int] = {h: 0 for h in range(24)}
        by_dow: dict[int, int] = {d: 0 for d in range(7)}
        by_date: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        by_service: dict[str, int] = {}
        by_team: dict[str, int] = {}

        for inc in filtered:
            triggered = self._parse_datetime(inc.get("triggered_at"))
            if triggered:
                by_hour[triggered.hour] += 1
                by_dow[triggered.weekday()] += 1

                date_key = triggered.strftime("%Y-%m-%d")
                by_date[date_key] = by_date.get(date_key, 0) + 1

            # By category
            sev = inc.get("severity", "medium").lower()
            by_severity[sev] = by_severity.get(sev, 0) + 1

            service = inc.get("service_name", "unknown")
            by_service[service] = by_service.get(service, 0) + 1

            team = inc.get("team_name")
            if team:
                by_team[team] = by_team.get(team, 0) + 1

        # Calculate aggregates
        total = len(filtered)
        days_in_period = max(1, (period_end - period_start).days)
        daily_avg = total / days_in_period

        # Find peaks
        peak_hour = max(by_hour.items(), key=lambda x: x[1])[0] if by_hour else None
        peak_day = max(by_dow.items(), key=lambda x: x[1])[0] if by_dow else None

        return IncidentVolume(
            period_start=period_start,
            period_end=period_end,
            granularity=granularity,
            by_hour=by_hour,
            by_day_of_week=by_dow,
            by_date=by_date,
            total_count=total,
            daily_average=daily_avg,
            peak_hour=peak_hour,
            peak_day=peak_day,
            by_severity=by_severity,
            by_service=by_service,
            by_team=by_team,
        )

    def calculate_time_distribution(
        self,
        incidents: list[dict],
        period_start: datetime,
        period_end: datetime,
    ) -> TimeDistribution:
        """
        Calculate time distribution (business hours vs off-hours).

        Args:
            incidents: List of incident dicts
            period_start: Start of period
            period_end: End of period

        Returns:
            TimeDistribution with business/off-hours breakdown
        """
        filtered = self._filter_incidents(incidents, period_start, period_end)

        business = 0
        off_hours = 0
        weekend = 0

        hourly_counts: dict[int, int] = {h: 0 for h in range(24)}
        daily_counts: dict[int, int] = {d: 0 for d in range(7)}

        for inc in filtered:
            triggered = self._parse_datetime(inc.get("triggered_at"))
            if not triggered:
                continue

            hourly_counts[triggered.hour] += 1
            daily_counts[triggered.weekday()] += 1

            if triggered.weekday() >= 5:
                weekend += 1
            elif 9 <= triggered.hour < 17:
                business += 1
            else:
                off_hours += 1

        total = len(filtered) or 1  # Avoid division by zero

        # Find busiest/quietest
        busiest_hour = max(hourly_counts.items(), key=lambda x: x[1])[0]
        quietest_hour = min(hourly_counts.items(), key=lambda x: x[1])[0]
        busiest_day = max(daily_counts.items(), key=lambda x: x[1])[0]
        quietest_day = min(daily_counts.items(), key=lambda x: x[1])[0]

        return TimeDistribution(
            period_start=period_start,
            period_end=period_end,
            business_hours_count=business,
            off_hours_count=off_hours,
            weekend_count=weekend,
            business_hours_percent=business / total * 100,
            off_hours_percent=off_hours / total * 100,
            weekend_percent=weekend / total * 100,
            busiest_hour=busiest_hour,
            busiest_day=busiest_day,
            quietest_hour=quietest_hour,
            quietest_day=quietest_day,
        )

    def calculate_workload_distribution(
        self,
        oncall_stats: list[OnCallStats],
        period_start: datetime,
        period_end: datetime,
        team_name: str | None = None,
    ) -> WorkloadDistribution:
        """
        Calculate workload distribution across responders.

        Args:
            oncall_stats: List of OnCallStats for each responder
            period_start: Start of period
            period_end: End of period
            team_name: Optional team filter

        Returns:
            WorkloadDistribution with fairness metrics
        """
        if not oncall_stats:
            return WorkloadDistribution(
                period_start=period_start,
                period_end=period_end,
                team_name=team_name,
            )

        # Get incident counts per responder
        counts = {stat.responder_name: stat.total_pages for stat in oncall_stats}
        values = list(counts.values())

        total_incidents = sum(values)
        total_responders = len(oncall_stats)
        avg = total_incidents / total_responders if total_responders > 0 else 0

        # Calculate standard deviation
        std = stdev(values) if len(values) > 1 else 0

        # Calculate Gini coefficient (measure of inequality)
        gini = self._calculate_gini(values) if values else None

        # Top responder percentage
        max_count = max(values) if values else 0
        top_percent = (max_count / total_incidents * 100) if total_incidents > 0 else 0

        return WorkloadDistribution(
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            total_responders=total_responders,
            total_incidents=total_incidents,
            avg_incidents_per_responder=avg,
            std_dev_incidents=std,
            gini_coefficient=gini,
            top_responder_percent=top_percent,
            responder_counts=counts,
        )

    def calculate_sla_compliance(
        self,
        incidents: list[dict],
        period_start: datetime,
        period_end: datetime,
        team_name: str | None = None,
        service_name: str | None = None,
        previous_compliance: SLACompliance | None = None,
    ) -> SLACompliance:
        """
        Calculate SLA compliance metrics.

        Args:
            incidents: List of incident dicts
            period_start: Start of period
            period_end: End of period
            team_name: Optional team filter
            service_name: Optional service filter
            previous_compliance: Previous period for comparison

        Returns:
            SLACompliance with overall and per-severity breakdown
        """
        filtered = self._filter_incidents(
            incidents, period_start, period_end, team_name, service_name
        )

        if not filtered:
            return SLACompliance(
                period_start=period_start,
                period_end=period_end,
                team_name=team_name,
                service_name=service_name,
                sla_targets=self.sla_targets,
            )

        sla_met = 0
        sla_breached = 0
        by_severity: dict[str, dict[str, float]] = {}

        for sev in self.sla_targets:
            by_severity[sev] = {"met": 0, "breached": 0, "percent": 0.0}

        for inc in filtered:
            sev = inc.get("severity", "medium").lower()
            if sev not in by_severity:
                sev = "medium"

            if self._is_sla_met(inc):
                sla_met += 1
                by_severity[sev]["met"] += 1
            else:
                sla_breached += 1
                by_severity[sev]["breached"] += 1

        # Calculate percentages
        total = len(filtered)
        compliance_percent = sla_met / total * 100

        for sev, stats in by_severity.items():
            sev_total = stats["met"] + stats["breached"]
            if sev_total > 0:
                stats["percent"] = stats["met"] / sev_total * 100

        # Comparison to previous
        prev_percent = (
            previous_compliance.compliance_percent if previous_compliance else None
        )
        change = compliance_percent - prev_percent if prev_percent is not None else None

        return SLACompliance(
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            service_name=service_name,
            total_incidents=total,
            sla_met=sla_met,
            sla_breached=sla_breached,
            compliance_percent=compliance_percent,
            by_severity=by_severity,
            sla_targets=self.sla_targets,
            previous_compliance_percent=prev_percent,
            compliance_change_percent=change,
        )

    def calculate_burnout_indicator(
        self,
        oncall_stats: OnCallStats,
    ) -> BurnoutIndicator:
        """
        Calculate burnout risk indicators for a responder.

        Args:
            oncall_stats: OnCallStats for the responder

        Returns:
            BurnoutIndicator with risk score and recommendations
        """
        # Calculate risk factors
        period_days = max(
            1, (oncall_stats.period_end - oncall_stats.period_start).days
        )
        weekly_factor = 7 / period_days

        weekly_pages = oncall_stats.total_pages * weekly_factor
        weekly_off_hours = oncall_stats.off_hours_pages * weekly_factor

        pages_per_hour = (
            oncall_stats.total_pages / oncall_stats.total_oncall_hours
            if oncall_stats.total_oncall_hours and oncall_stats.total_oncall_hours > 0
            else 0
        )

        # Check thresholds
        exceeds_pages = weekly_pages > self.PAGE_THRESHOLD_WEEKLY
        exceeds_off_hours = weekly_off_hours > self.OFF_HOURS_PAGE_THRESHOLD_WEEKLY
        exceeds_consecutive = False  # Would need additional data

        # Calculate risk score (0-100)
        risk_score = 0

        # Page volume factor (up to 40 points)
        if weekly_pages > self.PAGE_THRESHOLD_WEEKLY:
            risk_score += min(40, (weekly_pages / self.PAGE_THRESHOLD_WEEKLY - 1) * 20)

        # Off-hours factor (up to 30 points)
        if weekly_off_hours > self.OFF_HOURS_PAGE_THRESHOLD_WEEKLY:
            risk_score += min(
                30, (weekly_off_hours / self.OFF_HOURS_PAGE_THRESHOLD_WEEKLY - 1) * 15
            )

        # Night pages factor (up to 20 points)
        night_ratio = (
            oncall_stats.night_pages / oncall_stats.total_pages
            if oncall_stats.total_pages > 0
            else 0
        )
        if night_ratio > 0.3:
            risk_score += min(20, night_ratio * 50)

        # Intensity factor (up to 10 points)
        if pages_per_hour > 0.5:
            risk_score += min(10, pages_per_hour * 10)

        risk_score = min(100, risk_score)

        # Determine risk level
        if risk_score >= 75:
            risk_level = "critical"
        elif risk_score >= 50:
            risk_level = "high"
        elif risk_score >= 25:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Generate recommendations
        recommendations = []
        if exceeds_pages:
            recommendations.append(
                "Consider redistributing on-call duties to reduce page volume"
            )
        if exceeds_off_hours:
            recommendations.append(
                "Review alert thresholds to reduce off-hours noise"
            )
        if night_ratio > 0.3:
            recommendations.append(
                "High proportion of night pages - consider follow-the-sun rotation"
            )
        if pages_per_hour > 0.5:
            recommendations.append(
                "High page intensity - consider alert consolidation"
            )

        logger.info(
            "burnout_indicator_calculated",
            responder=oncall_stats.responder_name,
            risk_score=risk_score,
            risk_level=risk_level,
        )

        return BurnoutIndicator(
            responder_id=oncall_stats.responder_id,
            responder_name=oncall_stats.responder_name,
            team_name=oncall_stats.team_name,
            period_start=oncall_stats.period_start,
            period_end=oncall_stats.period_end,
            total_pages=oncall_stats.total_pages,
            off_hours_pages=oncall_stats.off_hours_pages,
            consecutive_oncall_days=0,  # Would need additional data
            pages_per_oncall_hour=pages_per_hour,
            exceeds_page_threshold=exceeds_pages,
            exceeds_off_hours_threshold=exceeds_off_hours,
            exceeds_consecutive_days_threshold=exceeds_consecutive,
            risk_score=risk_score,
            risk_level=risk_level,
            recommendations=recommendations,
        )

    # --- Helper Methods ---

    def _filter_incidents(
        self,
        incidents: list[dict],
        period_start: datetime,
        period_end: datetime,
        team_name: str | None = None,
        service_name: str | None = None,
    ) -> list[dict]:
        """Filter incidents by time period and optional filters."""
        result = []
        for inc in incidents:
            triggered = self._parse_datetime(inc.get("triggered_at"))
            if not triggered:
                continue
            if triggered < period_start or triggered > period_end:
                continue
            if team_name and inc.get("team_name") != team_name:
                continue
            if service_name and inc.get("service_name") != service_name:
                continue
            result.append(inc)
        return result

    def _parse_datetime(self, value) -> datetime | None:
        """Parse datetime from various formats."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                pass
        return None

    def _is_sla_met(self, incident: dict) -> bool:
        """Check if SLA was met for an incident."""
        triggered = self._parse_datetime(incident.get("triggered_at"))
        resolved = self._parse_datetime(incident.get("resolved_at"))

        if not triggered or not resolved:
            return False

        resolution_minutes = (resolved - triggered).total_seconds() / 60
        severity = incident.get("severity", "medium").lower()
        target = self.sla_targets.get(severity, 60)

        return resolution_minutes <= target

    def _is_off_hours(self, dt: datetime) -> bool:
        """Check if datetime is off-hours (outside 9-17 weekdays)."""
        if dt.weekday() >= 5:  # Weekend
            return True
        if dt.hour < 9 or dt.hour >= 17:  # Outside business hours
            return True
        return False

    def _calculate_gini(self, values: list[int | float]) -> float:
        """Calculate Gini coefficient (0 = equal, 1 = unequal)."""
        if not values or sum(values) == 0:
            return 0.0

        sorted_vals = sorted(values)
        n = len(sorted_vals)
        cumsum = 0
        for i, val in enumerate(sorted_vals):
            cumsum += val * (n - i)

        total = sum(values)
        return (2 * cumsum) / (n * total) - (n + 1) / n
