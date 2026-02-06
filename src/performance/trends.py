"""Trend analysis for performance metrics (week-over-week, month-over-month)."""

from datetime import datetime, timedelta
from statistics import mean, stdev

import structlog

from .calculator import PerformanceCalculator
from .models import (
    PerformanceTrend,
    TeamMetrics,
    TrendDirection,
)

logger = structlog.get_logger()


class TrendAnalyzer:
    """Analyze trends in performance metrics over time."""

    def __init__(self, calculator: PerformanceCalculator | None = None):
        """Initialize with optional calculator."""
        self.calculator = calculator or PerformanceCalculator()

    def calculate_mttr_trend(
        self,
        incidents: list[dict],
        period_start: datetime,
        period_end: datetime,
        team_name: str | None = None,
        service_name: str | None = None,
        comparison_periods: int = 1,
    ) -> PerformanceTrend:
        """
        Calculate MTTR trend vs previous period(s).

        Args:
            incidents: All incidents (will be filtered by period)
            period_start: Start of current period
            period_end: End of current period
            team_name: Optional team filter
            service_name: Optional service filter
            comparison_periods: Number of previous periods to compare

        Returns:
            PerformanceTrend with MTTR change analysis
        """
        period_duration = period_end - period_start

        # Current period metrics
        current_metrics = self.calculator.calculate_team_metrics(
            incidents=incidents,
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            service_name=service_name,
        )

        # Previous period metrics
        prev_start = period_start - period_duration
        prev_end = period_start
        previous_metrics = self.calculator.calculate_team_metrics(
            incidents=incidents,
            period_start=prev_start,
            period_end=prev_end,
            team_name=team_name,
            service_name=service_name,
        )

        current_value = current_metrics.mttr_minutes or 0
        previous_value = previous_metrics.mttr_minutes or 0

        change_absolute = current_value - previous_value
        change_percent = (
            (change_absolute / previous_value * 100) if previous_value > 0 else 0
        )

        # For MTTR, lower is better
        if change_percent < -5:
            direction = TrendDirection.IMPROVING
            is_improvement = True
        elif change_percent > 5:
            direction = TrendDirection.DECLINING
            is_improvement = False
        else:
            direction = TrendDirection.STABLE
            is_improvement = False

        # Build historical data points
        data_points = self._build_historical_data_points(
            incidents=incidents,
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            service_name=service_name,
            metric_name="mttr",
            num_periods=comparison_periods + 1,
        )

        logger.info(
            "mttr_trend_calculated",
            current=current_value,
            previous=previous_value,
            change_percent=change_percent,
            direction=direction.value,
        )

        return PerformanceTrend(
            metric_name="mttr",
            team_name=team_name,
            service_name=service_name,
            period_start=period_start,
            period_end=period_end,
            comparison_period_start=prev_start,
            comparison_period_end=prev_end,
            current_value=current_value,
            previous_value=previous_value,
            change_absolute=change_absolute,
            change_percent=change_percent,
            direction=direction,
            is_improvement=is_improvement,
            data_points=data_points,
        )

    def calculate_mtta_trend(
        self,
        incidents: list[dict],
        period_start: datetime,
        period_end: datetime,
        team_name: str | None = None,
        service_name: str | None = None,
        comparison_periods: int = 1,
    ) -> PerformanceTrend:
        """
        Calculate MTTA trend vs previous period(s).

        Args:
            incidents: All incidents
            period_start: Start of current period
            period_end: End of current period
            team_name: Optional team filter
            service_name: Optional service filter
            comparison_periods: Number of previous periods to compare

        Returns:
            PerformanceTrend with MTTA change analysis
        """
        period_duration = period_end - period_start

        # Current period metrics
        current_metrics = self.calculator.calculate_team_metrics(
            incidents=incidents,
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            service_name=service_name,
        )

        # Previous period metrics
        prev_start = period_start - period_duration
        prev_end = period_start
        previous_metrics = self.calculator.calculate_team_metrics(
            incidents=incidents,
            period_start=prev_start,
            period_end=prev_end,
            team_name=team_name,
            service_name=service_name,
        )

        current_value = current_metrics.mtta_minutes or 0
        previous_value = previous_metrics.mtta_minutes or 0

        change_absolute = current_value - previous_value
        change_percent = (
            (change_absolute / previous_value * 100) if previous_value > 0 else 0
        )

        # For MTTA, lower is better
        if change_percent < -5:
            direction = TrendDirection.IMPROVING
            is_improvement = True
        elif change_percent > 5:
            direction = TrendDirection.DECLINING
            is_improvement = False
        else:
            direction = TrendDirection.STABLE
            is_improvement = False

        data_points = self._build_historical_data_points(
            incidents=incidents,
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            service_name=service_name,
            metric_name="mtta",
            num_periods=comparison_periods + 1,
        )

        return PerformanceTrend(
            metric_name="mtta",
            team_name=team_name,
            service_name=service_name,
            period_start=period_start,
            period_end=period_end,
            comparison_period_start=prev_start,
            comparison_period_end=prev_end,
            current_value=current_value,
            previous_value=previous_value,
            change_absolute=change_absolute,
            change_percent=change_percent,
            direction=direction,
            is_improvement=is_improvement,
            data_points=data_points,
        )

    def calculate_incident_count_trend(
        self,
        incidents: list[dict],
        period_start: datetime,
        period_end: datetime,
        team_name: str | None = None,
        service_name: str | None = None,
        comparison_periods: int = 1,
    ) -> PerformanceTrend:
        """
        Calculate incident count trend vs previous period(s).

        Args:
            incidents: All incidents
            period_start: Start of current period
            period_end: End of current period
            team_name: Optional team filter
            service_name: Optional service filter
            comparison_periods: Number of previous periods to compare

        Returns:
            PerformanceTrend with incident count change analysis
        """
        period_duration = period_end - period_start

        # Current period metrics
        current_metrics = self.calculator.calculate_team_metrics(
            incidents=incidents,
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            service_name=service_name,
        )

        # Previous period metrics
        prev_start = period_start - period_duration
        prev_end = period_start
        previous_metrics = self.calculator.calculate_team_metrics(
            incidents=incidents,
            period_start=prev_start,
            period_end=prev_end,
            team_name=team_name,
            service_name=service_name,
        )

        current_value = float(current_metrics.total_incidents)
        previous_value = float(previous_metrics.total_incidents)

        change_absolute = current_value - previous_value
        change_percent = (
            (change_absolute / previous_value * 100) if previous_value > 0 else 0
        )

        # For incident count, lower is better
        if change_percent < -10:
            direction = TrendDirection.IMPROVING
            is_improvement = True
        elif change_percent > 10:
            direction = TrendDirection.DECLINING
            is_improvement = False
        else:
            direction = TrendDirection.STABLE
            is_improvement = False

        data_points = self._build_historical_data_points(
            incidents=incidents,
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            service_name=service_name,
            metric_name="incident_count",
            num_periods=comparison_periods + 1,
        )

        return PerformanceTrend(
            metric_name="incident_count",
            team_name=team_name,
            service_name=service_name,
            period_start=period_start,
            period_end=period_end,
            comparison_period_start=prev_start,
            comparison_period_end=prev_end,
            current_value=current_value,
            previous_value=previous_value,
            change_absolute=change_absolute,
            change_percent=change_percent,
            direction=direction,
            is_improvement=is_improvement,
            data_points=data_points,
        )

    def calculate_sla_compliance_trend(
        self,
        incidents: list[dict],
        period_start: datetime,
        period_end: datetime,
        team_name: str | None = None,
        service_name: str | None = None,
        comparison_periods: int = 1,
    ) -> PerformanceTrend:
        """
        Calculate SLA compliance trend vs previous period(s).

        Args:
            incidents: All incidents
            period_start: Start of current period
            period_end: End of current period
            team_name: Optional team filter
            service_name: Optional service filter
            comparison_periods: Number of previous periods to compare

        Returns:
            PerformanceTrend with SLA compliance change analysis
        """
        period_duration = period_end - period_start

        # Current period compliance
        current_sla = self.calculator.calculate_sla_compliance(
            incidents=incidents,
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            service_name=service_name,
        )

        # Previous period compliance
        prev_start = period_start - period_duration
        prev_end = period_start
        previous_sla = self.calculator.calculate_sla_compliance(
            incidents=incidents,
            period_start=prev_start,
            period_end=prev_end,
            team_name=team_name,
            service_name=service_name,
        )

        current_value = current_sla.compliance_percent
        previous_value = previous_sla.compliance_percent

        change_absolute = current_value - previous_value
        change_percent = (
            (change_absolute / previous_value * 100) if previous_value > 0 else 0
        )

        # For SLA compliance, higher is better
        if change_absolute > 2:  # >2% improvement
            direction = TrendDirection.IMPROVING
            is_improvement = True
        elif change_absolute < -2:  # >2% decline
            direction = TrendDirection.DECLINING
            is_improvement = False
        else:
            direction = TrendDirection.STABLE
            is_improvement = False

        data_points = self._build_historical_data_points(
            incidents=incidents,
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            service_name=service_name,
            metric_name="sla_compliance",
            num_periods=comparison_periods + 1,
        )

        return PerformanceTrend(
            metric_name="sla_compliance",
            team_name=team_name,
            service_name=service_name,
            period_start=period_start,
            period_end=period_end,
            comparison_period_start=prev_start,
            comparison_period_end=prev_end,
            current_value=current_value,
            previous_value=previous_value,
            change_absolute=change_absolute,
            change_percent=change_percent,
            direction=direction,
            is_improvement=is_improvement,
            data_points=data_points,
        )

    def calculate_all_trends(
        self,
        incidents: list[dict],
        period_start: datetime,
        period_end: datetime,
        team_name: str | None = None,
        service_name: str | None = None,
        comparison_periods: int = 4,
    ) -> list[PerformanceTrend]:
        """
        Calculate all key performance trends.

        Args:
            incidents: All incidents
            period_start: Start of current period
            period_end: End of current period
            team_name: Optional team filter
            service_name: Optional service filter
            comparison_periods: Number of historical periods for charting

        Returns:
            List of PerformanceTrend for all key metrics
        """
        trends = [
            self.calculate_mttr_trend(
                incidents, period_start, period_end, team_name, service_name,
                comparison_periods,
            ),
            self.calculate_mtta_trend(
                incidents, period_start, period_end, team_name, service_name,
                comparison_periods,
            ),
            self.calculate_incident_count_trend(
                incidents, period_start, period_end, team_name, service_name,
                comparison_periods,
            ),
            self.calculate_sla_compliance_trend(
                incidents, period_start, period_end, team_name, service_name,
                comparison_periods,
            ),
        ]

        logger.info(
            "all_trends_calculated",
            team=team_name,
            service=service_name,
            num_trends=len(trends),
        )

        return trends

    def week_over_week(
        self,
        incidents: list[dict],
        reference_date: datetime | None = None,
        team_name: str | None = None,
        service_name: str | None = None,
    ) -> list[PerformanceTrend]:
        """
        Calculate week-over-week trends.

        Args:
            incidents: All incidents
            reference_date: Reference date (defaults to now)
            team_name: Optional team filter
            service_name: Optional service filter

        Returns:
            List of PerformanceTrend comparing this week to last week
        """
        if reference_date is None:
            reference_date = datetime.utcnow()

        # Calculate week boundaries (Monday to Sunday)
        days_since_monday = reference_date.weekday()
        week_start = (
            reference_date - timedelta(days=days_since_monday)
        ).replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)

        return self.calculate_all_trends(
            incidents=incidents,
            period_start=week_start,
            period_end=week_end,
            team_name=team_name,
            service_name=service_name,
            comparison_periods=4,  # 4 weeks of history
        )

    def month_over_month(
        self,
        incidents: list[dict],
        reference_date: datetime | None = None,
        team_name: str | None = None,
        service_name: str | None = None,
    ) -> list[PerformanceTrend]:
        """
        Calculate month-over-month trends.

        Args:
            incidents: All incidents
            reference_date: Reference date (defaults to now)
            team_name: Optional team filter
            service_name: Optional service filter

        Returns:
            List of PerformanceTrend comparing this month to last month
        """
        if reference_date is None:
            reference_date = datetime.utcnow()

        # Calculate month boundaries
        month_start = reference_date.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1)
        month_end = next_month

        return self.calculate_all_trends(
            incidents=incidents,
            period_start=month_start,
            period_end=month_end,
            team_name=team_name,
            service_name=service_name,
            comparison_periods=3,  # 3 months of history
        )

    def detect_anomalies(
        self,
        incidents: list[dict],
        period_start: datetime,
        period_end: datetime,
        team_name: str | None = None,
        service_name: str | None = None,
        threshold_std_dev: float = 2.0,
    ) -> list[dict]:
        """
        Detect anomalies in performance metrics.

        Args:
            incidents: All incidents
            period_start: Start of period
            period_end: End of period
            team_name: Optional team filter
            service_name: Optional service filter
            threshold_std_dev: Number of standard deviations for anomaly

        Returns:
            List of anomaly dicts with metric, value, expected, and severity
        """
        anomalies = []
        period_duration = period_end - period_start

        # Build historical data (last 4 periods)
        historical_metrics: list[TeamMetrics] = []
        for i in range(1, 5):
            hist_end = period_start - (period_duration * (i - 1))
            hist_start = hist_end - period_duration
            metrics = self.calculator.calculate_team_metrics(
                incidents=incidents,
                period_start=hist_start,
                period_end=hist_end,
                team_name=team_name,
                service_name=service_name,
            )
            historical_metrics.append(metrics)

        # Current period
        current = self.calculator.calculate_team_metrics(
            incidents=incidents,
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            service_name=service_name,
        )

        # Check MTTR anomaly
        mttr_values = [m.mttr_minutes for m in historical_metrics if m.mttr_minutes]
        if mttr_values and current.mttr_minutes:
            avg_mttr = mean(mttr_values)
            std_mttr = stdev(mttr_values) if len(mttr_values) > 1 else avg_mttr * 0.2
            if abs(current.mttr_minutes - avg_mttr) > threshold_std_dev * std_mttr:
                anomalies.append({
                    "metric": "mttr",
                    "current_value": current.mttr_minutes,
                    "expected_value": avg_mttr,
                    "std_dev": std_mttr,
                    "deviation": (current.mttr_minutes - avg_mttr) / std_mttr,
                    "severity": (
                        "high" if current.mttr_minutes > avg_mttr else "info"
                    ),
                    "message": (
                        f"MTTR is {current.mttr_minutes:.1f} min, "
                        f"expected ~{avg_mttr:.1f} min"
                    ),
                })

        # Check incident count anomaly
        count_values = [m.total_incidents for m in historical_metrics]
        if count_values and current.total_incidents:
            avg_count = mean(count_values)
            std_count = (
                stdev(count_values) if len(count_values) > 1 else avg_count * 0.2
            )
            if (
                std_count > 0
                and abs(current.total_incidents - avg_count)
                > threshold_std_dev * std_count
            ):
                anomalies.append({
                    "metric": "incident_count",
                    "current_value": current.total_incidents,
                    "expected_value": avg_count,
                    "std_dev": std_count,
                    "deviation": (current.total_incidents - avg_count) / std_count,
                    "severity": (
                        "high" if current.total_incidents > avg_count else "info"
                    ),
                    "message": (
                        f"Incident count is {current.total_incidents}, "
                        f"expected ~{avg_count:.0f}"
                    ),
                })

        logger.info(
            "anomaly_detection_complete",
            team=team_name,
            service=service_name,
            anomalies_found=len(anomalies),
        )

        return anomalies

    def _build_historical_data_points(
        self,
        incidents: list[dict],
        period_start: datetime,
        period_end: datetime,
        team_name: str | None,
        service_name: str | None,
        metric_name: str,
        num_periods: int,
    ) -> list[tuple[datetime, float]]:
        """Build historical data points for charting."""
        period_duration = period_end - period_start
        data_points: list[tuple[datetime, float]] = []

        for i in range(num_periods - 1, -1, -1):
            p_end = period_end - (period_duration * i)
            p_start = p_end - period_duration

            if metric_name == "sla_compliance":
                sla = self.calculator.calculate_sla_compliance(
                    incidents, p_start, p_end, team_name, service_name
                )
                value = sla.compliance_percent
            else:
                metrics = self.calculator.calculate_team_metrics(
                    incidents, p_start, p_end, team_name, service_name
                )
                if metric_name == "mttr":
                    value = metrics.mttr_minutes or 0
                elif metric_name == "mtta":
                    value = metrics.mtta_minutes or 0
                elif metric_name == "incident_count":
                    value = float(metrics.total_incidents)
                else:
                    value = 0

            data_points.append((p_start, value))

        return data_points
