"""Scoring utilities for incident memory recall."""


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
