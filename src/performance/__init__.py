"""Team Performance Analytics Module.

Provides comprehensive performance analytics for incident management teams,
including DORA-style metrics, burnout indicators, and industry benchmarks.

Example usage:
    from performance import PerformanceService, PerformancePeriod, ReportGenerator
    
    service = PerformanceService(incident_repo, oncall_repo)
    period = PerformancePeriod.month()
    
    # Get team metrics
    metrics = await service.calculate_team_metrics("team-1", "Platform Team", period)
    
    # Generate report
    generator = ReportGenerator(service)
    report = await generator.generate_team_report("team-1", "Platform Team", period)
"""

from .models import (
    PerformanceTier,
    BurnoutRisk,
    PerformancePeriod,
    MetricValue,
    WorkloadDistribution,
    BurnoutIndicators,
    EngineerMetrics,
    TeamMetrics,
    Benchmark,
    PeriodComparison,
    LeaderboardEntry,
    PerformanceReport,
)

from .calculators import (
    calculate_mttr,
    calculate_mtta,
    calculate_mttd,
    count_incidents_by_severity,
    calculate_engineer_workloads,
    calculate_workload_distribution,
    calculate_oncall_burden,
    calculate_after_hours_incidents,
    calculate_burnout_risk,
    calculate_trend,
    create_metric_value,
)

from .benchmarks import (
    DORA_BENCHMARKS,
    WORKLOAD_BENCHMARKS,
    classify_metric,
    classify_team,
    calculate_overall_tier,
    estimate_percentile,
    get_benchmark_context,
    compare_to_industry,
)

from .service import (
    PerformanceService,
    IncidentRepository,
    OncallRepository,
)

from .reports import ReportGenerator

from .routes import router

__all__ = [
    # Enums
    "PerformanceTier",
    "BurnoutRisk",
    # Models
    "PerformancePeriod",
    "MetricValue",
    "WorkloadDistribution",
    "BurnoutIndicators",
    "EngineerMetrics",
    "TeamMetrics",
    "Benchmark",
    "PeriodComparison",
    "LeaderboardEntry",
    "PerformanceReport",
    # Calculators
    "calculate_mttr",
    "calculate_mtta",
    "calculate_mttd",
    "count_incidents_by_severity",
    "calculate_engineer_workloads",
    "calculate_workload_distribution",
    "calculate_oncall_burden",
    "calculate_after_hours_incidents",
    "calculate_burnout_risk",
    "calculate_trend",
    "create_metric_value",
    # Benchmarks
    "DORA_BENCHMARKS",
    "WORKLOAD_BENCHMARKS",
    "classify_metric",
    "classify_team",
    "calculate_overall_tier",
    "estimate_percentile",
    "get_benchmark_context",
    "compare_to_industry",
    # Service
    "PerformanceService",
    "IncidentRepository",
    "OncallRepository",
    # Reports
    "ReportGenerator",
    # Routes
    "router",
]
