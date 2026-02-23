"""API routes for Incident Copilot."""

from ..oncall import oncall_handoff_router
from ..postmortem import postmortem_router
from .analytics import router as analytics_router
from .correlation import router as correlation_router
from .demo import router as demo_router
from .email import router as email_router
from .health import router as health_router
from .incidents import router as incidents_router
from .insights import router as insights_router
from .latency import router as latency_router
from .memory_advanced import router as memory_advanced_router
from .memory_feedback import feedback_router as ai_feedback_router
from .memory_feedback import router as memory_feedback_router
from .memory_stats import router as memory_stats_router
from .metrics import router as metrics_router
from .onboarding import router as onboarding_router
from .plugins import router as plugins_router
from .runbooks import router as runbooks_router
from .webhooks import router as webhooks_router

__all__ = [
    "webhooks_router",
    "correlation_router",
    "runbooks_router",
    "demo_router",
    "analytics_router",
    "health_router",
    "postmortem_router",
    "plugins_router",
    "email_router",
    "insights_router",
    "incidents_router",
    "metrics_router",
    "ai_feedback_router",
    "memory_feedback_router",
    "memory_stats_router",
    "oncall_handoff_router",
    "onboarding_router",
    "memory_advanced_router",
    "latency_router",
]
