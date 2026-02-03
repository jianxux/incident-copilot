"""AI Insights & Pattern Detection for Incident Copilot.

This module provides intelligent analysis of incidents to detect:
- Recurring patterns (same service, time of day, error type)
- Service dependency chains (cascading failures)
- Temporal patterns (deploy days, weekends, etc.)
- Root cause clustering
- Anomaly detection (unusual spikes)
"""

from .analyzer import InsightsAnalyzer
from .detector import PatternDetector
from .models import (
    Anomaly,
    AnomalySeverity,
    AnomalyType,
    DependencyChain,
    Insight,
    InsightCategory,
    InsightPriority,
    Pattern,
    PatternType,
    Recommendation,
    RootCauseCluster,
    ServiceInsight,
    TemporalPattern,
    Trend,
    TrendDirection,
    WeeklyDigest,
)
from .store import InsightsStore, insights_store

__all__ = [
    # Core classes
    "PatternDetector",
    "InsightsAnalyzer",
    "InsightsStore",
    "insights_store",
    # Models
    "Pattern",
    "PatternType",
    "Insight",
    "InsightCategory",
    "InsightPriority",
    "Trend",
    "TrendDirection",
    "Anomaly",
    "AnomalyType",
    "AnomalySeverity",
    "DependencyChain",
    "TemporalPattern",
    "RootCauseCluster",
    "ServiceInsight",
    "Recommendation",
    "WeeklyDigest",
]
