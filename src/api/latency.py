"""API endpoints for latency metrics and tracking."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/latency", tags=["latency"])


# In-memory store for recent latency reports (use Redis in production)
_recent_reports: list[dict] = []
MAX_REPORTS = 100


def record_latency_report(report_summary: dict) -> None:
    """Record a latency report for the API."""
    _recent_reports.append(report_summary)
    if len(_recent_reports) > MAX_REPORTS:
        _recent_reports.pop(0)


@router.get("/recent")
async def get_recent_latency() -> dict:
    """Get recent latency reports for all incidents."""
    return {
        "count": len(_recent_reports),
        "reports": _recent_reports[-20:],  # Last 20
    }


@router.get("/stats")
async def get_latency_stats() -> dict:
    """Get aggregate latency statistics."""
    if not _recent_reports:
        return {
            "count": 0,
            "avg_total_ms": None,
            "p50_total_ms": None,
            "p95_total_ms": None,
            "budget_hit_rate": None,
        }

    totals = [r["total_ms"] for r in _recent_reports if r.get("total_ms") is not None]
    if not totals:
        return {"count": len(_recent_reports), "avg_total_ms": None}

    totals.sort()
    n = len(totals)
    within = sum(1 for r in _recent_reports if r.get("within_budget"))

    return {
        "count": n,
        "avg_total_ms": int(sum(totals) / n),
        "p50_total_ms": totals[n // 2],
        "p95_total_ms": totals[int(n * 0.95)] if n >= 20 else totals[-1],
        "min_total_ms": totals[0],
        "max_total_ms": totals[-1],
        "budget_hit_rate": f"{(within / len(_recent_reports)) * 100:.1f}%",
    }
