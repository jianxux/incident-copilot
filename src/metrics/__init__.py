"""Prometheus metrics for Incident Copilot."""

from prometheus_client import Counter, Histogram, Gauge, Info
from typing import Optional
import time
from functools import wraps
from collections.abc import Callable

# Application info
APP_INFO = Info(
    "incident_copilot",
    "Incident Copilot application information"
)

# Webhook metrics
WEBHOOK_REQUESTS_TOTAL = Counter(
    "incident_copilot_webhook_requests_total",
    "Total number of webhook requests received",
    ["source", "status"]  # source: pagerduty, opsgenie; status: success, error, invalid
)

WEBHOOK_PROCESSING_SECONDS = Histogram(
    "incident_copilot_webhook_processing_seconds",
    "Time spent processing webhooks",
    ["source"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
)

# Context assembly metrics
CONTEXT_ASSEMBLY_TOTAL = Counter(
    "incident_copilot_context_assembly_total",
    "Total number of context assembly operations",
    ["status"]  # success, error, partial
)

CONTEXT_ASSEMBLY_SECONDS = Histogram(
    "incident_copilot_context_assembly_seconds",
    "Time spent assembling context",
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 7.5, 10.0, 15.0, 30.0]
)

# Integration metrics
INTEGRATION_REQUESTS_TOTAL = Counter(
    "incident_copilot_integration_requests_total",
    "Total number of integration API requests",
    ["integration", "operation", "status"]  # integration: github, datadog, slack, etc.
)

INTEGRATION_LATENCY_SECONDS = Histogram(
    "incident_copilot_integration_latency_seconds",
    "Latency of integration API calls",
    ["integration", "operation"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

INTEGRATION_ERRORS_TOTAL = Counter(
    "incident_copilot_integration_errors_total",
    "Total number of integration errors",
    ["integration", "error_type"]
)

# AI/LLM metrics
AI_REQUESTS_TOTAL = Counter(
    "incident_copilot_ai_requests_total",
    "Total number of AI/LLM requests",
    ["model", "operation", "status"]
)

AI_LATENCY_SECONDS = Histogram(
    "incident_copilot_ai_latency_seconds",
    "Latency of AI/LLM calls",
    ["model", "operation"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0]
)

AI_TOKENS_TOTAL = Counter(
    "incident_copilot_ai_tokens_total",
    "Total tokens used by AI/LLM",
    ["model", "token_type"]  # token_type: input, output
)

# Notification metrics
NOTIFICATION_SENT_TOTAL = Counter(
    "incident_copilot_notifications_sent_total",
    "Total number of notifications sent",
    ["destination", "status"]  # destination: slack, teams
)

NOTIFICATION_LATENCY_SECONDS = Histogram(
    "incident_copilot_notification_latency_seconds",
    "Latency of notification delivery",
    ["destination"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# Similarity search metrics
SIMILARITY_SEARCH_TOTAL = Counter(
    "incident_copilot_similarity_search_total",
    "Total number of similarity searches",
    ["status", "matches_found"]  # matches_found: yes, no
)

SIMILARITY_SEARCH_SECONDS = Histogram(
    "incident_copilot_similarity_search_seconds",
    "Time spent on similarity search",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0]
)

INCIDENT_INDEX_SIZE = Gauge(
    "incident_copilot_incident_index_size",
    "Number of incidents in the similarity index"
)

# Runbook metrics
RUNBOOK_MATCHES_TOTAL = Counter(
    "incident_copilot_runbook_matches_total",
    "Total number of runbook matches found",
    ["match_type"]  # match_type: exact, fuzzy, keyword
)

RUNBOOK_INDEX_SIZE = Gauge(
    "incident_copilot_runbook_index_size",
    "Number of runbooks in the index"
)

# HTTP request metrics (for API endpoints)
HTTP_REQUESTS_TOTAL = Counter(
    "incident_copilot_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"]
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "incident_copilot_http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# Active connections gauge
ACTIVE_CONNECTIONS = Gauge(
    "incident_copilot_active_connections",
    "Number of active HTTP connections"
)

# Health status
HEALTH_STATUS = Gauge(
    "incident_copilot_health_status",
    "Health status of the application (1=healthy, 0=unhealthy)",
    ["component"]  # component: app, redis, database, etc.
)


def set_app_info(version: str, git_sha: Optional[str] = None) -> None:
    """Set application information metric."""
    info = {"version": version}
    if git_sha:
        info["git_sha"] = git_sha
    APP_INFO.info(info)


def track_integration_call(integration: str, operation: str):
    """Decorator to track integration API calls."""
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            status = "success"
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                INTEGRATION_ERRORS_TOTAL.labels(
                    integration=integration,
                    error_type=type(e).__name__
                ).inc()
                raise
            finally:
                duration = time.perf_counter() - start_time
                INTEGRATION_REQUESTS_TOTAL.labels(
                    integration=integration,
                    operation=operation,
                    status=status
                ).inc()
                INTEGRATION_LATENCY_SECONDS.labels(
                    integration=integration,
                    operation=operation
                ).observe(duration)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            status = "success"
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                INTEGRATION_ERRORS_TOTAL.labels(
                    integration=integration,
                    error_type=type(e).__name__
                ).inc()
                raise
            finally:
                duration = time.perf_counter() - start_time
                INTEGRATION_REQUESTS_TOTAL.labels(
                    integration=integration,
                    operation=operation,
                    status=status
                ).inc()
                INTEGRATION_LATENCY_SECONDS.labels(
                    integration=integration,
                    operation=operation
                ).observe(duration)
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


class ContextTimer:
    """Context manager for timing operations."""
    
    def __init__(self, histogram: Histogram, labels: Optional[dict] = None):
        self.histogram = histogram
        self.labels = labels or {}
        self.start_time: Optional[float] = None
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = time.perf_counter() - self.start_time
            if self.labels:
                self.histogram.labels(**self.labels).observe(duration)
            else:
                self.histogram.observe(duration)
        return False
