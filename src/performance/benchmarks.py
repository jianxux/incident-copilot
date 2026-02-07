"""Industry benchmarks and DORA metrics comparisons."""
from .models import Benchmark, PerformanceTier, TeamMetrics

DORA_BENCHMARKS: dict[str, Benchmark] = {
    "mttr": Benchmark(name="Mean Time To Resolve", metric="mttr_minutes", elite_threshold=60, high_threshold=240, medium_threshold=1440, unit="min", source="DORA"),
    "mtta": Benchmark(name="Mean Time To Acknowledge", metric="mtta_minutes", elite_threshold=5, high_threshold=15, medium_threshold=60, unit="min", source="DORA"),
    "change_failure_rate": Benchmark(name="Change Failure Rate", metric="change_failure_rate", elite_threshold=5, high_threshold=10, medium_threshold=15, unit="%", source="DORA"),
    "sla_compliance": Benchmark(name="SLA Compliance", metric="sla_compliance_rate", elite_threshold=99.5, high_threshold=99, medium_threshold=95, unit="%", lower_is_better=False, source="Industry"),
    "first_call_resolution": Benchmark(name="First Call Resolution", metric="first_call_resolution_rate", elite_threshold=80, high_threshold=70, medium_threshold=60, unit="%", lower_is_better=False, source="Industry"),
    "escalation_rate": Benchmark(name="Escalation Rate", metric="escalation_rate", elite_threshold=5, high_threshold=10, medium_threshold=20, unit="%", source="Industry"),
    "reopen_rate": Benchmark(name="Reopen Rate", metric="reopen_rate", elite_threshold=2, high_threshold=5, medium_threshold=10, unit="%", source="Industry"),
}

WORKLOAD_BENCHMARKS = {"gini_coefficient": {"elite": 0.15, "high": 0.25, "medium": 0.35}, "top_10_share": {"elite": 15, "high": 25, "medium": 35}}


def classify_metric(metric_name: str, value: float) -> PerformanceTier:
    return DORA_BENCHMARKS[metric_name].classify(value) if metric_name in DORA_BENCHMARKS else PerformanceTier.MEDIUM


def classify_team(metrics: TeamMetrics) -> dict[str, PerformanceTier]:
    return {k: b.classify(v) for k, b in DORA_BENCHMARKS.items() if (v := getattr(metrics, b.metric, None)) is not None}


def calculate_overall_tier(classifications: dict[str, PerformanceTier]) -> PerformanceTier:
    if not classifications: return PerformanceTier.MEDIUM
    scores = {PerformanceTier.ELITE: 4, PerformanceTier.HIGH: 3, PerformanceTier.MEDIUM: 2, PerformanceTier.LOW: 1}
    avg = sum(scores[t] for t in classifications.values()) / len(classifications)
    return PerformanceTier.ELITE if avg >= 3.5 else (PerformanceTier.HIGH if avg >= 2.5 else (PerformanceTier.MEDIUM if avg >= 1.5 else PerformanceTier.LOW))


def estimate_percentile(metric_name: str, value: float) -> int:
    if metric_name not in DORA_BENCHMARKS: return 50
    tier = DORA_BENCHMARKS[metric_name].classify(value)
    ranges = {PerformanceTier.ELITE: (90, 99), PerformanceTier.HIGH: (70, 89), PerformanceTier.MEDIUM: (30, 69), PerformanceTier.LOW: (1, 29)}
    return sum(ranges[tier]) // 2


def get_benchmark_context(metric_name: str) -> dict:
    if metric_name not in DORA_BENCHMARKS: return {"available": False}
    b = DORA_BENCHMARKS[metric_name]
    op = "<" if b.lower_is_better else ">"
    return {"available": True, "name": b.name, "thresholds": {t: f"{op} {getattr(b, f'{t}_threshold')}{b.unit}" for t in ["elite", "high", "medium"]}, "source": b.source}


def compare_to_industry(metrics: TeamMetrics) -> dict:
    classifications = classify_team(metrics)
    overall = calculate_overall_tier(classifications)
    descs = {PerformanceTier.ELITE: "Top 10% of teams", PerformanceTier.HIGH: "Above average, top 30%", PerformanceTier.MEDIUM: "Average, room for improvement", PerformanceTier.LOW: "Below average, needs work"}
    return {"overall_tier": overall, "description": descs[overall], "metric_tiers": {k: v.value for k, v in classifications.items()},
            "strengths": [k for k, v in classifications.items() if v == PerformanceTier.ELITE],
            "improvement_areas": [k for k, v in classifications.items() if v == PerformanceTier.LOW],
            "percentile_estimate": estimate_percentile("mttr", metrics.mttr_minutes)}
