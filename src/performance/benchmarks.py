"""Industry benchmarks and comparisons (DORA metrics)."""

from .models import Benchmark, PerformanceTier, TeamMetrics


# DORA-inspired benchmarks
DORA_BENCHMARKS: dict[str, Benchmark] = {
    "mttr": Benchmark(
        name="Mean Time To Resolve",
        metric="mttr_minutes",
        elite_threshold=60,      # < 1 hour
        high_threshold=240,      # < 4 hours
        medium_threshold=1440,   # < 24 hours
        unit="minutes",
        lower_is_better=True,
        source="DORA"
    ),
    "mtta": Benchmark(
        name="Mean Time To Acknowledge",
        metric="mtta_minutes",
        elite_threshold=5,       # < 5 min
        high_threshold=15,       # < 15 min
        medium_threshold=60,     # < 1 hour
        unit="minutes",
        lower_is_better=True,
        source="DORA"
    ),
    "change_failure_rate": Benchmark(
        name="Change Failure Rate",
        metric="change_failure_rate",
        elite_threshold=5,       # < 5%
        high_threshold=10,       # < 10%
        medium_threshold=15,     # < 15%
        unit="%",
        lower_is_better=True,
        source="DORA"
    ),
    "sla_compliance": Benchmark(
        name="SLA Compliance Rate",
        metric="sla_compliance_rate",
        elite_threshold=99.5,    # > 99.5%
        high_threshold=99,       # > 99%
        medium_threshold=95,     # > 95%
        unit="%",
        lower_is_better=False,
        source="Industry"
    ),
    "first_call_resolution": Benchmark(
        name="First Call Resolution",
        metric="first_call_resolution_rate",
        elite_threshold=80,      # > 80%
        high_threshold=70,       # > 70%
        medium_threshold=60,     # > 60%
        unit="%",
        lower_is_better=False,
        source="Industry"
    ),
    "escalation_rate": Benchmark(
        name="Escalation Rate",
        metric="escalation_rate",
        elite_threshold=5,       # < 5%
        high_threshold=10,       # < 10%
        medium_threshold=20,     # < 20%
        unit="%",
        lower_is_better=True,
        source="Industry"
    ),
    "reopen_rate": Benchmark(
        name="Reopen Rate",
        metric="reopen_rate",
        elite_threshold=2,       # < 2%
        high_threshold=5,        # < 5%
        medium_threshold=10,     # < 10%
        unit="%",
        lower_is_better=True,
        source="Industry"
    ),
}

# Workload distribution benchmarks
WORKLOAD_BENCHMARKS = {
    "gini_coefficient": {
        "elite": 0.15,    # Very balanced
        "high": 0.25,
        "medium": 0.35,
        "description": "Lower is more equitable distribution"
    },
    "top_10_share": {
        "elite": 15,      # Top 10% handles < 15% of work
        "high": 25,
        "medium": 35,
        "description": "Percentage of work handled by top 10%"
    }
}


def classify_metric(metric_name: str, value: float) -> PerformanceTier:
    """Classify a single metric against benchmarks."""
    benchmark = DORA_BENCHMARKS.get(metric_name)
    if not benchmark:
        return PerformanceTier.MEDIUM
    return benchmark.classify(value)


def classify_team(metrics: TeamMetrics) -> dict[str, PerformanceTier]:
    """Classify all team metrics against benchmarks."""
    classifications = {}
    
    for key, benchmark in DORA_BENCHMARKS.items():
        value = getattr(metrics, benchmark.metric, None)
        if value is not None:
            classifications[key] = benchmark.classify(value)
    
    return classifications


def calculate_overall_tier(classifications: dict[str, PerformanceTier]) -> PerformanceTier:
    """Calculate overall performance tier from individual classifications."""
    if not classifications:
        return PerformanceTier.MEDIUM
    
    tier_scores = {
        PerformanceTier.ELITE: 4,
        PerformanceTier.HIGH: 3,
        PerformanceTier.MEDIUM: 2,
        PerformanceTier.LOW: 1
    }
    
    avg_score = sum(tier_scores[t] for t in classifications.values()) / len(classifications)
    
    if avg_score >= 3.5:
        return PerformanceTier.ELITE
    elif avg_score >= 2.5:
        return PerformanceTier.HIGH
    elif avg_score >= 1.5:
        return PerformanceTier.MEDIUM
    return PerformanceTier.LOW


def estimate_percentile(metric_name: str, value: float) -> int:
    """Estimate industry percentile based on benchmarks."""
    benchmark = DORA_BENCHMARKS.get(metric_name)
    if not benchmark:
        return 50
    
    tier = benchmark.classify(value)
    percentile_ranges = {
        PerformanceTier.ELITE: (90, 99),
        PerformanceTier.HIGH: (70, 89),
        PerformanceTier.MEDIUM: (30, 69),
        PerformanceTier.LOW: (1, 29)
    }
    
    low, high = percentile_ranges[tier]
    # Interpolate within tier
    if benchmark.lower_is_better:
        thresholds = [benchmark.elite_threshold, benchmark.high_threshold, 
                      benchmark.medium_threshold, benchmark.medium_threshold * 2]
        for i, thresh in enumerate(thresholds):
            if value <= thresh:
                range_low, range_high = percentile_ranges[list(PerformanceTier)[i]]
                return (range_low + range_high) // 2
    return (low + high) // 2


def get_benchmark_context(metric_name: str) -> dict:
    """Get benchmark context for a metric."""
    benchmark = DORA_BENCHMARKS.get(metric_name)
    if not benchmark:
        return {"available": False}
    
    return {
        "available": True,
        "name": benchmark.name,
        "thresholds": {
            "elite": f"{'<' if benchmark.lower_is_better else '>'} {benchmark.elite_threshold}{benchmark.unit}",
            "high": f"{'<' if benchmark.lower_is_better else '>'} {benchmark.high_threshold}{benchmark.unit}",
            "medium": f"{'<' if benchmark.lower_is_better else '>'} {benchmark.medium_threshold}{benchmark.unit}",
        },
        "source": benchmark.source
    }


def compare_to_industry(metrics: TeamMetrics) -> dict:
    """Generate industry comparison summary."""
    classifications = classify_team(metrics)
    overall = calculate_overall_tier(classifications)
    
    tier_descriptions = {
        PerformanceTier.ELITE: "Top 10% of teams in the industry",
        PerformanceTier.HIGH: "Above average, top 30% of teams",
        PerformanceTier.MEDIUM: "Average performance, room for improvement",
        PerformanceTier.LOW: "Below average, significant improvement needed"
    }
    
    strengths = [k for k, v in classifications.items() if v == PerformanceTier.ELITE]
    weaknesses = [k for k, v in classifications.items() if v == PerformanceTier.LOW]
    
    return {
        "overall_tier": overall,
        "description": tier_descriptions[overall],
        "metric_tiers": {k: v.value for k, v in classifications.items()},
        "strengths": strengths,
        "improvement_areas": weaknesses,
        "percentile_estimate": estimate_percentile("mttr", metrics.mttr_minutes)
    }
