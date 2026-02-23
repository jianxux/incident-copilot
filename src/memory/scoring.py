"""Scoring utilities for incident memory recall."""

from collections.abc import Mapping


def apply_feedback_weight(
    score: float,
    feedback_summary: Mapping[str, int | float] | None,
) -> float:
    """Apply aggregate feedback multiplier to a score."""
    if score <= 0.0 or not feedback_summary:
        return max(score, 0.0)

    helpful = int(feedback_summary.get("helpful", 0))
    not_helpful = int(feedback_summary.get("not_helpful", 0))
    partial = int(feedback_summary.get("partial", 0))
    total = helpful + not_helpful + partial
    if total <= 0:
        return max(score, 0.0)

    weighted_multiplier = (
        (helpful * 1.20) + (not_helpful * 0.70) + (partial * 1.05)
    ) / total
    return max(score * weighted_multiplier, 0.0)


def apply_temporal_decay(
    similarity: float,
    days_ago: int,
    decay_rate: float = 0.95,
    window_days: int = 30,
) -> float:
    """Apply exponential temporal decay to a similarity score."""
    if window_days <= 0:
        return max(similarity, 0.0)
    if days_ago <= 0:
        return max(similarity, 0.0)

    decay_factor = decay_rate ** (days_ago / window_days)
    return max(similarity * decay_factor, 0.0)
